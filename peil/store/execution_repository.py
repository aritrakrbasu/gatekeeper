"""peil_executions repository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from peil.config import get_aril_settings
from peil.logging import log_aril_event
from peil.models.enums import (
    ExecutionSource,
    ExecutionStatus,
    ExecutionType,
    OutcomeProfile,
)
from peil.models.execution import PeilExecution, PeilExecutionCreate
from peil.models.subject import SubjectRef


class ExecutionRepository:
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
        return self._settings.collection_executions

    async def create(self, data: PeilExecutionCreate) -> PeilExecution:
        now = datetime.now(timezone.utc)
        partition_key = data.partition_key or now.strftime("%Y%m")
        execution = PeilExecution(
            execution_id=data.execution_id,
            task_id=data.task_id,
            execution_type=data.execution_type,
            execution_source=data.execution_source,
            repository_id=data.repository_id,
            subject_ref=data.subject_ref,
            subject_id=data.subject_id,
            objective=data.objective,
            context_snapshot=data.context_snapshot,
            parent_execution_id=data.parent_execution_id,
            partition_key=partition_key,
            schema_version=self._settings.schema_version,
            created_at=now,
            updated_at=now,
        )
        db = await self._database()
        collection = db[self._collection_name]
        await collection.insert_one(execution.to_mongo())
        log_aril_event(
            "execution_created",
            execution_id=execution.execution_id,
            task_id=execution.task_id,
            subject_id=execution.subject_id,
        )
        return execution

    async def upsert(self, execution: PeilExecution) -> PeilExecution:
        execution.updated_at = datetime.now(timezone.utc)
        db = await self._database()
        collection = db[self._collection_name]
        await collection.update_one(
            {"execution_id": execution.execution_id},
            {"$set": execution.to_mongo()},
            upsert=True,
        )
        return execution

    async def get_by_execution_id(self, execution_id: str) -> Optional[PeilExecution]:
        db = await self._database()
        doc = await db[self._collection_name].find_one({"execution_id": execution_id})
        if not doc:
            return None
        return _execution_from_mongo(doc)

    async def get_by_task_id(self, task_id: str) -> Optional[PeilExecution]:
        db = await self._database()
        doc = await db[self._collection_name].find_one({"task_id": task_id})
        if not doc:
            return None
        return _execution_from_mongo(doc)

    async def list_by_subject_id_paginated(
        self,
        subject_id: str,
        repository_id: str,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> Tuple[List[PeilExecution], int]:
        query = {"subject_id": subject_id, "repository_id": repository_id}
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
        return [_execution_from_mongo(doc) for doc in docs], total

    async def find_by_subject(
        self,
        repository_id: str,
        subject_ref: SubjectRef,
        *,
        limit: int = 50,
    ) -> List[PeilExecution]:
        query: Dict[str, Any] = {
            "repository_id": repository_id,
            "subject_ref.type": subject_ref.type.value,
            "subject_ref.id": subject_ref.id,
        }
        if subject_ref.sub_id:
            query["subject_ref.sub_id"] = subject_ref.sub_id
        db = await self._database()
        cursor = (
            db[self._collection_name]
            .find(query)
            .sort("created_at", -1)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [_execution_from_mongo(doc) for doc in docs]

    async def update_fields(self, execution_id: str, fields: Dict[str, Any]) -> bool:
        fields = dict(fields)
        fields["updated_at"] = datetime.now(timezone.utc)
        db = await self._database()
        result = await db[self._collection_name].update_one(
            {"execution_id": execution_id},
            {"$set": fields},
        )
        return result.modified_count > 0 or result.matched_count > 0


def _execution_from_mongo(doc: dict) -> PeilExecution:
    data = dict(doc)
    data.pop("_id", None)
    for key, enum_cls in (
        ("execution_type", ExecutionType),
        ("execution_source", ExecutionSource),
        ("status", ExecutionStatus),
        ("outcome_profile", OutcomeProfile),
    ):
        if isinstance(data.get(key), str):
            data[key] = enum_cls(data[key])
    if isinstance(data.get("subject_ref"), dict):
        ref = data["subject_ref"]
        if isinstance(ref.get("type"), str):
            from peil.models.enums import SubjectType
            ref["type"] = SubjectType(ref["type"])
        data["subject_ref"] = SubjectRef.model_validate(ref)
    return PeilExecution.model_validate(data)
"""peil_executions repository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from peil.config import get_aril_settings
from peil.logging import log_aril_event
from peil.models.enums import (
    ExecutionSource,
    ExecutionStatus,
    ExecutionType,
    OutcomeProfile,
)
from peil.models.execution import PeilExecution, PeilExecutionCreate
from peil.models.subject import SubjectRef


