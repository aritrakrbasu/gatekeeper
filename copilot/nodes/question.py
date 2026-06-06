"""Question intake node."""

from __future__ import annotations

import re

from copilot.models.state import CopilotState

_ASSERTION_PATTERNS = [
    re.compile(r"\bthe (finding|issue|bug) is (correct|wrong|valid|invalid)\b", re.I),
    re.compile(r"\bthis (definitely|clearly) (is|was)\b", re.I),
    re.compile(r"\byou (must|should) have\b", re.I),
    re.compile(r"\bwithout (any )?evidence\b", re.I),
]


async def question_node(state: CopilotState) -> dict:
    text = (state.question or "").strip()
    if not text:
        raise ValueError("Question is required")

    assertions: list[str] = []
    for pattern in _ASSERTION_PATTERNS:
        if pattern.search(text):
            assertions.append(pattern.pattern)

    state.user_assertions_detected = assertions
    return {
        "question_length": len(text),
        "assertions_detected": len(assertions),
    }
