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


def reconnect_poll_interval_seconds() -> float:
    return float(os.getenv("COPILOT_SSE_POLL_INTERVAL", "0.25"))


def reconnect_max_poll_seconds() -> int:
    return int(os.getenv("COPILOT_SSE_MAX_POLL_SECONDS", "600"))


def stale_stream_timeout_seconds() -> int:
    return int(os.getenv("COPILOT_SSE_STALE_STREAM_SECONDS", "120"))
