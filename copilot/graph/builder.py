"""CopilotGraph v1 topology definition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from copilot.models.enums import CopilotNodeName


@dataclass(frozen=True)
class GraphEdge:
    source: CopilotNodeName
    target: CopilotNodeName
    conditional: bool = False


COPILOT_GRAPH_V1_EDGES: List[GraphEdge] = [
    GraphEdge(CopilotNodeName.QUESTION, CopilotNodeName.EXECUTION_RESOLVER),
    GraphEdge(CopilotNodeName.EXECUTION_RESOLVER, CopilotNodeName.REPLAY_RETRIEVAL),
    GraphEdge(CopilotNodeName.REPLAY_RETRIEVAL, CopilotNodeName.EVIDENCE_RETRIEVAL),
    GraphEdge(CopilotNodeName.EVIDENCE_RETRIEVAL, CopilotNodeName.QUESTION_CLASSIFIER),
    GraphEdge(
        CopilotNodeName.QUESTION_CLASSIFIER,
        CopilotNodeName.LIVE_INVESTIGATION,
        conditional=True,
    ),
    GraphEdge(CopilotNodeName.QUESTION_CLASSIFIER, CopilotNodeName.RESPONSE_GENERATOR),
    GraphEdge(CopilotNodeName.LIVE_INVESTIGATION, CopilotNodeName.RESPONSE_GENERATOR),
    GraphEdge(CopilotNodeName.RESPONSE_GENERATOR, CopilotNodeName.KNOWLEDGE_PROPOSAL),
]


def linear_node_order() -> List[CopilotNodeName]:
    """Deterministic execution order for v1 pipeline."""
    return [
        CopilotNodeName.QUESTION,
        CopilotNodeName.EXECUTION_RESOLVER,
        CopilotNodeName.REPLAY_RETRIEVAL,
        CopilotNodeName.EVIDENCE_RETRIEVAL,
        CopilotNodeName.QUESTION_CLASSIFIER,
        CopilotNodeName.LIVE_INVESTIGATION,
        CopilotNodeName.RESPONSE_GENERATOR,
        CopilotNodeName.KNOWLEDGE_PROPOSAL,
    ]
