"""Repository Knowledge Layer configuration."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel, Field


class KnowledgeSettings(BaseModel):
    collection_assertions: str = "knowledge_assertions"
    default_confidence: float = 0.5
    schema_version: int = 1
    resolver_limit: int = Field(default=20, ge=1, le=100)


@lru_cache
def get_knowledge_settings() -> KnowledgeSettings:
    return KnowledgeSettings(
        collection_assertions=os.getenv(
            "KNOWLEDGE_COLLECTION_ASSERTIONS", "knowledge_assertions"
        ),
        default_confidence=float(os.getenv("KNOWLEDGE_DEFAULT_CONFIDENCE", "0.5")),
        schema_version=int(os.getenv("KNOWLEDGE_SCHEMA_VERSION", "1")),
        resolver_limit=int(os.getenv("KNOWLEDGE_RESOLVER_LIMIT", "20")),
    )
