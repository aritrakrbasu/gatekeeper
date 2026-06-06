"""Unit tests for LangGraph Copilot v2 compile and routing."""

from __future__ import annotations

import pytest

from copilot.graph.v2.compile import compile_copilot_graph
from copilot.graph.v2.routing import route_after_classifier, should_plan_investigation
from copilot.graph.v2.state import graph_input_from_copilot
from copilot.models.enums import CopilotNodeName, QuestionType, QuestionType
from copilot.models.state import CopilotState


def test_route_after_classifier_skips_live_investigation_by_default():
    state = CopilotState(
        conversation_id="conv-1",
        user_id="user-1",
        repository_id="repo-1",
        question_type=QuestionType.WHAT_EVIDENCE,
    )
    graph_state = graph_input_from_copilot(state)
    assert route_after_classifier(graph_state) == CopilotNodeName.RESPONSE_GENERATOR.value


def test_route_after_classifier_routes_to_plan_investigation():
    state = CopilotState(
        conversation_id="conv-1",
        user_id="user-1",
        repository_id="repo-1",
        live_investigation_enabled=True,
    )
    graph_state = graph_input_from_copilot(state)
    assert route_after_classifier(graph_state) == CopilotNodeName.PLAN_INVESTIGATION.value


def test_should_plan_investigation_for_finding_challenge():
    state = CopilotState(
        conversation_id="conv-1",
        user_id="user-1",
        repository_id="repo-1",
        question_type=QuestionType.IS_FINDING_CORRECT,
    )
    assert should_plan_investigation(state) is True


@pytest.mark.asyncio
async def test_minimal_graph_compiles(fake_db):
    compiled, saver = compile_copilot_graph(db=fake_db, persist_checkpoints=False)
    assert compiled is not None
    assert saver is not None
