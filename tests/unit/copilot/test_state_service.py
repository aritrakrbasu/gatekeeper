"""Unit tests for Copilot state derivation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from copilot.api.state_service import (
    build_conversation_state,
    build_current_plan,
    build_pending_approval,
)
from copilot.conversation_status import derive_conversation_status
from copilot.models.enums import CopilotNodeName, QuestionType
from copilot.models.investigation import InvestigationPlan, InvestigationPlanStep, InvestigationProfile
from copilot.models.state import CopilotState, NodeTraceEntry


def _base_state(**overrides) -> CopilotState:
    payload = {
        "conversation_id": "conv-1",
        "user_id": "user-1",
        "repository_id": "repo-1",
        "execution_id": "exec-1",
        "question": "Why did this fail?",
        "question_type": QuestionType.WHY_ISSUE_RAISED,
    }
    payload.update(overrides)
    return CopilotState(**payload)


def test_derive_status_waiting_approval():
    state = _base_state(pending_approval={"tool_name": "x", "reason": "r"})
    assert derive_conversation_status(state) == "waiting_approval"


def test_derive_status_running_when_stream_active():
    state = _base_state()
    assert derive_conversation_status(state, stream_active=True) == "running"


def test_derive_status_failed_on_errors():
    state = _base_state(errors=["boom"])
    assert derive_conversation_status(state) == "failed"


def test_build_current_plan():
    plan = InvestigationPlan(
        plan_id="plan-1",
        conversation_id="conv-1",
        question_type=QuestionType.WHY_ISSUE_RAISED,
        profile=InvestigationProfile.DEEP_INVESTIGATION,
        steps=[
            InvestigationPlanStep(
                step_id="s1",
                rationale="check",
                tool_name="read_file",
                tool_args={"path": "a.py"},
                expected_evidence="file contents",
            )
        ],
    )
    state = _base_state(investigation_plan=plan, plan_step_cursor=1)
    current = build_current_plan(state)
    assert current is not None
    assert current.profile == InvestigationProfile.DEEP_INVESTIGATION.value
    assert current.step_cursor == 1
    assert current.steps[0].tool_name == "read_file"


def test_build_pending_approval():
    state = _base_state(
        pending_approval={
            "reason": "needs approval",
            "tool_name": "post_gitlab_mr_comment",
            "tool_args": {"body": "hi"},
            "risk_level": "mutating",
            "estimated_scope": "1 comment",
            "step_id": "s1",
            "requires_admin": False,
        }
    )
    pending = build_pending_approval(state)
    assert pending is not None
    assert pending.tool_name == "post_gitlab_mr_comment"


@pytest.mark.asyncio
async def test_build_conversation_state_from_checkpoint(fake_db):
    now = datetime.now(timezone.utc)
    state = _base_state(
        response_text="done",
        node_trace=[
            NodeTraceEntry(node=CopilotNodeName.RESPONSE_GENERATOR, started_at=now)
        ],
    )
    doc = {
        "conversation_id": "conv-1",
        "execution_id": "exec-1",
        "updated_at": now,
        "stream_active": False,
        "state": state.model_dump(mode="json"),
    }
    result = await build_conversation_state(doc=doc, db=fake_db)
    assert result.conversation_id == "conv-1"
    assert result.thread_id == "conv-1"
    assert result.status == "completed"
    assert result.current_node == CopilotNodeName.RESPONSE_GENERATOR.value
