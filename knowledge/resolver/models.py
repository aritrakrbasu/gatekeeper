"""KnowledgeResolver output models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from knowledge.models.assertion import AssertionProvenance
from knowledge.models.enums import AssertionType
from peil.models.subject import SubjectRef


class ConfidenceSummary(BaseModel):
    count: int = 0
    min_confidence: float = 0.0
    max_confidence: float = 0.0
    avg_confidence: float = 0.0


class ResolvedAssertion(BaseModel):
    assertion_id: str
    type: AssertionType
    statement: str
    confidence: float
    evidence_refs: List[str] = Field(default_factory=list)
    provenance: AssertionProvenance
    source_execution_id: str
    reviewed_at: Optional[datetime] = None
    created_at: datetime


class KnowledgeManifest(BaseModel):
    """Compact manifest stored on executions and plan_emitted events."""

    repository_id: str
    execution_type: str
    assertion_count: int
    assertion_ids: List[str] = Field(default_factory=list)
    groups: Dict[str, List[str]] = Field(default_factory=dict)
    limit: int
    total_available: int
    resolved_at: datetime
    subject_id: Optional[str] = None
    question: Optional[str] = None


class KnowledgeContext(BaseModel):
    repository_id: str
    execution_type: str
    subject_ref: Optional[SubjectRef] = None
    question: Optional[str] = None
    limit: int
    total_available: int
    assertions_by_type: Dict[str, List[ResolvedAssertion]] = Field(default_factory=dict)
    confidence_by_type: Dict[str, ConfidenceSummary] = Field(default_factory=dict)
    manifest: KnowledgeManifest

    def to_prompt_section(self) -> str:
        if not self.manifest.assertion_count:
            return ""

        lines = [
            "ACCEPTED REPOSITORY KNOWLEDGE (human-reviewed, use to inform plan strategy):",
        ]
        for assertion_type in sorted(self.assertions_by_type.keys()):
            items = self.assertions_by_type[assertion_type]
            if not items:
                continue
            lines.append(f"[{assertion_type}]")
            for item in items:
                lines.append(
                    f"- ({item.assertion_id}, confidence={item.confidence:.2f}) "
                    f"{item.statement}"
                )
                if item.provenance.replay_reference:
                    lines.append(
                        f"  provenance: execution={item.provenance.execution_id}, "
                        f"replay={item.provenance.replay_reference}"
                    )
        lines.append(
            "Treat this knowledge as advisory context; verify against current execution evidence."
        )
        return "\n".join(lines)

    def to_manifest_dict(self) -> Dict[str, Any]:
        return self.manifest.model_dump(mode="json")
