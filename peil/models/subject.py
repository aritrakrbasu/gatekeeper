"""Subject reference and peil_subjects document models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from peil.models.enums import SubjectType


class SubjectRef(BaseModel):
    """Polymorphic pointer to the entity an execution discusses."""

    type: SubjectType
    id: str
    sub_id: Optional[str] = None
    repository_id: Optional[str] = None


class PeilSubjectCreate(BaseModel):
    """Input for registering or upserting a subject index row."""

    subject_id: str = Field(description="Stable subject key, e.g. mr:82576405:42")
    repository_id: str
    subject_ref: SubjectRef
    display_name: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PeilSubject(BaseModel):
    """Materialized subject index document (peil_subjects collection)."""

    subject_id: str
    repository_id: str
    subject_ref: SubjectRef
    display_name: Optional[str] = None
    execution_ids: List[str] = Field(default_factory=list)
    latest_execution_id: Optional[str] = None
    execution_count: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump(mode="json")
        return data


def build_subject_id(subject_ref: SubjectRef) -> str:
    """Deterministic subject_id from ref components."""
    parts = [subject_ref.type.value, subject_ref.id]
    if subject_ref.sub_id:
        parts.append(subject_ref.sub_id)
    if subject_ref.repository_id:
        parts.append(subject_ref.repository_id)
    return ":".join(parts)
