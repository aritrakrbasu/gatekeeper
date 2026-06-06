"""Unit tests for GraphBuilder determinism and topology rules."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from peil.config import get_aril_settings
from peil.graph.builder import GraphBuilder
from peil.graph.fixtures import mr_review_capture_events, mr_review_execution
from peil.graph.hashing import compute_graph_hash
from peil.models.enums import GraphEdgeRelation, GraphNodeType
from peil.store.graph_repository import GraphRepository


def _builder() -> GraphBuilder:
    return GraphBuilder()


def test_build_mr_review_graph_topology():
    execution = mr_review_execution()
    events = mr_review_capture_events(execution.execution_id)
    builder = _builder()

    graph_create = builder.build_from_events(events, execution)
    node_types = {n.node_id: n.type for n in graph_create.nodes}
    edge_relations = {e.relation for e in graph_create.edges}

    assert node_types[f"execution:{execution.execution_id}"] == GraphNodeType.EXECUTION
    assert node_types["model_turn:0002"] == GraphNodeType.MODEL_TURN
    assert node_types["plan:0"] == GraphNodeType.PLAN
    assert node_types["plan_step:0:clone"] == GraphNodeType.PLAN_STEP
    assert node_types["tool_call:0004"] == GraphNodeType.TOOL_CALL
    assert node_types["tool_result:0005"] == GraphNodeType.TOOL_RESULT
    assert node_types["reflection:0006"] == GraphNodeType.REFLECTION
    assert node_types["outcome:terminal"] == GraphNodeType.OUTCOME

    assert GraphEdgeRelation.TRIGGERS in edge_relations
    assert GraphEdgeRelation.PRODUCES in edge_relations
    assert GraphEdgeRelation.DEPENDS_ON in edge_relations
    assert GraphEdgeRelation.VALIDATES in edge_relations

    meta = graph_create.metadata
    assert meta.root_node_ids == [f"execution:{execution.execution_id}"]
    assert "outcome:terminal" in meta.outcome_node_ids
    assert "outcome:terminal" in meta.terminal_node_ids
    assert meta.node_count == len(graph_create.nodes)
    assert meta.edge_count == len(graph_create.edges)
    assert graph_create.graph_version >= 1
    assert graph_create.builder_version == "graph_builder_v1"


def test_build_is_deterministic():
    execution = mr_review_execution("exec-deterministic")
    events = mr_review_capture_events("exec-deterministic")
    builder = _builder()

    g1 = builder.build_from_events(events, execution)
    g2 = builder.build_from_events(events, execution)

    assert compute_graph_hash(g1) == compute_graph_hash(g2)
    assert [n.node_id for n in g1.nodes] == [n.node_id for n in g2.nodes]
    assert [e.edge_id for e in g1.edges] == [e.edge_id for e in g2.edges]


def test_tool_result_carries_evidence_ref():
    execution = mr_review_execution()
    events = mr_review_capture_events(execution.execution_id)
    graph = _builder().build_from_events(events, execution)
    tool_result = next(n for n in graph.nodes if n.node_id == "tool_result:0005")
    assert tool_result.evidence_refs == ["inline:abc123"]


@pytest.mark.asyncio
async def test_build_and_persist_idempotent(fake_db):
    execution = mr_review_execution("exec-persist-01")
    events = mr_review_capture_events("exec-persist-01")

    from peil.store.capture_event_repository import CaptureEventRepository
    from peil.store.execution_repository import ExecutionRepository
    from peil.models.execution import PeilExecutionCreate
    from peil.models.enums import ExecutionSource, ExecutionType
    from peil.models.subject import SubjectRef, SubjectType

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
    event_repo = CaptureEventRepository(fake_db)
    await event_repo.append_events(events)

    builder = GraphBuilder(fake_db)
    first = await builder.build_and_persist(execution.execution_id)
    second = await builder.build_and_persist(execution.execution_id)

    assert first.created is True
    assert second.created is False
    assert first.graph_hash == second.graph_hash
    assert first.graph.graph_id == second.graph.graph_id

    graphs = fake_db[get_aril_settings().collection_decision_graphs].docs
    assert len(graphs) == 1


def test_sample_graph_fixture_written():
    """Ensure sample MR graph JSON exists for documentation."""
    from peil.config import get_aril_settings

    execution = mr_review_execution()
    events = mr_review_capture_events(execution.execution_id)
    graph_create = _builder().build_from_events(events, execution)
    graph_hash = compute_graph_hash(graph_create)

    sample = {
        "execution_id": execution.execution_id,
        "task_id": execution.task_id,
        "repository_id": execution.repository_id,
        "graph_version": graph_create.graph_version,
        "builder_version": graph_create.builder_version,
        "graph_hash": graph_hash,
        "status": graph_create.status,
        "metadata": graph_create.metadata.model_dump(mode="json"),
        "nodes": [n.model_dump(mode="json") for n in graph_create.nodes],
        "edges": [e.model_dump(mode="json") for e in graph_create.edges],
    }

    out_path = (
        Path(__file__).resolve().parents[4]
        / "peil"
        / "graph"
        / "samples"
        / "mr_review_sample_graph.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(sample, indent=2), encoding="utf-8")

    assert out_path.exists()
    assert sample["metadata"]["node_count"] >= 10

