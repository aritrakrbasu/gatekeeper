"""Copilot collection initialization."""

from __future__ import annotations

from typing import Any, Dict

from copilot.store.indexes import ensure_copilot_indexes


async def initialize_copilot_collections(db: Any = None) -> Dict[str, Any]:
    if db is None:
        from services import mongo_client

        db = await mongo_client.get_database()

    index_summary = await ensure_copilot_indexes(db)
    return {"indexes": index_summary}
