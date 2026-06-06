"""Copilot runtime configuration."""

from __future__ import annotations

import os
from functools import lru_cache


@lru_cache
def is_langgraph_enabled() -> bool:
    return os.getenv("COPILOT_LANGGRAPH_ENABLED", "true").lower() in {
        "1",
        "true",
        "yes",
    }


@lru_cache
def is_v1_fallback_enabled() -> bool:
    return os.getenv("COPILOT_V1_FALLBACK", "false").lower() in {
        "1",
        "true",
        "yes",
    }
