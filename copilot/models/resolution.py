"""MR execution resolution API models."""

from __future__ import annotations

from pydantic import BaseModel


class ExecutionLink(BaseModel):
    execution_id: str
    graph_id: str
    subject_id: str
    status: str
    copilot_ready: bool = True


class MrExecutionResponse(BaseModel):
    repository_id: str
    mr_iid: int
    subject_id: str
    execution_id: str
    graph_id: str
    status: str
    copilot_ready: bool = True
