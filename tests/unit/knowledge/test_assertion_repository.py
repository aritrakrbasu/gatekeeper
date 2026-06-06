"""Unit tests for knowledge assertion repository."""

import pytest
from fastapi import HTTPException

from knowledge.models.assertion import KnowledgeAssertionCreate
from knowledge.models.enums import AssertionStatus, AssertionType
from knowledge.store.assertion_repository import AssertionRepository

REPO_ID = "82576405"
EXEC_ID = "exec-knowledge-unit"
USER_ID = "user-1"


def _create_data(**overrides) -> KnowledgeAssertionCreate:
    base = dict(
        repository_id=REPO_ID,
        source_execution_id=EXEC_ID,
        type=AssertionType.REPOSITORY_PATTERN,
        statement="Always run gitnexus_analyze before posting MR comments.",
        evidence_refs=["inline:abc123"],
        confidence=0.6,
        graph_id="graph-1",
        graph_hash="hash-1",
        replay_reference=f"replay:{EXEC_ID}",
    )
    base.update(overrides)
    return KnowledgeAssertionCreate(**base)


@pytest.mark.asyncio
async def test_propose_creates_proposed_status(fake_db):
    repo = AssertionRepository(fake_db)
    assertion = await repo.propose(_create_data(), proposed_by_user_id=USER_ID)

    assert assertion.status == AssertionStatus.PROPOSED
    assert assertion.assertion_id.startswith("assert-")
    assert assertion.provenance.execution_id == EXEC_ID
    assert assertion.provenance.graph_id == "graph-1"
    assert len(assertion.audit_trail) == 1
    assert assertion.audit_trail[0].action.value == "proposed"
    assert assertion.reviewed_by_user_id is None


@pytest.mark.asyncio
async def test_propose_is_idempotent(fake_db):
    repo = AssertionRepository(fake_db)
    first = await repo.propose(_create_data(), proposed_by_user_id=USER_ID)
    second = await repo.propose(_create_data(), proposed_by_user_id="other-user")

    assert first.assertion_id == second.assertion_id
    assert len(fake_db["knowledge_assertions"].docs) == 1


@pytest.mark.asyncio
async def test_accept_requires_human_review(fake_db):
    repo = AssertionRepository(fake_db)
    assertion = await repo.propose(_create_data(), proposed_by_user_id=USER_ID)

    accepted = await repo.accept(
        assertion.assertion_id, actor_user_id="reviewer-1", reason="Validated in replay"
    )
    assert accepted.status == AssertionStatus.ACCEPTED
    assert accepted.reviewed_by_user_id == "reviewer-1"
    assert len(accepted.audit_trail) == 2

    with pytest.raises(HTTPException) as exc:
        await repo.reject(assertion.assertion_id, actor_user_id="reviewer-2")
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_reject_proposed_assertion(fake_db):
    repo = AssertionRepository(fake_db)
    assertion = await repo.propose(_create_data(), proposed_by_user_id=USER_ID)

    rejected = await repo.reject(
        assertion.assertion_id,
        actor_user_id="reviewer-1",
        reason="Insufficient evidence",
    )
    assert rejected.status == AssertionStatus.REJECTED


@pytest.mark.asyncio
async def test_list_paginated_repository_scoped(fake_db):
    repo = AssertionRepository(fake_db)
    await repo.propose(_create_data(statement="Rule A"), proposed_by_user_id=USER_ID)
    await repo.propose(
        _create_data(statement="Rule B", repository_id="other-repo"),
        proposed_by_user_id=USER_ID,
    )

    items, total = await repo.list_paginated(REPO_ID, limit=10)
    assert total == 1
    assert items[0].repository_id == REPO_ID
