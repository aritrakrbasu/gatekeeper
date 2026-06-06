"""Unit tests for MR execution resolver."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from copilot.resolution.mr_execution import resolve_mr_execution
from peil.graph.builder import GraphBuilder
from peil.graph.fixtures import mr_review_capture_events, mr_review_execution
from peil.models.enums import ExecutionSource, ExecutionType, SubjectType
from peil.models.execution import PeilExecutionCreate
from peil.models.subject import PeilSubjectCreate, SubjectRef
from peil.store.capture_event_repository import CaptureEventRepository
from peil.store.evidence_repository import EvidenceRepository
from peil.store.execution_repository import ExecutionRepository
from peil.store.subject_repository import SubjectRepository

REPO_ID = "82576405"
USER_ID = "user-1"
OTHER_USER = "user-2"
MR_IID = 42
EXECUTION_ID = "exec-mr-resolver-42"
SUBJECT_ID = "mr:42:82576405"


async def _grant_repo_access(fake_db, user_id: str = USER_ID) -> None:
    fake_db["connected_repositories"].docs.append(
        {"user_id": user_id, "id": REPO_ID, "name": "gatekeeper"}
    )


async def _seed_subject_and_execution(
    fake_db,
    *,
    execution_id: str = EXECUTION_ID,
    with_graph: bool = True,
) -> None:
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
    await SubjectRepository(fake_db).register_execution(SUBJECT_ID, execution_id)

    if with_graph:
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


@pytest.mark.asyncio
async def test_resolver_success(fake_db):
    await _grant_repo_access(fake_db)
    await _seed_subject_and_execution(fake_db)

    link = await resolve_mr_execution(REPO_ID, MR_IID, USER_ID, db=fake_db)

    assert link.execution_id == EXECUTION_ID
    assert link.subject_id == SUBJECT_ID
    assert link.graph_id is not None
    assert link.copilot_ready is True
    assert link.status


@pytest.mark.asyncio
async def test_resolver_missing_execution(fake_db):
    await _grant_repo_access(fake_db)

    with pytest.raises(HTTPException) as exc:
        await resolve_mr_execution(REPO_ID, MR_IID, USER_ID, db=fake_db)

    assert exc.value.status_code == 404
    assert exc.value.detail == "no_captured_review"


@pytest.mark.asyncio
async def test_resolver_missing_graph(fake_db):
    await _grant_repo_access(fake_db)
    await _seed_subject_and_execution(fake_db, with_graph=False)

    with pytest.raises(HTTPException) as exc:
        await resolve_mr_execution(REPO_ID, MR_IID, USER_ID, db=fake_db)

    assert exc.value.status_code == 404
    assert exc.value.detail == "no_captured_review"


@pytest.mark.asyncio
async def test_resolver_access_denied(fake_db):
    await _grant_repo_access(fake_db, user_id=USER_ID)
    await _seed_subject_and_execution(fake_db)

    with pytest.raises(HTTPException) as exc:
        await resolve_mr_execution(REPO_ID, MR_IID, OTHER_USER, db=fake_db)

    assert exc.value.status_code == 403
