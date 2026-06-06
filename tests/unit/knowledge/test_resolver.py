"""Unit tests for KnowledgeResolver."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from knowledge.models.assertion import KnowledgeAssertionCreate
from knowledge.models.enums import AssertionStatus, AssertionType
from knowledge.resolver.resolver import KnowledgeResolver
from knowledge.store.assertion_repository import AssertionRepository
from peil.models.enums import ExecutionType
from peil.models.subject import SubjectRef
from peil.models.enums import SubjectType

REPO_ID = "82576405"
USER_ID = "user-1"


async def _accept(repo: AssertionRepository, data: KnowledgeAssertionCreate) -> None:
    assertion = await repo.propose(data, proposed_by_user_id=USER_ID)
    await repo.accept(assertion.assertion_id, actor_user_id="reviewer-1")


@pytest.mark.asyncio
async def test_resolver_only_returns_accepted(fake_db):
    repo = AssertionRepository(fake_db)
    await repo.propose(
        KnowledgeAssertionCreate(
            repository_id=REPO_ID,
            source_execution_id="exec-1",
            type=AssertionType.BUSINESS_RULE,
            statement="Proposed only rule",
        ),
        proposed_by_user_id=USER_ID,
    )
    await _accept(
        repo,
        KnowledgeAssertionCreate(
            repository_id=REPO_ID,
            source_execution_id="exec-2",
            type=AssertionType.REPOSITORY_PATTERN,
            statement="Accepted pattern for MR reviews",
        ),
    )

    resolver = KnowledgeResolver(fake_db, limit=10)
    ctx = await resolver.resolve(
        repository_id=REPO_ID,
        execution_type=ExecutionType.MR_REVIEW.value,
    )

    assert ctx.manifest.assertion_count == 1
    assert ctx.total_available == 1
    assert "repository_pattern" in ctx.assertions_by_type
    assert ctx.assertions_by_type["repository_pattern"][0].statement.startswith(
        "Accepted pattern"
    )


@pytest.mark.asyncio
async def test_resolver_most_recent_first_deterministic(fake_db):
    repo = AssertionRepository(fake_db)
    now = datetime.now(timezone.utc)
    statements = ["Older rule", "Middle rule", "Newest rule"]
    for idx, statement in enumerate(statements):
        await _accept(
            repo,
            KnowledgeAssertionCreate(
                repository_id=REPO_ID,
                source_execution_id=f"exec-{idx}",
                type=AssertionType.BUSINESS_RULE,
                statement=statement,
                confidence=0.5 + idx * 0.1,
            ),
        )
        fake_db["knowledge_assertions"].docs[-1]["created_at"] = now - timedelta(
            hours=len(statements) - idx
        )

    resolver = KnowledgeResolver(fake_db, limit=2)
    ctx = await resolver.resolve(
        repository_id=REPO_ID,
        execution_type=ExecutionType.MR_REVIEW.value,
    )

    ids = ctx.manifest.assertion_ids
    assert len(ids) == 2
    newest = ctx.assertions_by_type["business_rule"][0]
    assert newest.statement == "Newest rule"


@pytest.mark.asyncio
async def test_resolver_question_filter_deterministic(fake_db):
    repo = AssertionRepository(fake_db)
    await _accept(
        repo,
        KnowledgeAssertionCreate(
            repository_id=REPO_ID,
            source_execution_id="exec-a",
            type=AssertionType.REVIEW_CORRECTION,
            statement="gitnexus analyze must run before comments",
        ),
    )
    await _accept(
        repo,
        KnowledgeAssertionCreate(
            repository_id=REPO_ID,
            source_execution_id="exec-b",
            type=AssertionType.BUSINESS_RULE,
            statement="Always tag release owners",
        ),
    )

    resolver = KnowledgeResolver(fake_db, limit=10)
    ctx = await resolver.resolve(
        repository_id=REPO_ID,
        execution_type=ExecutionType.MR_REVIEW.value,
        question="Why was gitnexus analyze called?",
    )

    assert ctx.manifest.assertion_count == 1
    assert "gitnexus" in ctx.assertions_by_type["review_correction"][0].statement.lower()


@pytest.mark.asyncio
async def test_resolver_groups_by_type_with_confidence(fake_db):
    repo = AssertionRepository(fake_db)
    await _accept(
        repo,
        KnowledgeAssertionCreate(
            repository_id=REPO_ID,
            source_execution_id="exec-1",
            type=AssertionType.ARCHITECTURE_RULE,
            statement="Schema inspection required before merge",
            confidence=0.9,
            graph_id="graph-1",
            replay_reference="replay:exec-1",
        ),
    )
    await _accept(
        repo,
        KnowledgeAssertionCreate(
            repository_id=REPO_ID,
            source_execution_id="exec-2",
            type=AssertionType.REPOSITORY_PATTERN,
            statement="Clone before analyze",
            confidence=0.7,
        ),
    )

    subject_ref = SubjectRef(type=SubjectType.MR, id="42", repository_id=REPO_ID)
    resolver = KnowledgeResolver(fake_db)
    ctx = await resolver.resolve(
        repository_id=REPO_ID,
        execution_type=ExecutionType.MR_REVIEW.value,
        subject_ref=subject_ref,
    )

    assert "architecture_rule" in ctx.assertions_by_type
    assert "repository_pattern" in ctx.assertions_by_type
    assert ctx.confidence_by_type["architecture_rule"].max_confidence == 0.9
    assert ctx.manifest.groups["architecture_rule"]
    assert ctx.assertions_by_type["architecture_rule"][0].provenance.replay_reference


@pytest.mark.asyncio
async def test_generate_sample_knowledge_context(fake_db):
    """Materialize sample resolver output JSON."""
    import json
    from pathlib import Path

    repo = AssertionRepository(fake_db)
    await _accept(
        repo,
        KnowledgeAssertionCreate(
            repository_id=REPO_ID,
            source_execution_id="exec-mr-42-sample",
            type=AssertionType.REPOSITORY_PATTERN,
            statement="Tool gitnexus_analyze is invoked for step analyze because impact surface must be established.",
            evidence_refs=["inline:def456"],
            confidence=0.72,
            graph_id="graph-2bc60fea344b37af",
            graph_hash="889193d8c92e025e5700083c2415f6068e1e9ed46054f2b37c810d032a76e71f",
            replay_reference="replay:exec-mr-42-sample",
        ),
    )

    resolver = KnowledgeResolver(fake_db)
    ctx = await resolver.resolve(
        repository_id=REPO_ID,
        execution_type=ExecutionType.MR_REVIEW.value,
        subject_ref=SubjectRef(type=SubjectType.MR, id="42", repository_id=REPO_ID),
    )

    sample_path = (
        Path(__file__).resolve().parents[3]
        / "knowledge"
        / "resolver"
        / "samples"
        / "mr_review_knowledge_context.json"
    )
    sample_path.parent.mkdir(parents=True, exist_ok=True)
    sample_path.write_text(
        json.dumps(ctx.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    assert sample_path.exists()
    assert ctx.to_prompt_section()
