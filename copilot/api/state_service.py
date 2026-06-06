"""Derive frontend conversation state from checkpoints and LangGraph."""

from __future__ import annotations

from typing import Any, Dict, Optional

from copilot.checkpoint.langgraph_saver import CHECKPOINTS_COLLECTION
from copilot.models.frontend_models import (
    ConversationStateResponse,
    CurrentPlanResponse,
    InvestigationPlanStepResponse,
    PendingApprovalResponse,
)
from copilot.conversation_status import derive_conversation_status
from copilot.models.state import CopilotState


def current_node_from_state(state: CopilotState) -> Optional[str]:
    if not state.node_trace:
        return None
    last = state.node_trace[-1]
    if last.completed_at is None:
        return last.node.value
    return last.node.value


def build_current_plan(state: CopilotState) -> Optional[CurrentPlanResponse]:
    plan = state.investigation_plan
    if plan is None:
        return None
    return CurrentPlanResponse(
        plan_id=plan.plan_id,
        profile=plan.profile.value,
        step_cursor=state.plan_step_cursor,
        steps=[
            InvestigationPlanStepResponse(
                step_id=step.step_id,
                rationale=step.rationale,
                tool_name=step.tool_name,
                tool_args=step.tool_args,
                expected_evidence=step.expected_evidence,
            )
            for step in plan.steps
        ],
    )


def build_pending_approval(state: CopilotState) -> Optional[PendingApprovalResponse]:
    raw = state.pending_approval
    if not raw:
        return None
    return PendingApprovalResponse(
        reason=raw.get("reason", ""),
        tool_name=raw.get("tool_name", ""),
        tool_args=raw.get("tool_args", {}),
        risk_level=raw.get("risk_level", ""),
        estimated_scope=raw.get("estimated_scope", ""),
        step_id=raw.get("step_id", ""),
        requires_admin=bool(raw.get("requires_admin", False)),
    )


async def latest_langgraph_checkpoint_id(
    db: Any,
    conversation_id: str,
) -> Optional[str]:
    query = {
        "thread_id": conversation_id,
        "deleted": {"$ne": True},
    }
    docs = [
        doc
        async for doc in _iter_find(db[CHECKPOINTS_COLLECTION], query)
    ]
    if not docs:
        return None
    latest = max(docs, key=lambda d: d.get("checkpoint_id", ""))
    return latest.get("checkpoint_id")


async def build_conversation_state(
    *,
    doc: Dict[str, Any],
    db: Any,
    stream_active: bool = False,
) -> ConversationStateResponse:
    state = CopilotState.model_validate(doc["state"])
    status = doc.get("status") or derive_conversation_status(
        state, stream_active=stream_active or doc.get("stream_active", False)
    )
    checkpoint_id = await latest_langgraph_checkpoint_id(db, state.conversation_id)

    return ConversationStateResponse(
        conversation_id=state.conversation_id,
        thread_id=state.conversation_id,
        status=status,
        execution_id=state.execution_id or doc.get("execution_id"),
        copilot_execution_id=state.copilot_execution_id,
        current_node=current_node_from_state(state),
        current_plan=build_current_plan(state),
        pending_approval=build_pending_approval(state),
        checkpoint_id=checkpoint_id,
        checkpoint_version=state.checkpoint_version,
        last_updated=doc["updated_at"],
    )


async def _iter_find(collection: Any, query: dict):
    cursor = collection.find(query)
    if hasattr(cursor, "to_list"):
        for doc in await cursor.to_list(length=None):
            yield doc
        return
    if hasattr(cursor, "docs"):
        for doc in cursor.docs:
            yield doc
        return
    for doc in cursor:
        yield doc
