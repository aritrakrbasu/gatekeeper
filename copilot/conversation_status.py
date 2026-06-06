"""Derive frontend conversation status from Copilot state."""

from __future__ import annotations

from copilot.models.state import CopilotState


def derive_conversation_status(
    state: CopilotState,
    *,
    stream_active: bool = False,
) -> str:
    if state.pending_approval or state.interrupted:
        return "waiting_approval"
    if state.errors:
        return "failed"
    if stream_active:
        return "running"
    if state.response_text or state.checkpoint_version > 0:
        return "completed"
    return "completed"
