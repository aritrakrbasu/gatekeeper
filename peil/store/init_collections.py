"""
ARIL collection initialization — indexes and GridFS bucket setup.
"""

from __future__ import annotations

from typing import Any, Dict

from motor.motor_asyncio import AsyncIOMotorGridFSBucket

from peil.config import get_aril_settings
from peil.logging import log_aril_event
from peil.store.indexes import ensure_aril_indexes


async def initialize_aril_collections(db: Any = None) -> Dict[str, Any]:
    """
    Initialize ARIL storage primitives.

    - Ensures MongoDB indexes on all ARIL collections
    - Initializes GridFS bucket for evidence (metadata indexes via bucket usage)

    Returns summary dict suitable for health/debug endpoints.
    """
    settings = get_aril_settings()

    if db is None:
        from services import mongo_client
        db = await mongo_client.get_database()

    index_summary = await ensure_aril_indexes(db)

    gridfs_ready = False
    try:
        bucket = AsyncIOMotorGridFSBucket(
            db, bucket_name=settings.evidence_gridfs_bucket
        )
        _ = bucket
        gridfs_ready = True
    except (TypeError, AttributeError) as exc:
        log_aril_event(
            "gridfs_init_skipped",
            level=30,
            extra={"reason": str(exc), "bucket": settings.evidence_gridfs_bucket},
        )

    collections = [
        settings.collection_capture_events,
        settings.collection_executions,
        settings.collection_decision_graphs,
        settings.collection_subjects,
    ]
    existing = await db.list_collection_names()
    present = {name: name in existing for name in collections}

    summary = {
        "indexes": index_summary,
        "collections_present": present,
        "gridfs_bucket": settings.evidence_gridfs_bucket,
        "gridfs_ready": gridfs_ready,
        "schema_version": settings.schema_version,
        "graph_version": settings.graph_version,
        "builder_version": settings.builder_version,
    }
    log_aril_event("collections_initialized", extra=summary)
    return summary
