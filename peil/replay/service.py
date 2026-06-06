"""
Deterministic ReasoningReplayService — graph-backed execution replay.

No LLM, vector search, or LangGraph. Walks peil_decision_graphs using the
causal chain:

  Outcome ← Reflection ← Tool Result ← Tool Call ← Plan Step ← Plan ← Model Turn ← Execution
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import HTTPException

from peil.models.enums import GraphEdgeRelation, GraphNodeType
from peil.models.execution import PeilExecution
from peil.models.graph import DecisionGraph, GraphNode
from peil.replay.models import (
    ExecutionSummary,
    GraphPathStep,
    NarrativeSection,
    ReplayBundle,
    ReplayEvidenceRef,
    ReplayMode,
    ReplayModelTurn,
    ReplayNarrative,
    ReplayOutcome,
    ReplayPlanStep,
    ReplayReflection,
    ReplayToolCall,
    ReplayToolResult,
)
from peil.store.evidence_repository import EvidenceRepository
from peil.store.execution_repository import ExecutionRepository
from peil.store.graph_repository import GraphRepository

# Parent selection when walking backward along the reasoning chain.
_PARENT_RULES: Dict[GraphNodeType, List[Tuple[GraphNodeType, Set[GraphEdgeRelation]]]] = {
    GraphNodeType.OUTCOME: [
        (GraphNodeType.EXECUTION, {GraphEdgeRelation.PRODUCES}),
    ],
    GraphNodeType.REFLECTION: [
        (GraphNodeType.TOOL_RESULT, {GraphEdgeRelation.VALIDATES, GraphEdgeRelation.CONTRADICTS}),
    ],
    GraphNodeType.TOOL_RESULT: [
        (GraphNodeType.TOOL_CALL, {GraphEdgeRelation.PRODUCES}),
    ],
    GraphNodeType.TOOL_CALL: [
        (GraphNodeType.PLAN_STEP, {GraphEdgeRelation.TRIGGERS}),
    ],
    GraphNodeType.PLAN_STEP: [
        (GraphNodeType.PLAN, {GraphEdgeRelation.PRODUCES}),
    ],
    GraphNodeType.PLAN: [
        (GraphNodeType.MODEL_TURN, {GraphEdgeRelation.PRODUCES}),
        (GraphNodeType.EXECUTION, {GraphEdgeRelation.TRIGGERS}),
    ],
    GraphNodeType.MODEL_TURN: [
        (GraphNodeType.EXECUTION, {GraphEdgeRelation.TRIGGERS}),
    ],
}

# Forward spine from execution root (planning phase).
_FORWARD_SPINE: List[Tuple[GraphNodeType, Set[GraphEdgeRelation]]] = [
    (GraphNodeType.MODEL_TURN, {GraphEdgeRelation.TRIGGERS}),
    (GraphNodeType.PLAN, {GraphEdgeRelation.PRODUCES}),
]


class ReasoningReplayService:
    """Build deterministic ReplayBundle documents from stored decision graphs."""

    def __init__(self, db: Any = None) -> None:
        self._db = db
        self._executions = ExecutionRepository(db)
        self._graphs = GraphRepository(db)
        self._evidence = EvidenceRepository(db)

    async def replay(
        self,
        execution_id: str,
        *,
        outcome_node_id: Optional[str] = None,
        mode: ReplayMode = ReplayMode.FORENSIC,
        graph_revision: Optional[int] = None,
        include_evidence: bool = True,
        evidence_max_chars: int = 256,
    ) -> ReplayBundle:
        execution = await self._executions.get_by_execution_id(execution_id)
        if execution is None:
            raise HTTPException(status_code=404, detail="Execution not found")

        graph = await self._graphs.get_by_execution_id(
            execution_id, graph_revision=graph_revision
        )
        if graph is None:
            raise HTTPException(status_code=404, detail="Decision graph not found")

        resolved_outcome = self._resolve_outcome_node(graph, outcome_node_id)
        nodes, incoming, outgoing = _build_indexes(graph)

        spine_ids = _collect_planning_spine(
            graph.metadata.root_node_ids, nodes, outgoing
        )
        step_chains = _collect_step_chains(nodes, incoming)
        graph_path = _build_graph_path(
            spine_ids, step_chains, resolved_outcome, nodes, incoming
        )

        model_turns = _extract_model_turns(graph_path, nodes)
        plan_steps = _extract_plan_steps(graph_path, nodes)
        tool_calls = _extract_tool_calls(graph_path, nodes)
        tool_results = _extract_tool_results(graph_path, nodes)
        reflections = _extract_reflections(graph_path, nodes)
        outcome = _extract_outcome(resolved_outcome, nodes)

        evidence_refs = await self._resolve_evidence(
            tool_results,
            include_evidence=include_evidence,
            evidence_max_chars=evidence_max_chars,
        )

        bundle = ReplayBundle(
            execution_id=execution_id,
            outcome_node_id=resolved_outcome,
            mode=mode,
            graph_id=graph.graph_id,
            graph_hash=graph.graph_hash,
            graph_revision=graph.graph_revision,
            execution_summary=_execution_summary(execution),
            graph_path=graph_path,
            model_turns=model_turns,
            plan_steps=plan_steps,
            tool_calls=tool_calls,
            tool_results=tool_results,
            reflections=reflections,
            evidence_references=evidence_refs,
            outcome=outcome,
        )

        if mode == ReplayMode.NARRATIVE:
            bundle.narrative = _build_narrative(bundle)

        return bundle

    @staticmethod
    def _resolve_outcome_node(
        graph: DecisionGraph, outcome_node_id: Optional[str]
    ) -> str:
        if outcome_node_id:
            known = {n.node_id for n in graph.nodes}
            if outcome_node_id not in known:
                raise HTTPException(status_code=404, detail="Outcome node not found")
            node = next(n for n in graph.nodes if n.node_id == outcome_node_id)
            if node.type != GraphNodeType.OUTCOME:
                raise HTTPException(
                    status_code=400,
                    detail=f"Node {outcome_node_id} is not an outcome node",
                )
            return outcome_node_id

        if graph.metadata.outcome_node_ids:
            return graph.metadata.outcome_node_ids[0]

        for node in sorted(graph.nodes, key=lambda n: n.node_id):
            if node.type == GraphNodeType.OUTCOME:
                return node.node_id

        raise HTTPException(status_code=404, detail="No outcome node in graph")

    async def _resolve_evidence(
        self,
        tool_results: List[ReplayToolResult],
        *,
        include_evidence: bool,
        evidence_max_chars: int,
    ) -> List[ReplayEvidenceRef]:
        refs: List[ReplayEvidenceRef] = []
        for result in tool_results:
            for ref in result.evidence_refs:
                excerpt: Optional[str] = None
                byte_length: Optional[int] = None
                if include_evidence:
                    excerpt = await self._evidence.resolve(
                        ref, max_chars=evidence_max_chars
                    )
                    if excerpt:
                        byte_length = len(excerpt.encode("utf-8"))
                refs.append(
                    ReplayEvidenceRef(
                        ref=ref,
                        node_id=result.node_id,
                        excerpt=excerpt or None,
                        byte_length=byte_length,
                    )
                )
        return refs


def _build_indexes(
    graph: DecisionGraph,
) -> Tuple[Dict[str, GraphNode], Dict[str, List[Tuple[str, GraphEdgeRelation]]], Dict[str, List[Tuple[str, GraphEdgeRelation]]]]:
    nodes = {n.node_id: n for n in graph.nodes}
    incoming: Dict[str, List[Tuple[str, GraphEdgeRelation]]] = defaultdict(list)
    outgoing: Dict[str, List[Tuple[str, GraphEdgeRelation]]] = defaultdict(list)
    for edge in graph.edges:
        incoming[edge.to_node_id].append((edge.from_node_id, edge.relation))
        outgoing[edge.from_node_id].append((edge.to_node_id, edge.relation))
    return nodes, incoming, outgoing


def _pick_parent(
    node: GraphNode,
    incoming: List[Tuple[str, GraphEdgeRelation]],
    nodes: Dict[str, GraphNode],
) -> Optional[Tuple[str, GraphEdgeRelation]]:
    rules = _PARENT_RULES.get(node.type, [])
    matches: List[Tuple[str, GraphEdgeRelation]] = []
    for parent_type, relations in rules:
        for from_id, relation in incoming:
            parent = nodes.get(from_id)
            if parent is None:
                continue
            if parent.type == parent_type and relation in relations:
                matches.append((from_id, relation))
    if not matches:
        return None
    matches.sort(key=lambda item: item[0])
    return matches[0]


def walk_backward_chain(
    start_id: str,
    nodes: Dict[str, GraphNode],
    incoming: Dict[str, List[Tuple[str, GraphEdgeRelation]]],
    *,
    max_depth: int = 64,
) -> List[Tuple[str, Optional[GraphEdgeRelation], Optional[str]]]:
    """
    Walk backward from start_id following causal parent rules.

    Returns list of (node_id, edge_relation_to_parent, parent_node_id) in
    visit order (start first). Cycle-safe.
    """
    path: List[Tuple[str, Optional[GraphEdgeRelation], Optional[str]]] = []
    visited: Set[str] = set()
    current = start_id

    for _ in range(max_depth):
        if current is None or current in visited:
            break
        visited.add(current)
        node = nodes.get(current)
        if node is None:
            break

        parent_info = _pick_parent(node, incoming.get(current, []), nodes)
        relation = parent_info[1].value if parent_info else None
        parent_id = parent_info[0] if parent_info else None
        path.append((current, relation, parent_id))

        if parent_info is None:
            break
        current = parent_info[0]

    return path


def _collect_planning_spine(
    root_ids: List[str],
    nodes: Dict[str, GraphNode],
    outgoing: Dict[str, List[Tuple[str, GraphEdgeRelation]]],
) -> List[str]:
    """execution → model_turn → plan in deterministic order."""
    if not root_ids:
        return []

    spine: List[str] = []
    current = sorted(root_ids)[0]
    if current not in nodes:
        return spine

    spine.append(current)

    for target_type, relations in _FORWARD_SPINE:
        candidates: List[str] = []
        for to_id, relation in outgoing.get(current, []):
            child = nodes.get(to_id)
            if child and child.type == target_type and relation in relations:
                candidates.append(to_id)
        if not candidates:
            break
        current = sorted(candidates)[0]
        spine.append(current)

    return spine


def _collect_step_chains(
    nodes: Dict[str, GraphNode],
    incoming: Dict[str, List[Tuple[str, GraphEdgeRelation]]],
) -> List[List[str]]:
    """
    One backward chain per reflection (or orphaned tool_result), ordered by
    tool_call sequence.
    """
    reflections = [
        n
        for n in nodes.values()
        if n.type == GraphNodeType.REFLECTION
    ]
    reflections.sort(
        key=lambda n: (
            n.content.get("sequence") or 0,
            n.node_id,
        )
    )

    chains: List[List[str]] = []
    seen_starts: Set[str] = set()

    for reflection in reflections:
        backward = walk_backward_chain(reflection.node_id, nodes, incoming)
        chain_ids = [entry[0] for entry in reversed(backward)]
        if chain_ids and chain_ids[0] not in seen_starts:
            chains.append(chain_ids)
            seen_starts.add(chain_ids[0])
        elif chain_ids:
            chains.append(chain_ids)

    if not chains:
        tool_results = [
            n for n in nodes.values() if n.type == GraphNodeType.TOOL_RESULT
        ]
        tool_results.sort(
            key=lambda n: (n.content.get("sequence") or 0, n.node_id)
        )
        for tr in tool_results:
            backward = walk_backward_chain(tr.node_id, nodes, incoming)
            chain_ids = [entry[0] for entry in reversed(backward)]
            if chain_ids:
                chains.append(chain_ids)

    chains.sort(key=lambda chain: _chain_sort_key(chain, nodes))
    return chains


def _chain_sort_key(chain: List[str], nodes: Dict[str, GraphNode]) -> Tuple[int, str]:
    for node_id in chain:
        node = nodes.get(node_id)
        if node and node.type == GraphNodeType.TOOL_CALL:
            return (node.content.get("sequence") or 0, node_id)
    return (0, chain[0] if chain else "")


def _build_graph_path(
    spine_ids: List[str],
    step_chains: List[List[str]],
    outcome_id: str,
    nodes: Dict[str, GraphNode],
    incoming: Dict[str, List[Tuple[str, GraphEdgeRelation]]],
) -> List[GraphPathStep]:
    """
    Chronological replay path:

    execution → model_turn → plan → [per-step chains] → outcome
    """
    ordered_ids: List[str] = []
    seen: Set[str] = set()

    def _append_unique(node_id: str) -> None:
        if node_id not in seen and node_id in nodes:
            seen.add(node_id)
            ordered_ids.append(node_id)

    for node_id in spine_ids:
        _append_unique(node_id)

    for chain in step_chains:
        for node_id in chain:
            node = nodes.get(node_id)
            if node and node.type in {
                GraphNodeType.PLAN_STEP,
                GraphNodeType.TOOL_CALL,
                GraphNodeType.TOOL_RESULT,
                GraphNodeType.REFLECTION,
            }:
                _append_unique(node_id)

    _append_unique(outcome_id)

    steps: List[GraphPathStep] = []
    for index, node_id in enumerate(ordered_ids):
        node = nodes[node_id]
        parent_info = _pick_parent(node, incoming.get(node_id, []), nodes)
        steps.append(
            GraphPathStep(
                index=index,
                node_id=node_id,
                node_type=node.type.value,
                edge_relation=parent_info[1].value if parent_info else None,
                parent_node_id=parent_info[0] if parent_info else None,
            )
        )
    return steps


def _execution_summary(execution: PeilExecution) -> ExecutionSummary:
    return ExecutionSummary(
        execution_id=execution.execution_id,
        task_id=execution.task_id,
        execution_type=execution.execution_type.value,
        execution_source=execution.execution_source.value,
        repository_id=execution.repository_id,
        subject_id=execution.subject_id,
        objective=execution.objective,
        status=execution.status.value,
        graph_id=execution.graph_id,
        created_at=execution.created_at,
        updated_at=execution.updated_at,
        completed_at=execution.completed_at,
    )


def _node_content(node: GraphNode) -> Dict[str, Any]:
    return node.content or {}


def _extract_model_turns(
    path: List[GraphPathStep], nodes: Dict[str, GraphNode]
) -> List[ReplayModelTurn]:
    items: List[ReplayModelTurn] = []
    for step in path:
        node = nodes.get(step.node_id)
        if not node or node.type != GraphNodeType.MODEL_TURN:
            continue
        content = _node_content(node)
        items.append(
            ReplayModelTurn(
                node_id=node.node_id,
                source=content.get("source"),
                prompt_hash=content.get("prompt_hash"),
                response_hash=content.get("response_hash"),
                token_count=content.get("token_count"),
                sequence=content.get("sequence"),
                created_at=node.created_at,
            )
        )
    return items


def _extract_plan_steps(
    path: List[GraphPathStep], nodes: Dict[str, GraphNode]
) -> List[ReplayPlanStep]:
    items: List[ReplayPlanStep] = []
    seen: Set[str] = set()
    for step in path:
        node = nodes.get(step.node_id)
        if not node or node.type != GraphNodeType.PLAN_STEP:
            continue
        if node.node_id in seen:
            continue
        seen.add(node.node_id)
        content = _node_content(node)
        items.append(
            ReplayPlanStep(
                node_id=node.node_id,
                step_id=str(content.get("step_id") or ""),
                tool_name=content.get("tool_name"),
                action=content.get("action"),
                reason=content.get("reason"),
                plan_revision=content.get("plan_revision"),
                dependencies=list(content.get("dependencies") or []),
                sequence=content.get("sequence"),
                created_at=node.created_at,
            )
        )
    return items


def _extract_tool_calls(
    path: List[GraphPathStep], nodes: Dict[str, GraphNode]
) -> List[ReplayToolCall]:
    items: List[ReplayToolCall] = []
    for step in path:
        node = nodes.get(step.node_id)
        if not node or node.type != GraphNodeType.TOOL_CALL:
            continue
        content = _node_content(node)
        items.append(
            ReplayToolCall(
                node_id=node.node_id,
                tool_name=content.get("tool_name"),
                step_id=content.get("step_id"),
                masked_arguments=dict(content.get("masked_arguments") or {}),
                sequence=content.get("sequence"),
                created_at=node.created_at,
            )
        )
    return items


def _extract_tool_results(
    path: List[GraphPathStep], nodes: Dict[str, GraphNode]
) -> List[ReplayToolResult]:
    items: List[ReplayToolResult] = []
    for step in path:
        node = nodes.get(step.node_id)
        if not node or node.type != GraphNodeType.TOOL_RESULT:
            continue
        content = _node_content(node)
        items.append(
            ReplayToolResult(
                node_id=node.node_id,
                tool_name=content.get("tool_name"),
                step_id=content.get("step_id"),
                status=content.get("status"),
                duration_ms=content.get("duration_ms"),
                error_message=content.get("error_message"),
                evidence_refs=list(node.evidence_refs or []),
                sequence=content.get("sequence"),
                created_at=node.created_at,
            )
        )
    return items


def _extract_reflections(
    path: List[GraphPathStep], nodes: Dict[str, GraphNode]
) -> List[ReplayReflection]:
    items: List[ReplayReflection] = []
    for step in path:
        node = nodes.get(step.node_id)
        if not node or node.type != GraphNodeType.REFLECTION:
            continue
        content = _node_content(node)
        items.append(
            ReplayReflection(
                node_id=node.node_id,
                step_id=content.get("step_id"),
                passed=content.get("passed"),
                reason=content.get("reason"),
                warning=content.get("warning"),
                sequence=content.get("sequence"),
                created_at=node.created_at,
            )
        )
    return items


def _extract_outcome(outcome_id: str, nodes: Dict[str, GraphNode]) -> ReplayOutcome:
    node = nodes[outcome_id]
    content = _node_content(node)
    return ReplayOutcome(
        node_id=node.node_id,
        status=content.get("status"),
        step_count=content.get("step_count"),
        duration_ms=content.get("duration_ms"),
        error=content.get("error"),
        event_type=content.get("event_type"),
        sequence=content.get("sequence"),
        created_at=node.created_at,
    )


def _build_narrative(bundle: ReplayBundle) -> ReplayNarrative:
    summary = bundle.execution_summary
    sections: List[NarrativeSection] = []

    sections.append(
        NarrativeSection(
            title="Execution",
            body=(
                f"{summary.objective} "
                f"(type={summary.execution_type}, status={summary.status})."
            ),
        )
    )

    plan_steps_by_id = {s.step_id: s for s in bundle.plan_steps if s.step_id}
    for turn in bundle.model_turns:
        sections.append(
            NarrativeSection(
                title="Model turn",
                body=(
                    f"Planner model turn from {turn.source or 'unknown'} "
                    f"({turn.token_count or 0} tokens)."
                ),
            )
        )

    if bundle.plan_steps:
        plan_lines = []
        for ps in bundle.plan_steps:
            plan_lines.append(
                f"- {ps.step_id}: {ps.action or ps.tool_name or 'step'}"
                + (f" — {ps.reason}" if ps.reason else "")
            )
        sections.append(
            NarrativeSection(
                title="Plan",
                body="Proposed steps:\n" + "\n".join(plan_lines),
            )
        )

    for idx, call in enumerate(bundle.tool_calls):
        result = bundle.tool_results[idx] if idx < len(bundle.tool_results) else None
        reflection = (
            bundle.reflections[idx] if idx < len(bundle.reflections) else None
        )
        step = plan_steps_by_id.get(call.step_id or "")

        lines = [
            f"Step '{call.step_id or 'unknown'}' invoked {call.tool_name or 'tool'}.",
        ]
        if step and step.reason:
            lines.append(f"Rationale: {step.reason}.")
        if result:
            lines.append(
                f"Result: {result.status or 'unknown'}"
                + (
                    f" ({result.duration_ms:.0f}ms)"
                    if result.duration_ms is not None
                    else ""
                )
                + "."
            )
        if reflection is not None:
            verdict = "passed" if reflection.passed else "failed"
            lines.append(f"Reflection: {verdict}.")
        sections.append(
            NarrativeSection(
                title=f"Step {idx + 1}: {call.step_id or call.tool_name or 'action'}",
                body=" ".join(lines),
            )
        )

    outcome = bundle.outcome
    sections.append(
        NarrativeSection(
            title="Outcome",
            body=(
                f"Execution finished with status '{outcome.status or 'unknown'}'"
                + (
                    f" after {outcome.step_count} steps"
                    if outcome.step_count is not None
                    else ""
                )
                + (
                    f" in {outcome.duration_ms:.0f}ms"
                    if outcome.duration_ms is not None
                    else ""
                )
                + "."
            ),
        )
    )

    narrative_summary = (
        f"Replayed {len(bundle.graph_path)} graph nodes for "
        f"{summary.execution_id}: {outcome.status or summary.status}."
    )

    return ReplayNarrative(summary=narrative_summary, sections=sections)
