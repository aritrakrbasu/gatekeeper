"""Tests for agentic MR webhook helpers."""

from __future__ import annotations

from agents.executor import sanitize_comment_templates
from agents.webhook_mr import _comment_was_posted, _extract_posted_summary


def test_sanitize_comment_templates_resolves_jinja_default():
    text = (
        "Schema Inspection Report:\n"
        "{{run_schema_inspection_step.result.markdown_report | default('Schema inspection could not be performed.')}}"
    )
    resolved = sanitize_comment_templates(
        text,
        {
            "run_schema_inspection_step": {
                "markdown_report": "## Schema OK\nNo drift detected.",
            }
        },
    )
    assert "## Schema OK" in resolved
    assert "{{" not in resolved


def test_sanitize_comment_templates_uses_default_when_step_missing():
    text = "{{missing_step.result.markdown_report | default('fallback message')}}"
    resolved = sanitize_comment_templates(text, {})
    assert resolved == "fallback message"


def test_comment_was_posted_detects_gitlab_note():
    assert _comment_was_posted(
        {"post_step": {"id": 123, "body": "Review complete"}}
    )


def test_extract_posted_summary_reads_body():
    summary = _extract_posted_summary(
        {"post_step": {"id": 1, "body": "### Gatekeeper Review\nAll good."}}
    )
    assert "Gatekeeper Review" in summary
