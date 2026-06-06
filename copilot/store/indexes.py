"""MongoDB index definitions for Copilot frontend collections."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from copilot.approval.store import COLLECTION as APPROVALS_COLLECTION
from copilot.checkpoint.langgraph_saver import (
    CHECKPOINTS_COLLECTION as LANGGRAPH_CHECKPOINTS_COLLECTION,
)
from copilot.store.checkpoint_repository import COLLECTION as CHECKPOINTS_COLLECTION
from copilot.store.sse_event_store import COLLECTION as SSE_EVENTS_COLLECTION

IndexSpec = Tuple[str, List[Tuple[str, int]], bool, Dict[str, Any]]


def get_copilot_index_specs() -> List[IndexSpec]:
    return [
        (
            CHECKPOINTS_COLLECTION,
            [("conversation_id", 1)],
            True,
            {"name": "uniq_conversation_id"},
        ),
        (
            CHECKPOINTS_COLLECTION,
            [("repository_id", 1), ("updated_at", -1)],
            False,
            {"name": "idx_repo_updated"},
        ),
        (
            CHECKPOINTS_COLLECTION,
            [("user_id", 1), ("repository_id", 1), ("updated_at", -1)],
            False,
            {"name": "idx_user_repo_updated"},
        ),
        (
            CHECKPOINTS_COLLECTION,
            [("execution_id", 1), ("updated_at", -1)],
            False,
            {"name": "idx_execution_updated"},
        ),
        (
            CHECKPOINTS_COLLECTION,
            [("status", 1), ("repository_id", 1)],
            False,
            {"name": "idx_status_repo"},
        ),
        (
            APPROVALS_COLLECTION,
            [("approval_id", 1)],
            True,
            {"name": "uniq_approval_id"},
        ),
        (
            APPROVALS_COLLECTION,
            [("status", 1), ("repository_id", 1), ("created_at", -1)],
            False,
            {"name": "idx_pending_repo_created"},
        ),
        (
            APPROVALS_COLLECTION,
            [("conversation_id", 1), ("created_at", -1)],
            False,
            {"name": "idx_conversation_created"},
        ),
        (
            SSE_EVENTS_COLLECTION,
            [("conversation_id", 1), ("event_id", 1)],
            True,
            {"name": "uniq_conversation_event_id"},
        ),
        (
            SSE_EVENTS_COLLECTION,
            [("thread_id", 1), ("event_id", 1)],
            False,
            {"name": "idx_thread_event"},
        ),
        (
            LANGGRAPH_CHECKPOINTS_COLLECTION,
            [("thread_id", 1), ("checkpoint_id", -1)],
            False,
            {"name": "idx_thread_checkpoint"},
        ),
    ]


async def ensure_copilot_indexes(db: Any = None) -> Dict[str, int]:
    if db is None:
        from services import mongo_client

        db = await mongo_client.get_database()

    created = 0
    for collection_name, keys, unique, options in get_copilot_index_specs():
        collection = db[collection_name]
        name = options.get("name", "")
        await collection.create_index(keys, unique=unique, name=name)
        created += 1
    return {"indexes_ensured": created}
