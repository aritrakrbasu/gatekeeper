"""Unit tests for ReasoningReplayService graph walking and replay bundles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from peil.graph.builder import GraphBuilder
from peil.graph.fixtures import mr_review_capture_events, mr_review_execution
from peil.models.enums import GraphNodeType
from peil.replay.models import ReplayMode
from peil.replay.service import ReasoningReplayService, walk_backward_chain
from peil.store.capture_event_repository import CaptureEventRepository
from peil.store.evidence_repository import EvidenceRepository
from peil.store.execution_repository import ExecutionRepository
from peil.store.graph_repository import GraphRepository

SAMPLE_GRAPH_PATH = (
    Path(__file__).resolve().parents[4]
    / "peil"
    / "graph"
    / "samples"
    / "mr_review_sample_graph.json"
)
SAMPLE_REPLAY_PATH = (
    Path(__file__).resolve().parents[4]
    / "peil"
    / "replay"
    / "samples"
    / "mr_review_forensic_replay.json"
)

EXECUTION_ID = "exec-mr-42-sample"


@pytest.fixture
async def mr_graph(fake_db):
    execution = mr_review_execution(EXECUTION_ID)
    exec_repo = ExecutionRepository(fake_db)
    await exec_repo.create(_execution_create_from_fixture(execution))

    events = mr_review_capture_events(EXECUTION_ID)
    await CaptureEventRepository(fake_db).append_events(events)

    for suffix, payload in [
        ("abc123", b'{"cloned": true}'),
        ("def456", b'{"findings": 2}'),
        ("ghi789", b'{"comment_id": 99}'),
    ]:
        await EvidenceRepository(fake_db)._persist_inline_blob(
            content_hash=suffix,
            execution_id=EXECUTION_ID,
            payload=payload,
            content_type="application/json",
            metadata={"execution_id": EXECUTION_ID},
        )

    result = await GraphBuilder(fake_db).build_and_persist(EXECUTION_ID)
    return result.graph


def _execution_create_from_fixture(execution):
    from peil.models.enums import ExecutionSource, ExecutionType
    from peil.models.execution import PeilExecutionCreate

    return PeilExecutionCreate(
        execution_id=execution.execution_id,
        task_id=execution.task_id,
        execution_type=ExecutionType.MR_REVIEW,
        execution_source=ExecutionSource.WORKFLOW_ENGINE,
        repository_id=execution.repository_id,
        subject_ref=execution.subject_ref,
        subject_id=execution.subject_id,
        objective=execution.objective,
    )


@pytest.mark.asyncio
async def test_walk_backward_chain_from_reflection(fake_db, mr_graph):
    nodes = {n.node_id: n for n in mr_graph.nodes}
    incoming = {}
    for edge in mr_graph.edges:
        incoming.setdefault(edge.to_node_id, []).append(
            (edge.from_node_id, edge.relation)
        )

    path = walk_backward_chain("reflection:0006", nodes, incoming)
    visited_ids = [entry[0] for entry in path]

    assert visited_ids[0] == "reflection:0006"
    assert "tool_result:0005" in visited_ids
    assert "tool_call:0004" in visited_ids
    assert "plan_step:0:clone" in visited_ids
    assert "plan:0" in visited_ids
    assert "model_turn:0002" in visited_ids
    assert visited_ids[-1] == f"execution:{EXECUTION_ID}"


@pytest.mark.asyncio
async def test_walk_backward_chain_cycle_protection(fake_db, mr_graph):
    from peil.models.enums import GraphEdgeRelation

    nodes = {n.node_id: n for n in mr_graph.nodes}
    incoming = {}
    for edge in mr_graph.edges:
        incoming.setdefault(edge.to_node_id, []).append(
            (edge.from_node_id, edge.relation)
        )
    incoming["plan:0"].append(
        ("reflection:0006", GraphEdgeRelation.PRODUCES)
    )

    path = walk_backward_chain("reflection:0006", nodes, incoming)
    assert len(path) == len({entry[0] for entry in path})


@pytest.mark.asyncio
async def test_forensic_replay_bundle_topology(fake_db, mr_graph):
    service = ReasoningReplayService(fake_db)
    bundle = await service.replay(EXECUTION_ID, mode=ReplayMode.FORENSIC)

    assert bundle.outcome_node_id == "outcome:terminal"
    assert bundle.mode == ReplayMode.FORENSIC
    assert bundle.narrative is None

    path_types = [step.node_type for step in bundle.graph_path]
    assert path_types[0] == GraphNodeType.EXECUTION.value
    assert GraphNodeType.MODEL_TURN.value in path_types
    assert GraphNodeType.PLAN.value in path_types
    assert path_types[-1] == GraphNodeType.OUTCOME.value

    assert len(bundle.plan_steps) == 3
    assert len(bundle.tool_calls) == 3
    assert len(bundle.tool_results) == 3
    assert len(bundle.reflections) == 3
    assert bundle.outcome.status == "completed"

    step_ids = [s.step_id for s in bundle.plan_steps]
    assert step_ids == ["clone", "analyze", "comment"]


@pytest.mark.asyncio
async def test_narrative_replay_is_deterministic(fake_db, mr_graph):
    service = ReasoningReplayService(fake_db)
    first = await service.replay(EXECUTION_ID, mode=ReplayMode.NARRATIVE)
    second = await service.replay(EXECUTION_ID, mode=ReplayMode.NARRATIVE)

    assert first.model_dump() == second.model_dump()
    assert first.narrative is not None
    assert first.narrative.summary
    assert len(first.narrative.sections) >= 5
    assert first.narrative.sections[-1].title == "Outcome"


@pytest.mark.asyncio
async def test_replay_resolves_evidence_refs(fake_db, mr_graph):
    service = ReasoningReplayService(fake_db)
    bundle = await service.replay(
        EXECUTION_ID,
        mode=ReplayMode.FORENSIC,
        include_evidence=True,
    )

    assert len(bundle.evidence_references) == 3
    refs = {item.ref for item in bundle.evidence_references}
    assert "inline:abc123" in refs
    assert any(item.excerpt for item in bundle.evidence_references)


@pytest.mark.asyncio
async def test_replay_unknown_execution_raises(fake_db):
    service = ReasoningReplayService(fake_db)
    with pytest.raises(HTTPException) as exc:
        await service.replay("missing-exec")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_replay_invalid_outcome_node(fake_db, mr_graph):
    service = ReasoningReplayService(fake_db)
    with pytest.raises(HTTPException) as exc:
        await service.replay(EXECUTION_ID, outcome_node_id="plan:0")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_generate_mr_review_sample_replay_output(fake_db, mr_graph):
    """Materialize example forensic replay JSON for MR review execution."""
    service = ReasoningReplayService(fake_db)
    bundle = await service.replay(EXECUTION_ID, mode=ReplayMode.FORENSIC)

    SAMPLE_REPLAY_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = bundle.model_dump(mode="json")
    SAMPLE_REPLAY_PATH.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )

    assert SAMPLE_REPLAY_PATH.exists()
    assert payload["execution_id"] == EXECUTION_ID
    assert payload["graph_path"][0]["node_type"] == "execution"
    assert payload["graph_path"][-1]["node_type"] == "outcome"
