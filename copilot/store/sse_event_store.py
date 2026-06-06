"""Persist Copilot SSE events for reconnection."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

COLLECTION = "copilot_sse_events"


class SseEventStore:
    def __init__(self, db: Any = None) -> None:
        self._db = db

    async def _database(self) -> Any:
        if self._db is not None:
            return self._db
        from services import mongo_client

        return await mongo_client.get_database()

    async def append(
        self,
        *,
        conversation_id: str,
        thread_id: str,
        event_type: str,
        data: Dict[str, Any],
        execution_id: Optional[str] = None,
    ) -> int:
        db = await self._database()
        cursor = (
            db[COLLECTION]
            .find({"conversation_id": conversation_id})
            .sort("event_id", -1)
            .limit(1)
        )
        if hasattr(cursor, "to_list"):
            latest = await cursor.to_list(length=1)
        elif hasattr(cursor, "docs"):
            latest = cursor.docs[:1]
        else:
            latest = list(cursor)[:1]
        next_id = 1 if not latest else int(latest[0].get("event_id", 0)) + 1

        doc = {
            "conversation_id": conversation_id,
            "thread_id": thread_id,
            "event_id": next_id,
            "event_type": event_type,
            "data": data,
            "execution_id": execution_id,
            "created_at": datetime.now(timezone.utc),
        }
        await db[COLLECTION].insert_one(doc)
        return next_id

    async def list_after(
        self,
        conversation_id: str,
        *,
        last_event_id: int = 0,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        db = await self._database()
        cursor = (
            db[COLLECTION]
            .find(
                {
                    "conversation_id": conversation_id,
                    "event_id": {"$gt": last_event_id},
                }
            )
            .sort("event_id", 1)
            .limit(limit)
        )
        if hasattr(cursor, "to_list"):
            return await cursor.to_list(length=limit)
        if hasattr(cursor, "docs"):
            return [
                doc
                for doc in cursor.docs
                if int(doc.get("event_id", 0)) > last_event_id
            ][:limit]
        return list(cursor)

    async def get_last_event_id(self, conversation_id: str) -> int:
        db = await self._database()
        cursor = (
            db[COLLECTION]
            .find({"conversation_id": conversation_id})
            .sort("event_id", -1)
            .limit(1)
        )
        if hasattr(cursor, "to_list"):
            docs = await cursor.to_list(length=1)
        elif hasattr(cursor, "docs"):
            docs = cursor.docs[:1]
        else:
            docs = list(cursor)[:1]
        if not docs:
            return 0
        return int(docs[0].get("event_id", 0))
