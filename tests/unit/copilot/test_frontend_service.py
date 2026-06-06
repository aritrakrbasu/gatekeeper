"""Unit tests for Copilot frontend service methods."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from copilot.api.service import CopilotService, format_sse, parse_last_event_id
from copilot.models.enums import QuestionType
from copilot.models.state import CopilotState
from copilot.store.checkpoint_repository import CheckpointRepository
from copilot.store.sse_event_store import SseEventStore
from peil.graph.fixtures import mr_review_execution
from peil.models.enums import ExecutionSource, ExecutionType
from peil.models.execution import PeilExecutionCreate
from peil.store.execution_repository import ExecutionRepository

EXECUTION_ID = "exec-frontend"
REPO_ID = "82576405"
USER_ID = "user-1"


async def _seed(fake_db) -> str:
    fake_db["connected_repositories"].docs.append(
        {"user_id": USER_ID, "id": REPO_ID, "name": "gatekeeper"}
    )
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
    state = await CheckpointRepository(fake_db).create_conversation(
        user_id=USER_ID,
        repository_id=REPO_ID,
        execution_id=EXECUTION_ID,
    )
    state.question = "What happened?"
    state.question_type = QuestionType.WHY_ISSUE_RAISED
    state.response_text = "Summary"
    await CheckpointRepository(fake_db).save(state)
    return state.conversation_id


@pytest.mark.asyncio
async def test_list_conversations_paginated(fake_db):
    conversation_id = await _seed(fake_db)
    service = CopilotService(fake_db)
    result = await service.list_conversations(
        USER_ID, repository_id=REPO_ID, page=1, page_size=10
    )
    assert result.total == 1
    assert result.items[0].conversation_id == conversation_id
    assert result.items[0].execution_id == EXECUTION_ID


@pytest.mark.asyncio
async def test_get_conversation_state(fake_db):
    conversation_id = await _seed(fake_db)
    service = CopilotService(fake_db)
    state = await service.get_conversation_state(USER_ID, conversation_id)
    assert state.conversation_id == conversation_id
    assert state.execution_id == EXECUTION_ID
    assert state.status == "completed"


@pytest.mark.asyncio
async def test_get_execution_link(fake_db):
    conversation_id = await _seed(fake_db)
    service = CopilotService(fake_db)
    link = await service.get_conversation_execution_link(USER_ID, conversation_id)
    assert link.execution_id == EXECUTION_ID
    assert link.repository_id == REPO_ID
    assert link.subject_id is not None


@pytest.mark.asyncio
async def test_bootstrap_response(fake_db):
    conversation_id = await _seed(fake_db)
    service = CopilotService(fake_db)
    bootstrap = await service.get_conversation_bootstrap(USER_ID, conversation_id)
    assert bootstrap.conversation.conversation_id == conversation_id
    assert bootstrap.execution.execution_id == EXECUTION_ID
    assert bootstrap.state.thread_id == conversation_id
    assert bootstrap.checkpoint.thread_id == conversation_id


@pytest.mark.asyncio
async def test_pending_approval_queue(fake_db):
    conversation_id = await _seed(fake_db)
    from copilot.approval.store import CopilotApprovalStore
    from copilot.models.approval import PendingApproval

    await CopilotApprovalStore(fake_db).record_pending(
        conversation_id=conversation_id,
        repository_id=REPO_ID,
        pending=PendingApproval(
            reason="needs review",
            tool_name="post_gitlab_mr_comment",
            tool_args={},
            risk_level="mutating",
            estimated_scope="1 comment",
            step_id="s1",
        ),
    )
    service = CopilotService(fake_db)
    queue = await service.list_pending_approvals(USER_ID, repository_id=REPO_ID)
    assert queue.total == 1
    assert queue.items[0].conversation_id == conversation_id
    assert queue.items[0].tool_name == "post_gitlab_mr_comment"


@pytest.mark.asyncio
async def test_sse_event_store_replay(fake_db):
    store = SseEventStore(fake_db)
    first = await store.append(
        conversation_id="conv-1",
        thread_id="conv-1",
        event_type="node_started",
        data={"node": "planner"},
    )
    second = await store.append(
        conversation_id="conv-1",
        thread_id="conv-1",
        event_type="node_completed",
        data={"node": "planner"},
    )
    replay = await store.list_after("conv-1", last_event_id=first)
    assert len(replay) == 1
    assert replay[0]["event_id"] == second


def test_format_sse_includes_event_id():
    rendered = format_sse({"event": "done", "data": {"ok": True}, "id": 7})
    assert "id: 7" in rendered
    assert "event: done" in rendered


def test_parse_last_event_id():
    assert parse_last_event_id("12") == 12
    assert parse_last_event_id(None) == 0
    assert parse_last_event_id("bad") == 0


@pytest.mark.asyncio
async def test_authorization_denied_for_other_user(fake_db):
    conversation_id = await _seed(fake_db)
    service = CopilotService(fake_db)
    with pytest.raises(HTTPException) as exc:
        await service.get_conversation_state("other-user", conversation_id)
    assert exc.value.status_code == 403
