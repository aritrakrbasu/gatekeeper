"""Integration tests for MR → execution resolution and Copilot create."""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from copilot.api.router import _copilot_service, copilot_router
from copilot.api.service import CopilotService
from copilot.resolution.mr_execution import resolve_mr_execution_response
from peil.api.auth import require_jwt_user
from peil.graph.builder import GraphBuilder
from peil.graph.fixtures import mr_review_capture_events, mr_review_execution
from peil.models.enums import ExecutionSource, ExecutionType, SubjectType
from peil.models.execution import PeilExecutionCreate
from peil.models.subject import PeilSubjectCreate, SubjectRef
from peil.replay.models import ReplayMode
from peil.replay.service import ReasoningReplayService
from peil.store.capture_event_repository import CaptureEventRepository
from peil.store.evidence_repository import EvidenceRepository
from peil.store.execution_repository import ExecutionRepository
from peil.store.subject_repository import SubjectRepository

EXECUTION_ID = "exec-copilot-mr-resolve"
REPO_ID = "82576405"
USER_ID = "user-1"
MR_IID = 42
SUBJECT_ID = "mr:42:82576405"


async def _seed_mr_review(fake_db) -> None:
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
    await SubjectRepository(fake_db).upsert(
        PeilSubjectCreate(
            subject_id=SUBJECT_ID,
            repository_id=REPO_ID,
            subject_ref=SubjectRef(
                type=SubjectType.MR,
                id=str(MR_IID),
                repository_id=REPO_ID,
            ),
            display_name="MR !42",
        )
    )
    await SubjectRepository(fake_db).register_execution(SUBJECT_ID, EXECUTION_ID)
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
async def resolution_client(fake_db):
    await _seed_mr_review(fake_db)

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


@pytest.mark.asyncio
async def test_create_conversation_using_mr_iid(resolution_client):
    response = resolution_client.post(
        "/api/copilot/conversations",
        json={"repository_id": REPO_ID, "mr_iid": MR_IID},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_id"] == EXECUTION_ID
    assert payload["repository_id"] == REPO_ID
    assert payload["conversation_id"]


@pytest.mark.asyncio
async def test_replay_retrieval_succeeds_for_resolved_execution(fake_db):
    await _seed_mr_review(fake_db)

    link = await resolve_mr_execution_response(
        REPO_ID,
        MR_IID,
        USER_ID,
        db=fake_db,
    )
    bundle = await ReasoningReplayService(fake_db).replay(
        link.execution_id,
        mode=ReplayMode.FORENSIC,
        include_evidence=True,
    )
    assert bundle.execution_summary.execution_id == EXECUTION_ID
    assert bundle.graph_id == link.graph_id


@pytest.mark.asyncio
async def test_mr_execution_resolver_endpoint(fake_db):
    await _seed_mr_review(fake_db)

    app = FastAPI()

    @app.get("/api/repositories/{repository_id}/mrs/{mr_iid}/execution")
    async def get_mr_execution(
        repository_id: str,
        mr_iid: int,
        user: dict = Depends(require_jwt_user),
    ):
        return await resolve_mr_execution_response(
            repository_id,
            mr_iid,
            str(user["id"]),
            db=fake_db,
        )

    app.dependency_overrides[require_jwt_user] = lambda: {
        "id": USER_ID,
        "username": "dev",
    }

    with TestClient(app) as client:
        response = client.get(
            f"/api/repositories/{REPO_ID}/mrs/{MR_IID}/execution",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["repository_id"] == REPO_ID
    assert payload["mr_iid"] == MR_IID
    assert payload["subject_id"] == SUBJECT_ID
    assert payload["execution_id"] == EXECUTION_ID
    assert payload["graph_id"] is not None
    assert payload["copilot_ready"] is True


@pytest.mark.asyncio
async def test_create_conversation_rejects_both_sources(resolution_client):
    response = resolution_client.post(
        "/api/copilot/conversations",
        json={
            "repository_id": REPO_ID,
            "mr_iid": MR_IID,
            "execution_id": EXECUTION_ID,
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_conversation_rejects_neither_source(resolution_client):
    response = resolution_client.post(
        "/api/copilot/conversations",
        json={"repository_id": REPO_ID},
    )
    assert response.status_code == 422