class ExecutionRepository:
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
        return self._settings.collection_executions

    async def create(self, data: PeilExecutionCreate) -> PeilExecution:
        now = datetime.now(timezone.utc)
        partition_key = data.partition_key or now.strftime("%Y%m")
        execution = PeilExecution(
            execution_id=data.execution_id,
            task_id=data.task_id,
            execution_type=data.execution_type,
            execution_source=data.execution_source,
            repository_id=data.repository_id,
            subject_ref=data.subject_ref,
            subject_id=data.subject_id,
            objective=data.objective,
            context_snapshot=data.context_snapshot,
            parent_execution_id=data.parent_execution_id,
            partition_key=partition_key,
            schema_version=self._settings.schema_version,
            created_at=now,
            updated_at=now,
        )
        db = await self._database()
        collection = db[self._collection_name]
        await collection.insert_one(execution.to_mongo())
        log_aril_event(
            "execution_created",
            execution_id=execution.execution_id,
            task_id=execution.task_id,
            subject_id=execution.subject_id,
        )
        return execution

    async def upsert(self, execution: PeilExecution) -> PeilExecution:
        execution.updated_at = datetime.now(timezone.utc)
        db = await self._database()
        collection = db[self._collection_name]
        await collection.update_one(
            {"execution_id": execution.execution_id},
            {"$set": execution.to_mongo()},
            upsert=True,
        )
        return execution

    async def get_by_execution_id(self, execution_id: str) -> Optional[PeilExecution]:
        db = await self._database()
        doc = await db[self._collection_name].find_one({"execution_id": execution_id})
        if not doc:
            return None
        return _execution_from_mongo(doc)

    async def get_by_task_id(self, task_id: str) -> Optional[PeilExecution]:
        db = await self._database()
        doc = await db[self._collection_name].find_one({"task_id": task_id})
        if not doc:
            return None
        return _execution_from_mongo(doc)

    async def list_by_subject_id_paginated(
        self,
        subject_id: str,
        repository_id: str,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> Tuple[List[PeilExecution], int]:
        query = {"subject_id": subject_id, "repository_id": repository_id}
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
        return [_execution_from_mongo(doc) for doc in docs], total

    async def find_by_subject(
        self,
        repository_id: str,
        subject_ref: SubjectRef,
        *,
        limit: int = 50,
    ) -> List[PeilExecution]:
        query: Dict[str, Any] = {
            "repository_id": repository_id,
            "subject_ref.type": subject_ref.type.value,
            "subject_ref.id": subject_ref.id,
        }
        if subject_ref.sub_id:
            query["subject_ref.sub_id"] = subject_ref.sub_id
        db = await self._database()
        cursor = (
            db[self._collection_name]
            .find(query)
            .sort("created_at", -1)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [_execution_from_mongo(doc) for doc in docs]

    async def update_fields(self, execution_id: str, fields: Dict[str, Any]) -> bool:
        fields = dict(fields)
        fields["updated_at"] = datetime.now(timezone.utc)
        db = await self._database()
        result = await db[self._collection_name].update_one(
            {"execution_id": execution_id},
            {"$set": fields},
        )
        return result.modified_count > 0 or result.matched_count > 0


def _execution_from_mongo(doc: dict) -> PeilExecution:
    data = dict(doc)
    data.pop("_id", None)
    for key, enum_cls in (
        ("execution_type", ExecutionType),
        ("execution_source", ExecutionSource),
        ("status", ExecutionStatus),
        ("outcome_profile", OutcomeProfile),
    ):
        if isinstance(data.get(key), str):
            data[key] = enum_cls(data[key])
    if isinstance(data.get("subject_ref"), dict):
        ref = data["subject_ref"]
        if isinstance(ref.get("type"), str):
            from peil.models.enums import SubjectType
            ref["type"] = SubjectType(ref["type"])
        data["subject_ref"] = SubjectRef.model_validate(ref)
    completed_at = data.get("completed_at")
    if isinstance(completed_at, datetime):
        data["completed_at"] = completed_at.isoformat()
    return PeilExecution.model_validate(data)
