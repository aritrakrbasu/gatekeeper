"""
Structured logging for ARIL components.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional


_LOGGER = logging.getLogger("gatekeeper.aril")


def get_aril_logger(name: Optional[str] = None) -> logging.Logger:
    if name:
        return _LOGGER.getChild(name)
    return _LOGGER


def _configure_root_once() -> None:
    if _LOGGER.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _LOGGER.addHandler(handler)
    _LOGGER.setLevel(logging.INFO)
    _LOGGER.propagate = False


def log_aril_event(
    event: str,
    *,
    level: int = logging.INFO,
    execution_id: Optional[str] = None,
    task_id: Optional[str] = None,
    subject_id: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Emit a single-line JSON log record for ARIL operations."""
    _configure_root_once()
    payload: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "component": "aril",
        "event": event,
    }
    if execution_id is not None:
        payload["execution_id"] = execution_id
    if task_id is not None:
        payload["task_id"] = task_id
    if subject_id is not None:
        payload["subject_id"] = subject_id
    if extra:
        payload.update(extra)
    _LOGGER.log(level, json.dumps(payload, default=str))
