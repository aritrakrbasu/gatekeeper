"""Tests for Principal Review infrastructure fixes."""

from __future__ import annotations

from datetime import datetime

import pytest

from peil.capture.bus import ExecutionCaptureBus
from peil.config import get_aril_settings
from peil.models.enums import CaptureEventType, ExecutionType, SubjectType
from peil.models.events import CaptureEvent
from peil.models.execution import PeilExecutionCreate
from peil.models.subject import PeilSubjectCreate, SubjectRef
from peil.store.capture_event_repository import CaptureEventRepository
from peil.store.evidence_repository import EvidenceRepository, GRIDFS_PREFIX, INLINE_PREFIX
from peil.store.execution_repository import ExecutionRepository
from peil.store.indexes import get_aril_index_specs, get_gridfs_index_specs
from peil.store.subject_repository import SubjectRepository


def _subject_ref() -> SubjectRef:
    return SubjectRef(type=SubjectType.MR, id="42", repository_id="82576405")


@pytest.fixture
def enabled_capture(monkeypatch):
    monkeypatch.setenv("ARIL_CAPTURE_ENABLED", "true")
    get_aril_settings.cache_clear()


@pytest.mark.asyncio
async def test_evidence_resolves_after_process_restart(fake_db):
    """Simulate restart: new repository instance, empty cache, same database."""
    writer = EvidenceRepository(fake_db)
    ref = await writer.store(
        execution_id="exec-1",
        payload=b"persistent tool output",
        content_type="text/plain",
    )
    assert ref.startswith(INLINE_PREFIX)

    reader = EvidenceRepository(fake_db)
    assert ref not in reader._inline_cache
    text = await reader.resolve(ref)
    assert text == "persistent tool output"


@pytest.mark.asyncio
async def test_resumed_execution_sequence_continuity(fake_db, enabled_capture):
    event_repo = CaptureEventRepository(fake_db)
    existing = [
        CaptureEvent(
            execution_id="exec-resume",
            task_id="task-1",
            event_type=CaptureEventType.EXECUTION_STARTED,
            sequence=1,
            payload={},
        ),
        CaptureEvent(
            execution_id="exec-resume",
            task_id="task-1",
            event_type=CaptureEventType.PLAN_EMITTED,
            sequence=2,
            payload={},
        ),
        CaptureEvent(
            execution_id="exec-resume",
            task_id="task-1",
            event_type=CaptureEventType.STEP_STARTED,
            sequence=3,
            payload={},
        ),
    ]
    await event_repo.append_events(existing)

    bus = await ExecutionCaptureBus.open(
        task_id="task-1",
        repository_id="82576405",
        execution_id="exec-resume",
        event_repository=event_repo,
    )
    assert isinstance(bus, ExecutionCaptureBus)

    bus.emit(bus.build_envelope(CaptureEventType.STEP_COMPLETED, {"step_id": "s1"}))
    buffered = bus.get_buffer()
    assert len(buffered) == 1
    assert buffered[0].sequence == 4

    await bus.flush()
    loaded = await event_repo.list_by_execution_id("exec-resume")
    assert [e.sequence for e in loaded] == [1, 2, 3, 4]


@pytest.mark.asyncio
async def test_duplicate_execution_registration_does_not_inflate_count(fake_db):
    repo = SubjectRepository(fake_db)
    await repo.upsert(
        PeilSubjectCreate(
            subject_id="mr:42:82576405",
            repository_id="82576405",
            subject_ref=_subject_ref(),
        )
    )

    first = await repo.register_execution("mr:42:82576405", "exec-1")
    second = await repo.register_execution("mr:42:82576405", "exec-1")

    assert first is not None
    assert second is not None
    assert first.execution_count == 1
    assert second.execution_count == 1
    assert second.execution_ids.count("exec-1") == 1


def test_subject_query_index_aligns_with_find_by_subject():
    settings = get_aril_settings()
    specs = get_aril_index_specs()
    execution_specs = [s for s in specs if s[0] == settings.collection_executions]
    ref_index = next(
        s for s in execution_specs if s[3].get("name") == "idx_repo_subject_ref_created"
    )
    keys = [k for k, _ in ref_index[1]]
    assert keys == [
        "repository_id",
        "subject_ref.type",
        "subject_ref.id",
        "created_at",
    ]


@pytest.mark.asyncio
async def test_find_by_subject_uses_subject_ref_query_path(fake_db):
    exec_repo = ExecutionRepository(fake_db)
    subject_ref = _subject_ref()
    for idx, execution_id in enumerate(("exec-1", "exec-2"), start=1):
        await exec_repo.create(
            PeilExecutionCreate(
                execution_id=execution_id,
                task_id=f"task-{idx}",
                execution_type=ExecutionType.MR_REVIEW,
                repository_id="82576405",
                subject_ref=subject_ref,
                subject_id="mr:42:82576405",
                objective=f"Review {idx}",
            )
        )

    results = await exec_repo.find_by_subject("82576405", subject_ref)
    assert len(results) == 2
    assert results[0].execution_id == "exec-2"
    assert results[1].execution_id == "exec-1"


class _FakeGridFSBucket:
    """Minimal GridFS stand-in for unit tests without Motor."""

    def __init__(self, db, bucket_name: str) -> None:
        self._files = db[f"{bucket_name}.files"]
        self._counter = 0

    async def upload_from_stream(self, filename, source, metadata):
        self._counter += 1
        file_id = f"file-{self._counter}"
        self._files.docs.append(
            {
                "_id": file_id,
                "filename": filename,
                "metadata": metadata,
            }
        )
        return file_id


@pytest.mark.asyncio
async def test_gridfs_dedup_returns_same_ref(fake_db, monkeypatch):
    monkeypatch.setenv("ARIL_EVIDENCE_INLINE_MAX_BYTES", "16")
    get_aril_settings.cache_clear()
    settings = get_aril_settings()

    repo = EvidenceRepository(fake_db)
    monkeypatch.setattr(
        repo,
        "_bucket",
        lambda db: _FakeGridFSBucket(db, settings.evidence_gridfs_bucket),
    )

    payload = b"x" * 64
    ref1 = await repo.store(execution_id="exec-1", payload=payload)
    ref2 = await repo.store(execution_id="exec-2", payload=payload)

    assert ref1.startswith(GRIDFS_PREFIX)
    assert ref1 == ref2

    files = fake_db[f"{settings.evidence_gridfs_bucket}.files"].docs
    assert len(files) == 1


def test_gridfs_metadata_indexes_defined():
    specs = get_gridfs_index_specs()
    names = {s[3]["name"] for s in specs}
    assert "idx_evidence_execution_id" in names
    assert "uniq_evidence_content_hash" in names


@pytest.mark.asyncio
async def test_update_fields_stores_datetime_updated_at(fake_db):
    exec_repo = ExecutionRepository(fake_db)
    subject_ref = _subject_ref()
    created = await exec_repo.create(
        PeilExecutionCreate(
            execution_id="exec-ts",
            task_id="task-ts",
            execution_type=ExecutionType.MR_REVIEW,
            repository_id="82576405",
            subject_ref=subject_ref,
            subject_id="mr:42:82576405",
            objective="timestamp test",
        )
    )
    await exec_repo.update_fields("exec-ts", {"status": "complete"})

    collection = fake_db[get_aril_settings().collection_executions]
    stored = collection.docs[0]
    assert isinstance(stored["updated_at"], datetime)
    assert stored["updated_at"] != created.updated_at
