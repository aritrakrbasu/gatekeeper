"""ARIL Execution Explorer API response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PaginationMeta(BaseModel):
    page: int = 1
    page_size: int = 50
    total: int = 0
    has_more: bool = False


class SubjectRefResponse(BaseModel):
    type: str
    id: str
    sub_id: Optional[str] = None
    repository_id: Optional[str] = None


class GraphSummaryResponse(BaseModel):
    graph_id: Optional[str] = None
    graph_revision: Optional[int] = None
    graph_version: Optional[int] = None
    builder_version: Optional[str] = None
    graph_hash: Optional[str] = None
    status: Optional[str] = None
    root_node_ids: List[str] = Field(default_factory=list)
    terminal_node_ids: List[str] = Field(default_factory=list)
    outcome_node_ids: List[str] = Field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0


class ExecutionDetailResponse(BaseModel):
    execution_id: str
    task_id: str
    execution_type: str
    execution_source: str
    repository_id: str
    subject_id: str
    subject_ref: SubjectRefResponse
    objective: str
    status: str
    graph_id: Optional[str] = None
    outcome_profile: str = "none"
    terminal_outcome_ids: List[str] = Field(default_factory=list)
    partition_key: str
    schema_version: int = 1
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[str] = None
    graph_summary: Optional[GraphSummaryResponse] = None


class CaptureEventResponse(BaseModel):
    event_id: str
    execution_id: str
    task_id: str
    event_type: str
    sequence: int
    timestamp: datetime
    payload: Dict[str, Any] = Field(default_factory=dict)
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    partition_key: Optional[str] = None


class CaptureEventListResponse(BaseModel):
    execution_id: str
    items: List[CaptureEventResponse]
    pagination: PaginationMeta


class EvidenceRefResponse(BaseModel):
    ref: str
    excerpt: Optional[str] = None
    byte_length: Optional[int] = None


class GraphNodeResponse(BaseModel):
    node_id: str
    type: str
    content: Dict[str, Any] = Field(default_factory=dict)
    evidence_refs: List[str] = Field(default_factory=list)
    evidence: List[EvidenceRefResponse] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class GraphEdgeResponse(BaseModel):
    edge_id: str
    from_node_id: str
    to_node_id: str
    relation: str
    weight: Optional[float] = None


class GraphMetadataResponse(BaseModel):
    root_node_ids: List[str] = Field(default_factory=list)
    terminal_node_ids: List[str] = Field(default_factory=list)
    outcome_node_ids: List[str] = Field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0
    graph_revision: int = 0


class DecisionGraphResponse(BaseModel):
    graph_id: str
    execution_id: str
    task_id: str
    repository_id: str
    graph_version: int
    builder_version: str
    schema_version: int
    graph_revision: int
    graph_hash: Optional[str] = None
    status: str
    metadata: GraphMetadataResponse
    nodes: List[GraphNodeResponse]
    edges: List[GraphEdgeResponse]
    created_at: datetime


class SubjectResponse(BaseModel):
    subject_id: str
    repository_id: str
    subject_ref: SubjectRefResponse
    display_name: Optional[str] = None
    execution_ids: List[str] = Field(default_factory=list)
    latest_execution_id: Optional[str] = None
    execution_count: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class TimelineEntryResponse(BaseModel):
    execution_id: str
    task_id: str
    execution_type: str
    status: str
    objective: str
    graph_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SubjectTimelineResponse(BaseModel):
    subject_id: str
    repository_id: str
    items: List[TimelineEntryResponse]
    pagination: PaginationMeta
