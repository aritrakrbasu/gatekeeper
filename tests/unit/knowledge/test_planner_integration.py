"""Unit tests for Planner + KnowledgeResolver integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.context import (
    AgentContext,
    BranchContext,
    RepositoryContext,
    SchemaContext,
    UserContext,
)
from agents.planner import PlannerAgent, StepSchema
from knowledge.models.assertion import KnowledgeAssertionCreate
from knowledge.models.enums import AssertionType
from knowledge.store.assertion_repository import AssertionRepository
from peil.models.enums import CaptureEventType

REPO_ID = "82576405"


def _context() -> AgentContext:
    return AgentContext(
        task_id="mr-review-planner-knowledge",
        objective="Review MR 42",
        repository=RepositoryContext(id=REPO_ID, name="gatekeeper"),
        branch=BranchContext(source_branch="feature", target_branch="main"),
        user=UserContext(user_id="user-1", username="dev"),
        schema_ctx=SchemaContext(),
        metadata={"trigger_type": "gitlab_mr", "mr_iid": "42"},
    )


@pytest.mark.asyncio
async def test_planner_emits_knowledge_manifest(fake_db, monkeypatch):
    repo = AssertionRepository(fake_db)
    assertion = await repo.propose(
        KnowledgeAssertionCreate(
            repository_id=REPO_ID,
            source_execution_id="exec-src",
            type=AssertionType.BUSINESS_RULE,
            statement="Run schema inspection before posting MR comments.",
            confidence=0.8,
        ),
        proposed_by_user_id="user-1",
    )
    await repo.accept(assertion.assertion_id, actor_user_id="reviewer")

    emitted: list = []

    from peil.models.execution import PeilExecutionCreate
    from peil.models.enums import ExecutionSource, ExecutionType
    from peil.models.subject import SubjectRef
    from peil.models.enums import SubjectType
    from peil.store.execution_repository import ExecutionRepository

    exec_repo = ExecutionRepository(fake_db)
    await exec_repo.create(
        PeilExecutionCreate(
            execution_id="exec-plan-1",
            task_id="mr-review-planner-knowledge",
            execution_type=ExecutionType.MR_REVIEW,
            execution_source=ExecutionSource.WORKFLOW_ENGINE,
            repository_id=REPO_ID,
            subject_ref=SubjectRef(type=SubjectType.MR, id="42", repository_id=REPO_ID),
            subject_id="mr:42:82576405",
            objective="Review MR 42",
        )
    )

    class _FakeAril:
        execution_id = "exec-plan-1"
        plan_revision = 0

        def __init__(self):
            self.execution_repo = exec_repo

        def emit(self, event_type, payload):
            emitted.append((event_type, payload))

        async def flush(self):
            return None

    fake_aril = _FakeAril()

    plan_response = MagicMock()
    plan_response.text = (
        '{"explanation": "test", "steps": [{"step_id": "s1", "tool_name": "clone_repo", '
        '"arguments_json": "{}", "dependencies": [], "action": "clone", "reason": "setup"}]}'
    )
    plan_response.usage_metadata = None

    monkeypatch.setattr(
        "agents.planner.ai_client.models.generate_content",
        lambda **kwargs: plan_response,
    )

    registry = MagicMock()
    registry._tools = {}

    planner = PlannerAgent()
    steps = await planner.generate_plan(
        _context(),
        registry,
        aril=fake_aril,
    )

    assert len(steps) == 1
    plan_events = [p for et, p in emitted if et == CaptureEventType.PLAN_EMITTED]
    assert plan_events
    manifest = plan_events[0].get("knowledge_manifest")
    assert manifest is not None
    assert manifest.get("assertion_count", 0) >= 1
    assert REPO_ID == manifest.get("repository_id")
