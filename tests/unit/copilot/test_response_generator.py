"""Unit tests for deterministic response generation."""

import pytest

from copilot.models.enums import QuestionType
from copilot.models.state import CopilotState
from copilot.nodes.response_generator import generate_response
from peil.replay.models import ReplayMode
from peil.replay.service import ReasoningReplayService


@pytest.mark.asyncio
async def test_generate_response_why_tool_called(fake_db, mr_replay_bundle):
    state = CopilotState(
        conversation_id="conv-test",
        user_id="user-1",
        repository_id="82576405",
        execution_id=mr_replay_bundle.execution_id,
        question="Why was clone_repo called?",
        question_type=QuestionType.WHY_TOOL_CALLED,
        focus_step_id="clone",
        replay_bundle=mr_replay_bundle,
    )
    text = generate_response(state)
    assert "clone_repo" in text
    assert "Replay source" in text


@pytest.mark.asyncio
async def test_generate_response_includes_counter_evidence_note(fake_db, mr_replay_bundle):
    state = CopilotState(
        conversation_id="conv-test",
        user_id="user-1",
        repository_id="82576405",
        execution_id=mr_replay_bundle.execution_id,
        question="What evidence supports this?",
        question_type=QuestionType.WHAT_EVIDENCE,
        replay_bundle=mr_replay_bundle,
        evidence_excerpts=[
            {"ref": "inline:abc123", "excerpt": '{"cloned": true}'}
        ],
    )
    text = generate_response(state)
    assert "inline:abc123" in text
    assert "ReasoningReplayService" in text


@pytest.fixture
async def mr_replay_bundle(fake_db):
    from peil.graph.builder import GraphBuilder
    from peil.graph.fixtures import mr_review_capture_events, mr_review_execution
    from peil.models.enums import ExecutionSource, ExecutionType
    from peil.models.execution import PeilExecutionCreate
    from peil.store.capture_event_repository import CaptureEventRepository
    from peil.store.evidence_repository import EvidenceRepository
    from peil.store.execution_repository import ExecutionRepository

    execution_id = "exec-copilot-unit"
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
    for suffix, payload in [
        ("abc123", b'{"cloned": true}'),
        ("def456", b'{"findings": 2}'),
        ("ghi789", b'{"comment_id": 99}'),
    ]:
        await evidence_repo._persist_inline_blob(
            content_hash=suffix,
            execution_id=execution_id,
            payload=payload,
            content_type="application/json",
            metadata={"execution_id": execution_id},
        )
    await GraphBuilder(fake_db).build_and_persist(execution_id)
    return await ReasoningReplayService(fake_db).replay(
        execution_id, mode=ReplayMode.FORENSIC
    )
