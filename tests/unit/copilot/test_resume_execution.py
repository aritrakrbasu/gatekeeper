"""Unit tests for resume_execution approval handling."""

from __future__ import annotations

import pytest

from agents.base_tool import BaseTool, ToolResult
from agents.context import AgentContext
from agents.registry import ToolRegistry
from copilot.models.enums import QuestionType
from copilot.models.investigation import InvestigationPlan, InvestigationPlanStep, InvestigationProfile
from copilot.models.state import CopilotState
from copilot.nodes.resume_execution import resume_execution_node
from copilot.tools.execution import build_interrupt_payload
from copilot.tools.categories import classify_tool

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
        return ToolResult(status="success", content={"posted": True})


@pytest.mark.asyncio
async def test_resume_reject_skips_mutating_step(fake_db):
    registry = ToolRegistry()
    registry.register_tool(_StubTool("post_gitlab_mr_comment"))

    step = InvestigationPlanStep(
        step_id="inv-02",
        rationale="post",
        tool_name="post_gitlab_mr_comment",
        tool_args={"mr_iid": 1, "comment": "x"},
        expected_evidence="comment",
    )
    state = CopilotState(
        conversation_id="conv-resume",
        user_id="user-1",
        repository_id=REPO_ID,
        question_type=QuestionType.INVESTIGATE_FURTHER,
        investigation_plan=InvestigationPlan(
            plan_id="plan-1",
            conversation_id="conv-resume",
            question_type=QuestionType.INVESTIGATE_FURTHER,
            profile=InvestigationProfile.DEEP_INVESTIGATION,
            steps=[step],
        ),
        plan_step_cursor=0,
        pending_approval=build_interrupt_payload(
            step,
            reason=step.rationale,
            category=classify_tool(step.tool_name),
        ),
        approval_resume={"action": "reject", "actor_user_id": "reviewer-1"},
    )

    detail = await resume_execution_node(state, registry=registry, db=fake_db)
    assert detail["decision"] == "reject"
    assert detail["executed"] is False
    assert state.plan_step_cursor == 1
    assert state.pending_approval is None
    assert len(fake_db["copilot_approvals"].docs) == 1


@pytest.mark.asyncio
async def test_resume_approve_executes_mutating_step(fake_db):
    registry = ToolRegistry()
    registry.register_tool(_StubTool("post_gitlab_mr_comment"))

    step = InvestigationPlanStep(
        step_id="inv-02",
        rationale="post",
        tool_name="post_gitlab_mr_comment",
        tool_args={"mr_iid": 1, "comment": "x"},
        expected_evidence="comment",
    )
    state = CopilotState(
        conversation_id="conv-resume-approve",
        user_id="user-1",
        repository_id=REPO_ID,
        question_type=QuestionType.INVESTIGATE_FURTHER,
        investigation_plan=InvestigationPlan(
            plan_id="plan-2",
            conversation_id="conv-resume-approve",
            question_type=QuestionType.INVESTIGATE_FURTHER,
            profile=InvestigationProfile.DEEP_INVESTIGATION,
            steps=[step],
        ),
        plan_step_cursor=0,
        pending_approval=build_interrupt_payload(
            step,
            reason=step.rationale,
            category=classify_tool(step.tool_name),
        ),
        approval_resume={"action": "approve", "actor_user_id": "reviewer-1"},
    )

    detail = await resume_execution_node(state, registry=registry, db=fake_db)
    assert detail["decision"] == "approve"
    assert detail["executed"] is True
    assert len(state.investigation_results) == 1
