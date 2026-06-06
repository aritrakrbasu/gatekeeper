"""LangGraph interrupt gate for mutating/destructive tool approval."""

from __future__ import annotations

from typing import Any, Optional

from langgraph.types import interrupt

from agents.aril_bridge import ArilSession
from copilot.approval.store import CopilotApprovalStore
from copilot.aril.capture import emit_approval_required
from copilot.models.approval import PendingApproval
from copilot.models.state import CopilotState


async def approval_gate_node(
    state: CopilotState,
    *,
    aril: Optional[ArilSession] = None,
    db: Any = None,
) -> dict:
    pending = state.pending_approval
    if not pending:
        return {"skipped": True, "reason": "no_pending_approval"}

    payload = dict(pending)
    if db is not None:
        store = CopilotApprovalStore(db)
        approval_id = await store.record_pending(
            conversation_id=state.conversation_id,
            repository_id=state.repository_id,
            copilot_execution_id=state.copilot_execution_id,
            pending=PendingApproval.model_validate(payload),
        )
        payload["approval_id"] = approval_id
    await emit_approval_required(aril, payload)
    state.interrupted = True
    state.interrupt_payload = payload

    decision = interrupt(payload)
    state.approval_resume = decision if isinstance(decision, dict) else {"action": decision}
    return {
        "interrupted": True,
        "tool_name": payload.get("tool_name"),
        "resume_received": True,
    }
