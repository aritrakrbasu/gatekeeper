"""KnowledgeAssertion domain models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from knowledge.models.enums import AssertionStatus, AssertionType, AuditAction


class AssertionAuditEntry(BaseModel):
    action: AuditAction
    actor_user_id: str
    timestamp: datetime
    detail: Dict[str, Any] = Field(default_factory=dict)


class AssertionProvenance(BaseModel):
    """Links an assertion back to ARIL execution intelligence."""

    execution_id: str
    conversation_id: Optional[str] = None
    graph_id: Optional[str] = None
    graph_hash: Optional[str] = None
    replay_reference: Optional[str] = None


class KnowledgeAssertionCreate(BaseModel):
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

    @field_validator("statement")
    @classmethod
    def _statement_not_empty(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("statement must not be empty")
        return text


class KnowledgeAssertion(BaseModel):
    assertion_id: str
    repository_id: str
    source_execution_id: str
    source_conversation_id: Optional[str] = None
    type: AssertionType
    statement: str
    evidence_refs: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    status: AssertionStatus = AssertionStatus.PROPOSED
    graph_id: Optional[str] = None
    graph_hash: Optional[str] = None
    replay_reference: Optional[str] = None
    provenance: AssertionProvenance
    proposed_by_user_id: str
    reviewed_by_user_id: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    audit_trail: List[AssertionAuditEntry] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    schema_version: int = 1
    created_at: datetime
    updated_at: datetime

    def to_mongo(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")
