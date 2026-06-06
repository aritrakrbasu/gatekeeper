"""peil_executions document models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from peil.models.enums import ExecutionSource, ExecutionStatus, ExecutionType, OutcomeProfile
from peil.models.subject import SubjectRef


class PeilExecutionCreate(BaseModel):
    """Fields required to open a new execution record."""

    execution_id: str
    task_id: str
    execution_type: ExecutionType
    execution_source: ExecutionSource = ExecutionSource.WORKFLOW_ENGINE
    repository_id: str
    subject_ref: SubjectRef
    subject_id: str
    objective: str
    context_snapshot: Dict[str, Any] = Field(default_factory=dict)
    parent_execution_id: Optional[str] = None
    partition_key: Optional[str] = None


class PeilExecution(BaseModel):
    """Materialized execution header (peil_executions collection)."""

    execution_id: str
    task_id: str
    execution_type: ExecutionType
    execution_source: ExecutionSource
    repository_id: str
    subject_ref: SubjectRef
    subject_id: str
    objective: str
    context_snapshot: Dict[str, Any] = Field(default_factory=dict)
    parent_execution_id: Optional[str] = None
    graph_id: Optional[str] = None
    outcome_profile: OutcomeProfile = OutcomeProfile.NONE
    terminal_outcome_ids: List[str] = Field(default_factory=list)
    status: ExecutionStatus = ExecutionStatus.CAPTURING
    partition_key: str
    schema_version: int = 1
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[str] = None
    knowledge_manifest: Dict[str, Any] = Field(default_factory=dict)

    def to_mongo(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")
