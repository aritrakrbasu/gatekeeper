"""CopilotGraph shared state."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from copilot.models.enums import CopilotNodeName, QuestionType
from copilot.models.investigation import InvestigationPlan
from knowledge.resolver.models import KnowledgeContext
from peil.replay.models import ReplayBundle


class CounterEvidenceItem(BaseModel):
    source: str
    description: str
    node_id: Optional[str] = None
    ref: Optional[str] = None


class InvestigationResult(BaseModel):
    tool_name: str
    status: str
    summary: str
    raw_preview: Optional[str] = None


class NodeTraceEntry(BaseModel):
    node: CopilotNodeName
    started_at: datetime
    completed_at: Optional[datetime] = None
    detail: Dict[str, Any] = Field(default_factory=dict)


class CopilotState(BaseModel):
    conversation_id: str
    user_id: str
    repository_id: str
    execution_id: Optional[str] = None
    question: str = ""
    focus_node_id: Optional[str] = None
    focus_step_id: Optional[str] = None
    focus_tool_name: Optional[str] = None
    question_type: QuestionType = QuestionType.UNKNOWN
    replay_bundle: Optional[ReplayBundle] = None
    evidence_excerpts: List[Dict[str, Any]] = Field(default_factory=list)
    counter_evidence: List[CounterEvidenceItem] = Field(default_factory=list)
    investigation_results: List[InvestigationResult] = Field(default_factory=list)
    user_assertions_detected: List[str] = Field(default_factory=list)
    assertion_conflicts: List[str] = Field(default_factory=list)
    response_text: str = ""
    response_chunks: List[str] = Field(default_factory=list)
    node_trace: List[NodeTraceEntry] = Field(default_factory=list)
    checkpoint_version: int = 0
    errors: List[str] = Field(default_factory=list)
    live_investigation_enabled: bool = False
    proposed_assertion_ids: List[str] = Field(default_factory=list)
    knowledge_context: Optional[KnowledgeContext] = None
    knowledge_manifest: Dict[str, Any] = Field(default_factory=dict)
    knowledge_citations: List[str] = Field(default_factory=list)
    investigation_plan: Optional[InvestigationPlan] = None
    copilot_execution_id: Optional[str] = None
    plan_step_cursor: int = 0
    pending_approval: Optional[dict] = None
    approval_resume: Optional[dict] = None
    approval_history: List[dict] = Field(default_factory=list)
    interrupted: bool = False
    interrupt_payload: Optional[dict] = None

    def bump_checkpoint(self) -> None:
        self.checkpoint_version += 1

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)
