"""Unit tests for investigation plan execution."""

from __future__ import annotations

import pytest

from agents.base_tool import BaseTool, ToolResult
from agents.context import AgentContext
from agents.registry import ToolRegistry
from copilot.models.enums import QuestionType
from copilot.models.investigation import InvestigationPlan, InvestigationPlanStep, InvestigationProfile
from copilot.models.state import CopilotState
from copilot.nodes.execute_investigation_plan import execute_investigation_plan_node


class _StubTool(BaseTool):
    def __init__(self, name: str) -> None:
        self._name = name

    def get_name(self) -> str:
        return self._name

    def get_description(self) -> str:
        return "stub"

    def get_schema(self) -> dict:
        return {"name": self._name, "parameters": {}}

    def validate(self, arguments: dict) -> None:
        return None

    async def execute(self, arguments: dict, context: AgentContext) -> ToolResult:
        return ToolResult(status="success", content={"ok": True})


@pytest.mark.asyncio
async def test_execute_safe_steps_immediately():
    registry = ToolRegistry()
    registry.register_tool(_StubTool("get_gitlab_mr_diffs"))
    registry.register_tool(_StubTool("post_gitlab_mr_comment"))

    state = CopilotState(
        conversation_id="conv-exec",
        user_id="user-1",
        repository_id="repo-1",
        question_type=QuestionType.INVESTIGATE_FURTHER,
        investigation_plan=InvestigationPlan(
            plan_id="plan-1",
            conversation_id="conv-exec",
            question_type=QuestionType.INVESTIGATE_FURTHER,
            profile=InvestigationProfile.DEEP_INVESTIGATION,
            steps=[
                InvestigationPlanStep(
                    step_id="inv-01",
                    rationale="read diffs",
                    tool_name="get_gitlab_mr_diffs",
                    tool_args={"repository_id": "repo-1"},
                    expected_evidence="diffs",
                ),
                InvestigationPlanStep(
                    step_id="inv-02",
                    rationale="post comment",
                    tool_name="post_gitlab_mr_comment",
                    tool_args={"mr_iid": 1, "comment": "test"},
                    expected_evidence="comment id",
                ),
            ],
        ),
    )

    detail = await execute_investigation_plan_node(state, registry=registry)
    assert detail["pending_approval"] is True
    assert len(state.investigation_results) == 1
    assert state.investigation_results[0].tool_name == "get_gitlab_mr_diffs"
    assert state.pending_approval["tool_name"] == "post_gitlab_mr_comment"
