"""Apply approval decision and continue investigation plan execution."""

from __future__ import annotations

from typing import Any, Optional

from agents.aril_bridge import ArilSession
from agents.registry import ToolRegistry
from copilot.approval.store import CopilotApprovalStore
from copilot.aril.capture import emit_approval_decision
from copilot.models.approval import ApprovalDecision, PendingApproval
from copilot.models.state import CopilotState
from copilot.tools.categories import ToolRiskCategory, classify_tool, requires_admin
from copilot.tools.execution import execute_plan_step


async def resume_execution_node(
    state: CopilotState,
    *,
    registry: Optional[ToolRegistry] = None,
    aril: Optional[ArilSession] = None,
    db: Any = None,
    actor_user_id: Optional[str] = None,
) -> dict:
    pending_raw = state.pending_approval
    resume = state.approval_resume
    if not pending_raw or not resume:
        return {"skipped": True, "reason": "nothing_to_resume"}

    pending = PendingApproval.model_validate(pending_raw)
    action = str(resume.get("action", resume.get("decision", ""))).lower()
    if action not in {d.value for d in ApprovalDecision}:
        raise ValueError(f"Unsupported approval action: {action}")

    decision = ApprovalDecision(action)
    actor = actor_user_id or state.user_id
    category = classify_tool(pending.tool_name)
    admin_confirmed = bool(resume.get("admin_confirmed", False))

    if requires_admin(category) and decision != ApprovalDecision.REJECT and not admin_confirmed:
        raise ValueError("Admin approval required for destructive tools")

    modified_args = resume.get("modified_tool_args")
    await emit_approval_decision(
        aril,
        decision=decision.value,
        payload=pending_raw,
        actor_user_id=actor,
        modified_tool_args=modified_args,
    )

    store = CopilotApprovalStore(db)
    await store.resolve_pending(
        state.conversation_id,
        decision=decision,
        actor_user_id=actor,
        pending=pending,
        copilot_execution_id=state.copilot_execution_id,
        repository_id=state.repository_id,
        modified_tool_args=modified_args,
        admin_confirmed=admin_confirmed,
    )

    state.approval_history.append(
        {
            "decision": decision.value,
            "tool_name": pending.tool_name,
            "step_id": pending.step_id,
            "actor_user_id": actor,
        }
    )

    executed = False
    if decision in {ApprovalDecision.APPROVE, ApprovalDecision.MODIFY}:
        if registry is None:
            from agents.registry import build_default_registry

            registry = await build_default_registry(aril=aril)

        plan = state.investigation_plan
        if plan and state.plan_step_cursor < len(plan.steps):
            step = plan.steps[state.plan_step_cursor]
            args = modified_args if decision == ApprovalDecision.MODIFY and modified_args else step.tool_args
            result = await execute_plan_step(
                state,
                step,
                registry=registry,
                aril=aril,
                tool_args=args,
            )
            state.investigation_results.append(result)
            executed = result.status == "success"

    state.plan_step_cursor += 1
    state.pending_approval = None
    state.approval_resume = None
    state.interrupted = False
    state.interrupt_payload = None

    return {
        "decision": decision.value,
        "executed": executed,
        "plan_step_cursor": state.plan_step_cursor,
    }
