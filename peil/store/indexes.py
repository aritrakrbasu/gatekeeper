"""
MongoDB index definitions for ARIL collections.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from peil.config import get_aril_settings
from peil.logging import log_aril_event

IndexSpec = Tuple[str, List[Tuple[str, int]], bool, Dict[str, Any]]


def get_aril_index_specs() -> List[IndexSpec]:
    settings = get_aril_settings()
    return [
        (
            settings.collection_capture_events,
            [("execution_id", 1), ("sequence", 1)],
            True,
            {"name": "uniq_execution_sequence"},
        ),
        (
            settings.collection_capture_events,
            [("execution_id", 1), ("timestamp", 1)],
            False,
            {"name": "idx_execution_timestamp"},
        ),
        (
            settings.collection_capture_events,
            [("partition_key", 1), ("timestamp", -1)],
            False,
            {"name": "idx_partition_timestamp"},
        ),
        (
            settings.collection_capture_events,
            [("task_id", 1)],
            False,
            {"name": "idx_task_id"},
        ),
        (
            settings.collection_executions,
            [("execution_id", 1)],
            True,
            {"name": "uniq_execution_id"},
        ),
        (
            settings.collection_executions,
            [("task_id", 1)],
            True,
            {"name": "uniq_task_id"},
        ),
        (
            settings.collection_executions,
            [("repository_id", 1), ("subject_id", 1), ("created_at", -1)],
            False,
            {"name": "idx_repo_subject_created"},
        ),
        (
            settings.collection_executions,
            [
                ("repository_id", 1),
                ("subject_ref.type", 1),
                ("subject_ref.id", 1),
                ("created_at", -1),
            ],
            False,
            {"name": "idx_repo_subject_ref_created"},
        ),
        (
            settings.collection_executions,
            [("partition_key", 1), ("execution_type", 1)],
            False,
            {"name": "idx_partition_execution_type"},
        ),
        (
            settings.collection_executions,
            [("status", 1)],
            False,
            {"name": "idx_execution_status"},
        ),
        (
            settings.collection_decision_graphs,
            [("graph_id", 1)],
            True,
            {"name": "uniq_graph_id"},
        ),
        (
            settings.collection_decision_graphs,
            [("execution_id", 1), ("graph_revision", 1)],
            True,
            {"name": "uniq_execution_graph_revision"},
        ),
        (
            settings.collection_decision_graphs,
            [("task_id", 1)],
            False,
            {"name": "idx_graph_task_id"},
        ),
        (
            settings.collection_decision_graphs,
            [("repository_id", 1)],
            False,
            {"name": "idx_graph_repository"},
        ),
        (
            settings.collection_decision_graphs,
            [("repository_id", 1), ("metadata.outcome_node_ids", 1)],
            False,
            {"name": "idx_graph_outcome_nodes"},
        ),
        (
            settings.collection_subjects,
            [("subject_id", 1)],
            True,
            {"name": "uniq_subject_id"},
        ),
        (
            settings.collection_subjects,
            [("repository_id", 1), ("subject_ref.type", 1), ("subject_ref.id", 1)],
            False,
            {"name": "idx_subject_repo_ref"},
        ),
        (
            settings.collection_subjects,
            [("latest_execution_id", 1)],
            False,
            {"name": "idx_subject_latest_execution"},
        ),
        (
            settings.collection_evidence_blobs,
            [("content_hash", 1)],
            True,
            {"name": "uniq_evidence_blob_hash"},
        ),
        (
            settings.collection_evidence_blobs,
            [("execution_id", 1)],
            False,
            {"name": "idx_evidence_blob_execution"},
        ),
    ]


def get_gridfs_index_specs() -> List[IndexSpec]:
    settings = get_aril_settings()
    files_collection = f"{settings.evidence_gridfs_bucket}.files"
    return [
        (
            files_collection,
            [("metadata.execution_id", 1)],
            False,
            {"name": "idx_evidence_execution_id"},
        ),
        (
            files_collection,
            [("metadata.content_hash", 1)],
            True,
            {"name": "uniq_evidence_content_hash"},
        ),
    ]


async def ensure_aril_indexes(db: Any = None) -> Dict[str, int]:
    """
    Idempotently create ARIL indexes.

    Args:
        db: Optional Motor database. If omitted, uses services.mongo_client.

    Returns:
        Dict mapping collection name to number of indexes ensured.
    """
    if db is None:
        from services import mongo_client
        db = await mongo_client.get_database()

    created: Dict[str, int] = {}
    for collection_name, keys, unique, options in (
        get_aril_index_specs() + get_gridfs_index_specs()
    ):
        collection = db[collection_name]
        name = options.get("name", "_".join(f"{k}_{d}" for k, d in keys))
        try:
            await collection.create_index(keys, unique=unique, name=name)
            created[collection_name] = created.get(collection_name, 0) + 1
        except Exception as exc:
            log_aril_event(
                "index_create_failed",
                level=40,
                extra={
                    "collection": collection_name,
                    "index": name,
                    "error": str(exc),
                },
            )
    log_aril_event("indexes_ensured", extra={"collections": created})
    return created
