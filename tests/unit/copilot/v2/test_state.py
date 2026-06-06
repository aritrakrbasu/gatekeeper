"""Unit tests for CopilotGraphState helpers."""

from copilot.graph.v2.state import (
    copilot_from_graph_state,
    graph_input_from_copilot,
    merge_copilot_update,
)
from copilot.models.state import CopilotState


def test_graph_input_round_trip():
    state = CopilotState(
        conversation_id="conv-1",
        user_id="user-1",
        repository_id="repo-1",
        question="Why?",
    )
    graph_state = graph_input_from_copilot(state)
    restored = copilot_from_graph_state(graph_state)
    assert restored.conversation_id == "conv-1"
    assert restored.question == "Why?"


def test_merge_copilot_update_preserves_halted_flag():
    state = CopilotState(
        conversation_id="conv-1",
        user_id="user-1",
        repository_id="repo-1",
    )
    graph_state = graph_input_from_copilot(state)
    graph_state["halted"] = True
    state.response_text = "answer"
    merged = merge_copilot_update(graph_state, state)
    assert merged["halted"] is True
    assert copilot_from_graph_state(merged).response_text == "answer"
