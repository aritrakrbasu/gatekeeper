"""Unit tests for copilot knowledge proposals."""

import pytest

from copilot.models.enums import QuestionType
from copilot.models.state import CopilotState
from knowledge.models.enums import AssertionType
from knowledge.proposal import propose_from_copilot_state
from peil.replay.models import ReplayMode
from peil.replay.service import ReasoningReplayService


@pytest.mark.asyncio
async def test_propose_from_copilot_why_tool_called(fake_db, mr_replay_bundle):
    state = CopilotState(
        conversation_id="conv-1",
        user_id="user-1",
        repository_id="82576405",
        execution_id=mr_replay_bundle.execution_id,
        question="Why was gitnexus_analyze called?",
        question_type=QuestionType.WHY_TOOL_CALLED,
        focus_step_id="analyze",
        replay_bundle=mr_replay_bundle,
    )
    proposals = propose_from_copilot_state(state)

    assert proposals
    assert proposals[0].type == AssertionType.REPOSITORY_PATTERN
    assert proposals[0].graph_id == mr_replay_bundle.graph_id
    assert proposals[0].replay_reference.startswith("replay:")


@pytest.fixture
async def mr_replay_bundle(fake_db):
    from peil.graph.builder import GraphBuilder
    from peil.graph.fixtures import mr_review_capture_events, mr_review_execution
    from peil.models.enums import ExecutionSource, ExecutionType
    from peil.models.execution import PeilExecutionCreate
    from peil.store.capture_event_repository import CaptureEventRepository
    from peil.store.evidence_repository import EvidenceRepository
    from peil.store.execution_repository import ExecutionRepository

    execution_id = "exec-knowledge-proposal"
    execution = mr_review_execution(execution_id)
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
        mr_review_capture_events(execution_id)
    )
    evidence_repo = EvidenceRepository(fake_db)
    for suffix, payload in [("abc123", b'{"cloned": true}')]:
        await evidence_repo._persist_inline_blob(
            content_hash=suffix,
            execution_id=execution_id,
            payload=payload,
            content_type="application/json",
            metadata={"execution_id": execution_id},
        )
    await GraphBuilder(fake_db).build_and_persist(execution_id)
    bundle = await ReasoningReplayService(fake_db).replay(
        execution_id, mode=ReplayMode.FORENSIC, include_evidence=True
    )
    bundle.evidence_references  # populated by replay
    return bundle
