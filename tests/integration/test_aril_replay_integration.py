"""Integration tests for ReasoningReplayService against built graphs."""

from __future__ import annotations

import pytest

from peil.graph.builder import GraphBuilder
from peil.graph.fixtures import mr_review_capture_events, mr_review_execution
from peil.models.enums import ExecutionSource, ExecutionType
from peil.models.execution import PeilExecutionCreate
from peil.replay.models import ReplayMode
from peil.replay.service import ReasoningReplayService
from peil.store.capture_event_repository import CaptureEventRepository
from peil.store.evidence_repository import EvidenceRepository
from peil.store.execution_repository import ExecutionRepository


EXECUTION_ID = "exec-replay-integration"


async def _seed_mr_review(fake_db) -> None:
    execution = mr_review_execution(EXECUTION_ID)
    await ExecutionRepository(fake_db).create(
        PeilExecutionCreate(
            execution_id=execution.execution_id,
            task_id=execution.task_id,
            execution_type=ExecutionType.MR_REVIEW,
            execution_source=ExecutionSource.WORKFLOW_ENGINE,
            repository_id=execution.repository_id,
            subject_ref=execution.subject_ref,
            subject_id=execution.subject_id,
            objective=execution.objective,
        )
    )
    await CaptureEventRepository(fake_db).append_events(
        mr_review_capture_events(EXECUTION_ID)
    )
    evidence_repo = EvidenceRepository(fake_db)
    for suffix, payload in [
        ("abc123", b'{"cloned": true}'),
        ("def456", b'{"findings": 2}'),
        ("ghi789", b'{"comment_id": 99}'),
    ]:
        await evidence_repo._persist_inline_blob(
            content_hash=suffix,
            execution_id=EXECUTION_ID,
            payload=payload,
            content_type="application/json",
            metadata={"execution_id": EXECUTION_ID},
        )
    await GraphBuilder(fake_db).build_and_persist(EXECUTION_ID)


@pytest.mark.asyncio
async def test_end_to_end_forensic_replay(fake_db):
    await _seed_mr_review(fake_db)
    service = ReasoningReplayService(fake_db)

    bundle = await service.replay(EXECUTION_ID, mode=ReplayMode.FORENSIC)

    assert bundle.execution_summary.execution_id == EXECUTION_ID
    assert bundle.graph_hash is not None
    assert len(bundle.graph_path) == 16
    assert bundle.outcome.node_id == "outcome:terminal"
    assert bundle.evidence_references[0].excerpt


@pytest.mark.asyncio
async def test_end_to_end_narrative_replay(fake_db):
    await _seed_mr_review(fake_db)
    service = ReasoningReplayService(fake_db)

    bundle = await service.replay(
        EXECUTION_ID,
        mode=ReplayMode.NARRATIVE,
        outcome_node_id="outcome:terminal",
    )

    assert bundle.narrative is not None
    section_titles = [s.title for s in bundle.narrative.sections]
    assert "Execution" in section_titles
    assert "Plan" in section_titles
    assert "Outcome" in section_titles
    assert any(title.startswith("Step ") for title in section_titles)


@pytest.mark.asyncio
async def test_replay_without_graph_raises(fake_db):
    execution = mr_review_execution("exec-no-graph")
    await ExecutionRepository(fake_db).create(
        PeilExecutionCreate(
            execution_id=execution.execution_id,
            task_id=execution.task_id,
            execution_type=ExecutionType.MR_REVIEW,
            execution_source=ExecutionSource.WORKFLOW_ENGINE,
            repository_id=execution.repository_id,
            subject_ref=execution.subject_ref,
            subject_id=execution.subject_id,
            objective=execution.objective,
        )
    )

    service = ReasoningReplayService(fake_db)
    with pytest.raises(Exception) as exc:
        await service.replay("exec-no-graph")
    assert getattr(exc.value, "status_code", None) == 404
