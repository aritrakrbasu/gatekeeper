"""LangGraph Copilot v2 state schema."""

from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, TypedDict

from copilot.models.state import CopilotState


class CopilotGraphState(TypedDict):
    """LangGraph channel state for the Copilot v2 graph."""

    copilot: dict
    sse_events: Annotated[List[Dict[str, Any]], operator.add]
    halted: bool


def graph_input_from_copilot(state: CopilotState) -> CopilotGraphState:
    return {
        "copilot": state.model_dump(mode="json"),
        "sse_events": [],
        "halted": False,
    }


def copilot_from_graph_state(graph_state: CopilotGraphState) -> CopilotState:
    return CopilotState.model_validate(graph_state["copilot"])


def merge_copilot_update(
    graph_state: CopilotGraphState,
    copilot: CopilotState,
) -> CopilotGraphState:
    return {
        "copilot": copilot.model_dump(mode="json"),
        "sse_events": [],
        "halted": graph_state.get("halted", False),
    }
