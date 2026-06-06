"""Unit tests for CopilotGraph topology."""

from copilot.graph.builder import COPILOT_GRAPH_V1_EDGES, linear_node_order
from copilot.models.enums import CopilotNodeName


def test_linear_node_order_matches_v1_pipeline():
    order = linear_node_order()
    assert order[0] == CopilotNodeName.QUESTION
    assert order[-1] == CopilotNodeName.KNOWLEDGE_PROPOSAL
    assert CopilotNodeName.REPLAY_RETRIEVAL in order
    assert order.index(CopilotNodeName.REPLAY_RETRIEVAL) < order.index(
        CopilotNodeName.QUESTION_CLASSIFIER
    )


def test_graph_edges_cover_pipeline():
    sources = {edge.source for edge in COPILOT_GRAPH_V1_EDGES}
    targets = {edge.target for edge in COPILOT_GRAPH_V1_EDGES}
    assert CopilotNodeName.QUESTION in sources
    assert CopilotNodeName.RESPONSE_GENERATOR in targets
