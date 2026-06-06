"""Knowledge HTTP API routes."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query

from knowledge.api.service import KnowledgeService
from knowledge.models.api_models import (
    AssertionListResponse,
    AssertionResponse,
    CreateAssertionRequest,
    ReviewAssertionRequest,
)
from knowledge.models.enums import AssertionStatus
from peil.api.auth import require_jwt_user

knowledge_router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def _knowledge_service() -> KnowledgeService:
    return KnowledgeService()


@knowledge_router.post(
    "/assertions",
    response_model=AssertionResponse,
    status_code=201,
)
async def create_assertion(
    request: CreateAssertionRequest,
    user: Dict[str, Any] = Depends(require_jwt_user),
    service: KnowledgeService = Depends(_knowledge_service),
) -> AssertionResponse:
    return await service.propose_assertion(str(user["id"]), request)


@knowledge_router.get(
    "/assertions",
    response_model=AssertionListResponse,
)
async def list_assertions(
    repository_id: str = Query(...),
    status: Optional[AssertionStatus] = Query(None),
    type: Optional[str] = Query(None, alias="type"),
    source_execution_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    user: Dict[str, Any] = Depends(require_jwt_user),
    service: KnowledgeService = Depends(_knowledge_service),
) -> AssertionListResponse:
    return await service.list_assertions(
        str(user["id"]),
        repository_id,
        status=status,
        assertion_type=type,
        source_execution_id=source_execution_id,
        page=page,
        page_size=page_size,
    )


@knowledge_router.post(
    "/assertions/{assertion_id}/accept",
    response_model=AssertionResponse,
)
async def accept_assertion(
    assertion_id: str,
    request: ReviewAssertionRequest = ReviewAssertionRequest(),
    user: Dict[str, Any] = Depends(require_jwt_user),
    service: KnowledgeService = Depends(_knowledge_service),
) -> AssertionResponse:
    return await service.accept_assertion(str(user["id"]), assertion_id, request)


@knowledge_router.post(
    "/assertions/{assertion_id}/reject",
    response_model=AssertionResponse,
)
async def reject_assertion(
    assertion_id: str,
    request: ReviewAssertionRequest = ReviewAssertionRequest(),
    user: Dict[str, Any] = Depends(require_jwt_user),
    service: KnowledgeService = Depends(_knowledge_service),
) -> AssertionResponse:
    return await service.reject_assertion(str(user["id"]), assertion_id, request)
