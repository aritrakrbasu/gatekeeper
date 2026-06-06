"""Integration test: knowledge manifest persisted on peil_executions."""

from __future__ import annotations

import pytest

from agents.context import (
    AgentContext,
    BranchContext,
    RepositoryContext,
    SchemaContext,
    UserContext,
)
from agents.planner import PlannerAgent
from knowledge.models.assertion import KnowledgeAssertionCreate
from knowledge.models.enums import AssertionType
from knowledge.store.assertion_repository import AssertionRepository
from peil.models.enums import ExecutionSource, ExecutionType
from peil.models.execution import PeilExecutionCreate
from peil.models.subject import SubjectRef
from peil.models.enums import SubjectType
from peil.store.execution_repository import ExecutionRepository

REPO_ID = "82576405"
EXEC_ID = "exec-knowledge-resolver"


def _context() -> AgentContext:
    return AgentContext(
        task_id="task-knowledge-resolver",
        objective="Review MR 42",
        repository=RepositoryContext(id=REPO_ID, name="gatekeeper"),
        branch=BranchContext(source_branch="feature", target_branch="main"),
        user=UserContext(user_id="user-1", username="dev"),
        schema_ctx=SchemaContext(),
        metadata={"trigger_type": "gitlab_mr", "mr_iid": "42"},
    )


@pytest.mark.asyncio
async def test_knowledge_manifest_persisted_on_execution(fake_db, monkeypatch):
    fake_db["connected_repositories"].docs.append(
        {"user_id": "user-1", "id": REPO_ID, "name": "gatekeeper"}
    )

    subject_ref = SubjectRef(type=SubjectType.MR, id="42", repository_id=REPO_ID)
    await ExecutionRepository(fake_db).create(
        PeilExecutionCreate(
            execution_id=EXEC_ID,
            task_id="task-knowledge-resolver",
            execution_type=ExecutionType.MR_REVIEW,
            execution_source=ExecutionSource.WORKFLOW_ENGINE,
            repository_id=REPO_ID,
            subject_ref=subject_ref,
            subject_id="mr:42:82576405",
            objective="Review MR 42",
        )
    )

    assertion_repo = AssertionRepository(fake_db)
    proposed = await assertion_repo.propose(
        KnowledgeAssertionCreate(
            repository_id=REPO_ID,
            source_execution_id="exec-prior",
            type=AssertionType.REVIEW_CORRECTION,
            statement="Verify gitnexus findings before posting comments.",
            confidence=0.85,
        ),
        proposed_by_user_id="user-1",
    )
    await assertion_repo.accept(proposed.assertion_id, actor_user_id="reviewer")

    class _FakeAril:
        execution_id = EXEC_ID
        plan_revision = 0
        execution_repo = ExecutionRepository(fake_db)

        def emit(self, event_type, payload):
            self.last_payload = payload

        async def flush(self):
            return None

    fake_aril = _FakeAril()

    from unittest.mock import MagicMock

    plan_response = MagicMock()
    plan_response.text = (
        '{"explanation": "knowledge-aware plan", "steps": [{"step_id": "clone", '
        '"tool_name": "clone_repo", "arguments_json": "{}", "dependencies": [], '
        '"action": "clone", "reason": "workspace"}]}'
    )
    plan_response.usage_metadata = None
    monkeypatch.setattr(
        "agents.planner.ai_client.models.generate_content",
        lambda **kwargs: plan_response,
    )

    registry = MagicMock()
    registry._tools = {}

    planner = PlannerAgent()
    await planner.generate_plan(_context(), registry, aril=fake_aril)

    execution = await ExecutionRepository(fake_db).get_by_execution_id(EXEC_ID)
    assert execution is not None
    assert execution.knowledge_manifest
    assert execution.knowledge_manifest.get("assertion_count", 0) >= 1
    assert execution.knowledge_manifest.get("repository_id") == REPO_ID
