"""Deterministic question type classifier."""

from __future__ import annotations

import re

from copilot.models.enums import QuestionType
from copilot.models.state import CopilotState

_RULES: list[tuple[QuestionType, re.Pattern[str]]] = [
    (
        QuestionType.INVESTIGATE_FURTHER,
        re.compile(
            r"\b(investigate|dig deeper|look into|explore|check (this|it) (further|more))\b",
            re.I,
        ),
    ),
    (
        QuestionType.IS_FINDING_CORRECT,
        re.compile(
            r"\b(is (this|the) (finding|issue|conclusion) (correct|valid|wrong|accurate)|"
            r"should (this|the) (finding|issue) have been raised)\b",
            re.I,
        ),
    ),
    (
        QuestionType.WHY_TOOL_CALLED,
        re.compile(
            r"\b(why (was|did) .*(tool|clone|analyze|gitnexus|comment)|"
            r"why call .*(tool|clone_repo|gitnexus))\b",
            re.I,
        ),
    ),
    (
        QuestionType.WHAT_EVIDENCE,
        re.compile(
            r"\b(what evidence|which evidence|evidence led|proof|supporting data)\b",
            re.I,
        ),
    ),
    (
        QuestionType.WHAT_ALTERNATIVES,
        re.compile(
            r"\b(alternatives?|other options?|could (we|it) have|instead of)\b",
            re.I,
        ),
    ),
    (
        QuestionType.WHY_ISSUE_RAISED,
        re.compile(
            r"\b(why (was|were) (this|the) (issue|finding|comment) raised|"
            r"why flag|reason for (the )?(finding|issue))\b",
            re.I,
        ),
    ),
]


def classify_question(text: str) -> QuestionType:
    for qtype, pattern in _RULES:
        if pattern.search(text):
            return qtype
    return QuestionType.UNKNOWN


async def question_classifier_node(state: CopilotState) -> dict:
    if state.question_type and state.question_type != QuestionType.UNKNOWN:
        classified = state.question_type
    else:
        classified = classify_question(state.question)

    state.question_type = classified
    state.live_investigation_enabled = classified == QuestionType.INVESTIGATE_FURTHER

    if state.focus_tool_name and classified == QuestionType.UNKNOWN:
        state.question_type = QuestionType.WHY_TOOL_CALLED

    return {
        "question_type": classified.value,
        "live_investigation": state.live_investigation_enabled,
    }
