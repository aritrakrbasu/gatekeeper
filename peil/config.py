"""
ARIL feature flags and runtime configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class ArilSettings:
    """Environment-driven ARIL configuration."""

    capture_enabled: bool = True
    evidence_inline_max_bytes: int = 32768
    event_flush_batch_size: int = 10
    graph_build_on_pause: bool = True
    evidence_gridfs_bucket: str = "peil_evidence"
    schema_version: int = 1
    graph_version: int = 1
    builder_version: str = "graph_builder_v1"

    collection_capture_events: str = "peil_capture_events"
    collection_executions: str = "peil_executions"
    collection_decision_graphs: str = "peil_decision_graphs"
    collection_subjects: str = "peil_subjects"
    collection_evidence_blobs: str = "peil_evidence_blobs"
    capture_via_registry: bool = True


@lru_cache
def get_aril_settings() -> ArilSettings:
    return ArilSettings(
        capture_enabled=_env_bool("ARIL_CAPTURE_ENABLED", True),
        evidence_inline_max_bytes=_env_int("ARIL_EVIDENCE_INLINE_MAX_BYTES", 32768),
        event_flush_batch_size=_env_int("ARIL_EVENT_FLUSH_BATCH_SIZE", 10),
        graph_build_on_pause=_env_bool("ARIL_GRAPH_BUILD_ON_PAUSE", True),
        evidence_gridfs_bucket=os.getenv("ARIL_EVIDENCE_GRIDFS_BUCKET", "peil_evidence"),
        schema_version=_env_int("ARIL_SCHEMA_VERSION", 1),
        graph_version=_env_int("ARIL_GRAPH_VERSION", 1),
        builder_version=os.getenv("ARIL_BUILDER_VERSION", "graph_builder_v1"),
        collection_capture_events=os.getenv("ARIL_COLLECTION_CAPTURE_EVENTS", "peil_capture_events"),
        collection_executions=os.getenv("ARIL_COLLECTION_EXECUTIONS", "peil_executions"),
        collection_decision_graphs=os.getenv("ARIL_COLLECTION_DECISION_GRAPHS", "peil_decision_graphs"),
        collection_subjects=os.getenv("ARIL_COLLECTION_SUBJECTS", "peil_subjects"),
        collection_evidence_blobs=os.getenv(
            "ARIL_COLLECTION_EVIDENCE_BLOBS", "peil_evidence_blobs"
        ),
        capture_via_registry=_env_bool("ARIL_CAPTURE_VIA_REGISTRY", True),
    )


def is_capture_enabled() -> bool:
    return get_aril_settings().capture_enabled
