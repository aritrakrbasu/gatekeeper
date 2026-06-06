import pytest

from peil.config import get_aril_settings
from peil.models.enums import (
    CaptureEventType,
    ExecutionType,
    GraphNodeType,
    SubjectType,
)
from peil.models.events import CaptureEvent
from peil.models.execution import PeilExecutionCreate
from peil.models.graph import DecisionGraphCreate, GraphMetadata, GraphNode
from peil.models.subject import PeilSubjectCreate, SubjectRef
from peil.store.capture_event_repository import CaptureEventRepository
from peil.store.evidence_repository import EvidenceRepository, INLINE_PREFIX
from peil.store.execution_repository import ExecutionRepository
from peil.store.graph_repository import GraphRepository
from peil.store.subject_repository import SubjectRepository


def _subject_ref() -> SubjectRef:
    return SubjectRef(type=SubjectType.MR, id="42", repository_id="82576405")


def _execution_create(execution_id: str, task_id: str) -> PeilExecutionCreate:
    return PeilExecutionCreate(
        execution_id=execution_id,
        task_id=task_id,
        execution_type=ExecutionType.MR_REVIEW,
        repository_id="82576405",
        subject_ref=_subject_ref(),
        subject_id="mr:42:82576405",
        objective="Review MR 42",
    )


@pytest.mark.asyncio
async def test_execution_repository_create_and_lookup(fake_db):
    repo = ExecutionRepository(fake_db)
    created = await repo.create(_execution_create("exec-a", "task-a"))
    assert created.execution_id == "exec-a"
    assert created.task_id == "task-a"

    by_exec = await repo.get_by_execution_id("exec-a")
    by_task = await repo.get_by_task_id("task-a")
    assert by_exec is not None
    assert by_task is not None
    assert by_exec.execution_id != by_task.task_id


@pytest.mark.asyncio
async def test_subject_repository_upsert_and_register(fake_db):
    repo = SubjectRepository(fake_db)
    subject = await repo.upsert(
        PeilSubjectCreate(
            subject_id="mr:42:82576405",
            repository_id="82576405",
            subject_ref=_subject_ref(),
            display_name="MR !42",
        )
    )
    assert subject.execution_count == 0

    updated = await repo.register_execution("mr:42:82576405", "exec-1")
    assert updated is not None
    assert updated.latest_execution_id == "exec-1"
    assert "exec-1" in updated.execution_ids
    assert updated.execution_count == 1

    found = await repo.find_by_ref("82576405", _subject_ref())
    assert found is not None
    assert found.subject_id == "mr:42:82576405"


@pytest.mark.asyncio
async def test_capture_event_repository_append_and_list(fake_db):
    repo = CaptureEventRepository(fake_db)
    events = [
        CaptureEvent(
            execution_id="exec-1",
            task_id="task-1",
            event_type=CaptureEventType.EXECUTION_STARTED,
            sequence=1,
            payload={"objective": "x"},
        ),
        CaptureEvent(
            execution_id="exec-1",
            task_id="task-1",
            event_type=CaptureEventType.PLAN_EMITTED,
            sequence=2,
            payload={"explanation": "plan"},
        ),
    ]
    count = await repo.append_events(events)
    assert count == 2

    loaded = await repo.list_by_execution_id("exec-1")
    assert len(loaded) == 2
    assert loaded[0].sequence == 1
    assert loaded[1].event_type == CaptureEventType.PLAN_EMITTED


@pytest.mark.asyncio
async def test_graph_repository_insert_with_metadata(fake_db):
    repo = GraphRepository(fake_db)
    meta = GraphMetadata(
        root_node_ids=["root"],
        terminal_node_ids=["out"],
        outcome_node_ids=["out"],
        graph_revision=0,
    )
    graph = await repo.insert(
        DecisionGraphCreate(
            graph_id="graph-1",
            execution_id="exec-1",
            task_id="task-1",
            repository_id="82576405",
            nodes=[
                GraphNode(node_id="root", type=GraphNodeType.PLAN_STRATEGY),
                GraphNode(node_id="out", type=GraphNodeType.OUTCOME),
            ],
            metadata=meta,
            graph_version=1,
            builder_version="graph_builder_v0",
        )
    )
    assert graph.graph_version == 1
    assert graph.metadata.root_node_ids == ["root"]
    assert graph.metadata.outcome_node_ids == ["out"]
    assert graph.graph_hash is not None

    loaded = await repo.get_by_execution_id("exec-1")
    assert loaded is not None
    assert loaded.graph_id == "graph-1"


@pytest.mark.asyncio
async def test_evidence_repository_inline_store_and_resolve(fake_db):
    repo = EvidenceRepository(fake_db)
    ref = await repo.store(
        execution_id="exec-1",
        payload=b"tool result payload",
        content_type="text/plain",
    )
    assert ref.startswith(INLINE_PREFIX)
    text = await repo.resolve(ref)
    assert text == "tool result payload"

    settings = get_aril_settings()
    blobs = fake_db[settings.collection_evidence_blobs].docs
    assert len(blobs) == 1
    assert blobs[0]["content_hash"] in ref


@pytest.mark.asyncio
async def test_capture_event_repository_list_paginated(fake_db):
    repo = CaptureEventRepository(fake_db)
    events = [
        CaptureEvent(
            execution_id="exec-paginate",
            task_id="task-1",
            event_type=CaptureEventType.EXECUTION_STARTED,
            sequence=i,
            payload={"n": i},
        )
        for i in range(1, 8)
    ]
    await repo.append_events(events)

    page1, total = await repo.list_paginated("exec-paginate", offset=0, limit=3)
    page2, _ = await repo.list_paginated("exec-paginate", offset=3, limit=3)

    assert total == 7
    assert [e.sequence for e in page1] == [1, 2, 3]
    assert [e.sequence for e in page2] == [4, 5, 6]
    assert await repo.count_by_execution_id("exec-paginate") == 7


@pytest.mark.asyncio
async def test_execution_repository_list_by_subject_id_paginated(fake_db):
    exec_repo = ExecutionRepository(fake_db)
    subject_id = "mr:42:82576405"
    for idx in range(5):
        await exec_repo.create(
            _execution_create(f"exec-{idx}", f"task-{idx}").model_copy(
                update={"subject_id": subject_id}
            )
        )

    items, total = await exec_repo.list_by_subject_id_paginated(
        subject_id, "82576405", offset=0, limit=2
    )
    assert total == 5
    assert len(items) == 2
    assert items[0].execution_id == "exec-4"
