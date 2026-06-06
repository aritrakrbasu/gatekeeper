"""ARIL event emission for Copilot approval and execution lifecycle."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from agents.aril_bridge import ArilSession
from peil.config import get_aril_settings
from peil.graph.builder import GraphBuilder
from peil.models.enums import CaptureEventType, ExecutionStatus


def _approval_event_type(decision: str) -> CaptureEventType:
    mapping = {
        "approve": CaptureEventType.APPROVAL_GRANTED,
        "reject": CaptureEventType.APPROVAL_REJECTED,
        "modify": CaptureEventType.APPROVAL_MODIFIED,
    }
    return mapping.get(decision, CaptureEventType.APPROVAL_RESOLVED)


async def emit_approval_required(
    aril: Optional[ArilSession],
    payload: Dict[str, Any],
) -> None:
    if aril is None:
        return
    aril.emit(
        CaptureEventType.APPROVAL_REQUIRED,
        {
            **payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    aril.emit(
        CaptureEventType.EXECUTION_PAUSED,
        {
            "reason": "approval_required",
            "tool_name": payload.get("tool_name"),
            "step_id": payload.get("step_id"),
        },
    )
    await aril.flush()


async def emit_approval_decision(
    aril: Optional[ArilSession],
    *,
    decision: str,
    payload: Dict[str, Any],
    actor_user_id: str,
    modified_tool_args: Optional[Dict[str, Any]] = None,
) -> None:
    if aril is None:
        return
    event_type = _approval_event_type(decision)
    aril.emit(
        event_type,
        {
            "decision": decision,
            "actor_user_id": actor_user_id,
            "tool_name": payload.get("tool_name"),
            "tool_args": payload.get("tool_args"),
            "modified_tool_args": modified_tool_args,
            "step_id": payload.get("step_id"),
            "risk_level": payload.get("risk_level"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    aril.emit(
        CaptureEventType.APPROVAL_RESOLVED,
        {
            "decision": decision,
            "tool_name": payload.get("tool_name"),
            "step_id": payload.get("step_id"),
        },
    )
    await aril.flush()


async def finalize_copilot_execution(
    aril: Optional[ArilSession],
    *,
    status: str = "completed",
    db: Any = None,
) -> None:
    if aril is None:
        return
    event_type = CaptureEventType.EXECUTION_COMPLETED
    exec_status = ExecutionStatus.COMPLETE
    if status == "failed":
        event_type = CaptureEventType.EXECUTION_FAILED
        exec_status = ExecutionStatus.FAILED
    elif status == "paused":
        event_type = CaptureEventType.EXECUTION_PAUSED
        exec_status = ExecutionStatus.PAUSED

    aril.emit(event_type, {"status": status})
    await aril.flush()
    await aril.update_status(
        exec_status,
        completed_at=datetime.now(timezone.utc),
    )

    settings = get_aril_settings()
    if status in ("completed", "failed") or (
        status == "paused" and settings.graph_build_on_pause
    ):
        try:
            builder = GraphBuilder(db)
            await builder.build_and_persist(aril.execution_id)
        except Exception:
            pass
