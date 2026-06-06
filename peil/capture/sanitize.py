"""Sanitization helpers for capture payloads and evidence."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Union

_SENSITIVE_KEY_FRAGMENTS = frozenset(
    {"token", "password", "secret", "auth", "jwt", "credential", "api_key", "apikey"}
)

_GITLAB_TOKEN_RE = re.compile(r"glpat-[a-zA-Z0-9_\-]{20,}")
_GEMINI_KEY_RE = re.compile(r"AIzaSy[a-zA-Z0-9_\-]{33}")
_MONGODB_URI_RE = re.compile(r"mongodb(?:\+srv)?://[^\s\n]+", re.IGNORECASE)
_BEARER_RE = re.compile(r"bearer\s+[a-zA-Z0-9_\-\.]+", re.IGNORECASE)


def _key_is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in _SENSITIVE_KEY_FRAGMENTS)


def mask_sensitive_arguments(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively mask sensitive dict keys (compatible with agents/observability)."""
    masked: Dict[str, Any] = {}
    for key, value in arguments.items():
        if _key_is_sensitive(key):
            masked[key] = "[MASKED]"
        elif isinstance(value, dict):
            masked[key] = mask_sensitive_arguments(value)
        elif isinstance(value, list):
            masked[key] = [
                mask_sensitive_arguments(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            masked[key] = value
    return masked


def sanitize_text(text: str) -> str:
    """Mask credentials and secrets in free-form text."""
    if not text:
        return ""
    text = _GITLAB_TOKEN_RE.sub("[MASKED_GITLAB_TOKEN]", text)
    text = _GEMINI_KEY_RE.sub("[MASKED_GEMINI_KEY]", text)
    text = _MONGODB_URI_RE.sub("mongodb+srv://[MASKED_USER]:[MASKED_PWD]@[MASKED_HOST]", text)
    text = _BEARER_RE.sub("Bearer [MASKED_BEARER_TOKEN]", text)
    return text


def sanitize_payload_value(value: Any) -> Any:
    """Sanitize nested payload values for capture events."""
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, dict):
        return mask_sensitive_arguments(value)
    if isinstance(value, list):
        return [sanitize_payload_value(item) for item in value]
    return value


def sanitize_event_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    masked = mask_sensitive_arguments(payload)
    return {k: sanitize_payload_value(v) for k, v in masked.items()}
