"""Knowledge HTTP API models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from knowledge.models.assertion import AssertionAuditEntry, AssertionProvenance
from knowledge.models.enums import AssertionStatus, AssertionType


class CreateAssertionRequest(BaseModel):
    repository_id: str
    source_execution_id: str
    source_conversation_id: Optional[str] = None
    type: AssertionType
    statement: str
    evidence_refs: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    graph_id: Optional[str] = None
    graph_hash: Optional[str] = None
    replay_reference: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AssertionResponse(BaseModel):
    assertion_id: str
    repository_id: str
    source_execution_id: str
    source_conversation_id: Optional[str] = None
    type: str
    statement: str
    evidence_refs: List[str]
    confidence: float
    status: str
    graph_id: Optional[str] = None
    graph_hash: Optional[str] = None
    replay_reference: Optional[str] = None
    provenance: AssertionProvenance
    proposed_by_user_id: str
    reviewed_by_user_id: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    audit_trail: List[AssertionAuditEntry]
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class AssertionListResponse(BaseModel):
    items: List[AssertionResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class ReviewAssertionRequest(BaseModel):
    reason: Optional[str] = None
