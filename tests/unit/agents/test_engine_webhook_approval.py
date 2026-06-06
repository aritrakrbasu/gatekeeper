"""Unit tests for webhook unattended approval policy in WorkflowEngine."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agents.context import (
    AgentContext,
    BranchContext,
    RepositoryContext,
    SchemaContext,
    UserContext,
)
from agents.engine import WEBHOOK_UNATTENDED_TRIGGERS, WorkflowEngine


def _context(trigger_type: str = "") -> AgentContext:
    return AgentContext(
        task_id="mr-review-test01",
        objective="Review MR 42",
        repository=RepositoryContext(id="82576405", name="gatekeeper"),
        branch=BranchContext(source_branch="feature", target_branch="main"),
        user=UserContext(user_id="user-1", username="dev"),
        schema_ctx=SchemaContext(),
        metadata={"trigger_type": trigger_type} if trigger_type else {},
    )


@pytest.fixture
def engine() -> WorkflowEngine:
    return WorkflowEngine(MagicMock())


@pytest.mark.parametrize(
    ("trigger_type", "tool_name", "expected_pause"),
    [
        ("gitlab_mr", "post_gitlab_mr_comment", False),
        ("dynatrace_crash", "apply_hotfix_patch", False),
        ("", "post_gitlab_mr_comment", True),
        ("manual", "post_gitlab_mr_comment", True),
        ("gitlab_mr", "get_gitlab_mr_diffs", False),
        ("gitlab_mr", "gitnexus_analyze", False),
    ],
)
def test_should_pause_for_approval_matrix(
    engine: WorkflowEngine,
    trigger_type: str,
    tool_name: str,
    expected_pause: bool,
):
    context = _context(trigger_type)
    assert engine._should_pause_for_approval(context, tool_name) is expected_pause


def test_webhook_unattended_triggers_constant():
    assert WEBHOOK_UNATTENDED_TRIGGERS == frozenset({"gitlab_mr", "dynatrace_crash"})
