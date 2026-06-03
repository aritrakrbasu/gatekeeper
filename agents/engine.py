import json
import datetime
from typing import Dict, Any, List, Set, Optional
from agents.context import AgentContext
from agents.registry import ToolRegistry
from agents.memory import MemoryStore
from agents.planner import Planner, StepSchema
from agents.executor import Executor
from agents.reflection import ReflectionLayer
from agents.approval import HumanApprovalLayer
from services import mongo_client

def get_ready_steps(steps: List[StepSchema], executed_ids: Set[str]) -> List[StepSchema]:
    """
    Returns plan steps that haven't been run yet and whose dependencies are met.
    """
    ready = []
    for step in steps:
        if step.step_id in executed_ids:
            continue
        if all(dep in executed_ids for dep in step.dependencies):
            ready.append(step)
    return ready


class WorkflowEngine:
    """
    The main orchestrator driving the ReAct planning and execution loop with Human Approval gates.
    """
    
    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        self.planner = Planner()
        self.reflection = ReflectionLayer()
        self.approval = HumanApprovalLayer()

    async def run_task(self, context: AgentContext) -> Dict[str, Any]:
        """
        Runs the planning-execution-reflection loop until completion, error, or human approval pause.
        """
        # 1. Initialize memory trace logging
        memory = MemoryStore(task_id=context.task_id, objective=context.objective)
        executor = Executor(self.registry, memory)
        
        executed_ids: Set[str] = set()
        active_plan: List[StepSchema] = []
        
        memory.log_message("system", f"Workflow engine started. Objective: '{context.objective}'")
        await memory.persist_to_mongodb()
        
        # 2. Retrieve semantic memories for the Planner context
        memories = []
        try:
            # Query similar root causes or remediations to feed to planner
            memories = await memory.find_similar_fixes(context.objective, limit=2)
            if not memories:
                memories = await memory.find_similar_incidents(context.objective, limit=2)
        except Exception as e:
            print(f"[WARN] [WorkflowEngine] Failed to retrieve history memories: {e}")
            
        # 3. Build initial execution plan
        try:
            active_plan = await self.planner.generate_plan(context, self.registry, memories=memories)
        except Exception as e:
            memory.status = "failed"
            memory.log_message("system", f"Initial planning failed: {e}")
            await memory.persist_to_mongodb()
            return {"status": "failed", "error": f"Initial planning failed: {e}"}
            
        return await self._run_execution_loop(context, executor, memory, executed_ids, active_plan)

    async def resume_task(self, task_id: str) -> Dict[str, Any]:
        """
        Resumes a paused task from saved execution state.
        """
        # Load execution trace from DB
        trace = await mongo_client.find_one("agent_execution_traces", {"task_id": task_id})
        if not trace:
            raise ValueError(f"No execution trace found to resume for task {task_id}")
            
        # Reconstruct Context
        ctx_data = trace["context"]
        context = AgentContext(**ctx_data)
        
        # Reconstruct execution state
        executed_ids = set(trace.get("executed_ids", []))
        step_results = trace.get("step_results", {})
        active_plan = [StepSchema(**s) for s in trace.get("active_plan", [])]
        
        # Reconstruct memory trace logs
        memory = MemoryStore(task_id=context.task_id, objective=context.objective)
        memory.steps = trace.get("steps", [])
        memory.messages = trace.get("messages", [])
        
        executor = Executor(self.registry, memory)
        executor.step_results = step_results
        
        memory.log_message("system", "Workflow engine resumed from approval state.")
        await memory.persist_to_mongodb()
        
        return await self._run_execution_loop(context, executor, memory, executed_ids, active_plan)

    async def save_execution_state(
        self,
        context: AgentContext,
        executed_ids: Set[str],
        step_results: Dict[str, Any],
        active_plan: List[StepSchema],
        memory: MemoryStore
    ):
        """Persists workflow run state to resume later after human approvals."""
        state_doc = {
            "task_id": context.task_id,
            "objective": context.objective,
            "context": context.serialize(),
            "executed_ids": list(executed_ids),
            "step_results": step_results,
            "active_plan": [step.model_dump() for step in active_plan],
            "steps": memory.steps,
            "messages": memory.messages,
            "status": "awaiting_approval",
            "updated_at": datetime.datetime.utcnow().isoformat()
        }
        await mongo_client.upsert_one(
            collection_name="agent_execution_traces",
            filter={"task_id": context.task_id},
            document=state_doc
        )
        print(f"[OK] [WorkflowEngine] Saved execution state for task {context.task_id}")

    async def _run_execution_loop(
        self,
        context: AgentContext,
        executor: Executor,
        memory: MemoryStore,
        executed_ids: Set[str],
        active_plan: List[StepSchema]
    ) -> Dict[str, Any]:
        max_total_steps = 15
        total_steps_run = len(executed_ids)
        
        while total_steps_run < max_total_steps:
            # Query steps whose dependencies are met
            ready_steps = get_ready_steps(active_plan, executed_ids)
            
            if not ready_steps:
                all_done = all(step.step_id in executed_ids for step in active_plan)
                if all_done:
                    print(f"[OK] [WorkflowEngine] All plan steps executed successfully.")
                    memory.status = "completed"
                    memory.log_message("system", "Workflow execution completed successfully.")
                    await memory.persist_to_mongodb()
                    return {
                        "status": "completed",
                        "task_id": context.task_id,
                        "results": executor.step_results
                    }
                else:
                    err_msg = "Plan execution stalled. Circular dependency or unresolvable step dependencies detected."
                    memory.status = "failed"
                    memory.log_message("system", err_msg)
                    await memory.persist_to_mongodb()
                    return {"status": "failed", "error": err_msg}
            
            # Pull the next executable step
            step_to_run = ready_steps[0]
            
            # 1. Mutate Step check for Human-in-the-Loop gate
            if self.planner._is_mutate_action(step_to_run.tool_name):
                approval_status = await self.approval.check_approval_status(context.task_id, step_to_run.step_id)
                
                if approval_status == "rejected":
                    err_msg = f"Task aborted: Mutating step '{step_to_run.step_id}' rejected by human reviewer."
                    memory.status = "failed"
                    memory.log_message("system", err_msg)
                    await memory.persist_to_mongodb()
                    return {"status": "failed", "error": err_msg}
                    
                elif approval_status != "approved":
                    # Generate approval package with resolved arguments to display diffs/details
                    raw_args = {}
                    try:
                        raw_args = json.loads(step_to_run.arguments_json) if step_to_run.arguments_json else {}
                    except Exception as parse_err:
                        print(f"[WARN] Failed to parse arguments_json for approval: {parse_err}")
                        
                    from agents.executor import resolve_arguments
                    resolved_args = resolve_arguments(raw_args, executor.step_results)
                    executor._inject_context_args(step_to_run.tool_name, resolved_args, context)
                    
                    package = await self.approval.generate_package(
                        task_id=context.task_id,
                        step_id=step_to_run.step_id,
                        tool_name=step_to_run.tool_name,
                        arguments=resolved_args
                    )
                    await self.approval.submit_for_approval(package)
                    
                    # Update trace state and pause
                    memory.status = "awaiting_approval"
                    memory.log_message("system", f"Mutating step '{step_to_run.step_id}' requires human approval. Loop paused.")
                    await memory.persist_to_mongodb()
                    
                    await self.save_execution_state(context, executed_ids, executor.step_results, active_plan, memory)
                    
                    return {
                        "status": "awaiting_approval",
                        "task_id": context.task_id,
                        "approval_id": package.approval_id,
                        "approval_package": package.model_dump()
                    }
            
            # 2. Execute Step
            total_steps_run += 1
            try:
                result = await executor.execute_step(step_to_run, context)
                
                # Quality Reflection Check
                await self.reflection.evaluate_step_result(step_to_run, result)
                
                # Mark as executed successfully
                executed_ids.add(step_to_run.step_id)
                
            except Exception as step_err:
                print(f"[WARN] [WorkflowEngine] Step '{step_to_run.step_id}' failed: {step_err}. Triggering replanning...")
                
                # Compile execution history to send to Planner for feedback
                history_steps = []
                for s in active_plan:
                    status = "pending"
                    if s.step_id in executed_ids:
                        status = "completed"
                    elif s.step_id == step_to_run.step_id:
                        status = "failed"
                    history_steps.append({
                        "step_id": s.step_id,
                        "tool_name": s.tool_name,
                        "arguments_json": s.arguments_json,
                        "status": status,
                        "result": str(executor.step_results.get(s.step_id, "")) if s.step_id in executed_ids else None,
                        "error": str(step_err) if s.step_id == step_to_run.step_id else None
                    })
                
                # Query planner to adjust remaining steps
                try:
                    active_plan = await self.planner.generate_plan(
                        context=context,
                        registry=self.registry,
                        history_steps=history_steps
                    )
                    memory.log_message("system", f"Step '{step_to_run.step_id}' failed. Dynamically re-planned active path.")
                    await memory.persist_to_mongodb()
                except Exception as replan_err:
                    err_msg = f"Replanning failed after step '{step_to_run.step_id}' failure: {replan_err}"
                    memory.status = "failed"
                    memory.log_message("system", err_msg)
                    await memory.persist_to_mongodb()
                    return {"status": "failed", "error": err_msg}
                    
        # Exceeded step safety ceiling
        err_msg = f"Max execution step limit ({max_total_steps}) reached. Aborting execution loop."
        memory.status = "failed"
        memory.log_message("system", err_msg)
        await memory.persist_to_mongodb()
        return {"status": "failed", "error": err_msg}
