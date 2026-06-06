"""Unit tests for resolve_knowledge node."""

from __future__ import annotations

import pytest

from copilot.models.state import CopilotState
from copilot.nodes.resolve_knowledge import resolve_knowledge_node
from knowledge.models.assertion import KnowledgeAssertionCreate
from knowledge.models.enums import AssertionType
from knowledge.store.assertion_repository import AssertionRepository

REPO_ID = "82576405"
USER_ID = "user-1"


@pytest.mark.asyncio
async def test_resolve_knowledge_builds_citations_and_manifest(fake_db):
    repo = AssertionRepository(fake_db)
    assertion = await repo.propose(
        KnowledgeAssertionCreate(
            repository_id=REPO_ID,
            source_execution_id="exec-1",
            type=AssertionType.REPOSITORY_PATTERN,
            statement="gitnexus_analyze must run before commenting on MRs",
        ),
        proposed_by_user_id=USER_ID,
    )
    await repo.accept(assertion.assertion_id, actor_user_id="reviewer-1")

    state = CopilotState(
        conversation_id="conv-knowledge",
        user_id=USER_ID,
        repository_id=REPO_ID,
        execution_id="exec-1",
        question="Why was gitnexus_analyze called?",
    )

    detail = await resolve_knowledge_node(state, db=fake_db)

    assert detail["assertion_count"] == 1
    assert state.knowledge_manifest
    assert state.knowledge_manifest["repository_id"] == REPO_ID
    assert state.knowledge_citations
    assert "[knowledge:" in state.knowledge_citations[0]
