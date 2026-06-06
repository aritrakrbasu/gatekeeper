"""Frontend-readiness API models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from copilot.models.api_models import ConversationCheckpointResponse


class InvestigationPlanStepResponse(BaseModel):
    step_id: str
    rationale: str
    tool_name: str
    tool_args: Dict[str, Any] = Field(default_factory=dict)
    expected_evidence: str


class CurrentPlanResponse(BaseModel):
    plan_id: Optional[str] = None
    profile: Optional[str] = None
    steps: List[InvestigationPlanStepResponse] = Field(default_factory=list)
    step_cursor: int = 0


class PendingApprovalResponse(BaseModel):
    reason: str
    tool_name: str
    tool_args: Dict[str, Any] = Field(default_factory=dict)
    risk_level: str
    estimated_scope: str
    step_id: str
    requires_admin: bool = False


class ConversationStateResponse(BaseModel):
    conversation_id: str
    thread_id: str
    status: str
    execution_id: Optional[str] = None
    copilot_execution_id: Optional[str] = None
    current_node: Optional[str] = None
    current_plan: Optional[CurrentPlanResponse] = None
    pending_approval: Optional[PendingApprovalResponse] = None
    checkpoint_id: Optional[str] = None
    checkpoint_version: int = 0
    last_updated: datetime


class ConversationListItem(BaseModel):
    conversation_id: str
    execution_id: str
    repository_id: str
    status: str
    last_question: Optional[str] = None
    last_updated: datetime
    pending_approval: bool = False


class ConversationListResponse(BaseModel):
    items: List[ConversationListItem]
    total: int
    page: int
    page_size: int


class ConversationExecutionLinkResponse(BaseModel):
    conversation_id: str
    execution_id: str
    copilot_execution_id: Optional[str] = None
    graph_id: Optional[str] = None
    subject_id: Optional[str] = None
    repository_id: str


class PendingApprovalQueueItem(BaseModel):
    approval_id: str
    conversation_id: str
    repository_id: str
    tool_name: str
    risk_level: str
    reason: str
    created_at: datetime


class PendingApprovalQueueResponse(BaseModel):
    items: List[PendingApprovalQueueItem]
    total: int
    page: int
    page_size: int


class BootstrapCheckpointInfo(BaseModel):
    checkpoint_id: Optional[str] = None
    checkpoint_version: int = 0
    thread_id: str
    last_updated: datetime


class BootstrapExecutionInfo(BaseModel):
    execution_id: str
    copilot_execution_id: Optional[str] = None
    graph_id: Optional[str] = None
    subject_id: Optional[str] = None
    repository_id: str
    status: Optional[str] = None


class ConversationBootstrapResponse(BaseModel):
    conversation: ConversationCheckpointResponse
    state: ConversationStateResponse
    execution: BootstrapExecutionInfo
    knowledge_manifest: Dict[str, Any] = Field(default_factory=dict)
    current_plan: Optional[CurrentPlanResponse] = None
    pending_approval: Optional[PendingApprovalResponse] = None
    checkpoint: BootstrapCheckpointInfo
