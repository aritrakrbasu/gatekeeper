"""MongoDB persistence for copilot conversation checkpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from copilot.conversation_status import derive_conversation_status
from copilot.models.state import CopilotState

COLLECTION = "copilot_conversation_checkpoints"


class CheckpointRepository:
    def __init__(self, db: Any = None) -> None:
        self._db = db

    async def _database(self) -> Any:
        if self._db is not None:
            return self._db
        from services import mongo_client

        return await mongo_client.get_database()

    async def create_conversation(
        self,
        *,
        user_id: str,
        repository_id: str,
        execution_id: str,
    ) -> CopilotState:
        conversation_id = f"conv-{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        state = CopilotState(
            conversation_id=conversation_id,
            user_id=user_id,
            repository_id=repository_id,
            execution_id=execution_id,
        )
        doc = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "repository_id": repository_id,
            "execution_id": execution_id,
            "state": state.model_dump(mode="json"),
            "checkpoint_version": 0,
            "status": "completed",
            "stream_active": False,
            "pending_approval": False,
            "created_at": now,
            "updated_at": now,
        }
        db = await self._database()
        await db[COLLECTION].insert_one(doc)
        return state

    async def get(self, conversation_id: str) -> Optional[CopilotState]:
        db = await self._database()
        doc = await db[COLLECTION].find_one({"conversation_id": conversation_id})
        if not doc:
            return None
        return CopilotState.model_validate(doc["state"])

    async def save(
        self,
        state: CopilotState,
        *,
        stream_active: Optional[bool] = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        status = derive_conversation_status(
            state,
            stream_active=stream_active if stream_active is not None else False,
        )
        db = await self._database()
        update: Dict[str, Any] = {
            "state": state.model_dump(mode="json"),
            "checkpoint_version": state.checkpoint_version,
            "execution_id": state.execution_id,
            "repository_id": state.repository_id,
            "user_id": state.user_id,
            "knowledge_manifest": state.knowledge_manifest,
            "status": status,
            "pending_approval": bool(state.pending_approval or state.interrupted),
            "updated_at": now,
        }
        if stream_active is not None:
            update["stream_active"] = stream_active
        await db[COLLECTION].update_one(
            {"conversation_id": state.conversation_id},
            {"$set": update},
        )

    async def set_stream_active(
        self,
        conversation_id: str,
        *,
        active: bool,
        status: Optional[str] = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        update: Dict[str, Any] = {
            "stream_active": active,
            "updated_at": now,
        }
        if status is not None:
            update["status"] = status
        db = await self._database()
        await db[COLLECTION].update_one(
            {"conversation_id": conversation_id},
            {"$set": update},
        )

    async def get_doc(self, conversation_id: str) -> Optional[dict]:
        db = await self._database()
        return await db[COLLECTION].find_one({"conversation_id": conversation_id})

    async def list_conversations(
        self,
        *,
        user_id: str,
        repository_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        query: Dict[str, Any] = {"user_id": user_id}
        if repository_id:
            query["repository_id"] = repository_id
        if execution_id:
            query["execution_id"] = execution_id
        if status:
            query["status"] = status

        db = await self._database()
        total = await db[COLLECTION].count_documents(query)
        offset = (page - 1) * page_size
        cursor = (
            db[COLLECTION]
            .find(query)
            .sort("updated_at", -1)
            .skip(offset)
            .limit(page_size)
        )
        if hasattr(cursor, "to_list"):
            items = await cursor.to_list(length=page_size)
        else:
            items = list(cursor)
        return items, total
