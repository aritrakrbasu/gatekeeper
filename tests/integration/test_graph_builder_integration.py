"""Integration tests — capture events → GraphBuilder → peil_decision_graphs."""

from __future__ import annotations

import pytest

from peil.graph.builder import GraphBuilder
from peil.graph.fixtures import mr_review_capture_events, mr_review_execution
from peil.graph.hashing import compute_graph_hash
from peil.models.enums import CaptureEventType, ExecutionSource, ExecutionType, GraphNodeType
from peil.models.execution import PeilExecutionCreate
from peil.store.capture_event_repository import CaptureEventRepository
from peil.store.execution_repository import ExecutionRepository
from peil.store.graph_repository import GraphRepository


@pytest.mark.asyncio
async def test_end_to_end_mr_review_graph_build(fake_db):
    execution = mr_review_execution("exec-mr-integration")
    events = mr_review_capture_events("exec-mr-integration")

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
    await CaptureEventRepository(fake_db).append_events(events)

    builder = GraphBuilder(fake_db)
    result = await builder.build_and_persist(execution.execution_id)

    assert result.created is True
    assert result.graph.metadata.node_count >= 10
    assert result.graph.metadata.outcome_node_ids == ["outcome:terminal"]
    assert result.graph.graph_hash is not None

    loaded = await GraphRepository(fake_db).get_by_execution_id(execution.execution_id)
    assert loaded is not None
    assert loaded.graph_hash == result.graph_hash

    node_type_values = {n.type.value for n in loaded.nodes}
    assert "execution" in node_type_values
    assert "plan" in node_type_values
    assert "plan_step" in node_type_values
    assert "tool_call" in node_type_values
    assert "tool_result" in node_type_values
    assert "reflection" in node_type_values
    assert "outcome" in node_type_values


@pytest.mark.asyncio
async def test_graph_revision_preserved(fake_db):
    execution = mr_review_execution("exec-revision")
    events = mr_review_capture_events("exec-revision")

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
    await CaptureEventRepository(fake_db).append_events(events)

    builder = GraphBuilder(fake_db)
    create = await builder.build(execution.execution_id, graph_revision=2)
    assert create.metadata.graph_revision == 2

    result = await builder.build_and_persist(execution.execution_id, graph_revision=2)
    assert result.graph.metadata.graph_revision == 2
