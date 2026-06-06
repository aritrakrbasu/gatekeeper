"""
Deterministic GraphBuilder — transforms peil_capture_events into peil_decision_graphs.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from peil.config import get_aril_settings
from peil.logging import log_aril_event
from peil.models.enums import CaptureEventType, ExecutionStatus, GraphEdgeRelation, GraphNodeType
from peil.models.events import CaptureEvent
from peil.models.execution import PeilExecution
from peil.models.graph import DecisionGraph, DecisionGraphCreate, GraphEdge, GraphMetadata, GraphNode
from peil.store.capture_event_repository import CaptureEventRepository
from peil.store.execution_repository import ExecutionRepository
from peil.graph.hashing import compute_graph_hash
from peil.store.graph_repository import GraphRepository


BUILDER_VERSION = "graph_builder_v1"


@dataclass
class GraphBuildResult:
    graph: DecisionGraph
    created: bool
    graph_hash: str


@dataclass
class _GraphState:
    nodes: Dict[str, GraphNode] = field(default_factory=dict)
    edges: Dict[str, GraphEdge] = field(default_factory=dict)
    execution_node_id: Optional[str] = None
    latest_model_turn_id: Optional[str] = None
    latest_plan_revision: int = -1
    plan_step_ids: Dict[Tuple[int, str], str] = field(default_factory=dict)
    pending_tool_call_id: Optional[str] = None
    step_tool_result_ids: Dict[str, str] = field(default_factory=dict)
    outcome_node_id: Optional[str] = None
    terminal_status: str = "complete"


class GraphBuilder:
    """Builds immutable decision graphs from capture events for one execution."""

    def __init__(
        self,
        db: Any = None,
        *,
        graph_version: Optional[int] = None,
        builder_version: Optional[str] = None,
    ) -> None:
        self._db = db
        self._settings = get_aril_settings()
        self._event_repo = CaptureEventRepository(db)
        self._execution_repo = ExecutionRepository(db)
        self._graph_repo = GraphRepository(db)
        self._graph_version = graph_version or self._settings.graph_version
        self._builder_version = builder_version or self._settings.builder_version

    async def build(self, execution_id: str, *, graph_revision: int = 0) -> DecisionGraphCreate:
        events = await self._event_repo.list_by_execution_id(execution_id)
        execution = await self._execution_repo.get_by_execution_id(execution_id)
        if execution is None:
            raise ValueError(f"No peil_executions header for execution_id={execution_id}")
        return self.build_from_events(
            events,
            execution,
            graph_revision=graph_revision,
        )

    def build_from_events(
        self,
        events: List[CaptureEvent],
        execution: PeilExecution,
        *,
        graph_revision: int = 0,
    ) -> DecisionGraphCreate:
        ordered = sorted(events, key=lambda e: (e.sequence, e.timestamp.isoformat()))
        state = _GraphState()

        for event in ordered:
            self._apply_event(state, event, execution.execution_id)

        nodes = [state.nodes[nid] for nid in sorted(state.nodes.keys())]
        edges = [state.edges[eid] for eid in sorted(state.edges.keys())]
        metadata = self._build_metadata(state, nodes, edges, graph_revision)

        status = state.terminal_status
        if state.outcome_node_id is None and ordered:
            status = "partial"

        return DecisionGraphCreate(
            graph_id=self._graph_id(execution.execution_id, graph_revision),
            execution_id=execution.execution_id,
            task_id=execution.task_id,
            repository_id=execution.repository_id,
            nodes=nodes,
            edges=edges,
            metadata=metadata,
            graph_version=self._graph_version,
            builder_version=self._builder_version,
            schema_version=self._settings.schema_version,
            status=status,
        )

    async def build_and_persist(
        self,
        execution_id: str,
        *,
        graph_revision: int = 0,
    ) -> GraphBuildResult:
        graph_create = await self.build(execution_id, graph_revision=graph_revision)
        graph_hash = compute_graph_hash(graph_create)

        existing = await self._graph_repo.get_by_execution_id(
            execution_id, graph_revision=graph_revision
        )
        if existing is not None and existing.graph_hash == graph_hash:
            log_aril_event(
                "graph_build_idempotent_hit",
                execution_id=execution_id,
                extra={"graph_id": existing.graph_id, "graph_hash": graph_hash},
            )
            return GraphBuildResult(graph=existing, created=False, graph_hash=graph_hash)

        graph = await self._graph_repo.insert(graph_create)
        await self._execution_repo.update_fields(
            execution_id,
            {
                "status": ExecutionStatus.GRAPH_BUILT.value,
                "graph_id": graph.graph_id,
            },
        )
        log_aril_event(
            "graph_built",
            execution_id=execution_id,
            task_id=graph.task_id,
            extra={
                "graph_id": graph.graph_id,
                "graph_hash": graph.graph_hash,
                "node_count": graph.metadata.node_count,
            },
        )
        return GraphBuildResult(graph=graph, created=True, graph_hash=graph.graph_hash or graph_hash)

    def _apply_event(
        self,
        state: _GraphState,
        event: CaptureEvent,
        execution_id: str,
    ) -> None:
        seq = event.sequence
        payload = event.payload or {}
        etype = event.event_type

        if etype == CaptureEventType.EXECUTION_STARTED:
            node_id = f"execution:{execution_id}"
            state.execution_node_id = node_id
            self._add_node(
                state,
                node_id,
                GraphNodeType.EXECUTION,
                {
                    "objective": payload.get("objective"),
                    "trigger_type": payload.get("trigger_type"),
                    "execution_type": payload.get("execution_type"),
                    "repository_id": payload.get("repository_id"),
                    "subject_id": payload.get("subject_id"),
                    "sequence": seq,
                },
                event.timestamp,
            )

        elif etype == CaptureEventType.MODEL_TURN:
            node_id = f"model_turn:{seq:04d}"
            state.latest_model_turn_id = node_id
            self._add_node(
                state,
                node_id,
                GraphNodeType.MODEL_TURN,
                {
                    "source": payload.get("source"),
                    "prompt_hash": payload.get("prompt_hash"),
                    "response_hash": payload.get("response_hash"),
                    "token_count": payload.get("token_count"),
                    "sequence": seq,
                },
                event.timestamp,
            )
            if state.execution_node_id:
                self._add_edge(
                    state,
                    state.execution_node_id,
                    node_id,
                    GraphEdgeRelation.TRIGGERS,
                )

        elif etype in (CaptureEventType.PLAN_EMITTED, CaptureEventType.PLAN_REVISED):
            revision = int(payload.get("plan_revision", 0))
            state.latest_plan_revision = revision
            plan_id = f"plan:{revision}"
            self._add_node(
                state,
                plan_id,
                GraphNodeType.PLAN,
                {
                    "explanation": payload.get("explanation"),
                    "plan_revision": revision,
                    "event_type": etype.value,
                    "step_count": len(payload.get("steps") or []),
                    "sequence": seq,
                },
                event.timestamp,
            )
            if state.latest_model_turn_id:
                self._add_edge(
                    state,
                    state.latest_model_turn_id,
                    plan_id,
                    GraphEdgeRelation.PRODUCES,
                )
            elif state.execution_node_id:
                self._add_edge(
                    state,
                    state.execution_node_id,
                    plan_id,
                    GraphEdgeRelation.TRIGGERS,
                )

            for step in payload.get("steps") or []:
                step_id = step.get("step_id") or f"step_{seq}"
                ps_id = f"plan_step:{revision}:{step_id}"
                state.plan_step_ids[(revision, step_id)] = ps_id
                self._add_node(
                    state,
                    ps_id,
                    GraphNodeType.PLAN_STEP,
                    {
                        "step_id": step_id,
                        "tool_name": step.get("tool_name"),
                        "action": step.get("action"),
                        "reason": step.get("reason"),
                        "arguments_json": step.get("arguments_json"),
                        "dependencies": step.get("dependencies") or [],
                        "plan_revision": revision,
                        "sequence": seq,
                    },
                    event.timestamp,
                )
                self._add_edge(state, plan_id, ps_id, GraphEdgeRelation.PRODUCES)
                for dep in step.get("dependencies") or []:
                    dep_ps = state.plan_step_ids.get((revision, dep))
                    if dep_ps:
                        self._add_edge(state, dep_ps, ps_id, GraphEdgeRelation.DEPENDS_ON)

        elif etype == CaptureEventType.TOOL_INVOKED:
            node_id = f"tool_call:{seq:04d}"
            state.pending_tool_call_id = node_id
            step_id = payload.get("step_id")
            self._add_node(
                state,
                node_id,
                GraphNodeType.TOOL_CALL,
                {
                    "tool_name": payload.get("tool_name"),
                    "masked_arguments": payload.get("masked_arguments"),
                    "step_id": step_id,
                    "sequence": seq,
                },
                event.timestamp,
            )
            if step_id and state.latest_plan_revision >= 0:
                ps_id = state.plan_step_ids.get((state.latest_plan_revision, step_id))
                if ps_id:
                    self._add_edge(state, ps_id, node_id, GraphEdgeRelation.TRIGGERS)

        elif etype == CaptureEventType.TOOL_COMPLETED:
            node_id = f"tool_result:{seq:04d}"
            step_id = payload.get("step_id")
            evidence_refs: List[str] = []
            result_ref = payload.get("result_ref")
            if result_ref:
                evidence_refs.append(str(result_ref))
            self._add_node(
                state,
                node_id,
                GraphNodeType.TOOL_RESULT,
                {
                    "tool_name": payload.get("tool_name"),
                    "status": payload.get("status"),
                    "duration_ms": payload.get("duration_ms"),
                    "step_id": step_id,
                    "error_message": payload.get("error_message"),
                    "sequence": seq,
                },
                event.timestamp,
                evidence_refs=evidence_refs,
            )
            if state.pending_tool_call_id:
                self._add_edge(
                    state,
                    state.pending_tool_call_id,
                    node_id,
                    GraphEdgeRelation.PRODUCES,
                )
            if step_id:
                state.step_tool_result_ids[step_id] = node_id

        elif etype == CaptureEventType.REFLECTION_EVALUATED:
            node_id = f"reflection:{seq:04d}"
            step_id = payload.get("step_id")
            passed = bool(payload.get("passed"))
            self._add_node(
                state,
                node_id,
                GraphNodeType.REFLECTION,
                {
                    "step_id": step_id,
                    "passed": passed,
                    "reason": payload.get("reason"),
                    "warning": payload.get("warning"),
                    "sequence": seq,
                },
                event.timestamp,
            )
            source_id = state.step_tool_result_ids.get(step_id or "")
            if source_id:
                relation = (
                    GraphEdgeRelation.VALIDATES
                    if passed
                    else GraphEdgeRelation.CONTRADICTS
                )
                self._add_edge(state, source_id, node_id, relation)

        elif etype in (
            CaptureEventType.EXECUTION_COMPLETED,
            CaptureEventType.EXECUTION_FAILED,
            CaptureEventType.EXECUTION_PAUSED,
        ):
            node_id = "outcome:terminal"
            state.outcome_node_id = node_id
            state.terminal_status = payload.get("status") or (
                "failed" if etype == CaptureEventType.EXECUTION_FAILED else "complete"
            )
            if etype == CaptureEventType.EXECUTION_PAUSED:
                state.terminal_status = "paused"
            self._add_node(
                state,
                node_id,
                GraphNodeType.OUTCOME,
                {
                    "status": state.terminal_status,
                    "error": payload.get("error"),
                    "step_count": payload.get("step_count"),
                    "duration_ms": payload.get("duration_ms"),
                    "event_type": etype.value,
                    "sequence": seq,
                },
                event.timestamp,
            )
            parent_id = state.execution_node_id
            if parent_id:
                self._add_edge(state, parent_id, node_id, GraphEdgeRelation.PRODUCES)

    def _add_node(
        self,
        state: _GraphState,
        node_id: str,
        node_type: GraphNodeType,
        content: Dict[str, Any],
        created_at: datetime,
        *,
        evidence_refs: Optional[List[str]] = None,
    ) -> None:
        if node_id in state.nodes:
            return
        state.nodes[node_id] = GraphNode(
            node_id=node_id,
            type=node_type,
            content=content,
            evidence_refs=evidence_refs or [],
            created_at=created_at,
        )

    def _add_edge(
        self,
        state: _GraphState,
        from_id: str,
        to_id: str,
        relation: GraphEdgeRelation,
    ) -> None:
        edge_id = f"{from_id}|{relation.value}|{to_id}"
        if edge_id in state.edges:
            return
        state.edges[edge_id] = GraphEdge(
            edge_id=edge_id,
            from_node_id=from_id,
            to_node_id=to_id,
            relation=relation,
        )

    def _build_metadata(
        self,
        state: _GraphState,
        nodes: List[GraphNode],
        edges: List[GraphEdge],
        graph_revision: int,
    ) -> GraphMetadata:
        outgoing: Dict[str, int] = {}
        for edge in edges:
            outgoing[edge.from_node_id] = outgoing.get(edge.from_node_id, 0) + 1

        terminal_ids = sorted(
            [n.node_id for n in nodes if outgoing.get(n.node_id, 0) == 0]
        )
        root_ids: List[str] = []
        if state.execution_node_id and state.execution_node_id in state.nodes:
            root_ids = [state.execution_node_id]

        outcome_ids: List[str] = []
        if state.outcome_node_id and state.outcome_node_id in state.nodes:
            outcome_ids = [state.outcome_node_id]

        return GraphMetadata(
            root_node_ids=root_ids,
            terminal_node_ids=terminal_ids,
            outcome_node_ids=outcome_ids,
            node_count=len(nodes),
            edge_count=len(edges),
            graph_revision=graph_revision,
        )

    @staticmethod
    def _graph_id(execution_id: str, graph_revision: int) -> str:
        digest = hashlib.sha256(f"{execution_id}:{graph_revision}".encode()).hexdigest()[:16]
        return f"graph-{digest}"
