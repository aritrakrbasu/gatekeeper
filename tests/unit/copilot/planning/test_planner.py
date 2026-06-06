"""Unit tests for deterministic investigation planner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.base_tool import BaseTool, ToolResult
from agents.context import AgentContext
from agents.registry import ToolRegistry
from copilot.models.enums import QuestionType
from copilot.models.investigation import InvestigationProfile
from copilot.models.state import CopilotState
from copilot.planning.planner import build_investigation_plan, detect_investigation_profile
from peil.replay.models import (
    ExecutionSummary,
    ReplayBundle,
    ReplayMode,
    ReplayOutcome,
    ReplayToolCall,
)

REPO_ID = "82576405"
SAMPLES = Path(__file__).resolve().parents[4] / "copilot" / "planning" / "samples"


class _StubTool(BaseTool):
    def __init__(self, name: str) -> None:
        self._name = name

    def get_name(self) -> str:
        return self._name

    def get_description(self) -> str:
        return f"stub {self._name}"

    def get_schema(self) -> dict:
        return {"name": self._name, "description": "stub", "parameters": {}}

    def validate(self, arguments: dict) -> None:
        return None

    async def execute(self, arguments: dict, context: AgentContext) -> ToolResult:
        return ToolResult(status="success", content="ok")


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    for name in (
        "get_gitlab_mr_diffs",
        "gitnexus_analyze",
        "run_impact_analysis",
        "run_schema_inspection",
    ):
        registry.register_tool(_StubTool(name))
    return registry


def _state_with_replay(question_type: QuestionType, question: str) -> CopilotState:
    bundle = ReplayBundle(
        execution_id="exec-mr-42-sample",
        outcome_node_id="outcome-1",
        mode=ReplayMode.FORENSIC,
        graph_id="graph-1",
        graph_path=[],
        execution_summary=ExecutionSummary(
            execution_id="exec-mr-42-sample",
            task_id="task-1",
            execution_type="mr_review",
            execution_source="workflow_engine",
            repository_id=REPO_ID,
            subject_id="mr:42:82576405",
            objective="Review MR",
            status="complete",
            created_at="2026-06-06T00:00:00+00:00",
            updated_at="2026-06-06T00:00:00+00:00",
        ),
        tool_calls=[
            ReplayToolCall(node_id="n1", tool_name="gitnexus_analyze", step_id="analyze")
        ],
        outcome=ReplayOutcome(node_id="outcome-1", status="complete"),
    )
    return CopilotState(
        conversation_id="conv-plan",
        user_id="user-1",
        repository_id=REPO_ID,
        question=question,
        question_type=question_type,
        live_investigation_enabled=question_type == QuestionType.INVESTIGATE_FURTHER,
        replay_bundle=bundle,
    )


@pytest.mark.parametrize(
    ("question_type", "question", "expected_profile"),
    [
        (QuestionType.IS_FINDING_CORRECT, "Is this finding wrong?", InvestigationProfile.FINDING_CHALLENGE),
        (QuestionType.WHAT_ALTERNATIVES, "Compare repository patterns", InvestigationProfile.REPOSITORY_COMPARISON),
        (QuestionType.INVESTIGATE_FURTHER, "Investigate further", InvestigationProfile.DEEP_INVESTIGATION),
    ],
)
def test_detect_profile(question_type, question, expected_profile):
    state = _state_with_replay(question_type, question)
    assert detect_investigation_profile(state) == expected_profile


def test_build_plan_is_deterministic():
    state = _state_with_replay(
        QuestionType.INVESTIGATE_FURTHER,
        "Investigate this finding further",
    )
    registry = _registry()
    first = build_investigation_plan(state, registry=registry)
    second = build_investigation_plan(state, registry=registry)
    assert first.profile == InvestigationProfile.DEEP_INVESTIGATION
    assert len(first.steps) >= 3
    assert [s.tool_name for s in first.steps] == [s.tool_name for s in second.steps]
    assert first.steps[0].step_id == "inv-01"
    assert first.steps[0].expected_evidence.startswith("[deep_investigation]")


def test_sample_plan_fixtures_match_schema():
    for name in (
        "finding_challenge_plan.json",
        "repository_comparison_plan.json",
        "deep_investigation_plan.json",
    ):
        payload = json.loads((SAMPLES / name).read_text(encoding="utf-8"))
        assert payload["profile"] in {
            InvestigationProfile.FINDING_CHALLENGE.value,
            InvestigationProfile.REPOSITORY_COMPARISON.value,
            InvestigationProfile.DEEP_INVESTIGATION.value,
        }
        assert payload["steps"]
        assert payload["steps"][0]["step_id"]
        assert payload["steps"][0]["tool_name"]
        assert payload["steps"][0]["expected_evidence"]
