"""knowledge_assertions MongoDB repository."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from fastapi import HTTPException

from knowledge.config import get_knowledge_settings
from knowledge.models.assertion import (
    AssertionAuditEntry,
    AssertionProvenance,
    KnowledgeAssertion,
    KnowledgeAssertionCreate,
)
from knowledge.models.enums import AssertionStatus, AuditAction


def _assertion_id(repository_id: str, execution_id: str, statement: str) -> str:
    digest = hashlib.sha256(
        f"{repository_id}:{execution_id}:{statement}".encode()
    ).hexdigest()[:16]
    return f"assert-{digest}"


def _from_mongo(doc: Dict[str, Any]) -> KnowledgeAssertion:
    return KnowledgeAssertion.model_validate(doc)


class AssertionRepository:
    def __init__(self, db: Any = None) -> None:
        self._db = db
        self._settings = get_knowledge_settings()

    async def _database(self) -> Any:
        if self._db is not None:
            return self._db
        from services import mongo_client

        return await mongo_client.get_database()

    @property
    def _collection_name(self) -> str:
        return self._settings.collection_assertions

    async def propose(
        self,
        data: KnowledgeAssertionCreate,
        *,
        proposed_by_user_id: str,
    ) -> KnowledgeAssertion:
        """Create a proposed assertion. Never auto-accepts."""
        now = datetime.now(timezone.utc)
        assertion_id = _assertion_id(
            data.repository_id, data.source_execution_id, data.statement
        )

        db = await self._database()
        collection = db[self._collection_name]
        existing = await collection.find_one({"assertion_id": assertion_id})
        if existing is not None:
            return _from_mongo(existing)

        provenance = AssertionProvenance(
            execution_id=data.source_execution_id,
            conversation_id=data.source_conversation_id,
            graph_id=data.graph_id,
            graph_hash=data.graph_hash,
            replay_reference=data.replay_reference
            or f"replay:{data.source_execution_id}",
        )
        audit = AssertionAuditEntry(
            action=AuditAction.PROPOSED,
            actor_user_id=proposed_by_user_id,
            timestamp=now,
            detail={"source": data.metadata.get("source", "api")},
        )
        assertion = KnowledgeAssertion(
            assertion_id=assertion_id,
            repository_id=data.repository_id,
            source_execution_id=data.source_execution_id,
            source_conversation_id=data.source_conversation_id,
            type=data.type,
            statement=data.statement,
            evidence_refs=list(data.evidence_refs),
            confidence=data.confidence,
            status=AssertionStatus.PROPOSED,
            graph_id=data.graph_id,
            graph_hash=data.graph_hash,
            replay_reference=provenance.replay_reference,
            provenance=provenance,
            proposed_by_user_id=proposed_by_user_id,
            audit_trail=[audit],
            metadata=data.metadata,
            schema_version=self._settings.schema_version,
            created_at=now,
            updated_at=now,
        )
        await collection.insert_one(assertion.to_mongo())
        return assertion

    async def get_by_id(self, assertion_id: str) -> Optional[KnowledgeAssertion]:
        db = await self._database()
        doc = await db[self._collection_name].find_one({"assertion_id": assertion_id})
        if doc is None:
            return None
        return _from_mongo(doc)

    async def list_paginated(
        self,
        repository_id: str,
        *,
        status: Optional[AssertionStatus] = None,
        assertion_type: Optional[str] = None,
        source_execution_id: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> Tuple[List[KnowledgeAssertion], int]:
        query: Dict[str, Any] = {"repository_id": repository_id}
        if status is not None:
            query["status"] = status.value
        if assertion_type is not None:
            query["type"] = assertion_type
        if source_execution_id is not None:
            query["source_execution_id"] = source_execution_id

        db = await self._database()
        collection = db[self._collection_name]
        total = await collection.count_documents(query)
        cursor = (
            collection.find(query)
            .sort("created_at", -1)
            .skip(max(0, offset))
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [_from_mongo(doc) for doc in docs], total

    async def _review(
        self,
        assertion_id: str,
        *,
        new_status: AssertionStatus,
        actor_user_id: str,
        reason: Optional[str] = None,
    ) -> KnowledgeAssertion:
        assertion = await self.get_by_id(assertion_id)
        if assertion is None:
            raise HTTPException(status_code=404, detail="Assertion not found")

        if assertion.status != AssertionStatus.PROPOSED:
            raise HTTPException(
                status_code=409,
                detail=f"Assertion already {assertion.status.value}; human review closed",
            )

        now = datetime.now(timezone.utc)
        action = (
            AuditAction.ACCEPTED
            if new_status == AssertionStatus.ACCEPTED
            else AuditAction.REJECTED
        )
        audit = AssertionAuditEntry(
            action=action,
            actor_user_id=actor_user_id,
            timestamp=now,
            detail={"reason": reason} if reason else {},
        )

        db = await self._database()
        collection = db[self._collection_name]
        await collection.update_one(
            {"assertion_id": assertion_id, "status": AssertionStatus.PROPOSED.value},
            {
                "$set": {
                    "status": new_status.value,
                    "reviewed_by_user_id": actor_user_id,
                    "reviewed_at": now,
                    "updated_at": now,
                },
                "$push": {"audit_trail": audit.model_dump(mode="json")},
            },
        )

        updated = await self.get_by_id(assertion_id)
        if updated is None or updated.status != new_status:
            raise HTTPException(
                status_code=409,
                detail="Assertion review failed; status may have changed concurrently",
            )
        return updated

    async def accept(
        self,
        assertion_id: str,
        *,
        actor_user_id: str,
        reason: Optional[str] = None,
    ) -> KnowledgeAssertion:
        return await self._review(
            assertion_id,
            new_status=AssertionStatus.ACCEPTED,
            actor_user_id=actor_user_id,
            reason=reason,
        )

    async def reject(
        self,
        assertion_id: str,
        *,
        actor_user_id: str,
        reason: Optional[str] = None,
    ) -> KnowledgeAssertion:
        return await self._review(
            assertion_id,
            new_status=AssertionStatus.REJECTED,
            actor_user_id=actor_user_id,
            reason=reason,
        )
