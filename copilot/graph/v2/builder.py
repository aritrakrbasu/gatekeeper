"""LangGraph Copilot v2 StateGraph builder."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from langgraph.errors import GraphInterrupt
from langgraph.graph import END, START, StateGraph

from agents.aril_bridge import ArilSession
from agents.registry import ToolRegistry
from copilot.graph.v2.routing import (
    route_after_classifier,
    route_after_execute,
    route_after_resume,
)
from copilot.graph.v2.state import (
    CopilotGraphState,
    copilot_from_graph_state,
    merge_copilot_update,
)
from copilot.models.enums import CopilotNodeName
from copilot.models.state import CopilotState
from copilot.nodes.base import run_node
from copilot.nodes.evidence_retrieval import evidence_retrieval_node
from copilot.nodes.execution_resolver import execution_resolver_node
from copilot.nodes.approval_gate import approval_gate_node
from copilot.nodes.execute_investigation_plan import execute_investigation_plan_node
from copilot.nodes.knowledge_proposal import knowledge_proposal_node
from copilot.nodes.plan_investigation import plan_investigation_node
from copilot.nodes.resume_execution import resume_execution_node
from copilot.nodes.question import question_node
from copilot.nodes.resolve_knowledge import resolve_knowledge_node
from copilot.nodes.question_classifier import question_classifier_node
from copilot.nodes.replay_retrieval import replay_retrieval_node
from copilot.nodes.response_generator import response_generator_node
from copilot.store.checkpoint_repository import CheckpointRepository


def _make_node(
    node_name: CopilotNodeName,
    handler: Callable[[CopilotState], Any],
    *,
    db: Any = None,
    registry: Optional[ToolRegistry] = None,
    checkpoints: Optional[CheckpointRepository] = None,
    persist_checkpoints: bool = True,
) -> Callable[[CopilotGraphState], Dict[str, Any]]:
    async def _node(graph_state: CopilotGraphState) -> Dict[str, Any]:
        copilot = copilot_from_graph_state(graph_state)
        sse_events: list[dict] = []
        try:
            async for event in run_node(copilot, node_name, handler):
                sse_events.append(event)
        except GraphInterrupt:
            raise
        except Exception:
            return {
                "copilot": copilot.model_dump(mode="json"),
                "sse_events": sse_events,
                "halted": True,
            }
        if persist_checkpoints and checkpoints is not None:
            await checkpoints.save(copilot)
        return merge_copilot_update(graph_state, copilot) | {"sse_events": sse_events}

    return _node


def build_copilot_state_graph(
    *,
    db: Any = None,
    registry: Optional[ToolRegistry] = None,
    checkpoints: Optional[CheckpointRepository] = None,
    aril: Optional[ArilSession] = None,
    persist_checkpoints: bool = True,
) -> StateGraph:
    """Construct the v2 Copilot StateGraph mirroring the v1 pipeline."""
    graph = StateGraph(CopilotGraphState)
    checkpoint_repo = checkpoints or CheckpointRepository(db)

    graph.add_node(
        CopilotNodeName.QUESTION.value,
        _make_node(CopilotNodeName.QUESTION, question_node, checkpoints=checkpoint_repo, persist_checkpoints=persist_checkpoints),
    )
    graph.add_node(
        CopilotNodeName.EXECUTION_RESOLVER.value,
        _make_node(
            CopilotNodeName.EXECUTION_RESOLVER,
            lambda s: execution_resolver_node(s, db=db),
            checkpoints=checkpoint_repo,
            persist_checkpoints=persist_checkpoints,
        ),
    )
    graph.add_node(
        CopilotNodeName.REPLAY_RETRIEVAL.value,
        _make_node(
            CopilotNodeName.REPLAY_RETRIEVAL,
            lambda s: replay_retrieval_node(s, db=db),
            checkpoints=checkpoint_repo,
            persist_checkpoints=persist_checkpoints,
        ),
    )
    graph.add_node(
        CopilotNodeName.EVIDENCE_RETRIEVAL.value,
        _make_node(
            CopilotNodeName.EVIDENCE_RETRIEVAL,
            evidence_retrieval_node,
            checkpoints=checkpoint_repo,
            persist_checkpoints=persist_checkpoints,
        ),
    )
    graph.add_node(
        CopilotNodeName.RESOLVE_KNOWLEDGE.value,
        _make_node(
            CopilotNodeName.RESOLVE_KNOWLEDGE,
            lambda s: resolve_knowledge_node(s, db=db),
            checkpoints=checkpoint_repo,
            persist_checkpoints=persist_checkpoints,
        ),
    )
    graph.add_node(
        CopilotNodeName.QUESTION_CLASSIFIER.value,
        _make_node(
            CopilotNodeName.QUESTION_CLASSIFIER,
            question_classifier_node,
            checkpoints=checkpoint_repo,
            persist_checkpoints=persist_checkpoints,
        ),
    )
    graph.add_node(
        CopilotNodeName.PLAN_INVESTIGATION.value,
        _make_node(
            CopilotNodeName.PLAN_INVESTIGATION,
            lambda s: plan_investigation_node(s, registry=registry),
            checkpoints=checkpoint_repo,
            persist_checkpoints=persist_checkpoints,
        ),
    )
    graph.add_node(
        CopilotNodeName.EXECUTE_INVESTIGATION_PLAN.value,
        _make_node(
            CopilotNodeName.EXECUTE_INVESTIGATION_PLAN,
            lambda s: execute_investigation_plan_node(
                s, registry=registry, aril=aril, db=db
            ),
            checkpoints=checkpoint_repo,
            persist_checkpoints=persist_checkpoints,
        ),
    )
    graph.add_node(
        CopilotNodeName.APPROVAL_GATE.value,
        _make_node(
            CopilotNodeName.APPROVAL_GATE,
            lambda s: approval_gate_node(s, aril=aril, db=db),
            checkpoints=checkpoint_repo,
            persist_checkpoints=persist_checkpoints,
        ),
    )
    graph.add_node(
        CopilotNodeName.RESUME_EXECUTION.value,
        _make_node(
            CopilotNodeName.RESUME_EXECUTION,
            lambda s: resume_execution_node(s, registry=registry, aril=aril, db=db),
            checkpoints=checkpoint_repo,
            persist_checkpoints=persist_checkpoints,
        ),
    )
    graph.add_node(
        CopilotNodeName.RESPONSE_GENERATOR.value,
        _make_node(
            CopilotNodeName.RESPONSE_GENERATOR,
            response_generator_node,
            checkpoints=checkpoint_repo,
            persist_checkpoints=persist_checkpoints,
        ),
    )
    graph.add_node(
        CopilotNodeName.KNOWLEDGE_PROPOSAL.value,
        _make_node(
            CopilotNodeName.KNOWLEDGE_PROPOSAL,
            lambda s: knowledge_proposal_node(s, db=db),
            checkpoints=checkpoint_repo,
            persist_checkpoints=persist_checkpoints,
        ),
    )

    graph.add_edge(START, CopilotNodeName.QUESTION.value)
    graph.add_edge(CopilotNodeName.QUESTION.value, CopilotNodeName.EXECUTION_RESOLVER.value)
    graph.add_edge(
        CopilotNodeName.EXECUTION_RESOLVER.value,
        CopilotNodeName.REPLAY_RETRIEVAL.value,
    )
    graph.add_edge(
        CopilotNodeName.REPLAY_RETRIEVAL.value,
        CopilotNodeName.EVIDENCE_RETRIEVAL.value,
    )
    graph.add_edge(
        CopilotNodeName.EVIDENCE_RETRIEVAL.value,
        CopilotNodeName.RESOLVE_KNOWLEDGE.value,
    )
    graph.add_edge(
        CopilotNodeName.RESOLVE_KNOWLEDGE.value,
        CopilotNodeName.QUESTION_CLASSIFIER.value,
    )
    graph.add_conditional_edges(
        CopilotNodeName.QUESTION_CLASSIFIER.value,
        route_after_classifier,
        {
            CopilotNodeName.PLAN_INVESTIGATION.value: CopilotNodeName.PLAN_INVESTIGATION.value,
            CopilotNodeName.RESPONSE_GENERATOR.value: CopilotNodeName.RESPONSE_GENERATOR.value,
            END: END,
        },
    )
    graph.add_edge(
        CopilotNodeName.PLAN_INVESTIGATION.value,
        CopilotNodeName.EXECUTE_INVESTIGATION_PLAN.value,
    )
    graph.add_conditional_edges(
        CopilotNodeName.EXECUTE_INVESTIGATION_PLAN.value,
        route_after_execute,
        {
            CopilotNodeName.APPROVAL_GATE.value: CopilotNodeName.APPROVAL_GATE.value,
            CopilotNodeName.RESPONSE_GENERATOR.value: CopilotNodeName.RESPONSE_GENERATOR.value,
            END: END,
        },
    )
    graph.add_edge(
        CopilotNodeName.APPROVAL_GATE.value,
        CopilotNodeName.RESUME_EXECUTION.value,
    )
    graph.add_conditional_edges(
        CopilotNodeName.RESUME_EXECUTION.value,
        route_after_resume,
        {
            CopilotNodeName.EXECUTE_INVESTIGATION_PLAN.value: CopilotNodeName.EXECUTE_INVESTIGATION_PLAN.value,
            CopilotNodeName.RESPONSE_GENERATOR.value: CopilotNodeName.RESPONSE_GENERATOR.value,
            END: END,
        },
    )
    graph.add_edge(
        CopilotNodeName.RESPONSE_GENERATOR.value,
        CopilotNodeName.KNOWLEDGE_PROPOSAL.value,
    )
    graph.add_edge(CopilotNodeName.KNOWLEDGE_PROPOSAL.value, END)

    return graph
