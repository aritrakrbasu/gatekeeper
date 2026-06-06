"""peil_subjects repository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pymongo import ReturnDocument

from peil.config import get_aril_settings
from peil.logging import log_aril_event
from peil.models.enums import SubjectType
from peil.models.subject import PeilSubject, PeilSubjectCreate, SubjectRef


class SubjectRepository:
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
        return self._settings.collection_subjects

    async def upsert(self, data: PeilSubjectCreate) -> PeilSubject:
        now = datetime.now(timezone.utc)
        db = await self._database()
        collection = db[self._collection_name]
        existing = await collection.find_one({"subject_id": data.subject_id})
        if existing:
            subject = _subject_from_mongo(existing)
            subject.display_name = data.display_name or subject.display_name
            subject.metadata = data.metadata or subject.metadata
            subject.updated_at = now
        else:
            subject = PeilSubject(
                subject_id=data.subject_id,
                repository_id=data.repository_id,
                subject_ref=data.subject_ref,
                display_name=data.display_name,
                metadata=data.metadata,
                created_at=now,
                updated_at=now,
            )
        await collection.update_one(
            {"subject_id": data.subject_id},
            {"$set": subject.to_mongo()},
            upsert=True,
        )
        log_aril_event(
            "subject_upserted",
            subject_id=subject.subject_id,
            extra={"repository_id": subject.repository_id},
        )
        return subject

    async def get(self, subject_id: str) -> Optional[PeilSubject]:
        db = await self._database()
        doc = await db[self._collection_name].find_one({"subject_id": subject_id})
        if not doc:
            return None
        return _subject_from_mongo(doc)

    async def register_execution(
        self, subject_id: str, execution_id: str
    ) -> Optional[PeilSubject]:
        now = datetime.now(timezone.utc)
        db = await self._database()
        collection = db[self._collection_name]

        # Increment count only when execution_id is newly added to the set.
        result = await collection.find_one_and_update(
            {"subject_id": subject_id, "execution_ids": {"$ne": execution_id}},
            {
                "$addToSet": {"execution_ids": execution_id},
                "$inc": {"execution_count": 1},
                "$set": {
                    "latest_execution_id": execution_id,
                    "updated_at": now,
                },
            },
            return_document=ReturnDocument.AFTER,
        )
        if result:
            subject = _subject_from_mongo(result)
            log_aril_event(
                "subject_execution_registered",
                subject_id=subject_id,
                execution_id=execution_id,
                extra={"new_registration": True},
            )
            return subject

        doc = await collection.find_one({"subject_id": subject_id})
        if not doc:
            return None
        subject = _subject_from_mongo(doc)
        log_aril_event(
            "subject_execution_registered",
            subject_id=subject_id,
            execution_id=execution_id,
            extra={"new_registration": False},
        )
        return subject

    async def find_by_ref(
        self, repository_id: str, subject_ref: SubjectRef
    ) -> Optional[PeilSubject]:
        query = {
            "repository_id": repository_id,
            "subject_ref.type": subject_ref.type.value,
            "subject_ref.id": subject_ref.id,
        }
        if subject_ref.sub_id:
            query["subject_ref.sub_id"] = subject_ref.sub_id
        db = await self._database()
        doc = await db[self._collection_name].find_one(query)
        if not doc:
            return None
        return _subject_from_mongo(doc)


def _subject_from_mongo(doc: dict) -> PeilSubject:
    data = dict(doc)
    data.pop("_id", None)
    if isinstance(data.get("subject_ref"), dict):
        ref = data["subject_ref"]
        if isinstance(ref.get("type"), str):
            ref = dict(ref)
            ref["type"] = SubjectType(ref["type"])
        data["subject_ref"] = SubjectRef.model_validate(ref)
    return PeilSubject.model_validate(data)
