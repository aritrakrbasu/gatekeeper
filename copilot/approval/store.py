"""Persist Copilot approval decisions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

from copilot.models.approval import (
    ApprovalDecision,
    ApprovalRecord,
    ApprovalStatus,
    PendingApproval,
)

COLLECTION = "copilot_approvals"


class CopilotApprovalStore:
    def __init__(self, db: Any = None) -> None:
        self._db = db

    async def _database(self) -> Any:
        if self._db is not None:
            return self._db
        from services import mongo_client

        return await mongo_client.get_database()

    async def record(self, approval: ApprovalRecord) -> None:
        payload = approval.model_dump(mode="json")
        payload["status"] = ApprovalStatus.RESOLVED.value
        db = await self._database()
        await db[COLLECTION].insert_one(payload)

    async def record_pending(
        self,
        *,
        conversation_id: str,
        repository_id: str,
        pending: PendingApproval,
        copilot_execution_id: Optional[str] = None,
    ) -> str:
        db = await self._database()
        existing = await self._latest_pending_doc(conversation_id)
        if existing is not None:
            approval_id = existing["approval_id"]
            await db[COLLECTION].update_one(
                {"approval_id": approval_id},
                {
                    "$set": {
                        "repository_id": repository_id,
                        "copilot_execution_id": copilot_execution_id,
                        "pending": pending.model_dump(mode="json"),
                        "recorded_at": datetime.now(timezone.utc),
                    }
                },
            )
            return approval_id

        record = ApprovalRecord(
            conversation_id=conversation_id,
            repository_id=repository_id,
            copilot_execution_id=copilot_execution_id,
            status=ApprovalStatus.PENDING,
            pending=pending,
        )
        await db[COLLECTION].insert_one(record.model_dump(mode="json"))
        return record.approval_id

    async def resolve_pending(
        self,
        conversation_id: str,
        *,
        decision: ApprovalDecision,
        actor_user_id: str,
        pending: PendingApproval,
        copilot_execution_id: Optional[str] = None,
        repository_id: str = "",
        modified_tool_args: Optional[dict] = None,
        admin_confirmed: bool = False,
    ) -> str:
        db = await self._database()
        pending_doc = await self._latest_pending_doc(conversation_id)
        approval_id = (
            pending_doc.get("approval_id")
            if pending_doc
            else f"appr-resolved-{conversation_id}"
        )
        now = datetime.now(timezone.utc)
        resolved = ApprovalRecord(
            approval_id=approval_id,
            conversation_id=conversation_id,
            repository_id=repository_id or (pending_doc or {}).get("repository_id", ""),
            copilot_execution_id=copilot_execution_id,
            status=ApprovalStatus.RESOLVED,
            decision=decision,
            actor_user_id=actor_user_id,
            pending=pending,
            modified_tool_args=modified_tool_args,
            admin_confirmed=admin_confirmed,
            recorded_at=now,
        )
        if pending_doc:
            await db[COLLECTION].update_one(
                {"approval_id": approval_id},
                {"$set": resolved.model_dump(mode="json")},
            )
        else:
            await db[COLLECTION].insert_one(resolved.model_dump(mode="json"))
        return approval_id

    async def list_pending_paginated(
        self,
        *,
        repository_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[ApprovalRecord], int]:
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        query: dict = {"status": ApprovalStatus.PENDING.value}
        if repository_id:
            query["repository_id"] = repository_id

        db = await self._database()
        total = await db[COLLECTION].count_documents(query)
        offset = (page - 1) * page_size
        cursor = (
            db[COLLECTION]
            .find(query)
            .sort("recorded_at", -1)
            .skip(offset)
            .limit(page_size)
        )
        if hasattr(cursor, "to_list"):
            docs = await cursor.to_list(length=page_size)
        else:
            docs = list(cursor)
        return [ApprovalRecord.model_validate(doc) for doc in docs], total

    async def list_for_conversation(self, conversation_id: str) -> List[ApprovalRecord]:
        db = await self._database()
        docs = [
            doc
            async for doc in _iter_find(
                db[COLLECTION], {"conversation_id": conversation_id}
            )
        ]
        return [ApprovalRecord.model_validate(doc) for doc in docs]

    async def _latest_pending_doc(self, conversation_id: str) -> Optional[dict]:
        db = await self._database()
        cursor = (
            db[COLLECTION]
            .find({"conversation_id": conversation_id, "status": ApprovalStatus.PENDING.value})
            .sort("recorded_at", -1)
            .limit(1)
        )
        if hasattr(cursor, "to_list"):
            docs = await cursor.to_list(length=1)
            return docs[0] if docs else None
        if hasattr(cursor, "docs"):
            return cursor.docs[0] if cursor.docs else None
        docs = list(cursor)
        return docs[0] if docs else None


async def _iter_find(collection: Any, query: dict):
    cursor = collection.find(query)
    if hasattr(cursor, "to_list"):
        for doc in await cursor.to_list(length=None):
            yield doc
        return
    if hasattr(cursor, "docs"):
        for doc in cursor.docs:
            yield doc
        return
    for doc in cursor:
        yield doc
