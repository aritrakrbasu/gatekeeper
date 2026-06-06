"""Mongo-backed LangGraph checkpointer (thread_id = conversation_id)."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
)
from langgraph.checkpoint.memory import MemorySaver

CHECKPOINTS_COLLECTION = "copilot_langgraph_checkpoints"
WRITES_COLLECTION = "copilot_langgraph_writes"


async def _async_iter_find(collection: Any, query: Dict[str, Any]):
    """Iterate find() results for motor and FakeCollection."""
    cursor = collection.find(query)
    if hasattr(cursor, "to_list"):
        for doc in await cursor.to_list(length=None):
            yield doc
        return
    if hasattr(cursor, "__aiter__"):
        async for doc in cursor:
            yield doc
        return
    if hasattr(cursor, "docs"):
        for doc in cursor.docs:
            yield doc
        return
    for doc in cursor:
        yield doc


class MongoLangGraphSaver(MemorySaver):
    """LangGraph checkpointer with Mongo durability and in-memory hot path."""

    def __init__(self, db: Any = None) -> None:
        super().__init__()
        self._db = db

    async def _database(self) -> Any:
        if self._db is not None:
            return self._db
        from services import mongo_client

        return await mongo_client.get_database()

    async def aget_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        cached = self.get_tuple(config)
        if cached is not None:
            return cached
        return await self._load_tuple_from_mongo(config)

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, str | int | float],
    ) -> RunnableConfig:
        result = self.put(config, checkpoint, metadata, new_versions)
        await self._mirror_checkpoint(config, checkpoint, metadata)
        return result

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: list[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        self.put_writes(config, writes, task_id, task_path)
        await self._mirror_writes(config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id: str) -> None:
        self.delete_thread(thread_id)
        db = await self._database()
        await db[CHECKPOINTS_COLLECTION].update_many(
            {"thread_id": thread_id},
            {"$set": {"deleted": True, "deleted_at": datetime.now(timezone.utc)}},
        )
        await db[WRITES_COLLECTION].update_many(
            {"thread_id": thread_id},
            {"$set": {"deleted": True, "deleted_at": datetime.now(timezone.utc)}},
        )

    async def _mirror_checkpoint(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
    ) -> None:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        parent_checkpoint_id = config["configurable"].get("checkpoint_id")
        doc = {
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_ns,
            "checkpoint_id": checkpoint["id"],
            "parent_checkpoint_id": parent_checkpoint_id,
            "checkpoint": copy.deepcopy(checkpoint),
            "metadata": dict(metadata),
            "updated_at": datetime.now(timezone.utc),
            "deleted": False,
        }
        db = await self._database()
        await db[CHECKPOINTS_COLLECTION].update_one(
            {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint["id"],
            },
            {"$set": doc},
            upsert=True,
        )

    async def _mirror_writes(
        self,
        config: RunnableConfig,
        writes: list[tuple[str, Any]],
        task_id: str,
        task_path: str,
    ) -> None:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"]["checkpoint_id"]
        now = datetime.now(timezone.utc)
        db = await self._database()
        for idx, (channel, value) in enumerate(writes):
            await db[WRITES_COLLECTION].update_one(
                {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                    "task_id": task_id,
                    "idx": idx,
                },
                {
                    "$set": {
                        "channel": channel,
                        "value": value,
                        "task_path": task_path,
                        "updated_at": now,
                        "deleted": False,
                    }
                },
                upsert=True,
            )

    async def _load_tuple_from_mongo(
        self, config: RunnableConfig
    ) -> Optional[CheckpointTuple]:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = get_checkpoint_id(config)
        db = await self._database()
        query: Dict[str, Any] = {
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_ns,
            "deleted": {"$ne": True},
        }
        if checkpoint_id:
            query["checkpoint_id"] = checkpoint_id
        if checkpoint_id:
            doc = await db[CHECKPOINTS_COLLECTION].find_one(query)
        else:
            docs = [
                d
                async for d in _async_iter_find(db[CHECKPOINTS_COLLECTION], query)
            ]
            doc = max(docs, key=lambda d: d["checkpoint_id"]) if docs else None
        if doc is None:
            return None
        checkpoint = doc["checkpoint"]
        metadata = doc.get("metadata", {})
        parent_checkpoint_id = doc.get("parent_checkpoint_id")
        return CheckpointTuple(
            config={
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": doc["checkpoint_id"],
                }
            },
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=(
                {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": parent_checkpoint_id,
                    }
                }
                if parent_checkpoint_id
                else None
            ),
        )
