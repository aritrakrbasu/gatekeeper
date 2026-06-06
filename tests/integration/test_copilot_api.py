"""Integration tests for Copilot HTTP API."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from copilot.api.router import _copilot_service, copilot_router
from copilot.api.service import CopilotService
from peil.api.auth import require_jwt_user
from peil.graph.builder import GraphBuilder
from peil.graph.fixtures import mr_review_capture_events, mr_review_execution
from peil.models.enums import ExecutionSource, ExecutionType
from peil.models.execution import PeilExecutionCreate
from peil.store.capture_event_repository import CaptureEventRepository
from peil.store.evidence_repository import EvidenceRepository
from peil.store.execution_repository import ExecutionRepository

EXECUTION_ID = "exec-copilot-api"
REPO_ID = "82576405"
USER_ID = "user-1"


async def _seed(fake_db) -> None:
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


@pytest.fixture
async def copilot_client(fake_db):
    await _seed(fake_db)

    app = FastAPI()
    app.include_router(copilot_router)

    def _fake_user():
        return {"id": USER_ID, "username": "dev"}

    def _fake_service():
        return CopilotService(fake_db)

    app.dependency_overrides[require_jwt_user] = _fake_user
    app.dependency_overrides[_copilot_service] = _fake_service

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


def test_create_conversation_requires_auth(fake_db):
    app = FastAPI()
    app.include_router(copilot_router)
    app.dependency_overrides[_copilot_service] = lambda: CopilotService(fake_db)
    with TestClient(app) as client:
        response = client.post(
            "/api/copilot/conversations",
            json={"execution_id": EXECUTION_ID, "repository_id": REPO_ID},
        )
    assert response.status_code == 401


def test_create_and_ask_sse_stream(copilot_client):
    create_resp = copilot_client.post(
        "/api/copilot/conversations",
        json={"execution_id": EXECUTION_ID, "repository_id": REPO_ID},
        headers={"Authorization": "Bearer test-token"},
    )
    assert create_resp.status_code == 200
    conversation_id = create_resp.json()["conversation_id"]

    with copilot_client.stream(
        "POST",
        f"/api/copilot/conversations/{conversation_id}/ask",
        json={
            "question": "What evidence led to this conclusion?",
            "question_type": "what_evidence",
        },
        headers={"Authorization": "Bearer test-token"},
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "event: node_started" in body
    assert "event: done" in body
    assert "event: response_chunk" in body

    checkpoint = copilot_client.get(
        f"/api/copilot/conversations/{conversation_id}",
        headers={"Authorization": "Bearer test-token"},
    )
    assert checkpoint.status_code == 200
    data = checkpoint.json()
    assert data["question_type"] == "what_evidence"
    assert data["response_text"]
    assert data["checkpoint_version"] >= 1
