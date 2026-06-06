"""Integration tests for Copilot frontend-readiness APIs."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from copilot.api.router import _copilot_service, copilot_router
from copilot.api.service import CopilotService
from copilot.approval.store import CopilotApprovalStore
from copilot.models.approval import PendingApproval
from copilot.models.enums import QuestionType
from copilot.store.checkpoint_repository import CheckpointRepository
from copilot.store.sse_event_store import SseEventStore
from peil.api.auth import require_jwt_user
from peil.graph.builder import GraphBuilder
from peil.graph.fixtures import mr_review_capture_events, mr_review_execution
from peil.models.enums import ExecutionSource, ExecutionType
from peil.models.execution import PeilExecutionCreate
from peil.store.capture_event_repository import CaptureEventRepository
from peil.store.evidence_repository import EvidenceRepository
from peil.store.execution_repository import ExecutionRepository

EXECUTION_ID = "exec-copilot-frontend"
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
    await CaptureEventRepository(fake_db).append_events(
        mr_review_capture_events(EXECUTION_ID)
    )
    evidence_repo = EvidenceRepository(fake_db)
    for suffix, payload in [
        ("abc123", b'{"cloned": true}'),
        ("def456", b'{"findings": 2}'),
    ]:
        await evidence_repo._persist_inline_blob(
            content_hash=suffix,
            execution_id=EXECUTION_ID,
            payload=payload,
            content_type="application/json",
            metadata={"execution_id": EXECUTION_ID},
        )
    await GraphBuilder(fake_db).build_and_persist(EXECUTION_ID)
    state = await CheckpointRepository(fake_db).create_conversation(
        user_id=USER_ID,
        repository_id=REPO_ID,
        execution_id=EXECUTION_ID,
    )
    state.question = "Why was this rejected?"
    state.question_type = QuestionType.WHY_ISSUE_RAISED
    state.response_text = "Because of policy X."
    await CheckpointRepository(fake_db).save(state)
    return state.conversation_id


@pytest.fixture
async def frontend_client(fake_db):
    conversation_id = await _seed(fake_db)

    app = FastAPI()
    app.include_router(copilot_router)

    def _fake_user():
        return {"id": USER_ID, "username": "dev"}

    def _fake_service():
        return CopilotService(fake_db)

    app.dependency_overrides[require_jwt_user] = _fake_user
    app.dependency_overrides[_copilot_service] = _fake_service

    with TestClient(app) as client:
        yield client, conversation_id


@pytest.mark.asyncio
async def test_list_conversations_endpoint(frontend_client):
    client, conversation_id = frontend_client
    response = client.get(
        "/api/copilot/conversations",
        params={"repository_id": REPO_ID, "page": 1, "page_size": 10},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["conversation_id"] == conversation_id


@pytest.mark.asyncio
async def test_conversation_state_endpoint(frontend_client):
    client, conversation_id = frontend_client
    response = client.get(f"/api/copilot/conversations/{conversation_id}/state")
    assert response.status_code == 200
    payload = response.json()
    assert payload["conversation_id"] == conversation_id
    assert payload["thread_id"] == conversation_id
    assert payload["status"] == "completed"
    assert payload["execution_id"] == EXECUTION_ID


@pytest.mark.asyncio
async def test_execution_link_endpoint(frontend_client):
    client, conversation_id = frontend_client
    response = client.get(f"/api/copilot/conversations/{conversation_id}/execution")
    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_id"] == EXECUTION_ID
    assert payload["repository_id"] == REPO_ID
    assert payload["subject_id"] is not None


@pytest.mark.asyncio
async def test_bootstrap_endpoint(frontend_client):
    client, conversation_id = frontend_client
    response = client.get(f"/api/copilot/conversations/{conversation_id}/bootstrap")
    assert response.status_code == 200
    payload = response.json()
    assert payload["conversation"]["conversation_id"] == conversation_id
    assert payload["execution"]["execution_id"] == EXECUTION_ID
    assert payload["state"]["thread_id"] == conversation_id
    assert payload["checkpoint"]["thread_id"] == conversation_id


@pytest.mark.asyncio
async def test_pending_approvals_endpoint(frontend_client, fake_db):
    client, conversation_id = frontend_client
    await CopilotApprovalStore(fake_db).record_pending(
        conversation_id=conversation_id,
        repository_id=REPO_ID,
        pending=PendingApproval(
            reason="comment required",
            tool_name="post_gitlab_mr_comment",
            tool_args={},
            risk_level="mutating",
            estimated_scope="1 comment",
            step_id="s1",
        ),
    )
    response = client.get(
        "/api/copilot/approvals/pending",
        params={"repository_id": REPO_ID},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["conversation_id"] == conversation_id


@pytest.mark.asyncio
async def test_sse_reconnect_no_duplicates(frontend_client, fake_db):
    client, conversation_id = frontend_client
    store = SseEventStore(fake_db)
    await store.append(
        conversation_id=conversation_id,
        thread_id=conversation_id,
        event_type="node_started",
        data={"node": "planner"},
    )
    await store.append(
        conversation_id=conversation_id,
        thread_id=conversation_id,
        event_type="done",
        data={"ok": True},
    )

    with client.stream(
        "GET",
        f"/api/copilot/conversations/{conversation_id}/stream",
        headers={"Last-Event-ID": "1"},
        params={"thread_id": conversation_id},
    ) as response:
        assert response.status_code == 200
        chunks = "".join(response.iter_text())
    assert "id: 2" in chunks
    assert chunks.count("id: 1") == 0
    assert "event: done" in chunks


@pytest.mark.asyncio
async def test_state_restoration_after_save(frontend_client, fake_db):
    client, conversation_id = frontend_client
    repo = CheckpointRepository(fake_db)
    doc = await repo.get_doc(conversation_id)
    state = doc["state"]
    state["pending_approval"] = {
        "reason": "approval needed",
        "tool_name": "post_gitlab_mr_comment",
        "tool_args": {},
        "risk_level": "mutating",
        "estimated_scope": "1",
        "step_id": "s1",
    }
    state["interrupted"] = True
    from copilot.models.state import CopilotState

    await repo.save(CopilotState.model_validate(state))

    response = client.get(f"/api/copilot/conversations/{conversation_id}/state")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "waiting_approval"
    assert payload["pending_approval"]["tool_name"] == "post_gitlab_mr_comment"
