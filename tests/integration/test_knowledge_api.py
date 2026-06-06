"""Integration tests for Knowledge HTTP API."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from knowledge.api.router import _knowledge_service, knowledge_router
from knowledge.api.service import KnowledgeService
from knowledge.models.enums import AssertionStatus, AssertionType
from peil.api.auth import require_jwt_user
from peil.graph.builder import GraphBuilder
from peil.graph.fixtures import mr_review_capture_events, mr_review_execution
from peil.models.enums import ExecutionSource, ExecutionType
from peil.models.execution import PeilExecutionCreate
from peil.store.capture_event_repository import CaptureEventRepository
from peil.store.execution_repository import ExecutionRepository

EXECUTION_ID = "exec-knowledge-api"
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
    await GraphBuilder(fake_db).build_and_persist(EXECUTION_ID)


@pytest.fixture
async def knowledge_client(fake_db):
    await _seed(fake_db)

    app = FastAPI()
    app.include_router(knowledge_router)

    def _fake_user():
        return {"id": USER_ID, "username": "dev"}

    app.dependency_overrides[require_jwt_user] = _fake_user
    app.dependency_overrides[_knowledge_service] = lambda: KnowledgeService(fake_db)

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


def test_create_assertion_proposed_not_accepted(knowledge_client):
    response = knowledge_client.post(
        "/api/knowledge/assertions",
        json={
            "repository_id": REPO_ID,
            "source_execution_id": EXECUTION_ID,
            "type": AssertionType.BUSINESS_RULE.value,
            "statement": "MR reviews must inspect schema impact before commenting.",
            "evidence_refs": ["inline:abc123"],
            "confidence": 0.7,
            "graph_id": "graph-test",
            "replay_reference": f"replay:{EXECUTION_ID}",
        },
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == AssertionStatus.PROPOSED.value
    assertion_id = body["assertion_id"]

    accept = knowledge_client.post(
        f"/api/knowledge/assertions/{assertion_id}/accept",
        json={"reason": "Confirmed against replay"},
        headers={"Authorization": "Bearer test-token"},
    )
    assert accept.status_code == 200
    assert accept.json()["status"] == AssertionStatus.ACCEPTED.value
    assert len(accept.json()["audit_trail"]) == 2


def test_list_and_reject_assertions(knowledge_client):
    create = knowledge_client.post(
        "/api/knowledge/assertions",
        json={
            "repository_id": REPO_ID,
            "source_execution_id": EXECUTION_ID,
            "type": AssertionType.REVIEW_CORRECTION.value,
            "statement": "Finding severity should reference tool output hashes.",
            "confidence": 0.55,
        },
        headers={"Authorization": "Bearer test-token"},
    )
    assertion_id = create.json()["assertion_id"]

    listing = knowledge_client.get(
        "/api/knowledge/assertions",
        params={"repository_id": REPO_ID, "status": "proposed"},
        headers={"Authorization": "Bearer test-token"},
    )
    assert listing.status_code == 200
    assert listing.json()["total"] >= 1

    rejected = knowledge_client.post(
        f"/api/knowledge/assertions/{assertion_id}/reject",
        json={"reason": "Needs more evidence"},
        headers={"Authorization": "Bearer test-token"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == AssertionStatus.REJECTED.value


def test_create_requires_auth(fake_db):
    app = FastAPI()
    app.include_router(knowledge_router)
    app.dependency_overrides[_knowledge_service] = lambda: KnowledgeService(fake_db)
    with TestClient(app) as client:
        response = client.post(
            "/api/knowledge/assertions",
            json={
                "repository_id": REPO_ID,
                "source_execution_id": EXECUTION_ID,
                "type": "business_rule",
                "statement": "test",
            },
        )
    assert response.status_code == 401
