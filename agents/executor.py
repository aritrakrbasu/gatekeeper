import re
import json
import asyncio
import inspect
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from agents.context import AgentContext
from agents.memory import MemoryStore
from agents.planner import StepSchema
from agents.registry import ToolRegistry
from peil.models.enums import CaptureEventType

if TYPE_CHECKING:
    from agents.aril_bridge import ArilSession

def resolve_arguments(arguments: Any, step_results: Dict[str, Any]) -> Any:
    """
    Recursively substitute '{{step_id.result}}' or '{{step_id.result.field}}' references
    with values from step_results.
    """
    if isinstance(arguments, str):
        # 1. Exact match for a whole object reference: return the raw object (e.g. dict or list)
        exact_match = re.match(r"^\{\{\s*([a-zA-Z0-9_\-]+)\.result(?:\.([a-zA-Z0-9_\-]+))?\s*\}\}$", arguments)
        if exact_match:
            step_id = exact_match.group(1)
            field = exact_match.group(2)
            if step_id not in step_results:
                raise ValueError(f"Step '{step_id}' result was referenced but is not available.")
            res = step_results[step_id]
            if field:
                if isinstance(res, dict) and field in res:
                    return res[field]
                elif hasattr(res, field):
                    return getattr(res, field)
                else:
                    raise KeyError(f"Field '{field}' not found in step '{step_id}' result.")
            return res
            
        # 2. String substitution for substring matches: convert to string
        pattern = r"\{\{\s*([a-zA-Z0-9_\-]+)\.result(?:\.([a-zA-Z0-9_\-]+))?\s*\}\}"
        def replace_match(match):
            step_id = match.group(1)
            field = match.group(2)
            if step_id not in step_results:
                return match.group(0)
            res = step_results[step_id]
            if field:
                if isinstance(res, dict):
                    return str(res.get(field, ""))
                return str(getattr(res, field, ""))
            return str(res)
            
        return re.sub(pattern, replace_match, arguments)
        
    elif isinstance(arguments, dict):
        return {k: resolve_arguments(v, step_results) for k, v in arguments.items()}
    elif isinstance(arguments, list):
        return [resolve_arguments(x, step_results) for x in arguments]
    else:
        return arguments


