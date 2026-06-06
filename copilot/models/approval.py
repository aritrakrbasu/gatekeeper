"""Copilot approval workflow models."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class ApprovalDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    MODIFY = "modify"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    RESOLVED = "resolved"


class PendingApproval(BaseModel):
    reason: str
    tool_name: str
    tool_args: Dict[str, Any] = Field(default_factory=dict)
    risk_level: str
    estimated_scope: str
    step_id: str
    requires_admin: bool = False


class ApprovalRecord(BaseModel):
    approval_id: str = Field(default_factory=lambda: f"appr-{uuid4().hex[:12]}")
    conversation_id: str
    repository_id: str = ""
    copilot_execution_id: Optional[str] = None
    status: ApprovalStatus = ApprovalStatus.RESOLVED
    decision: Optional[ApprovalDecision] = None
    actor_user_id: Optional[str] = None
    pending: PendingApproval
    modified_tool_args: Optional[Dict[str, Any]] = None
    admin_confirmed: bool = False
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
