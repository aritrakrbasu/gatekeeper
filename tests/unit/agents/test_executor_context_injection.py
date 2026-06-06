"""Unit tests for executor context argument injection."""

from __future__ import annotations

from unittest.mock import MagicMock

from agents.context import (
    AgentContext,
    BranchContext,
    RepositoryContext,
    SchemaContext,
    UserContext,
)
from agents.executor import ExecutorAgent, derive_mr_comment_from_results
from agents.memory import MemoryStore
from agents.registry import ToolRegistry
from agents import tools


def _context(mr_iid: str = "3") -> AgentContext:
    return AgentContext(
        task_id="mr-review-test01",
        objective="Review MR",
        repository=RepositoryContext(id="82677447", name="gatekeeper"),
        branch=BranchContext(source_branch="feature", target_branch="main"),
        user=UserContext(user_id="38589527", username="dev"),
        schema_ctx=SchemaContext(),
        metadata={"trigger_type": "gitlab_mr", "mr_iid": mr_iid},
    )


def _executor() -> ExecutorAgent:
    registry = ToolRegistry()
    registry.register_local_tool(
        "post_gitlab_mr_comment",
        tools.post_gitlab_mr_comment_schema,
        tools.post_gitlab_mr_comment,
    )
    return ExecutorAgent(registry, MemoryStore(task_id="mr-review-test01", objective="Review MR"))


def test_inject_mr_iid_from_metadata():
    executor = _executor()
    resolved_args = {"user_id": "38589527", "project_id": "82677447"}
    executor._inject_context_args("post_gitlab_mr_comment", resolved_args, _context("3"))
    assert resolved_args["mr_iid"] == 3


def test_derive_mr_comment_from_markdown_report():
    comment = derive_mr_comment_from_results(
        {
            "schema_step": {"drift_detected": False},
            "summary_step": {"markdown_report": "## Gatekeeper Review\nAll good."},
        }
    )
    assert comment == "## Gatekeeper Review\nAll good."


def test_derive_mr_comment_prefers_latest_step():
    comment = derive_mr_comment_from_results(
        {
            "old_step": {"markdown_report": "old"},
            "new_step": {"summary": "new summary"},
        }
    )
    assert comment == "new summary"
