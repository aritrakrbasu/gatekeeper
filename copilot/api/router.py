"""Copilot HTTP API routes."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, Query
from sse_starlette.sse import EventSourceResponse

from copilot.api.service import CopilotService, format_sse, parse_last_event_id
from copilot.models.api_models import (
    AskQuestionRequest,
    ConversationCheckpointResponse,
    CreateConversationRequest,
    CreateConversationResponse,
    ResumeConversationRequest,
    ResumeConversationResponse,
)
from copilot.models.frontend_models import (
    ConversationBootstrapResponse,
    ConversationExecutionLinkResponse,
    ConversationListResponse,
    ConversationStateResponse,
    PendingApprovalQueueResponse,
)
from peil.api.auth import require_jwt_user

copilot_router = APIRouter(prefix="/api/copilot", tags=["copilot"])

_copilot_service_instance: CopilotService | None = None


def _copilot_service() -> CopilotService:
    global _copilot_service_instance
    if _copilot_service_instance is None:
        _copilot_service_instance = CopilotService()
    return _copilot_service_instance


async def warm_copilot_tool_registry() -> None:
    """Build the shared Copilot tool registry once after MCP is ready."""
    await _copilot_service().warm_registry()


@copilot_router.post(
    "/conversations",
    response_model=CreateConversationResponse,
)
async def create_conversation(
    request: CreateConversationRequest,
    user: Dict[str, Any] = Depends(require_jwt_user),
    service: CopilotService = Depends(_copilot_service),
) -> CreateConversationResponse:
    return await service.create_conversation(str(user["id"]), request)


@copilot_router.get(
    "/conversations",
    response_model=ConversationListResponse,
)
async def list_conversations(
    repository_id: Optional[str] = Query(default=None),
    execution_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: Dict[str, Any] = Depends(require_jwt_user),
    service: CopilotService = Depends(_copilot_service),
) -> ConversationListResponse:
    return await service.list_conversations(
        str(user["id"]),
        repository_id=repository_id,
        execution_id=execution_id,
        status=status,
        page=page,
        page_size=page_size,
    )


@copilot_router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationCheckpointResponse,
)
async def get_conversation(
    conversation_id: str,
    user: Dict[str, Any] = Depends(require_jwt_user),
    service: CopilotService = Depends(_copilot_service),
) -> ConversationCheckpointResponse:
    return await service.get_conversation(str(user["id"]), conversation_id)


@copilot_router.get(
    "/conversations/{conversation_id}/state",
    response_model=ConversationStateResponse,
)
async def get_conversation_state(
    conversation_id: str,
    user: Dict[str, Any] = Depends(require_jwt_user),
    service: CopilotService = Depends(_copilot_service),
) -> ConversationStateResponse:
    return await service.get_conversation_state(str(user["id"]), conversation_id)


@copilot_router.get(
    "/conversations/{conversation_id}/execution",
    response_model=ConversationExecutionLinkResponse,
)
async def get_conversation_execution_link(
    conversation_id: str,
    user: Dict[str, Any] = Depends(require_jwt_user),
    service: CopilotService = Depends(_copilot_service),
) -> ConversationExecutionLinkResponse:
    return await service.get_conversation_execution_link(
        str(user["id"]), conversation_id
    )


@copilot_router.get(
    "/conversations/{conversation_id}/bootstrap",
    response_model=ConversationBootstrapResponse,
)
async def get_conversation_bootstrap(
    conversation_id: str,
    user: Dict[str, Any] = Depends(require_jwt_user),
    service: CopilotService = Depends(_copilot_service),
) -> ConversationBootstrapResponse:
    return await service.get_conversation_bootstrap(str(user["id"]), conversation_id)


@copilot_router.get("/approvals/pending", response_model=PendingApprovalQueueResponse)
async def list_pending_approvals(
    repository_id: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: Dict[str, Any] = Depends(require_jwt_user),
    service: CopilotService = Depends(_copilot_service),
) -> PendingApprovalQueueResponse:
    return await service.list_pending_approvals(
        str(user["id"]),
        repository_id=repository_id,
        page=page,
        page_size=page_size,
    )


@copilot_router.post("/conversations/{conversation_id}/ask")
async def ask_question_stream(
    conversation_id: str,
    request: AskQuestionRequest,
    last_event_id: Optional[str] = Header(default=None, alias="Last-Event-ID"),
    user: Dict[str, Any] = Depends(require_jwt_user),
    service: CopilotService = Depends(_copilot_service),
) -> EventSourceResponse:
    resume_from = parse_last_event_id(last_event_id)

    async def event_generator():
        async for event in service.ask_stream(
            str(user["id"]),
            conversation_id,
            request,
            last_event_id=resume_from,
        ):
            yield format_sse(event)

    return EventSourceResponse(event_generator())


@copilot_router.get("/conversations/{conversation_id}/stream")
async def reconnect_conversation_stream(
    conversation_id: str,
    thread_id: Optional[str] = Query(default=None),
    last_event_id: Optional[str] = Header(default=None, alias="Last-Event-ID"),
    last_event_id_query: Optional[int] = Query(default=None, alias="last_event_id"),
    user: Dict[str, Any] = Depends(require_jwt_user),
    service: CopilotService = Depends(_copilot_service),
) -> EventSourceResponse:
    resume_from = (
        last_event_id_query
        if last_event_id_query is not None
        else parse_last_event_id(last_event_id)
    )

    async def event_generator():
        async for event in service.reconnect_stream(
            str(user["id"]),
            conversation_id,
            last_event_id=resume_from,
            thread_id=thread_id,
        ):
            yield format_sse(event)

    return EventSourceResponse(event_generator())


@copilot_router.post("/conversations/{conversation_id}/resume")
async def resume_conversation_stream(
    conversation_id: str,
    request: ResumeConversationRequest,
    last_event_id: Optional[str] = Header(default=None, alias="Last-Event-ID"),
    user: Dict[str, Any] = Depends(require_jwt_user),
    service: CopilotService = Depends(_copilot_service),
) -> EventSourceResponse:
    resume_from = parse_last_event_id(last_event_id)

    async def event_generator():
        async for event in service.resume_stream(
            str(user["id"]),
            conversation_id,
            request,
            last_event_id=resume_from,
        ):
            yield format_sse(event)

    return EventSourceResponse(event_generator())


@copilot_router.post(
    "/conversations/{conversation_id}/resume/sync",
    response_model=ResumeConversationResponse,
)
async def resume_conversation_sync(
    conversation_id: str,
    request: ResumeConversationRequest,
    user: Dict[str, Any] = Depends(require_jwt_user),
    service: CopilotService = Depends(_copilot_service),
) -> ResumeConversationResponse:
    return await service.resume_conversation(
        str(user["id"]), conversation_id, request
    )
