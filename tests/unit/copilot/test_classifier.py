"""Unit tests for question classifier."""

from copilot.models.enums import QuestionType
from copilot.nodes.question_classifier import classify_question


def test_classify_why_issue_raised():
    q = "Why was this issue raised in the MR review?"
    assert classify_question(q) == QuestionType.WHY_ISSUE_RAISED


def test_classify_why_tool_called():
    q = "Why was gitnexus_analyze tool called during step analyze?"
    assert classify_question(q) == QuestionType.WHY_TOOL_CALLED


def test_classify_what_evidence():
    q = "What evidence led to this conclusion?"
    assert classify_question(q) == QuestionType.WHAT_EVIDENCE


def test_classify_what_alternatives():
    q = "What alternatives were considered instead of posting a comment?"
    assert classify_question(q) == QuestionType.WHAT_ALTERNATIVES


def test_classify_is_finding_correct():
    q = "Is this finding correct?"
    assert classify_question(q) == QuestionType.IS_FINDING_CORRECT


def test_classify_investigate_further():
    q = "Can you investigate this finding further?"
    assert classify_question(q) == QuestionType.INVESTIGATE_FURTHER
