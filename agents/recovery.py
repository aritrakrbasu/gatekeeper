import asyncio
import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from agents.context import AgentContext
from services import mongo_client, mcp_service

class QueueTask(BaseModel):
    task_id: str
    context_data: Dict[str, Any]
    attempt: int = 1
    max_retries: int = 3
    next_retry_at: str
    error_log: str

class FailureRecoveryManager:
    """
    Handles background retry queues with exponential backoff, Dead Letter Queue (DLQ)
    persistence, and MCP session reconnection logic.
    """
    def __init__(self, retry_delay_base: float = 5.0):
        self.retry_delay_base = retry_delay_base

    async def enqueue_for_retry(self, task_id: str, context: AgentContext, error_message: str, attempt: int = 1) -> bool:
        """Enqueues a task for retry, calculating the next execution time with exponential backoff."""
        if attempt > 3:
            print(f"[INFO] [Recovery] Task {task_id} exhausted max retries. Sending to DLQ...")
            await self.send_to_dlq(task_id, context, f"Max retries exceeded. Last error: {error_message}")
            return False
            
        delay_seconds = self.retry_delay_base * (2 ** (attempt - 1))
        next_retry = (datetime.datetime.utcnow() + datetime.timedelta(seconds=delay_seconds)).isoformat()
        
        task_doc = {
            "task_id": task_id,
            "context_data": context.serialize(),
            "attempt": attempt,
            "max_retries": 3,
            "next_retry_at": next_retry,
            "error_log": error_message,
            "created_at": datetime.datetime.utcnow().isoformat()
        }
        
        await mongo_client.upsert_one(
            collection_name="agent_retry_queue",
            filter={"task_id": task_id},
            document=task_doc
        )
        print(f"[OK] [Recovery] Enqueued task {task_id} for retry attempt {attempt} at {next_retry}")
        return True

    async def send_to_dlq(self, task_id: str, context: AgentContext, error_message: str):
        """Persists failed task details to the Dead Letter Queue in MongoDB."""
        dlq_doc = {
            "task_id": task_id,
            "context_data": context.serialize(),
            "error_message": error_message,
            "failed_at": datetime.datetime.utcnow().isoformat()
        }
        await mongo_client.insert_one(
            collection_name="agent_dlq_tasks",
            document=dlq_doc
        )
        # Delete from retry queue if it was there
        await mongo_client.delete_one("agent_retry_queue", {"task_id": task_id})
        print(f"[OK] [Recovery] Task {task_id} written to DLQ 'agent_dlq_tasks'")

    async def reconnect_mcp_sessions(self) -> bool:
        """Verifies active connectivity to critical MCP servers, attempting reconnects if needed."""
        print("[INFO] [Recovery] Verifying MCP sessions status...")
        
        # Test if GitLab session is responsive
        gitlab_alive = False
        if mcp_service.gitlab_session:
            try:
                await mcp_service.gitlab_session.list_tools()
                gitlab_alive = True
            except Exception as e:
                print(f"[WARN] [Recovery] GitLab MCP session check failed: {e}")
                
        mongo_alive = False
        if mcp_service.mongo_session:
            try:
                await mcp_service.mongo_session.list_tools()
                mongo_alive = True
            except Exception as e:
                print(f"[WARN] [Recovery] MongoDB MCP session check failed: {e}")

        if gitlab_alive and mongo_alive:
            print("[OK] [Recovery] All critical MCP sessions are healthy.")
            return True
            
        print("[WARN] [Recovery] One or more critical MCP sessions disconnected. Initiating reconnect...")
        try:
            asyncio.create_task(mcp_service.boot_mcp_bridge())
            # Wait a few seconds for handshakes to complete
            await asyncio.sleep(5)
            return mcp_service.mcp_ready
        except Exception as e:
            print(f"[ERROR] [Recovery] Failed to reboot MCP bridge: {e}")
            return False

    async def process_retry_queue(self, engine: Any) -> int:
        """Polls and runs tasks in the retry queue whose next_retry_at times have passed."""
        now = datetime.datetime.utcnow().isoformat()
        # Find all pending retries due
        tasks = await mongo_client.find("agent_retry_queue", {"next_retry_at": {"$lte": now}})
        if not tasks:
            return 0
            
        processed_count = 0
        for task in tasks:
            task_id = task["task_id"]
            context_data = task["context_data"]
            attempt = task["attempt"]
            
            context = AgentContext(**context_data)
            print(f"[INFO] [Recovery] Processing retry for task {task_id} (attempt {attempt})...")
            
            try:
                # Re-verify MCP sessions first
                await self.reconnect_mcp_sessions()
                
                # Execute
                result = await engine.run_task(context)
                if result.get("status") == "completed":
                    # Delete from retry queue on success
                    await mongo_client.delete_one("agent_retry_queue", {"task_id": task_id})
                    print(f"[OK] [Recovery] Task {task_id} retry succeeded.")
                elif result.get("status") == "awaiting_approval":
                    # Suspended again: delete from retry queue so it doesn't loop retry
                    await mongo_client.delete_one("agent_retry_queue", {"task_id": task_id})
                    print(f"[OK] [Recovery] Task {task_id} paused for approval during retry.")
                else:
                    raise Exception(result.get("error", "Retry execution returned failed status."))
                    
            except Exception as e:
                # Re-enqueue with incremented attempt
                print(f"[WARN] [Recovery] Retry execution failed for task {task_id}: {e}")
                await self.enqueue_for_retry(task_id, context, str(e), attempt + 1)
                
            processed_count += 1
            
        return processed_count
