"""ARIL Reasoning Replay response models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ReplayMode(str, Enum):
    FORENSIC = "forensic"
    NARRATIVE = "narrative"


class GraphPathStep(BaseModel):
    """One node in the deterministic replay traversal order."""

    index: int
    node_id: str
    node_type: str
    edge_relation: Optional[str] = None
    parent_node_id: Optional[str] = None


class ExecutionSummary(BaseModel):
    execution_id: str
    task_id: str
    execution_type: str
    execution_source: str
    repository_id: str
    subject_id: str
    objective: str
    status: str
    graph_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[str] = None


class ReplayModelTurn(BaseModel):
    node_id: str
    source: Optional[str] = None
    prompt_hash: Optional[str] = None
    response_hash: Optional[str] = None
    token_count: Optional[int] = None
    sequence: Optional[int] = None
    created_at: Optional[datetime] = None


class ReplayPlanStep(BaseModel):
    node_id: str
    step_id: str
    tool_name: Optional[str] = None
    action: Optional[str] = None
    reason: Optional[str] = None
    plan_revision: Optional[int] = None
    dependencies: List[str] = Field(default_factory=list)
    sequence: Optional[int] = None
    created_at: Optional[datetime] = None


class ReplayToolCall(BaseModel):
    node_id: str
    tool_name: Optional[str] = None
    step_id: Optional[str] = None
    masked_arguments: Dict[str, Any] = Field(default_factory=dict)
    sequence: Optional[int] = None
    created_at: Optional[datetime] = None


class ReplayToolResult(BaseModel):
    node_id: str
    tool_name: Optional[str] = None
    step_id: Optional[str] = None
    status: Optional[str] = None
    duration_ms: Optional[float] = None
    error_message: Optional[str] = None
    evidence_refs: List[str] = Field(default_factory=list)
    sequence: Optional[int] = None
    created_at: Optional[datetime] = None


class ReplayReflection(BaseModel):
    node_id: str
    step_id: Optional[str] = None
    passed: Optional[bool] = None
    reason: Optional[str] = None
    warning: Optional[str] = None
    sequence: Optional[int] = None
    created_at: Optional[datetime] = None


class ReplayEvidenceRef(BaseModel):
    ref: str
    node_id: str
    excerpt: Optional[str] = None
    byte_length: Optional[int] = None


class ReplayOutcome(BaseModel):
    node_id: str
    status: Optional[str] = None
    step_count: Optional[int] = None
    duration_ms: Optional[float] = None
    error: Optional[str] = None
    event_type: Optional[str] = None
    sequence: Optional[int] = None
    created_at: Optional[datetime] = None


class NarrativeSection(BaseModel):
    title: str
    body: str


class ReplayNarrative(BaseModel):
    summary: str
    sections: List[NarrativeSection] = Field(default_factory=list)


class ReplayBundle(BaseModel):
    execution_id: str
    outcome_node_id: str
    mode: ReplayMode
    graph_id: str
    graph_hash: Optional[str] = None
    graph_revision: int = 0
    execution_summary: ExecutionSummary
    graph_path: List[GraphPathStep]
    model_turns: List[ReplayModelTurn] = Field(default_factory=list)
    plan_steps: List[ReplayPlanStep] = Field(default_factory=list)
    tool_calls: List[ReplayToolCall] = Field(default_factory=list)
    tool_results: List[ReplayToolResult] = Field(default_factory=list)
    reflections: List[ReplayReflection] = Field(default_factory=list)
    evidence_references: List[ReplayEvidenceRef] = Field(default_factory=list)
    outcome: ReplayOutcome
    narrative: Optional[ReplayNarrative] = None
