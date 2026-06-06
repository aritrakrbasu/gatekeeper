"""Agentic GitLab MR webhook orchestration with UI persistence."""

from __future__ import annotations

from typing import Any, Dict, Optional

from agents.context import ContextBuilder
from agents.engine import WorkflowEngine
from agents.registry import build_default_registry
from services import repository_service, review_service


async def run_agentic_mr_webhook(payload: dict) -> dict:
    """
    Run agentic MR review for a GitLab webhook and persist MR state for the frontend.
    """
    ingest = await review_service.ingest_mr_from_webhook(payload)
    if ingest.get("skipped"):
        return {"status": ingest.get("reason", "skipped"), **ingest}

    project_id = ingest["project_id"]
    mr_iid = ingest["mr_iid"]

    try:
        await repository_service.add_mr_progress_log(
            repo_id=project_id,
            mr_iid=mr_iid,
            step="agentic_review",
            message="Starting agentic merge request review",
            status="running",
        )
        await repository_service.update_mr_analysis(
            project_id,
            mr_iid,
            {"status": "reviewing", "analysis_status": "in_progress"},
        )
    except Exception as exc:
        print(f"[WARN] [Agentic MR] Failed to update MR progress: {exc}")

    context = ContextBuilder.build_from_gitlab_mr(payload)
    engine = WorkflowEngine(await build_default_registry())
    print(f"[INFO] [Agentic Mode] Executing agentic workflow for Merge Request: {context.task_id}")
    result = await engine.run_task(context)

    await _finalize_mr_ui_state(project_id, mr_iid, result)
    return result


async def _finalize_mr_ui_state(
    project_id: str,
    mr_iid: int,
    result: Dict[str, Any],
) -> None:
    """Map workflow terminal status to merge_requests collection fields."""
    workflow_status = result.get("status", "failed")
    step_results = result.get("results") or {}
    comment_posted = _comment_was_posted(step_results)

    if workflow_status == "completed" or comment_posted:
        analysis_status = "completed"
        mr_status = "reviewed"
        log_status = "completed"
        log_message = "Agentic review completed"
        if workflow_status != "completed":
            log_message = "Agentic review posted summary (workflow ended with partial completion)"
    else:
        analysis_status = "error"
        mr_status = "failed"
        log_status = "failed"
        log_message = result.get("error") or "Agentic review failed"

    ai_summary = _extract_posted_summary(step_results)

    try:
        update_fields: Dict[str, Any] = {
            "status": mr_status,
            "analysis_status": analysis_status,
        }
        if ai_summary:
            update_fields["ai_summary"] = ai_summary
        await repository_service.update_mr_analysis(project_id, mr_iid, update_fields)
        await repository_service.add_mr_progress_log(
            repo_id=project_id,
            mr_iid=mr_iid,
            step="agentic_review",
            message=log_message,
            status=log_status,
        )
    except Exception as exc:
        print(f"[WARN] [Agentic MR] Failed to finalize MR UI state: {exc}")


def _comment_was_posted(step_results: Dict[str, Any]) -> bool:
    for result in step_results.values():
        if isinstance(result, dict) and result.get("id") and result.get("body"):
            return True
        if isinstance(result, dict) and "note" in result:
            return True
    return False


def _extract_posted_summary(step_results: Dict[str, Any]) -> Optional[str]:
    for result in step_results.values():
        if isinstance(result, dict):
            body = result.get("body") or result.get("comment")
            if isinstance(body, str) and body.strip():
                return body
    return None
