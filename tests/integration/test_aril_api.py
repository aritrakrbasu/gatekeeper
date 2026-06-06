"""Integration tests for ARIL Execution Explorer APIs."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from peil.api.auth import require_jwt_user
from peil.api.explorer import ExecutionExplorerService
from peil.api.router import _explorer, aril_router
from peil.config import get_aril_settings
from peil.graph.builder import GraphBuilder
from peil.graph.fixtures import mr_review_capture_events, mr_review_execution
from peil.models.enums import ExecutionSource, ExecutionType
from peil.models.execution import PeilExecutionCreate
from peil.models.subject import PeilSubjectCreate, SubjectRef, SubjectType
from peil.store.capture_event_repository import CaptureEventRepository
from peil.store.evidence_repository import EvidenceRepository
from peil.store.execution_repository import ExecutionRepository
from peil.store.subject_repository import SubjectRepository


EXECUTION_ID = "exec-api-mr-42"
SUBJECT_ID = "mr:42:82576405"
REPO_ID = "82576405"
USER_ID = "user-1"


async def _seed_aril_explorer_data(fake_db) -> None:
    fake_db["connected_repositories"].docs.append(
        {
            "user_id": USER_ID,
            "id": REPO_ID,
            "name": "gatekeeper",
        }
    )

    subject_repo = SubjectRepository(fake_db)
    await subject_repo.upsert(
        PeilSubjectCreate(
            subject_id=SUBJECT_ID,
            repository_id=REPO_ID,
            subject_ref=SubjectRef(type=SubjectType.MR, id="42", repository_id=REPO_ID),
            display_name="MR !42",
        )
    )

    execution = mr_review_execution(EXECUTION_ID)
    exec_repo = ExecutionRepository(fake_db)
    await exec_repo.create(
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
    await subject_repo.register_execution(SUBJECT_ID, EXECUTION_ID)

    events = mr_review_capture_events(EXECUTION_ID)
    await CaptureEventRepository(fake_db).append_events(events)

    evidence_repo = EvidenceRepository(fake_db)
    for ref_suffix, payload in [
        ("abc123", b'{"cloned": true}'),
        ("def456", b'{"findings": 2}'),
        ("ghi789", b'{"comment_id": 99}'),
    ]:
        await evidence_repo._persist_inline_blob(
            content_hash=ref_suffix,
            execution_id=EXECUTION_ID,
            payload=payload,
            content_type="application/json",
            metadata={"execution_id": EXECUTION_ID},
        )

    builder = GraphBuilder(fake_db)
    await builder.build_and_persist(EXECUTION_ID)

    updated = await exec_repo.get_by_execution_id(EXECUTION_ID)
    graph = await builder._graph_repo.get_by_execution_id(EXECUTION_ID)
    if updated and graph:
        updated.graph_id = graph.graph_id
        await exec_repo.upsert(updated)


@pytest.fixture
async def aril_client(fake_db):
    get_aril_settings.cache_clear()
    await _seed_aril_explorer_data(fake_db)

    app = FastAPI()
    app.include_router(aril_router)

    def _fake_user():
        return {"id": USER_ID, "username": "dev"}

    def _fake_explorer():
        return ExecutionExplorerService(fake_db)

    app.dependency_overrides[require_jwt_user] = _fake_user
    app.dependency_overrides[_explorer] = _fake_explorer

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    get_aril_settings.cache_clear()


def test_get_execution_requires_auth(fake_db):
    app = FastAPI()
    app.include_router(aril_router)
    app.dependency_overrides[_explorer] = lambda: ExecutionExplorerService(fake_db)
    with TestClient(app) as client:
        response = client.get(f"/api/aril/executions/{EXECUTION_ID}")
    assert response.status_code == 401


def test_get_execution_success(aril_client):
    response = aril_client.get(
        f"/api/aril/executions/{EXECUTION_ID}",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["execution_id"] == EXECUTION_ID
    assert body["repository_id"] == REPO_ID
    assert body["graph_summary"] is not None
    assert body["graph_summary"]["node_count"] >= 10


def test_list_events_pagination(aril_client):
    response = aril_client.get(
        f"/api/aril/executions/{EXECUTION_ID}/events",
        params={"page": 1, "page_size": 5},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 5
    assert body["pagination"]["total"] == 13
    assert body["pagination"]["has_more"] is True
    assert body["items"][0]["sequence"] == 1


def test_get_graph_with_metadata_and_evidence(aril_client):
    response = aril_client.get(
        f"/api/aril/executions/{EXECUTION_ID}/graph",
        params={"include_evidence": True, "evidence_max_chars": 256},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["execution_id"] == EXECUTION_ID
    assert body["metadata"]["root_node_ids"]
    assert body["metadata"]["outcome_node_ids"] == ["outcome:terminal"]
    assert body["graph_hash"]
    assert body["builder_version"] == "graph_builder_v1"

    tool_results = [n for n in body["nodes"] if n["type"] == "tool_result"]
    assert tool_results
    node_with_evidence = next(n for n in tool_results if n["evidence_refs"])
    assert node_with_evidence["evidence"]
    assert node_with_evidence["evidence"][0]["ref"].startswith("inline:")


def test_get_subject(aril_client):
    encoded = "mr%3A42%3A82576405"
    response = aril_client.get(
        f"/api/aril/subjects/{encoded}",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["subject_id"] == SUBJECT_ID
    assert EXECUTION_ID in body["execution_ids"]


def test_get_subject_timeline(aril_client):
    encoded = "mr%3A42%3A82576405"
    response = aril_client.get(
        f"/api/aril/subjects/{encoded}/timeline",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["subject_id"] == SUBJECT_ID
    assert len(body["items"]) == 1
    assert body["items"][0]["execution_id"] == EXECUTION_ID


async def test_repository_access_denied(fake_db):
    get_aril_settings.cache_clear()

    execution = mr_review_execution("exec-denied")
    exec_repo = ExecutionRepository(fake_db)
    await exec_repo.create(
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

    app = FastAPI()
    app.include_router(aril_router)
    app.dependency_overrides[require_jwt_user] = lambda: {"id": "other-user"}
    app.dependency_overrides[_explorer] = lambda: ExecutionExplorerService(fake_db)

    with TestClient(app) as client:
        response = client.get(
            f"/api/aril/executions/{execution.execution_id}",
            headers={"Authorization": "Bearer test-token"},
        )
    assert response.status_code == 403
