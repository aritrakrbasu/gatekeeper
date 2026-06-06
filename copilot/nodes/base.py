"""Base helpers for CopilotGraph nodes."""

from __future__ import annotations

from typing import Any, AsyncIterator, Callable, Dict

from copilot.models.enums import CopilotNodeName, StreamEventType
from copilot.models.state import CopilotState, NodeTraceEntry


async def run_node(
    state: CopilotState,
    node: CopilotNodeName,
    handler: Callable[[CopilotState], Any],
) -> AsyncIterator[Dict[str, Any]]:
    started = CopilotState.now()
    trace = NodeTraceEntry(node=node, started_at=started)
    state.node_trace.append(trace)

    yield {
        "event": StreamEventType.NODE_STARTED.value,
        "data": {"node": node.value, "conversation_id": state.conversation_id},
    }

    try:
        detail = await handler(state)
        if detail is None:
            detail = {}
        trace.detail = detail
        trace.completed_at = CopilotState.now()
        state.bump_checkpoint()
        yield {
            "event": StreamEventType.NODE_COMPLETED.value,
            "data": {"node": node.value, "detail": detail},
        }
        yield {
            "event": StreamEventType.CHECKPOINT.value,
            "data": {
                "conversation_id": state.conversation_id,
                "checkpoint_version": state.checkpoint_version,
                "node": node.value,
            },
        }
    except Exception as exc:
        state.errors.append(str(exc))
        trace.completed_at = CopilotState.now()
        trace.detail = {"error": str(exc)}
        yield {
            "event": StreamEventType.ERROR.value,
            "data": {"node": node.value, "message": str(exc)},
        }
        raise
