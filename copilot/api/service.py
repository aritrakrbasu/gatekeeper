"""Copilot API service layer."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import HTTPException

from copilot.api.state_service import build_conversation_state
from copilot.approval.store import CopilotApprovalStore
from copilot.config import is_langgraph_enabled, is_v1_fallback_enabled
from copilot.graph.runner import CopilotGraphRunner
from copilot.graph.v2.streaming import CopilotLangGraphRunner
from copilot.models.api_models import (
    AskQuestionRequest,
    ConversationCheckpointResponse,
    CreateConversationRequest,
    CreateConversationResponse,
    ResumeConversationRequest,
    ResumeConversationResponse,
)
from copilot.models.approval import ApprovalDecision
from copilot.models.enums import QuestionType
from copilot.models.frontend_models import (
    BootstrapCheckpointInfo,
    BootstrapExecutionInfo,
    ConversationBootstrapResponse,
    ConversationExecutionLinkResponse,
    ConversationListItem,
    ConversationListResponse,
    ConversationStateResponse,
    PendingApprovalQueueItem,
    PendingApprovalQueueResponse,
)
from copilot.models.state import CopilotState
from copilot.resolution.mr_execution import resolve_mr_execution
from copilot.store.checkpoint_repository import COLLECTION, CheckpointRepository
from copilot.store.sse_event_store import SseEventStore
from peil.api.access import assert_repository_access, assert_repository_access_for_tests
from peil.store.execution_repository import ExecutionRepository


class CopilotService:
    def __init__(self, db: Any = None) -> None:
        self._db = db
        self._checkpoints = CheckpointRepository(db)
        self._approvals = CopilotApprovalStore(db)
        self._sse_events = SseEventStore(db)
        self._v1_runner = CopilotGraphRunner(db, checkpoints=self._checkpoints)
        self._v2_runner = CopilotLangGraphRunner(db, checkpoints=self._checkpoints)

    def _select_runner(self):
        if is_langgraph_enabled() or not is_v1_fallback_enabled():
            return self._v2_runner
        return self._v1_runner

    async def _check_repo(self, user_id: str, repository_id: str) -> None:
        if self._db is not None:
            await assert_repository_access_for_tests(user_id, repository_id, self._db)
        else:
            await assert_repository_access(user_id, repository_id)

    async def create_conversation(
        self,
        user_id: str,
        request: CreateConversationRequest,
    ) -> CreateConversationResponse:
        execution_id = request.execution_id
        if not execution_id:
            link = await resolve_mr_execution(
                request.repository_id,
                int(request.mr_iid),
                user_id,
                db=self._db,
            )
            execution_id = link.execution_id
        else:
            await self._check_repo(user_id, request.repository_id)

        state = await self._checkpoints.create_conversation(
            user_id=user_id,
            repository_id=request.repository_id,
            execution_id=execution_id,
        )
        doc = await self._get_checkpoint_doc(state.conversation_id)
        return CreateConversationResponse(
            conversation_id=state.conversation_id,
            execution_id=state.execution_id or execution_id,
            repository_id=state.repository_id,
            created_at=doc["created_at"],
        )

    async def _require_conversation_doc(
        self,
        user_id: str,
        conversation_id: str,
    ) -> dict:
        doc = await self._get_checkpoint_doc(conversation_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if doc["user_id"] != str(user_id):
            raise HTTPException(status_code=403, detail="Access denied")
        return doc

    def _conversation_response(self, doc: dict) -> ConversationCheckpointResponse:
        state = CopilotState.model_validate(doc["state"])
        return ConversationCheckpointResponse(
            conversation_id=state.conversation_id,
            execution_id=state.execution_id or doc["execution_id"],
            repository_id=state.repository_id,
            checkpoint_version=state.checkpoint_version,
            question_type=state.question_type.value if state.question_type else None,
            last_question=state.question or None,
            response_text=state.response_text or None,
            node_trace=[entry.model_dump(mode="json") for entry in state.node_trace],
            counter_evidence_count=len(state.counter_evidence),
            updated_at=doc["updated_at"],
        )

    async def get_conversation(
        self,
        user_id: str,
        conversation_id: str,
    ) -> ConversationCheckpointResponse:
        doc = await self._require_conversation_doc(user_id, conversation_id)
        return self._conversation_response(doc)

    async def get_conversation_state(
        self,
        user_id: str,
        conversation_id: str,
    ) -> ConversationStateResponse:
        doc = await self._require_conversation_doc(user_id, conversation_id)
        return await build_conversation_state(doc=doc, db=await self._database())

    async def list_conversations(
        self,
        user_id: str,
        *,
        repository_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ConversationListResponse:
        if repository_id:
            await self._check_repo(user_id, repository_id)
        items, total = await self._checkpoints.list_conversations(
            user_id=str(user_id),
            repository_id=repository_id,
            execution_id=execution_id,
            status=status,
            page=page,
            page_size=page_size,
        )
        return ConversationListResponse(
            items=[
                ConversationListItem(
                    conversation_id=doc["conversation_id"],
                    execution_id=doc.get("execution_id", ""),
                    repository_id=doc.get("repository_id", ""),
                    status=doc.get("status", "completed"),
                    last_question=(doc.get("state") or {}).get("question"),
                    last_updated=doc["updated_at"],
                    pending_approval=bool(doc.get("pending_approval", False)),
                )
                for doc in items
            ],
            total=total,
            page=max(1, page),
            page_size=max(1, min(page_size, 100)),
        )

    async def get_conversation_execution_link(
        self,
        user_id: str,
        conversation_id: str,
    ) -> ConversationExecutionLinkResponse:
        doc = await self._require_conversation_doc(user_id, conversation_id)
        state = CopilotState.model_validate(doc["state"])
        await self._check_repo(user_id, state.repository_id)
        execution_id = state.execution_id or doc.get("execution_id", "")
        graph_id = None
        subject_id = None
        if execution_id:
            execution = await ExecutionRepository(self._db).get_by_execution_id(
                execution_id
            )
            if execution is not None:
                graph_id = execution.graph_id
                subject_id = execution.subject_id
        return ConversationExecutionLinkResponse(
            conversation_id=conversation_id,
            execution_id=execution_id,
            copilot_execution_id=state.copilot_execution_id,
            graph_id=graph_id,
            subject_id=subject_id,
            repository_id=state.repository_id,
        )

    async def list_pending_approvals(
        self,
        user_id: str,
        *,
        repository_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PendingApprovalQueueResponse:
        if repository_id:
            await self._check_repo(user_id, repository_id)
        records, total = await self._approvals.list_pending_paginated(
            repository_id=repository_id,
            page=page,
            page_size=page_size,
        )
        if repository_id is None:
            records = [
                record
                for record in records
                if await self._user_can_access_repo(user_id, record.repository_id)
            ]
            total = len(records)
        return PendingApprovalQueueResponse(
            items=[
                PendingApprovalQueueItem(
                    approval_id=record.approval_id,
                    conversation_id=record.conversation_id,
                    repository_id=record.repository_id,
                    tool_name=record.pending.tool_name,
                    risk_level=record.pending.risk_level,
                    reason=record.pending.reason,
                    created_at=record.recorded_at,
                )
                for record in records
            ],
            total=total,
            page=max(1, page),
            page_size=max(1, min(page_size, 100)),
        )

    async def get_conversation_bootstrap(
        self,
        user_id: str,
        conversation_id: str,
    ) -> ConversationBootstrapResponse:
        doc = await self._require_conversation_doc(user_id, conversation_id)
        state = await build_conversation_state(doc=doc, db=await self._database())
        execution_link = await self.get_conversation_execution_link(
            user_id, conversation_id
        )
        execution_status = None
        if execution_link.execution_id:
            execution = await ExecutionRepository(self._db).get_by_execution_id(
                execution_link.execution_id
            )
            if execution is not None:
                execution_status = execution.status.value if execution.status else None
        return ConversationBootstrapResponse(
            conversation=self._conversation_response(doc),
            state=state,
            execution=BootstrapExecutionInfo(
                execution_id=execution_link.execution_id,
                copilot_execution_id=execution_link.copilot_execution_id,
                graph_id=execution_link.graph_id,
                subject_id=execution_link.subject_id,
                repository_id=execution_link.repository_id,
                status=execution_status,
            ),
            knowledge_manifest=doc.get("knowledge_manifest")
            or (doc.get("state") or {}).get("knowledge_manifest")
            or {},
            current_plan=state.current_plan,
            pending_approval=state.pending_approval,
            checkpoint=BootstrapCheckpointInfo(
                checkpoint_id=state.checkpoint_id,
                checkpoint_version=state.checkpoint_version,
                thread_id=state.thread_id,
                last_updated=state.last_updated,
            ),
        )

    async def ask_stream(
        self,
        user_id: str,
        conversation_id: str,
        request: AskQuestionRequest,
        *,
        last_event_id: int = 0,
    ) -> AsyncIterator[Dict[str, Any]]:
        doc = await self._require_conversation_doc(user_id, conversation_id)
        if last_event_id > 0:
            async for replay in self._replay_sse_events(
                conversation_id, last_event_id=last_event_id
            ):
                yield replay
            if not doc.get("stream_active"):
                return

        state = CopilotState.model_validate(doc["state"])
        state.question = request.question.strip()
        if request.question_type:
            state.question_type = request.question_type
        state.focus_node_id = request.focus_node_id
        state.focus_step_id = request.focus_step_id
        state.focus_tool_name = request.focus_tool_name
        if request.enable_live_investigation is not None:
            state.live_investigation_enabled = request.enable_live_investigation
        elif state.question_type == QuestionType.INVESTIGATE_FURTHER:
            state.live_investigation_enabled = True

        await self._checkpoints.set_stream_active(
            conversation_id, active=True, status="running"
        )
        try:
            async for event in self._select_runner().run(state):
                yield await self._persist_sse_event(conversation_id, event, state)
        finally:
            await self._checkpoints.set_stream_active(conversation_id, active=False)

    async def resume_stream(
        self,
        user_id: str,
        conversation_id: str,
        request: ResumeConversationRequest,
        *,
        last_event_id: int = 0,
    ) -> AsyncIterator[Dict[str, Any]]:
        doc = await self._require_conversation_doc(user_id, conversation_id)
        if last_event_id > 0:
            async for replay in self._replay_sse_events(
                conversation_id, last_event_id=last_event_id
            ):
                yield replay
            if not doc.get("stream_active"):
                return

        decision = request.decision.lower()
        if decision not in {d.value for d in ApprovalDecision}:
            raise HTTPException(status_code=400, detail="Invalid approval decision")

        state = CopilotState.model_validate(doc["state"])
        if not state.pending_approval and not state.interrupted:
            raise HTTPException(status_code=409, detail="Conversation is not awaiting approval")

        runner = self._select_runner()
        if not hasattr(runner, "resume"):
            raise HTTPException(status_code=501, detail="Resume requires LangGraph Copilot v2")

        resume_payload = {
            "action": decision,
            "decision": decision,
            "actor_user_id": user_id,
            "modified_tool_args": request.modified_tool_args,
            "admin_confirmed": request.admin_confirmed,
        }
        await self._checkpoints.set_stream_active(
            conversation_id, active=True, status="running"
        )
        try:
            async for event in runner.resume(state, resume_payload):
                yield await self._persist_sse_event(conversation_id, event, state)
        finally:
            await self._checkpoints.set_stream_active(conversation_id, active=False)

    async def reconnect_stream(
        self,
        user_id: str,
        conversation_id: str,
        *,
        last_event_id: int = 0,
        thread_id: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        doc = await self._require_conversation_doc(user_id, conversation_id)
        if thread_id and thread_id != conversation_id:
            raise HTTPException(status_code=400, detail="thread_id mismatch")

        seen = last_event_id
        async for replay in self._replay_sse_events(conversation_id, last_event_id=seen):
            yield replay
            if replay.get("id"):
                seen = int(replay["id"])

        if not doc.get("stream_active"):
            return

        while True:
            await asyncio.sleep(0.25)
            doc = await self._get_checkpoint_doc(conversation_id) or doc
            new_events = await self._sse_events.list_after(
                conversation_id, last_event_id=seen
            )
            for stored in new_events:
                seen = int(stored["event_id"])
                yield {
                    "event": stored["event_type"],
                    "data": stored["data"],
                    "id": seen,
                }
            if not doc.get("stream_active"):
                break

    async def resume_conversation(
        self,
        user_id: str,
        conversation_id: str,
        request: ResumeConversationRequest,
    ) -> ResumeConversationResponse:
        events = []
        async for event in self.resume_stream(user_id, conversation_id, request):
            events.append(event)
        doc = await self._get_checkpoint_doc(conversation_id)
        state = CopilotState.model_validate(doc["state"])
        status = "paused" if state.pending_approval or state.interrupted else "completed"
        return ResumeConversationResponse(
            conversation_id=conversation_id,
            thread_id=conversation_id,
            execution_id=state.copilot_execution_id,
            decision=request.decision,
            status=status,
        )

    async def _database(self) -> Any:
        if self._db is not None:
            return self._db
        from services import mongo_client

        return await mongo_client.get_database()

    async def _user_can_access_repo(self, user_id: str, repository_id: str) -> bool:
        try:
            await self._check_repo(user_id, repository_id)
            return True
        except HTTPException:
            return False

    async def _persist_sse_event(
        self,
        conversation_id: str,
        event: Dict[str, Any],
        state: CopilotState,
    ) -> Dict[str, Any]:
        event_id = await self._sse_events.append(
            conversation_id=conversation_id,
            thread_id=conversation_id,
            event_type=event.get("event", "message"),
            data=event.get("data", {}),
            execution_id=state.copilot_execution_id or state.execution_id,
        )
        return {**event, "id": event_id}

    async def _replay_sse_events(
        self,
        conversation_id: str,
        *,
        last_event_id: int,
    ) -> AsyncIterator[Dict[str, Any]]:
        stored_events = await self._sse_events.list_after(
            conversation_id, last_event_id=last_event_id
        )
        for stored in stored_events:
            yield {
                "event": stored["event_type"],
                "data": stored["data"],
                "id": stored["event_id"],
            }

    async def _get_checkpoint_doc(self, conversation_id: str) -> Optional[dict]:
        db = await self._database()
        return await db[COLLECTION].find_one({"conversation_id": conversation_id})


def format_sse(event: Dict[str, Any]) -> str:
    payload = json.dumps(event.get("data", {}), default=str)
    event_id = event.get("id")
    id_line = f"id: {event_id}\n" if event_id is not None else ""
    return f"{id_line}event: {event.get('event', 'message')}\ndata: {payload}\n\n"


def parse_last_event_id(header_value: Optional[str]) -> int:
    if not header_value:
        return 0
    try:
        return max(0, int(header_value.strip()))
    except ValueError:
        return 0
