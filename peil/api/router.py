"""ARIL Execution Explorer read-only API routes."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query

from peil.api.auth import require_jwt_user
from peil.api.explorer import ExecutionExplorerService
from peil.api.models import (
    CaptureEventListResponse,
    DecisionGraphResponse,
    ExecutionDetailResponse,
    SubjectResponse,
    SubjectTimelineResponse,
)

aril_router = APIRouter(prefix="/api/aril", tags=["aril"])


def _explorer() -> ExecutionExplorerService:
    return ExecutionExplorerService()


@aril_router.get(
    "/executions/{execution_id}",
    response_model=ExecutionDetailResponse,
)
async def get_execution(
    execution_id: str,
    user: Dict[str, Any] = Depends(require_jwt_user),
    explorer: ExecutionExplorerService = Depends(_explorer),
) -> ExecutionDetailResponse:
    return await explorer.get_execution(execution_id, str(user["id"]))


@aril_router.get(
    "/executions/{execution_id}/events",
    response_model=CaptureEventListResponse,
)
async def list_execution_events(
    execution_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    user: Dict[str, Any] = Depends(require_jwt_user),
    explorer: ExecutionExplorerService = Depends(_explorer),
) -> CaptureEventListResponse:
    return await explorer.list_events(
        execution_id,
        str(user["id"]),
        page=page,
        page_size=page_size,
    )


@aril_router.get(
    "/executions/{execution_id}/graph",
    response_model=DecisionGraphResponse,
)
async def get_execution_graph(
    execution_id: str,
    graph_revision: Optional[int] = Query(None, ge=0),
    include_evidence: bool = Query(True),
    evidence_max_chars: int = Query(512, ge=64, le=8192),
    user: Dict[str, Any] = Depends(require_jwt_user),
    explorer: ExecutionExplorerService = Depends(_explorer),
) -> DecisionGraphResponse:
    return await explorer.get_graph(
        execution_id,
        str(user["id"]),
        graph_revision=graph_revision,
        include_evidence=include_evidence,
        evidence_max_chars=evidence_max_chars,
    )


@aril_router.get(
    "/subjects/{subject_id:path}/timeline",
    response_model=SubjectTimelineResponse,
)
async def get_subject_timeline(
    subject_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    user: Dict[str, Any] = Depends(require_jwt_user),
    explorer: ExecutionExplorerService = Depends(_explorer),
) -> SubjectTimelineResponse:
    return await explorer.get_subject_timeline(
        subject_id,
        str(user["id"]),
        page=page,
        page_size=page_size,
    )


@aril_router.get(
    "/subjects/{subject_id:path}",
    response_model=SubjectResponse,
)
async def get_subject(
    subject_id: str,
    user: Dict[str, Any] = Depends(require_jwt_user),
    explorer: ExecutionExplorerService = Depends(_explorer),
) -> SubjectResponse:
    return await explorer.get_subject(subject_id, str(user["id"]))