class ExecutorAgent:
    """
    Resolves dependency ordering, substitutes step arguments, and runs tools
    with step timeouts, retries, circuit breakers, and automatic rollbacks.
    """
    
    def __init__(
        self,
        registry: ToolRegistry,
        memory: MemoryStore,
        step_timeout: float = 60.0,
        max_retries: int = 3,
        initial_retry_delay: float = 1.0,
        backoff_factor: float = 2.0,
        aril: Optional["ArilSession"] = None,
    ):
        self.registry = registry
        self.memory = memory
        self.aril = aril
        self.step_timeout = step_timeout
        self.max_retries = max_retries
        self.initial_retry_delay = initial_retry_delay
        self.backoff_factor = backoff_factor
        
        self.step_results: Dict[str, Any] = {}
        self.rollback_hooks: List[Callable[[], Any]] = []
        
        # Circuit breaker trackers
        self.consecutive_failures: Dict[str, int] = {}
        self.tripped_tools: set = set()

    def register_rollback(self, hook: Callable[[], Any]) -> None:
        """Registers an undo/rollback callable (sync or async)."""
        self.rollback_hooks.append(hook)

    async def rollback(self) -> None:
        """Executes registered rollback hooks in LIFO (Last In First Out) order."""
        if not self.rollback_hooks:
            print("[INFO] [Executor] No rollback hooks registered.")
            return
            
        print(f"[INFO] [Executor] Executing {len(self.rollback_hooks)} rollback hooks...")
        for hook in reversed(self.rollback_hooks):
            try:
                if inspect.iscoroutinefunction(hook):
                    await hook()
                else:
                    hook()
            except Exception as e:
                print(f"[WARN] [Executor] Rollback hook execution failed: {e}")
        self.rollback_hooks.clear()

    def _auto_register_rollbacks(self, tool_name: str, resolved_args: Dict[str, Any]) -> None:
        """Automatically registers safe file backups and branch rollbacks for mutating tools."""
        if tool_name == "apply_hotfix_patch":
            repo_path = resolved_args.get("repo_path")
            file_path = resolved_args.get("file_path")
            if repo_path and file_path:
                full_path = Path(repo_path) / file_path
                if full_path.exists():
                    try:
                        with open(full_path, "r", encoding="utf-8") as f:
                            backup_content = f.read()
                        def restore_backup():
                            print(f"[ROLLBACK] Restoring file backup for {file_path}")
                            with open(full_path, "w", encoding="utf-8") as bf:
                                bf.write(backup_content)
                        self.register_rollback(restore_backup)
                    except Exception as e:
                        print(f"[WARN] [Executor] Failed to create file backup for rollback: {e}")
                        
        elif tool_name == "create_hotfix_branch_and_mr":
            repo_path = resolved_args.get("repo_path")
            source_branch = resolved_args.get("source_branch")
            target_branch = resolved_args.get("target_branch")
            if repo_path and source_branch and target_branch:
                def delete_local_branch():
                    print(f"[ROLLBACK] Deleting local branch {source_branch}")
                    import subprocess
                    subprocess.run(["git", "checkout", target_branch], cwd=repo_path, check=False)
                    subprocess.run(["git", "branch", "-D", source_branch], cwd=repo_path, check=False)
                self.register_rollback(delete_local_branch)

    def _inject_context_args(self, tool_name: str, resolved_args: Dict[str, Any], context: AgentContext) -> None:
        """Injects default context parameters into tools if expected but omitted."""
        if tool_name in self.registry._tools:
            tool = self.registry._tools[tool_name]
            schema = tool.get_schema()
            props = schema.get("parameters", {}).get("properties", {})
            
            # Safely auto-inject parameters from Context
            if "user_id" in props and "user_id" not in resolved_args:
                resolved_args["user_id"] = context.user.user_id
            if "project_id" in props and "project_id" not in resolved_args:
                resolved_args["project_id"] = context.repository.id
            if "repo_path" in props and "repo_path" not in resolved_args:
                # Look up path in metadata or construct defaults
                repo_path = getattr(context.repository, "repo_path", None)
                if not repo_path:
                    repo_path = context.serialize().get("repository", {}).get("repo_path")
                if not repo_path:
                    repo_path = f"workspace/{context.repository.name}"
                resolved_args["repo_path"] = repo_path
            if "repo_name" in props and "repo_name" not in resolved_args:
                resolved_args["repo_name"] = context.repository.name
            if "target_branch" in props and "target_branch" not in resolved_args:
                resolved_args["target_branch"] = context.branch.target_branch
            if "source_branch" in props and "source_branch" not in resolved_args:
                resolved_args["source_branch"] = context.branch.source_branch

    async def execute_step(self, step: StepSchema, context: AgentContext) -> Any:
        """
        Executes a single plan step, wrapping execution with retries, timeouts, and circuit breakers.
        """
        tool_name = step.tool_name
        
        # 1. Circuit Breaker validation
        if tool_name in self.tripped_tools:
            err_msg = f"Circuit breaker tripped: Tool '{tool_name}' is disabled due to consecutive failures."
            print(f"[ERROR] [Executor] {err_msg}")
            raise RuntimeError(err_msg)
            
        # Parse and resolve any variable references in step arguments
        try:
            raw_args = json.loads(step.arguments_json) if step.arguments_json else {}
        except Exception as parse_err:
            print(f"[WARN] Failed to parse arguments_json: {step.arguments_json}. Error: {parse_err}")
            raw_args = {}
            
        resolved_args = resolve_arguments(raw_args, self.step_results)
        
        # Auto-inject standard parameters
        self._inject_context_args(tool_name, resolved_args, context)
        
        # Register rollback hooks automatically
        self._auto_register_rollbacks(tool_name, resolved_args)
        
        print(f"[INFO] [Executor] Executing step '{step.step_id}' using tool '{tool_name}'...")

        if self.aril is not None:
            try:
                from peil.capture.sanitize import mask_sensitive_arguments

                self.aril.emit(
                    CaptureEventType.STEP_STARTED,
                    {
                        "step_id": step.step_id,
                        "tool_name": tool_name,
                        "arguments": mask_sensitive_arguments(resolved_args),
                    },
                )
            except Exception as exc:
                print(f"[WARN] [Executor] ARIL step_started emit failed: {exc}")

        # Log start status to memory
        self.memory.add_step(
            step_id=step.step_id,
            tool_name=tool_name,
            arguments=resolved_args,
            status="running"
        )
        await self.memory.persist_to_mongodb()
        
        # 2. Execution Loop with Retries
        last_error = None
        step_start = time.time()
        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                delay = self.initial_retry_delay * (self.backoff_factor ** (attempt - 1))
                print(f"[INFO] [Executor] Retrying step '{step.step_id}' (attempt {attempt}/{self.max_retries}) after {delay}s...")
                await asyncio.sleep(delay)
                
            try:
                # Execute with Step Timeout
                res = await asyncio.wait_for(
                    self.registry.execute_tool(
                        name=tool_name,
                        arguments=resolved_args,
                        context=context,
                        step_id=step.step_id,
                    ),
                    timeout=self.step_timeout,
                )
                
                # Success: Reset Circuit Breaker for this tool
                self.consecutive_failures[tool_name] = 0
                
                # Store execution output locally
                self.step_results[step.step_id] = res
                
                # Log completion to memory
                self.memory.add_step(
                    step_id=step.step_id,
                    tool_name=tool_name,
                    arguments=resolved_args,
                    status="completed",
                    result=res
                )
                await self.memory.persist_to_mongodb()

                if self.aril is not None:
                    try:
                        duration_ms = (time.time() - step_start) * 1000.0
                        self.aril.emit(
                            CaptureEventType.STEP_COMPLETED,
                            {
                                "step_id": step.step_id,
                                "tool_name": tool_name,
                                "duration_ms": duration_ms,
                            },
                        )
                        await self.aril.flush()
                    except Exception as exc:
                        print(f"[WARN] [Executor] ARIL step_completed emit failed: {exc}")

                print(f"[OK] [Executor] Step '{step.step_id}' completed successfully.")
                return res
                
            except Exception as e:
                last_error = e
                print(f"[WARN] [Executor] Attempt {attempt} failed: {e}")
                # Don't retry security violations
                if "Security Violation" in str(e):
                    break
                    
        # 3. Handle Failure and Trip Circuit Breaker
        self.consecutive_failures[tool_name] = self.consecutive_failures.get(tool_name, 0) + 1
        if self.consecutive_failures[tool_name] >= 3:
            self.tripped_tools.add(tool_name)
            print(f"[WARN] [Executor] Circuit breaker tripped for tool '{tool_name}'! Subsequent runs are blocked.")
            
        # Record failure in memory
        self.memory.add_step(
            step_id=step.step_id,
            tool_name=tool_name,
            arguments=resolved_args,
            status="failed",
            error=str(last_error)
        )
        await self.memory.persist_to_mongodb()

        if self.aril is not None:
            try:
                duration_ms = (time.time() - step_start) * 1000.0
                self.aril.emit(
                    CaptureEventType.STEP_FAILED,
                    {
                        "step_id": step.step_id,
                        "tool_name": tool_name,
                        "error": str(last_error),
                        "retry_count": self.max_retries,
                        "duration_ms": duration_ms,
                    },
                )
                await self.aril.flush()
            except Exception as exc:
                print(f"[WARN] [Executor] ARIL step_failed emit failed: {exc}")

        # Rollback actions
        print(f"[WARN] [Executor] Step '{step.step_id}' failed. Initiating rollbacks...")
        await self.rollback()
        
        raise last_error

# Export alias to prevent breaking imports
Executor = ExecutorAgent
