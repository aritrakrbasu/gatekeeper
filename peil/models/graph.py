"""peil_decision_graphs document models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from peil.models.enums import GraphEdgeRelation, GraphNodeType


class GraphNode(BaseModel):
    node_id: str
    type: GraphNodeType
    content: Dict[str, Any] = Field(default_factory=dict)
    evidence_refs: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class GraphEdge(BaseModel):
    edge_id: str
    from_node_id: str
    to_node_id: str
    relation: GraphEdgeRelation
    weight: Optional[float] = None


class GraphMetadata(BaseModel):
    """Indexed graph topology summary stored on the graph document."""

    root_node_ids: List[str] = Field(default_factory=list)
    terminal_node_ids: List[str] = Field(default_factory=list)
    outcome_node_ids: List[str] = Field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0
    graph_revision: int = 0


class DecisionGraphCreate(BaseModel):
    graph_id: str
    execution_id: str
    task_id: str
    repository_id: str
    nodes: List[GraphNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)
    metadata: GraphMetadata = Field(default_factory=GraphMetadata)
    graph_version: int = 1
    builder_version: str = "graph_builder_v0"
    schema_version: int = 1
    status: str = "complete"


class DecisionGraph(BaseModel):
    """Immutable decision graph document."""

    graph_id: str
    execution_id: str
    task_id: str
    repository_id: str
    nodes: List[GraphNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)
    metadata: GraphMetadata = Field(default_factory=GraphMetadata)
    graph_version: int = 1
    builder_version: str = "graph_builder_v0"
    schema_version: int = 1
    graph_revision: int = 0
    status: str = "complete"
    graph_hash: Optional[str] = None
    created_at: datetime

    def to_mongo(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")
