import json
import sys
import datetime
from typing import Dict, Any, List, Set, Optional

from agents.context import AgentContext
from agents.registry import ToolRegistry
from agents.memory import MemoryStore
from agents.planner import Planner, StepSchema
from agents.executor import Executor
from agents.reflection import ReflectionLayer
from agents.approval import HumanApprovalLayer
from agents.aril_bridge import (
    ArilSession,
    bootstrap_new_execution,
    bootstrap_resumed_execution,
    resolve_execution_id_for_task,
)
from peil.config import get_aril_settings
from peil.graph.builder import GraphBuilder
from peil.models.enums import CaptureEventType, ExecutionStatus
from services import mongo_client

WEBHOOK_UNATTENDED_TRIGGERS = frozenset({"gitlab_mr", "dynatrace_crash"})


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

    def _is_webhook_mr_terminal_step(self, context: AgentContext, step: StepSchema) -> bool:
        """Successful MR comment post completes unattended webhook reviews."""
        return (
            context.metadata.get("trigger_type") == "gitlab_mr"
            and step.tool_name == "post_gitlab_mr_comment"
        )

    async def _return_completed(
        self,
        context: AgentContext,
        executor: Executor,
        memory: MemoryStore,
        executed_ids: Set[str],
        aril: Optional[ArilSession],
        loop_started: datetime.datetime,
    ) -> Dict[str, Any]:
        print("[OK] [WorkflowEngine] Webhook MR review completed after posting comment.")
        memory.status = "completed"
        memory.log_message("system", "Webhook MR review completed after posting GitLab comment.")
        await memory.persist_to_mongodb()
        duration_ms = (
            datetime.datetime.now(datetime.timezone.utc) - loop_started
        ).total_seconds() * 1000.0
        await self._emit_terminal(aril, "completed", step_count=len(executed_ids), duration_ms=duration_ms)
        result = {
            "status": "completed",
            "task_id": context.task_id,
            "results": executor.step_results,
        }
        if aril is not None:
            result["execution_id"] = aril.execution_id
        return result

    def _should_pause_for_approval(self, context: AgentContext, tool_name: str) -> bool:
        """Pause before mutating tools unless the workflow was webhook-triggered."""
        if not self.planner._is_mutate_action(tool_name):
            return False
        trigger = context.metadata.get("trigger_type", "")
        return trigger not in WEBHOOK_UNATTENDED_TRIGGERS

    async def run_task(self, context: AgentContext) -> Dict[str, Any]:
        """
        Runs the planning-execution-reflection loop until completion, error, or human approval pause.
        """
        aril = await bootstrap_new_execution(context)
        if aril is not None:
            self.registry.attach_aril(aril)
            context.metadata["execution_id"] = aril.execution_id

        memory = MemoryStore(task_id=context.task_id, objective=context.objective)
        executor = Executor(self.registry, memory, aril=aril)

        executed_ids: Set[str] = set()
        active_plan: List[StepSchema] = []
        plan_revision = 0

        memory.log_message("system", f"Workflow engine started. Objective: '{context.objective}'")
        await memory.persist_to_mongodb()

        memories = []
        try:
            memories = await memory.find_similar_fixes(context.objective, limit=2)
            if not memories:
                memories = await memory.find_similar_incidents(context.objective, limit=2)
        except Exception as e:
            print(f"[WARN] [WorkflowEngine] Failed to retrieve history memories: {e}")

        try:
            active_plan = await self.planner.generate_plan(
                context,
                self.registry,
                memories=memories,
                aril=aril,
                plan_revision=plan_revision,
            )
            if aril is not None:
                plan_revision = aril.plan_revision
        except Exception as e:
            memory.status = "failed"
            memory.log_message("system", f"Initial planning failed: {e}")
            await memory.persist_to_mongodb()
            await self._emit_terminal(aril, "failed", error=str(e), step_count=0)
            return {"status": "failed", "error": f"Initial planning failed: {e}"}

        return await self._run_execution_loop(
            context,
            executor,
            memory,
            executed_ids,
            active_plan,
            aril=aril,
            plan_revision=plan_revision,
        )

    async def resume_task(self, task_id: str) -> Dict[str, Any]:
        """
        Resumes a paused task from saved execution state.
        """
        trace = await mongo_client.find_one("agent_execution_traces", {"task_id": task_id})
        if not trace:
            raise ValueError(f"No execution trace found to resume for task {task_id}")

        ctx_data = trace["context"]
        context = AgentContext(**ctx_data)

        execution_id = trace.get("execution_id") or context.metadata.get("execution_id")
        if not execution_id:
            execution_id = await resolve_execution_id_for_task(task_id)

        aril = None
        if execution_id:
            aril = await bootstrap_resumed_execution(context, execution_id)
            if aril is not None:
                self.registry.attach_aril(aril)
                context.metadata["execution_id"] = execution_id

        executed_ids = set(trace.get("executed_ids", []))
        step_results = trace.get("step_results", {})
        active_plan = [StepSchema(**s) for s in trace.get("active_plan", [])]
        plan_revision = int(trace.get("plan_revision", 0))

        memory = MemoryStore(task_id=context.task_id, objective=context.objective)
        memory.steps = trace.get("steps", [])
        memory.messages = trace.get("messages", [])

        executor = Executor(self.registry, memory, aril=aril)
        executor.step_results = step_results

        memory.log_message("system", "Workflow engine resumed from approval state.")
        await memory.persist_to_mongodb()

        return await self._run_execution_loop(
            context,
            executor,
            memory,
            executed_ids,
            active_plan,
            aril=aril,
            plan_revision=plan_revision,
        )

    async def save_execution_state(
        self,
        context: AgentContext,
        executed_ids: Set[str],
        step_results: Dict[str, Any],
        active_plan: List[StepSchema],
        memory: MemoryStore,
        aril: Optional[ArilSession] = None,
        plan_revision: int = 0,
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
            "plan_revision": plan_revision,
            "updated_at": datetime.datetime.utcnow().isoformat(),
        }
        if aril is not None:
            state_doc["execution_id"] = aril.execution_id
        elif context.metadata.get("execution_id"):
            state_doc["execution_id"] = context.metadata["execution_id"]

        await mongo_client.upsert_one(
            collection_name="agent_execution_traces",
            filter={"task_id": context.task_id},
            document=state_doc,
        )
        print(f"[OK] [WorkflowEngine] Saved execution state for task {context.task_id}")

    async def _emit_terminal(
        self,
        aril: Optional[ArilSession],
        status: str,
        *,
        error: Optional[str] = None,
        step_count: int = 0,
        last_step_id: Optional[str] = None,
        duration_ms: Optional[float] = None,
    ) -> None:
        if aril is None:
            return
        try:
            event_type = CaptureEventType.EXECUTION_COMPLETED
            exec_status = ExecutionStatus.COMPLETE
            if status == "failed":
                event_type = CaptureEventType.EXECUTION_FAILED
                exec_status = ExecutionStatus.FAILED
            elif status == "awaiting_approval":
                event_type = CaptureEventType.EXECUTION_PAUSED
                exec_status = ExecutionStatus.PAUSED

            payload: Dict[str, Any] = {
                "status": status,
                "step_count": step_count,
            }
            if error:
                payload["error"] = error
            if last_step_id:
                payload["last_step_id"] = last_step_id
            if duration_ms is not None:
                payload["duration_ms"] = duration_ms

            aril.emit(event_type, payload)
            await aril.flush()
            await aril.update_status(
                exec_status,
                completed_at=datetime.datetime.now(datetime.timezone.utc),
            )
            await self._maybe_build_decision_graph(aril, status)
        except Exception as exc:
            print(f"[WARN] [WorkflowEngine] ARIL terminal emit failed: {exc}")

    async def _maybe_build_decision_graph(
        self,
        aril: ArilSession,
        status: str,
    ) -> None:
        settings = get_aril_settings()
        should_build = status in ("completed", "failed") or (
            status == "awaiting_approval" and settings.graph_build_on_pause
        )
        if not should_build:
            return
        try:
            builder = GraphBuilder()
            await builder.build_and_persist(aril.execution_id)
        except Exception as exc:
            print(f"[WARN] [WorkflowEngine] ARIL graph build failed: {exc}")

    async def _run_execution_loop(
        self,
        context: AgentContext,
        executor: Executor,
        memory: MemoryStore,
        executed_ids: Set[str],
        active_plan: List[StepSchema],
        aril: Optional[ArilSession] = None,
        plan_revision: int = 0,
    ) -> Dict[str, Any]:
        max_total_steps = 15
        total_steps_run = len(executed_ids)
        loop_started = datetime.datetime.now(datetime.timezone.utc)

        while total_steps_run < max_total_steps:
            ready_steps = get_ready_steps(active_plan, executed_ids)

            if not ready_steps:
                all_done = all(step.step_id in executed_ids for step in active_plan)
                if all_done:
                    print(f"[OK] [WorkflowEngine] All plan steps executed successfully.")
                    memory.status = "completed"
                    memory.log_message("system", "Workflow execution completed successfully.")
                    await memory.persist_to_mongodb()
                    duration_ms = (
                        datetime.datetime.now(datetime.timezone.utc) - loop_started
                    ).total_seconds() * 1000.0
                    await self._emit_terminal(
                        aril,
                        "completed",
                        step_count=len(executed_ids),
                        duration_ms=duration_ms,
                    )
                    result = {
                        "status": "completed",
                        "task_id": context.task_id,
                        "results": executor.step_results,
                    }
                    if aril is not None:
                        result["execution_id"] = aril.execution_id
                    return result
                err_msg = "Plan execution stalled. Circular dependency or unresolvable step dependencies detected."
                memory.status = "failed"
                memory.log_message("system", err_msg)
                await memory.persist_to_mongodb()
                await self._emit_terminal(aril, "failed", error=err_msg, step_count=len(executed_ids))
                return {"status": "failed", "error": err_msg}

            step_to_run = ready_steps[0]

            if self._should_pause_for_approval(context, step_to_run.tool_name):
                approval_status = await self.approval.check_approval_status(context.task_id, step_to_run.step_id)

                if approval_status == "rejected":
                    err_msg = f"Task aborted: Mutating step '{step_to_run.step_id}' rejected by human reviewer."
                    memory.status = "failed"
                    memory.log_message("system", err_msg)
                    await memory.persist_to_mongodb()
                    await self._emit_terminal(aril, "failed", error=err_msg, step_count=len(executed_ids))
                    return {"status": "failed", "error": err_msg}

                elif approval_status != "approved":
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
                        arguments=resolved_args,
                    )
                    await self.approval.submit_for_approval(package)

                    memory.status = "awaiting_approval"
                    memory.log_message("system", f"Mutating step '{step_to_run.step_id}' requires human approval. Loop paused.")
                    await memory.persist_to_mongodb()

                    await self.save_execution_state(
                        context,
                        executed_ids,
                        executor.step_results,
                        active_plan,
                        memory,
                        aril=aril,
                        plan_revision=plan_revision,
                    )
                    await self._emit_terminal(aril, "awaiting_approval", step_count=len(executed_ids))

                    return {
                        "status": "awaiting_approval",
                        "task_id": context.task_id,
                        "approval_id": package.approval_id,
                        "approval_package": package.model_dump(),
                        "execution_id": aril.execution_id if aril else context.metadata.get("execution_id"),
                    }

            elif self.planner._is_mutate_action(step_to_run.tool_name):
                trigger = context.metadata.get("trigger_type", "")
                sys.stderr.write(
                    f"[INFO] Webhook unattended mode: auto-executing mutating step "
                    f"'{step_to_run.tool_name}' (trigger={trigger})\n"
                )
                sys.stderr.flush()

            total_steps_run += 1
            try:
                result = await executor.execute_step(step_to_run, context)
                await self.reflection.evaluate_step_result(step_to_run, result, aril=aril)
                executed_ids.add(step_to_run.step_id)
                if aril is not None:
                    await aril.flush()

                if self._is_webhook_mr_terminal_step(context, step_to_run):
                    return await self._return_completed(
                        context,
                        executor,
                        memory,
                        executed_ids,
                        aril,
                        loop_started,
                    )

            except Exception as step_err:
                print(f"[WARN] [WorkflowEngine] Step '{step_to_run.step_id}' failed: {step_err}. Triggering replanning...")

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
                        "error": str(step_err) if s.step_id == step_to_run.step_id else None,
                    })

                try:
                    active_plan = await self.planner.generate_plan(
                        context=context,
                        registry=self.registry,
                        history_steps=history_steps,
                        aril=aril,
                        plan_revision=plan_revision,
                    )
                    if aril is not None:
                        plan_revision = aril.plan_revision
                        await aril.flush()
                    memory.log_message("system", f"Step '{step_to_run.step_id}' failed. Dynamically re-planned active path.")
                    await memory.persist_to_mongodb()
                except Exception as replan_err:
                    err_msg = f"Replanning failed after step '{step_to_run.step_id}' failure: {replan_err}"
                    memory.status = "failed"
                    memory.log_message("system", err_msg)
                    await memory.persist_to_mongodb()
                    await self._emit_terminal(
                        aril,
                        "failed",
                        error=err_msg,
                        step_count=len(executed_ids),
                        last_step_id=step_to_run.step_id,
                    )
                    return {"status": "failed", "error": err_msg}

        err_msg = f"Max execution step limit ({max_total_steps}) reached. Aborting execution loop."
        memory.status = "failed"
        memory.log_message("system", err_msg)
        await memory.persist_to_mongodb()
        await self._emit_terminal(aril, "failed", error=err_msg, step_count=len(executed_ids))
        return {"status": "failed", "error": err_msg}
