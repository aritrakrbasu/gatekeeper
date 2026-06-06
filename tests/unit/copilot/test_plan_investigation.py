"""Unit tests for plan_investigation node."""

from __future__ import annotations

import pytest

from agents.base_tool import BaseTool, ToolResult
from agents.context import AgentContext
from agents.registry import ToolRegistry
from copilot.models.enums import QuestionType
from copilot.models.state import CopilotState
from copilot.nodes.plan_investigation import plan_investigation_node

REPO_ID = "82576405"


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
        return ToolResult(status="success", content="ok")


@pytest.mark.asyncio
async def test_plan_investigation_skips_when_not_required():
    state = CopilotState(
        conversation_id="conv-1",
        user_id="user-1",
        repository_id=REPO_ID,
        live_investigation_enabled=False,
    )
    detail = await plan_investigation_node(state, registry=ToolRegistry())
    assert detail["skipped"] is True
    assert state.investigation_plan is None


@pytest.mark.asyncio
async def test_plan_investigation_builds_plan_without_executing_tools():
    registry = ToolRegistry()
    registry.register_tool(_StubTool("get_gitlab_mr_diffs"))
    registry.register_tool(_StubTool("gitnexus_analyze"))

    state = CopilotState(
        conversation_id="conv-1",
        user_id="user-1",
        repository_id=REPO_ID,
        question="Investigate this finding further",
        question_type=QuestionType.INVESTIGATE_FURTHER,
        live_investigation_enabled=True,
    )
    detail = await plan_investigation_node(state, registry=registry)

    assert detail["step_count"] >= 1
    assert state.investigation_plan is not None
    assert state.investigation_results == []
