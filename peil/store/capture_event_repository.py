"""peil_capture_events repository."""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from peil.config import get_aril_settings
from peil.logging import log_aril_event
from peil.models.enums import CaptureEventType
from peil.models.events import CaptureEvent


class CaptureEventRepository:
    def __init__(self, db: Any = None) -> None:
        self._db = db
        self._settings = get_aril_settings()

    async def _database(self) -> Any:
        if self._db is not None:
            return self._db
        from services import mongo_client
        return await mongo_client.get_database()

    @property
    def _collection_name(self) -> str:
        return self._settings.collection_capture_events

    async def append_events(self, events: List[CaptureEvent]) -> int:
        if not events:
            return 0
        db = await self._database()
        collection = db[self._collection_name]
        docs = [event.to_mongo() for event in events]
        result = await collection.insert_many(docs, ordered=True)
        count = len(result.inserted_ids)
        log_aril_event(
            "capture_events_persisted",
            execution_id=events[0].execution_id,
            task_id=events[0].task_id,
            extra={"count": count},
        )
        return count

    async def get_max_sequence(self, execution_id: str) -> int:
        """Return the highest persisted sequence for an execution (0 if none)."""
        db = await self._database()
        collection = db[self._collection_name]
        cursor = (
            collection.find({"execution_id": execution_id})
            .sort("sequence", -1)
            .limit(1)
        )
        docs = await cursor.to_list(length=1)
        if not docs:
            return 0
        return int(docs[0].get("sequence", 0))

    async def count_by_execution_id(self, execution_id: str) -> int:
        db = await self._database()
        collection = db[self._collection_name]
        return await collection.count_documents({"execution_id": execution_id})

    async def list_paginated(
        self,
        execution_id: str,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> Tuple[List[CaptureEvent], int]:
        db = await self._database()
        collection = db[self._collection_name]
        query = {"execution_id": execution_id}
        total = await collection.count_documents(query)
        cursor = (
            collection.find(query)
            .sort("sequence", 1)
            .skip(max(0, offset))
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [_capture_event_from_mongo(doc) for doc in docs], total

    async def list_by_execution_id(
        self,
        execution_id: str,
        *,
        limit: Optional[int] = None,
    ) -> List[CaptureEvent]:
        items, _ = await self.list_paginated(
            execution_id,
            offset=0,
            limit=limit or 10_000,
        )
        return items


def _capture_event_from_mongo(doc: dict) -> CaptureEvent:
    data = dict(doc)
    data.pop("_id", None)
    if isinstance(data.get("event_type"), str):
        data["event_type"] = CaptureEventType(data["event_type"])
    return CaptureEvent.model_validate(data)
