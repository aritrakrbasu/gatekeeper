"""Copilot HTTP API models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from copilot.models.enums import QuestionType


class CreateConversationRequest(BaseModel):
    repository_id: str
    execution_id: Optional[str] = None
    mr_iid: Optional[int] = None

    @model_validator(mode="after")
    def _exactly_one_execution_source(self) -> "CreateConversationRequest":
        has_execution_id = bool(self.execution_id)
        has_mr_iid = self.mr_iid is not None
        if has_execution_id == has_mr_iid:
            raise ValueError(
                "Exactly one of execution_id or mr_iid must be supplied"
            )
        return self


class CreateConversationResponse(BaseModel):
    conversation_id: str
    execution_id: str
    repository_id: str
    created_at: datetime


class AskQuestionRequest(BaseModel):
    question: str
    question_type: Optional[QuestionType] = None
    focus_node_id: Optional[str] = None
    focus_step_id: Optional[str] = None
    focus_tool_name: Optional[str] = None
    enable_live_investigation: Optional[bool] = None


class ConversationCheckpointResponse(BaseModel):
    conversation_id: str
    execution_id: str
    repository_id: str
    checkpoint_version: int
    question_type: Optional[str] = None
    last_question: Optional[str] = None
    response_text: Optional[str] = None
    node_trace: List[Dict[str, Any]] = Field(default_factory=list)
    counter_evidence_count: int = 0
    updated_at: datetime


class StreamEvent(BaseModel):
    event: str
    data: Dict[str, Any] = Field(default_factory=dict)


class ResumeConversationRequest(BaseModel):
    decision: str = Field(description="approve, reject, or modify")
    modified_tool_args: Optional[Dict[str, Any]] = None
    admin_confirmed: bool = False


class ResumeConversationResponse(BaseModel):
    conversation_id: str
    thread_id: str
    execution_id: Optional[str] = None
    decision: str
    status: str
