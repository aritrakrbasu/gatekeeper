"""Load deterministic replay bundle as primary source of truth."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from copilot.models.state import CopilotState
from peil.replay.models import ReplayMode
from peil.replay.service import ReasoningReplayService


async def replay_retrieval_node(state: CopilotState, *, db: Any = None) -> dict:
    if not state.execution_id:
        raise ValueError("execution_id must be resolved before replay retrieval")

    service = ReasoningReplayService(db)
    try:
        bundle = await service.replay(
            state.execution_id,
            mode=ReplayMode.FORENSIC,
            include_evidence=True,
            evidence_max_chars=1024,
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        state.replay_bundle = None
        return {
            "replay_available": False,
            "reason": detail,
            "execution_id": state.execution_id,
        }
    except Exception as exc:
        state.replay_bundle = None
        return {
            "replay_available": False,
            "reason": str(exc),
            "execution_id": state.execution_id,
        }

    state.replay_bundle = bundle

    return {
        "replay_available": True,
        "graph_id": bundle.graph_id,
        "graph_hash": bundle.graph_hash,
        "path_length": len(bundle.graph_path),
        "tool_calls": len(bundle.tool_calls),
        "reflections": len(bundle.reflections),
    }
