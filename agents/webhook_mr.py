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

    Pre-steps (executed before LLM):
    0) validate_mr_webhook - Validate if MR should be processed
    1) clone_repo - Clone repository to temp workspace
    2) gitnexus_analyze - Index repository for code search
    3) get_gitlab_mr_diffs - Fetch MR diff content
    """
    from agents import tools

    ingest = await review_service.ingest_mr_from_webhook(payload)
    if ingest.get("skipped"):
        return {"status": ingest.get("reason", "skipped"), **ingest}

    project_id = ingest["project_id"]
    mr_iid = ingest["mr_iid"]
    user_id = str(payload.get("user", {}).get("id", ""))
    repo_http_url = payload.get("repository", {}).get("git_http_url", "")
    source_branch = payload.get("object_attributes", {}).get("source_branch", "")
    target_branch = payload.get("object_attributes", {}).get("target_branch", "main")
    mr_state = payload.get("object_attributes", {}).get("state", "opened")
    action = payload.get("object_attributes", {}).get("action", "open")

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

    # ============================================================================
    # PRE-STEP 0: Validate MR Webhook
    # ============================================================================
    print(f"[INFO] [Agentic MR] [PRE-STEP 0] Validating MR webhook...")
    validation_result = await tools.validate_mr_webhook(
        project_id=project_id,
        mr_iid=int(mr_iid),
        target_branch=target_branch,
        source_branch=source_branch,
        mr_state=mr_state,
        action=action
    )
    if not validation_result.get("should_process", False):
        skip_reason = validation_result.get("skip_reason", "Unknown reason")
        print(f"[INFO] [Agentic MR] [PRE-STEP 0] MR validation failed, skipping workflow: {skip_reason}")
        await repository_service.add_mr_progress_log(
            repo_id=project_id,
            mr_iid=mr_iid,
            step="agentic_review",
            message=f"Skipped: {skip_reason}",
            status="failed",
        )
        return {
            "status": "skipped",
            "reason": skip_reason,
            "project_id": project_id,
            "mr_iid": mr_iid
        }
    print(f"[OK] [Agentic MR] [PRE-STEP 0] MR validation passed")

    # ============================================================================
    # PRE-STEP 1: Clone Repository
    # ============================================================================
    print(f"[INFO] [Agentic MR] [PRE-STEP 1] Cloning repository...")
    repo_path = await tools.clone_repo(
        project_id=project_id,
        source_branch=source_branch,
        repo_http_url=repo_http_url,
        user_id=user_id,
        target_branch=target_branch
    )
    print(f"[OK] [Agentic MR] [PRE-STEP 1] Repository cloned to: {repo_path}")

    # ============================================================================
    # PRE-STEP 2: GitNexus Analysis (Index Repository)
    # ============================================================================
    print(f"[INFO] [Agentic MR] [PRE-STEP 2] Running GitNexus analysis...")
    gitnexus_result = await tools.gitnexus_analyze(repo_path=repo_path)
    if gitnexus_result.get("status") != "success":
        print(f"[WARN] [Agentic MR] [PRE-STEP 2] GitNexus analysis failed: {gitnexus_result.get('message', 'Unknown error')}")
    else:
        print(f"[OK] [Agentic MR] [PRE-STEP 2] GitNexus analysis completed")

    # ============================================================================
    # PRE-STEP 3: Get MR Diff Content
    # ============================================================================
    print(f"[INFO] [Agentic MR] [PRE-STEP 3] Fetching MR diff content...")
    mr_diff_content = await tools.get_gitlab_mr_diffs(
        user_id=user_id,
        project_id=project_id,
        mr_iid=int(mr_iid)
    )
    print(f"[OK] [Agentic MR] [PRE-STEP 3] Fetched {len(mr_diff_content)} chars of diff content")

    # ============================================================================
    # Build Agent Context with Pre-step Results
    # ============================================================================
    context = await ContextBuilder.build_from_gitlab_mr(payload)

    # Handle validation failure (context is None)
    if context is None:
        return {"status": "skipped", "reason": "Webhook validation failed"}

    # Add pre-step results to metadata
    context.metadata["prestep_validation_passed"] = True
    context.metadata["prestep_repo_path"] = repo_path
    context.metadata["prestep_gitnexus_completed"] = gitnexus_result.get("status") == "success"
    context.metadata["mr_diff_content"] = mr_diff_content
    print(f"[INFO] [Agentic MR] Added pre-step results to context metadata")

    # ============================================================================
    # Execute Agentic Workflow (without prerequisite tools)
    # ============================================================================
    engine = WorkflowEngine(await build_default_registry(exclude_prerequisites=True))
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
