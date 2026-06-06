"""Capture event envelope and typed payloads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from peil.models.enums import CaptureEventType, ExecutionType


class PlanStepSnapshot(BaseModel):
    step_id: str
    tool_name: str
    action: str
    reason: str
    arguments_json: str = "{}"
    dependencies: List[str] = Field(default_factory=list)


class ExecutionStartedPayload(BaseModel):
    task_id: str
    objective: str
    context_snapshot: Dict[str, Any] = Field(default_factory=dict)
    trigger_type: str
    execution_type: ExecutionType
    repository_id: str
    subject_id: str


class PlanEmittedPayload(BaseModel):
    explanation: str
    steps: List[PlanStepSnapshot] = Field(default_factory=list)
    plan_revision: int = 0


class PlanRevisedPayload(BaseModel):
    explanation: str
    steps: List[PlanStepSnapshot] = Field(default_factory=list)
    plan_revision: int
    history_steps: List[Dict[str, Any]] = Field(default_factory=list)
    supersedes_plan_revision: Optional[int] = None


class ModelTurnPayload(BaseModel):
    source: str
    prompt_hash: str
    response_hash: str
    token_count: Optional[int] = None


class StepLifecyclePayload(BaseModel):
    step_id: str
    tool_name: str
    arguments: Optional[Dict[str, Any]] = None
    result_ref: Optional[str] = None
    duration_ms: Optional[float] = None
    error: Optional[str] = None
    retry_count: Optional[int] = None


class ToolLifecyclePayload(BaseModel):
    tool_name: str
    masked_arguments: Dict[str, Any] = Field(default_factory=dict)
    result_ref: Optional[str] = None
    duration_ms: Optional[float] = None
    status: str = "success"
    step_id: Optional[str] = None
    error_message: Optional[str] = None


class ReflectionPayload(BaseModel):
    step_id: str
    passed: bool
    reason: Optional[str] = None
    warning: Optional[str] = None


class ApprovalPayload(BaseModel):
    approval_id: str
    step_id: str
    tool_name: str
    risk_level: str = "LOW"
    status: str = "pending"
    approved: Optional[bool] = None


class ExecutionTerminalPayload(BaseModel):
    status: str
    error: Optional[str] = None
    last_step_id: Optional[str] = None
    step_count: int = 0
    duration_ms: Optional[float] = None


class CaptureEvent(BaseModel):
    """Typed capture event before persistence."""

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    execution_id: str
    task_id: str
    event_type: CaptureEventType
    sequence: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: Dict[str, Any] = Field(default_factory=dict)
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    partition_key: Optional[str] = None

    def to_mongo(self) -> Dict[str, Any]:
        doc = self.model_dump(mode="json")
        doc["event_type"] = self.event_type.value
        return doc


class CaptureEventEnvelope(BaseModel):
    """Wire-format envelope for bus emission."""

    execution_id: str
    task_id: str
    event_type: CaptureEventType
    payload: Dict[str, Any] = Field(default_factory=dict)
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
