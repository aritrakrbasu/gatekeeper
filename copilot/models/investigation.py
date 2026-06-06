"""Investigation planning models for Copilot v2."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List
from uuid import uuid4

from pydantic import BaseModel, Field

from copilot.models.enums import QuestionType


class InvestigationProfile(str, Enum):
    FINDING_CHALLENGE = "finding_challenge"
    REPOSITORY_COMPARISON = "repository_comparison"
    DEEP_INVESTIGATION = "deep_investigation"


class InvestigationPlanStep(BaseModel):
    step_id: str
    rationale: str
    tool_name: str
    tool_args: Dict[str, Any] = Field(default_factory=dict)
    expected_evidence: str


class InvestigationPlan(BaseModel):
    plan_id: str
    conversation_id: str
    question_type: QuestionType
    profile: InvestigationProfile
    steps: List[InvestigationPlanStep] = Field(default_factory=list)
    knowledge_assertion_ids: List[str] = Field(default_factory=list)
    replay_execution_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @staticmethod
    def new_id() -> str:
        return f"plan-{uuid4().hex[:12]}"
