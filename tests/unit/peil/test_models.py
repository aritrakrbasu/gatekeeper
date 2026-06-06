from datetime import datetime, timezone

from peil.models.enums import (
    ExecutionSource,
    ExecutionStatus,
    ExecutionType,
    GraphNodeType,
    SubjectType,
)
from peil.models.execution import PeilExecution, PeilExecutionCreate
from peil.models.graph import DecisionGraphCreate, GraphMetadata, GraphNode
from peil.models.subject import PeilSubjectCreate, SubjectRef, build_subject_id


def test_execution_id_distinct_from_task_id():
    create = PeilExecutionCreate(
        execution_id="exec-abc",
        task_id="task-xyz",
        execution_type=ExecutionType.MR_REVIEW,
        repository_id="82576405",
        subject_ref=SubjectRef(type=SubjectType.MR, id="42"),
        subject_id="mr:42:82576405",
        objective="Review MR",
    )
    assert create.execution_id != create.task_id


def test_build_subject_id_includes_repository():
    ref = SubjectRef(type=SubjectType.MR, id="42", repository_id="82576405")
    assert build_subject_id(ref) == "mr:42:82576405"


def test_graph_metadata_topology_fields():
    meta = GraphMetadata(
        root_node_ids=["n1"],
        terminal_node_ids=["n9"],
        outcome_node_ids=["n9"],
        node_count=2,
        edge_count=1,
    )
    graph = DecisionGraphCreate(
        graph_id="g1",
        execution_id="exec-1",
        task_id="task-1",
        repository_id="82576405",
        nodes=[
            GraphNode(node_id="n1", type=GraphNodeType.PLAN_STRATEGY),
            GraphNode(node_id="n9", type=GraphNodeType.OUTCOME),
        ],
        metadata=meta,
        graph_version=2,
        builder_version="graph_builder_v1",
    )
    doc = graph.model_dump(mode="json")
    assert doc["graph_version"] == 2
    assert doc["builder_version"] == "graph_builder_v1"
    assert doc["metadata"]["root_node_ids"] == ["n1"]
    assert doc["metadata"]["outcome_node_ids"] == ["n9"]


def test_execution_to_mongo_roundtrip():
    now = datetime.now(timezone.utc)
    execution = PeilExecution(
        execution_id="exec-1",
        task_id="task-1",
        execution_type=ExecutionType.MR_REVIEW,
        execution_source=ExecutionSource.WORKFLOW_ENGINE,
        repository_id="82576405",
        subject_ref=SubjectRef(type=SubjectType.MR, id="42"),
        subject_id="mr:42:82576405",
        objective="Review",
        partition_key="202606",
        status=ExecutionStatus.CAPTURING,
        created_at=now,
        updated_at=now,
    )
    doc = execution.to_mongo()
    assert doc["execution_id"] == "exec-1"
    assert doc["task_id"] == "task-1"


def test_subject_create_model():
    subject = PeilSubjectCreate(
        subject_id="mr:42:82576405",
        repository_id="82576405",
        subject_ref=SubjectRef(type=SubjectType.MR, id="42"),
        display_name="MR !42",
    )
    assert subject.subject_ref.type == SubjectType.MR
