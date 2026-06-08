import os
import json
import sys
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
import httpx

from services import (
    review_service,
    repository_service,
    schema_inspection_service,
    impact_measurement_service,
    incident_service,
    user_service,
    mcp_service
)

# ============================================================================
# Schemas for Gemini function calling declarations
# ============================================================================

clone_repo_schema = {
    "name": "clone_repo",
    "description": "Clones a GitLab repository branch to a local temporary workspace. Returns the absolute path as a string (use '{{clone_repo_step.result}}' directly, not '{{clone_repo_step.result.repo_path}}').",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "project_id": {"type": "STRING", "description": "The GitLab project ID."},
            "source_branch": {"type": "STRING", "description": "The branch to fetch/checkout (contains the changes)."},
            "repo_http_url": {"type": "STRING", "description": "The HTTP clone URL of the repository."},
            "user_id": {"type": "STRING", "description": "The user ID for authentication lookups."},
            "target_branch": {"type": "STRING", "description": "The target branch (e.g. main/master) to use as the baseline."},
            "checkout_source": {"type": "BOOLEAN", "description": "Whether to check out the source branch immediately after cloning (defaults to False, keeping baseline)."}
        },
        "required": ["project_id", "source_branch", "repo_http_url", "user_id", "target_branch"]
    }
}

run_impact_analysis_schema = {
    "name": "run_impact_analysis",
    "description": "Performs static call-graph impact analysis on the codebase to identify blast radius and breaking change risks for changed symbols. Returns an object with fields: status, analyzed_at, changed_symbols_count, impacted_dependencies_count, high_risk_count, medium_risk_count, markdown_report (string), and gemini_prompt_formatted (string). Use '{{impact_analysis_step.result.markdown_report}}' to get the formatted report.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "repo_path": {"type": "STRING", "description": "Absolute path to the cloned repository workspace."},
            "repo_name": {"type": "STRING", "description": "Repository identifier / directory name."},
            "source_branch": {"type": "STRING", "description": "The branch containing code modifications (e.g. feature-branch)."},
            "target_branch": {"type": "STRING", "description": "The base branch to compare against (default 'main')."},
            "changed_symbols": {"type": "ARRAY", "description": "Optional list of changed symbol names to analyze. If not provided, analysis will run without specific symbol focus.", "items": {"type": "STRING"}}
        },
        "required": ["repo_path", "repo_name", "source_branch"]
    }
}

run_schema_inspection_schema = {
    "name": "run_schema_inspection",
    "description": "Scans modified files to detect schema definition drift in MongoDB schemas and computes schema delta. Returns an object with fields: status, schema_changes_detected, markdown_report (string), and gemini_prompt_formatted (string). Use '{{schema_inspection_step.result.markdown_report}}' to get the formatted report.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "diff_text": {"type": "STRING", "description": "The git diff string containing modifications to scan."},
            "project_id": {"type": "STRING", "description": "Project or Repository ID (for credential lookups)."},
            "target_branch": {"type": "STRING", "description": "The target branch (e.g. 'main')."}
        },
        "required": ["diff_text"]
    }
}

get_gitlab_mr_diffs_schema = {
    "name": "get_gitlab_mr_diffs",
    "description": "Get merge request diffs as a raw unified diff string. Returns the diff text as a string (use '{{get_mr_diffs_step.result}}' directly).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "user_id": {"type": "STRING", "description": "The user ID for authentication lookups."},
            "project_id": {"type": "STRING", "description": "GitLab project ID."},
            "mr_iid": {"type": "INTEGER", "description": "Merge request internal ID (IID)."}
        },
        "required": ["user_id", "project_id", "mr_iid"]
    }
}

post_gitlab_mr_comment_schema = {
    "name": "post_gitlab_mr_comment",
    "description": "Post or update a comment note on a GitLab merge request thread.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "user_id": {"type": "STRING", "description": "The user ID for authentication lookups."},
            "project_id": {"type": "STRING", "description": "GitLab project ID."},
            "mr_iid": {"type": "INTEGER", "description": "Merge request internal ID (IID)."},
            "comment": {"type": "STRING", "description": "The comment content (supports markdown)."},
            "note_id": {"type": "INTEGER", "description": "Optional existing note ID to update instead of creating a new one."}
        },
        "required": ["user_id", "project_id", "mr_iid", "comment"]
    }
}

get_dynatrace_incident_details_schema = {
    "name": "get_dynatrace_incident_details",
    "description": "Fetch detailed runtime logs and stack traces from Dynatrace Grail for a problem ID.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "problem_id": {"type": "STRING", "description": "The Dynatrace problem ID."}
        },
        "required": ["problem_id"]
    }
}

apply_hotfix_patch_schema = {
    "name": "apply_hotfix_patch",
    "description": "Surgically apply a unified diff patch block to a local repository file.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "repo_path": {"type": "STRING", "description": "Absolute path to the cloned repository workspace."},
            "file_path": {"type": "STRING", "description": "Relative path to the target file to modify."},
            "diff_patch": {"type": "STRING", "description": "The unified diff patch block content to apply."}
        },
        "required": ["repo_path", "file_path", "diff_patch"]
    }
}

create_hotfix_branch_and_mr_schema = {
    "name": "create_hotfix_branch_and_mr",
    "description": "Create a Git branch, commit changes to it, push to remote, and open a GitLab Merge Request.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "project_id": {"type": "STRING", "description": "The GitLab project ID."},
            "repo_path": {"type": "STRING", "description": "Absolute path to the cloned repository workspace."},
            "source_branch": {"type": "STRING", "description": "The new branch name to create and commit to."},
            "target_branch": {"type": "STRING", "description": "The base branch to merge into (e.g. main/master)."},
            "title": {"type": "STRING", "description": "Merge Request title."},
            "description": {"type": "STRING", "description": "Merge Request description (supports markdown)."},
            "user_id": {"type": "STRING", "description": "The user ID for authentication lookups."}
        },
        "required": ["project_id", "repo_path", "source_branch", "target_branch", "title", "description", "user_id"]
    }
}

gitnexus_analyze_schema = {
    "name": "gitnexus_analyze",
    "description": "INDEX the repository - runs npx gitnexus analyze to build call graphs and enable gitnexus_grep/gitnexus_file tools. This does NOT analyze Sentry issues or bugs - it only indexes the repo for searching. NO query/search/pattern parameters - ONLY repo_path.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "repo_path": {"type": "STRING", "description": "Absolute path to the cloned repository workspace."}
        },
        "required": ["repo_path"]
    }
}

gitnexus_grep_schema = {
    "name": "gitnexus_grep",
    "description": "Fallback grep search across all indexed files in the repository. Use this tool when you need to find occurrences of a pattern across files. Returns file paths, line numbers, and matching text. This is a literal substring search (not regex) and scans all files in the indexed repo.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "pattern": {"type": "STRING", "description": "Search pattern - literal substring to find in files (max 200 chars)."},
            "limit": {"type": "INTEGER", "description": "Max number of results to return (default: 50, max: 200)."}
        },
        "required": ["pattern"]
    }
}

gitnexus_file_schema = {
    "name": "gitnexus_file",
    "description": "Read the full content of files from the indexed repository. Accepts a single file path (string) or multiple file paths (array). When given multiple paths, fetches all files and merges their contents. Use this tool after gitnexus_grep finds matching files.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {"oneOf": [{"type": "STRING"}, {"type": "ARRAY", "items": {"type": "STRING"}}], "description": "File path relative to repository root (e.g., 'src/main.js') or array of multiple file paths."},
            "start_line": {"type": "INTEGER", "description": "Optional start line number (0-indexed) for partial read. Only used for single file reads."},
            "end_line": {"type": "INTEGER", "description": "Optional end line number (0-indexed) for partial read. Only used for single file reads."}
        },
        "required": ["file_path"]
    }
}

create_gitlab_branch_schema = {
    "name": "create_gitlab_branch",
    "description": "Create a new branch in a GitLab repository using the GitLab REST API.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "user_id": {"type": "STRING", "description": "The user ID for authentication lookups."},
            "project_id": {"type": "STRING", "description": "GitLab project ID."},
            "branch_name": {"type": "STRING", "description": "The name of the new branch to create."},
            "ref": {"type": "STRING", "description": "The branch name or commit SHA to create the branch from (defaults to 'main')."}
        },
        "required": ["user_id", "project_id", "branch_name"]
    }
}

create_gitlab_merge_request_schema = {
    "name": "create_gitlab_merge_request",
    "description": "Create a new merge request in GitLab using the REST API.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "user_id": {"type": "STRING", "description": "The user ID for authentication lookups."},
            "project_id": {"type": "STRING", "description": "GitLab project ID."},
            "source_branch": {"type": "STRING", "description": "The source branch for the merge request."},
            "target_branch": {"type": "STRING", "description": "The target branch to merge into."},
            "title": {"type": "STRING", "description": "Title of the merge request."},
            "description": {"type": "STRING", "description": "Description of the merge request (supports markdown)."}
        },
        "required": ["user_id", "project_id", "source_branch", "target_branch", "title"]
    }
}

commit_file_to_branch_schema = {
    "name": "commit_file_to_branch",
    "description": "Commit a file to a GitLab branch using the REST API. Creates a new commit with the file content.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "user_id": {"type": "STRING", "description": "The user ID for authentication lookups."},
            "project_id": {"type": "STRING", "description": "GitLab project ID."},
            "file_path": {"type": "STRING", "description": "The full path to the file in the repository (e.g., 'src/app.py')."},
            "branch_name": {"type": "STRING", "description": "The branch name to commit to."},
            "content": {"type": "STRING", "description": "The file content to write."},
            "commit_message": {"type": "STRING", "description": "The commit message."}
        },
        "required": ["user_id", "project_id", "file_path", "branch_name", "content", "commit_message"]
    }
}

# ============================================================================
# Tool callback functions
# ============================================================================

async def clone_repo(
    project_id: str,
    source_branch: str,
    repo_http_url: str,
    user_id: str,
    target_branch: str,
    checkout_source: bool = False
) -> str:
    """Clones a GitLab repository branch and returns the local directory path as string."""
    path = await review_service._clone_repository_to_temp_workspace(
        project_id=str(project_id),
        source_branch=source_branch,
        repo_http_url=repo_http_url,
        user_id=str(user_id),
        target_branch=target_branch,
        checkout_source=checkout_source
    )
    return str(path)


async def run_impact_analysis(
    repo_path: str,
    repo_name: str,
    source_branch: str,
    target_branch: str = "main",
    changed_symbols: List[str] = None
) -> Dict[str, Any]:
    """Runs static impact analysis and returns a dictionary payload representing the report.

    Args:
        repo_path: Path to the cloned repository
        repo_name: Name of the repository
        source_branch: Source branch with changes
        target_branch: Target baseline branch
        changed_symbols: Optional list of changed symbol names. If not provided, will run analysis without specific symbols.
    """
    # If changed_symbols not provided, use empty list
    if changed_symbols is None:
        changed_symbols = []

    report = await impact_measurement_service.run_impact_analysis(
        repo_path=repo_path,
        repo_name=repo_name,
        source_branch=source_branch,
        target_branch=target_branch,
        changed_symbols=changed_symbols,
        max_symbols_to_analyze=3
    )
    if not report:
        return {"status": "skipped", "message": "No impact report compiled"}

    return {
        "status": "success",
        "analyzed_at": report.analyzed_at.isoformat() if report.analyzed_at else None,
        "source_branch": report.source_branch,
        "target_branch": report.target_branch,
        "changed_symbols_count": len(report.changed_symbols),
        "impacted_dependencies_count": len(report.impacted_dependencies),
        "high_risk_count": report.high_risk_count,
        "medium_risk_count": report.medium_risk_count,
        "skipped_reason": report.skipped_reason,
        "markdown_report": impact_measurement_service.format_impact_report_to_markdown(report),
        "gemini_prompt_formatted": impact_measurement_service.format_impact_report_for_gemini_prompt(report)
    }


async def run_schema_inspection(
    diff_text: str,
    project_id: Optional[str] = None,
    target_branch: Optional[str] = None
) -> Dict[str, Any]:
    """Runs schema inspection checks on diff text."""
    report = await schema_inspection_service.run_schema_inspection(
        diff_text=diff_text,
        mongo_session=mcp_service.mongo_session,
        project_id=project_id,
        target_branch=target_branch
    )
    if not report:
        return {"status": "skipped", "message": "No schema drift detected or run skipped"}
    
    return {
        "status": "success",
        "collections_checked": report.collections_checked,
        "drift_detected": report.drift_detected,
        "risk_level": report.risk_level,
        "markdown_report": schema_inspection_service.format_schema_report_to_markdown(report)
    }


run_gemini_mr_review_schema = {
    "name": "run_gemini_mr_review",
    "description": (
        "Run the full Gatekeeper Gemini security and quality review on an MR diff. "
        "Uses GitNexus MCP tools for deep code intelligence — same pipeline as standard mode. "
        "Returns audit_report (markdown), health_score, and issue summaries."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "project_id": {"type": "STRING", "description": "GitLab project ID"},
            "mr_iid": {"type": "INTEGER", "description": "Merge request IID"},
            "user_id": {"type": "STRING", "description": "Gatekeeper user ID for billing and Gemini config"},
            "diff_text": {"type": "STRING", "description": "Raw MR diff text"},
            "repo_path": {"type": "STRING", "description": "Local path to cloned repository"},
            "repo_name": {"type": "STRING", "description": "Repository name for GitNexus"},
            "source_branch": {"type": "STRING", "description": "Source branch name"},
            "target_branch": {"type": "STRING", "description": "Target branch name"},
            "impact_context": {"type": "STRING", "description": "Impact analysis markdown for Gemini prompt"},
            "schema_context": {"type": "STRING", "description": "Schema inspection markdown for Gemini prompt"},
        },
        "required": ["project_id", "mr_iid", "diff_text", "repo_path"],
    },
}


async def run_gemini_mr_review(
    project_id: str,
    mr_iid: int,
    diff_text: str,
    repo_path: str,
    user_id: str = "",
    repo_name: str = "",
    source_branch: str = "main",
    target_branch: str = "main",
    impact_context: str = "",
    schema_context: str = "",
) -> Dict[str, Any]:
    """
    Execute the same Gemini + GitNexus review pipeline used by review_service.orchestrate_review.
    """
    from pathlib import Path
    from services.gemini_service import run_gemini_review_with_gitnexus

    resolved_user_id, _ = await review_service.resolve_gitlab_token(
        str(project_id),
        user_id or None,
    )
    gatekeeper_user_id = resolved_user_id or user_id or ""
    user_config = await review_service.get_user_config_from_repo(str(project_id))

    combined_diff = diff_text or ""
    if impact_context:
        combined_diff += f"\n\n{impact_context}"
    if schema_context:
        combined_diff += f"\n\n{schema_context}"

    local_repo = Path(repo_path) if repo_path else None
    if local_repo is None or not local_repo.exists():
        return {
            "status": "error",
            "message": f"Repository path not found for Gemini review: {repo_path}",
        }

    try:
        gemini_result = await run_gemini_review_with_gitnexus(
            raw_diff_content=combined_diff,
            impact_context=impact_context or "",
            repo_path=local_repo,
            repo_name=repo_name or None,
            target_branch_name=target_branch,
            source_branch_name=source_branch,
            user_config=user_config,
            user_id=gatekeeper_user_id or None,
            mr_id=str(mr_iid),
            repository_id=str(project_id),
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Gemini MR review failed: {exc}",
        }

    audit_report = gemini_result.get("review_text", "") or ""
    if not audit_report.strip():
        return {
            "status": "error",
            "message": "Gemini MR review returned an empty report",
        }

    issues: list[str] = []
    for line in audit_report.splitlines():
        stripped = line.strip()
        if any(
            marker in stripped
            for marker in ("❌", "⚠️", "🔴", "🟠", "**ERROR**", "**WARNING**", "**Issue**")
        ):
            clean = stripped
            for marker in ("❌", "⚠️", "🔴", "🟠", "**", "*", "`"):
                clean = clean.replace(marker, "").strip()
            if clean and len(clean) > 5:
                issues.append(clean[:200])

    error_count = sum(1 for issue in issues if any(k in issue.lower() for k in ("error", "critical", "high")))
    warning_count = max(0, len(issues) - error_count)
    health_score = max(0, min(100, 100 - error_count * 20 - warning_count * 5))

    try:
        await repository_service.update_mr_analysis(
            repo_id=str(project_id),
            mr_iid=int(mr_iid),
            analysis_data={
                "analysis_status": "completed",
                "status": "reviewed",
                "ai_review": audit_report,
                "ai_issues": issues[:20],
                "health_score": health_score,
                "span_id": gemini_result.get("span_id"),
                "trace_id": gemini_result.get("trace_id"),
            },
        )
        await repository_service.add_mr_progress_log(
            repo_id=str(project_id),
            mr_iid=int(mr_iid),
            step="ai_analysis",
            message=f"AI analysis complete - {len(audit_report)} characters of findings generated",
            status="completed",
        )
    except Exception as persist_exc:
        print(f"[WARN] [run_gemini_mr_review] Failed to persist MR analysis: {persist_exc}")

    return {
        "status": "success",
        "audit_report": audit_report,
        "health_score": health_score,
        "issue_count": len(issues),
        "issues": issues[:20],
        "tools_called": gemini_result.get("tools_called", []),
        "usage": gemini_result.get("usage", {}),
    }


async def get_gitlab_mr_diffs(user_id: str, project_id: str, mr_iid: int) -> str:
    """Gets the raw diff content of the specified GitLab MR."""
    diff_str = await review_service._gitlab_get_mr_diffs(
        user_id=user_id,
        project_id=project_id,
        mr_iid=mr_iid
    )
    return diff_str


async def post_gitlab_mr_comment(
    user_id: str,
    project_id: str,
    mr_iid: int,
    comment: str,
    note_id: Optional[int] = None
) -> Dict[str, Any]:
    """Posts or updates a comment note on a GitLab merge request thread."""
    if note_id:
        endpoint = f"/projects/{project_id}/merge_requests/{mr_iid}/notes/{note_id}"
        method = "PUT"
    else:
        endpoint = f"/projects/{project_id}/merge_requests/{mr_iid}/notes"
        method = "POST"
        
    res = await review_service._gitlab_api_call(
        user_id=user_id,
        project_id=str(project_id),
        method=method,
        endpoint=endpoint,
        data={"body": comment}
    )
    return res


async def get_dynatrace_incident_details(problem_id: str) -> str:
    """Fetch Grail logs/stacktrace details or fall back to mock details."""
    dynatrace_session = mcp_service.dynatrace_session
    raw_crash_telemetry = ""
    
    try:
        if str(problem_id) in ["999888", "777888"]:
            raise ValueError("Simulating test incident")
        if dynatrace_session:
            dt_details = await dynatrace_session.call_tool(
                name="dynatrace:get-problem-details",
                arguments={"problemId": str(problem_id)}
            )
            raw_crash_telemetry = str(dt_details.content)
            if "No problems found" in raw_crash_telemetry:
                raise ValueError("Problem not found in Dynatrace environment")
    except Exception as e:
        if str(problem_id) == "999888":
            raw_crash_telemetry = (
                "Exception: TypeError in app.py\n"
                "TypeError: create_transaction_schema() missing 1 required positional argument: 'card_number'\n"
                "Traceback (most recent call last):\n"
                "  File \"app.py\", line 160, in process_payment\n"
                "    transaction_doc = create_transaction_schema(request.user_id, request.amount)\n"
            )
        elif str(problem_id) == "777888":
            raw_crash_telemetry = (
                "Exception: NameError in models.py\n"
                "NameError: name 'hash_pwd' is not defined\n"
                "Traceback (most recent call last):\n"
                "  File \"app.py\", line 125, in register_user\n"
                "    user_doc = create_user_schema(request.username, request.email, request.password)\n"
                "  File \"models.py\", line 22, in create_user_schema\n"
                "    \"password\": hash_pwd,\n"
            )
        else:
            raise Exception(f"Failed to fetch live Dynatrace problem details: {e}")
            
    return raw_crash_telemetry


async def apply_hotfix_patch(repo_path: str, file_path: str, diff_patch: str) -> Dict[str, Any]:
    """Reads a file, applies a unified diff patch, and writes it back."""
    full_path = Path(repo_path) / file_path
    if not full_path.exists():
        return {"status": "error", "message": f"File {file_path} does not exist at {repo_path}"}
        
    with open(full_path, "r", encoding="utf-8") as f:
        original_code = f.read()
        
    resolved_code = incident_service.apply_unified_patch(original_code, diff_patch)
    
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(resolved_code)
        
    return {"status": "success", "message": f"Successfully applied patch to {file_path}"}


async def create_hotfix_branch_and_mr(
    project_id: str,
    repo_path: str,
    source_branch: str,
    target_branch: str,
    title: str,
    description: str,
    user_id: str
) -> Dict[str, Any]:
    """Commits all changed files in repo_path to source_branch, pushes to remote, and opens a GitLab MR."""
    # 1. Get credentials/token to push
    user_token = await user_service.get_user_gitlab_token(str(user_id), str(project_id))
    if not user_token:
        # Fallback to env token if user token not configured
        user_token = os.getenv("GITLAB_PERSONAL_ACCESS_TOKEN", "")
        if not user_token:
            raise Exception(f"No GitLab token found for user {user_id} and fallback env token is missing")
        
    # Get project URL from GitLab or construct it
    project_info = await review_service._gitlab_api_call(
        user_id=user_id,
        project_id=str(project_id),
        method="GET",
        endpoint=f"/projects/{project_id}"
    )
    http_url_to_repo = project_info.get("http_url_to_repo", "")
    if not http_url_to_repo:
        gitlab_base_url = os.getenv("GITLAB_BASE_URL", "https://gitlab.com").rstrip("/")
        path_with_namespace = project_info.get("path_with_namespace", "")
        if path_with_namespace:
            http_url_to_repo = f"{gitlab_base_url}/{path_with_namespace}.git"
        else:
            raise Exception(f"Could not determine http_url_to_repo for project {project_id}")
        
    # Inject token into URL for authenticated git commands
    auth_url = http_url_to_repo.replace("https://", f"https://oauth2:{user_token}@")
    
    # 2. Configure Git user locally
    subprocess.run(["git", "config", "user.name", "Gatekeeper Autopilot"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.email", "gatekeeper-autopilot@gemini.ai"], cwd=repo_path, check=True)
    
    # 3. Create branch and checkout
    subprocess.run(["git", "checkout", "-b", source_branch], cwd=repo_path, check=False)
    subprocess.run(["git", "checkout", source_branch], cwd=repo_path, check=True)
    
    # 4. Add all changes and commit
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo_path, capture_output=True, text=True, check=True)
    if status.stdout.strip():
        subprocess.run(["git", "commit", "-m", "fix: automated code remediation patch by Gatekeeper"], cwd=repo_path, check=True)
    else:
        print("[WARN] No files changed to commit")
        
    # 5. Push branch to GitLab using auth_url
    subprocess.run(["git", "push", "-u", auth_url, source_branch, "--force"], cwd=repo_path, check=True)
    
    # 6. Create MR using API
    mr_payload = {
        "source_branch": source_branch,
        "target_branch": target_branch,
        "title": title,
        "description": description
    }
    
    mr_res = await review_service._gitlab_api_call(
        user_id=user_id,
        project_id=str(project_id),
        method="POST",
        endpoint=f"/projects/{project_id}/merge_requests",
        data=mr_payload
    )
    
    return mr_res


async def gitnexus_analyze(repo_path: str) -> Dict[str, Any]:
    """Runs gitnexus analyze via subprocess in the given repo_path."""
    npx_executable = "npx"
    npx_found = False

    if sys.platform == "win32":
        # Try multiple methods to find npx on Windows
        # Method 1: Check common Node.js installation paths
        possible_paths = [
            Path("C:/Program Files/nodejs/npx.cmd"),
            Path("C:/Program Files/nodejs/npx.ps1"),
            Path("C:/Program Files (x86)/nodejs/npx.cmd"),
            Path("C:/Program Files (x86)/nodejs/npx.ps1"),
        ]

        for npx_path in possible_paths:
            if npx_path.exists():
                npx_executable = str(npx_path)
                npx_found = True
                print(f"[DEBUG] Found npx at: {npx_path}")
                break

        # Method 2: Try 'where npx' command
        if not npx_found:
            try:
                where_result = subprocess.run(["where", "npx"], capture_output=True, text=True, timeout=5)
                if where_result.returncode == 0 and where_result.stdout.strip():
                    npx_executable = where_result.stdout.strip().split('\n')[0].strip()
                    npx_found = True
                    print(f"[DEBUG] Found npx via 'where': {npx_executable}")
            except Exception as e:
                print(f"[DEBUG] 'where npx' failed: {e}")

        # Method 3: Try 'npm config get prefix' to find Node.js location
        if not npx_found:
            try:
                npm_prefix_result = subprocess.run(["npm", "config", "get", "prefix"], capture_output=True, text=True, timeout=5, shell=True)
                if npm_prefix_result.returncode == 0 and npm_prefix_result.stdout.strip():
                    npm_prefix = Path(npm_prefix_result.stdout.strip())
                    npx_cmd = npm_prefix / "npx.cmd"
                    npx_ps1 = npm_prefix / "npx.ps1"
                    if npx_ps1.exists():
                        npx_executable = str(npx_ps1)
                        npx_found = True
                        print(f"[DEBUG] Found npx.ps1 via npm prefix: {npx_ps1}")
                    elif npx_cmd.exists():
                        npx_executable = str(npx_cmd)
                        npx_found = True
                        print(f"[DEBUG] Found npx.cmd via npm prefix: {npx_cmd}")
            except Exception as e:
                print(f"[DEBUG] 'npm config get prefix' failed: {e}")

        if not npx_found:
            print(f"[WARN] Could not find npx executable, will try default 'npx'")

    try:
        # On Windows, if the executable is a .ps1 file, we need to run it through PowerShell
        if sys.platform == "win32" and npx_executable.endswith(".ps1"):
            print(f"[DEBUG] Running npx via PowerShell: {npx_executable}")
            res = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", npx_executable, "gitnexus", "analyze"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=False
            )
        else:
            res = subprocess.run(
                [npx_executable, "gitnexus", "analyze"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=False
            )
        return {
            "status": "success" if res.returncode == 0 else "failed",
            "returncode": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def gitnexus_grep(pattern: str, limit: int = 50) -> Dict[str, Any]:
    """
    Call GitNexus HTTP /api/grep endpoint to search for a pattern across indexed files.

    This is a wrapper around the GitNexus grep functionality for Sentry bug fixing workflows.

    Args:
        pattern: Search pattern (literal substring search)
        limit: Max number of results to return (default: 50, max: 200)

    Returns:
        Dict with search results including file paths, line numbers, and matching text
    """
    try:
        from services.gemini_service import call_gitnexus_grep
        return await call_gitnexus_grep(pattern=pattern, limit=limit)
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def gitnexus_file(file_path, start_line: Optional[int] = None, end_line: Optional[int] = None) -> Dict[str, Any]:
    """
    Call GitNexus HTTP /api/file endpoint to read the full content of file(s).

    This wrapper accepts either a single file path (string) or multiple file paths (array).
    When given multiple paths, it fetches all files and merges their contents.

    Args:
        file_path: File path (string) or array of file paths relative to repository root
        start_line: Optional start line number (only used for single file reads)
        end_line: Optional end line number (only used for single file reads)

    Returns:
        Dict with file content(s) and metadata. Always includes 'merged_content' field.
    """
    try:
        from services.gemini_service import call_gitnexus_file

        # Handle single file path (string)
        if isinstance(file_path, str):
            print(f"[INFO] gitnexus_file fetching single file: {file_path}")
            result = await call_gitnexus_file(file_path=file_path, start_line=start_line, end_line=end_line)

            if "error" in result:
                return {"status": "error", "message": result.get("error")}

            # Extract content and wrap in consistent format
            content = result.get("content", "")

            # Return consistent format with merged_content for single file too
            return {
                "status": "success",
                "files_count": 1,
                "merged_content": content,  # Single file content as merged_content
                "individual_files": [{
                    "file_path": file_path,
                    "content": content,
                    "total_lines": result.get("totalLines", 0)
                }],
                "message": f"Fetched 1 file successfully"
            }

        # Handle multiple file paths (list/array)
        if isinstance(file_path, list) and len(file_path) > 0:
            print(f"[INFO] gitnexus_file fetching {len(file_path)} files...")
            all_contents = []
            merged_content = ""

            for i, path in enumerate(file_path):
                print(f"[INFO] Fetching file {i+1}/{len(file_path)}: {path}")
                result = await call_gitnexus_file(file_path=path, start_line=None, end_line=None)
                print(f"[DEBUG] gitnexus_file: Got result from call_gitnexus_file, status: {result.get('status', 'unknown')}")

                if "error" in result:
                    print(f"[WARN] Failed to fetch {path}: {result['error']}")
                    continue

                # Extract content from result
                content = result.get("content", "")
                print(f"[DEBUG] gitnexus_file: Extracted {len(content)} chars from {path}")
                all_contents.append({
                    "file_path": path,
                    "content": content,
                    "total_lines": result.get("totalLines", 0)
                })

                # Build merged content with file headers
                merged_content += f"\n{'='*60}\n"
                merged_content += f"FILE: {path}\n"
                merged_content += f"{'='*60}\n"
                merged_content += content + "\n"

            print(f"[DEBUG] gitnexus_file: Merged {len(all_contents)} files, total chars: {len(merged_content)}")
            return {
                "status": "success",
                "files_count": len(all_contents),
                "merged_content": merged_content,
                "individual_files": all_contents,
                "message": f"Fetched {len(all_contents)} files successfully"
            }

        # Invalid type
        return {"status": "error", "message": f"Invalid file_path type: {type(file_path)}. Expected string or list."}

    except Exception as e:
        return {"status": "error", "message": str(e)}


# ============================================================================
# AI Fix Generation Tool
# ============================================================================

generate_fix_schema = {
    "name": "generate_fix",
    "description": "Uses Gemini AI to generate fix code based on Sentry issue analysis and code context. Returns structured JSON with file_path, fixed_code, and description.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "sentry_issue_id": {"type": "STRING", "description": "The Sentry issue ID being fixed."},
            "sentry_title": {"type": "STRING", "description": "The Sentry issue title."},
            "stack_trace": {"type": "STRING", "description": "The stack trace or error message from Sentry."},
            "culprit": {"type": "STRING", "description": "The culprit file or function where the error occurred."},
            "problem_type": {"type": "STRING", "description": "Type of problem: 'code' (logic error, null reference, type error) or 'mongodb' (schema/validation issue)."},
            "analysis_findings": {"type": "STRING", "description": "Analysis results from gitnexus_file or schema inspection - includes the relevant code context."},
            "file_path": {"type": "STRING", "description": "The specific file path that needs to be fixed (from analysis)."}
        },
        "required": ["sentry_issue_id", "sentry_title", "stack_trace", "problem_type", "analysis_findings", "file_path"]
    }
}


async def generate_fix(
    sentry_issue_id: str,
    sentry_title: str,
    stack_trace: str,
    culprit: str,
    problem_type: str,
    analysis_findings: str,
    file_path: str
) -> Dict[str, Any]:
    """
    Generate fix code using Gemini AI based on Sentry issue analysis.

    This tool takes the Sentry issue details and code analysis results,
    then uses Gemini AI to generate a proper fix for the bug.

    Args:
        sentry_issue_id: Sentry issue ID
        sentry_title: Issue title
        stack_trace: Stack trace or error message
        culprit: Culprit file/function
        problem_type: 'code' or 'mongodb'
        analysis_findings: Code context from analysis tools
        file_path: File path to fix

    Returns:
        Dict with file_path, fixed_code, description
    """
    from google.genai import types
    from services.gemini_service import ai_client

    # Build the system instruction for fix generation
    system_instruction = """You are an elite code fixer specializing in automated bug remediation.

Your task is to analyze Sentry error reports and generate correct, minimal fixes.

CRITICAL RULES:
1. Generate ONLY the fix - no explanations, no markdown code blocks
2. Preserve imports, dependencies, and existing code structure
3. Make minimal changes to fix the specific issue
4. Return valid JSON with: file_path (string), fixed_code (string), description (string)

FOR CODE PROBLEMS (TypeError, ReferenceError, null checks):
- Add proper null/undefined guards
- Fix variable references and scoping issues
- Add type validations where missing
- Handle edge cases and error conditions

FOR MONGODB PROBLEMS (schema validation, duplicate keys):
- Fix schema definitions to match actual usage
- Add proper indexes for queries
- Handle validation failures gracefully
- Fix field type mismatches

OUTPUT FORMAT (must be valid JSON):
{
  "file_path": "path/to/file.ext",
  "fixed_code": "complete fixed file content here",
  "description": "Brief description of what was fixed"
}
"""

    # Build the prompt with Sentry context and analysis
    prompt = f"""SENTRY ISSUE DETAILS:
Issue ID: {sentry_issue_id}
Title: {sentry_title}
Error Type: {problem_type}
Stack Trace:
{stack_trace}
Culprit: {culprit}

ANALYSIS FINDINGS (code context from repository):
{analysis_findings}

TARGET FILE: {file_path}

Please generate a fix for this bug. Return valid JSON with file_path, fixed_code, and description."""

    try:
        print(f"[INFO] [generate_fix] Calling Gemini AI to generate fix for issue {sentry_issue_id}...")

        # Call Gemini with structured output request
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
            )
        )

        # Extract response text
        response_text = ""
        if response.candidates and len(response.candidates) > 0:
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'text') and part.text:
                    response_text += part.text

        print(f"[DEBUG] [generate_fix] Gemini response length: {len(response_text)}")

        # Try to parse as JSON
        import json
        try:
            # Clean up response - remove markdown code blocks if present
            cleaned = response_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]  # Remove ```json
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]  # Remove ```
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]  # Remove trailing ```
            cleaned = cleaned.strip()

            fix_data = json.loads(cleaned)

            # Validate required fields
            if not all(k in fix_data for k in ["file_path", "fixed_code", "description"]):
                raise ValueError("Missing required fields in fix response")

            print(f"[OK] [generate_fix] Successfully generated fix for {fix_data['file_path']}")
            return {
                "status": "success",
                "file_path": fix_data["file_path"],
                "fixed_code": fix_data["fixed_code"],
                "description": fix_data["description"]
            }

        except json.JSONDecodeError as je:
            print(f"[WARN] [generate_fix] Failed to parse JSON from Gemini: {je}")
            print(f"[WARN] [generate_fix] Response was: {response_text[:500]}...")
            # Fallback: create a structured response from the text
            return {
                "status": "partial",
                "file_path": file_path,
                "fixed_code": response_text,
                "description": f"Generated fix for Sentry issue {sentry_issue_id} (parse attempt failed)"
            }

    except Exception as e:
        print(f"[ERROR] [generate_fix] Failed to generate fix: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "message": str(e),
            "file_path": file_path,
            "fixed_code": "",
            "description": "Failed to generate fix"
        }


# ============================================================================
# MR Review Enhancement Tools (Feature Parity with Standard Mode)
# ============================================================================

validate_mr_webhook_schema = {
    "name": "validate_mr_webhook",
    "description": "Validate if a GitLab MR webhook should be processed. Checks MR action (allows open, reopen, update), MR state, branch monitoring configuration, and auto-fix branch detection. Returns validation result with skip reason if applicable.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "project_id": {"type": "STRING", "description": "GitLab project ID"},
            "mr_iid": {"type": "INTEGER", "description": "Merge request IID"},
            "target_branch": {"type": "STRING", "description": "Target branch name"},
            "source_branch": {"type": "STRING", "description": "Source branch name"},
            "mr_state": {"type": "STRING", "description": "MR state (opened, closed, merged)"},
            "action": {"type": "STRING", "description": "Webhook action (open, reopen, update, merge, close)"}
        },
        "required": ["project_id", "mr_iid", "target_branch", "source_branch", "mr_state", "action"]
    }
}


async def validate_mr_webhook(
    project_id: str,
    mr_iid: int,
    target_branch: str,
    source_branch: str,
    mr_state: str,
    action: str
) -> Dict[str, Any]:
    """
    Validate if a GitLab MR webhook should be processed.

    Checks:
    1. MR action must be 'open', 'reopen', or 'update' (not merge, close)
    2. MR state must be 'opened'
    3. Target branch must be monitored (configured in repository)
    4. Source branch must not be auto-fix branch (gatekeeper/*)

    Returns:
        Dict with should_process, skip_reason, project_id, mr_iid
    """
    # Check 1: Action must be 'open', 'reopen', or 'update'
    valid_actions = {"open", "reopen", "update"}
    if action not in valid_actions:
        return {
            "should_process": False,
            "skip_reason": f"MR action is '{action}', only '{', '.join(valid_actions)}' actions are processed",
            "project_id": project_id,
            "mr_iid": mr_iid
        }

    # Check 2: State must be 'opened'
    if mr_state != "opened":
        return {
            "should_process": False,
            "skip_reason": f"MR state is '{mr_state}', only 'opened' MRs are processed",
            "project_id": project_id,
            "mr_iid": mr_iid
        }

    # Check 3: Target branch must be monitored
    try:
        should_process = await review_service.should_process_webhook(str(project_id), target_branch)
        if not should_process:
            repo = await repository_service.get_repository(str(project_id))
            monitored_branches = repo.get("target_branches", []) if repo else []
            return {
                "should_process": False,
                "skip_reason": f"Target branch '{target_branch}' is not monitored. Monitored branches: {monitored_branches}",
                "project_id": project_id,
                "mr_iid": mr_iid
            }
    except Exception as e:
        print(f"[WARN] [validate_mr_webhook] Failed to check branch monitoring: {e}")
        return {
            "should_process": False,
            "skip_reason": f"Failed to validate branch monitoring: {str(e)}",
            "project_id": project_id,
            "mr_iid": mr_iid
        }

    # Check 4: Source branch must not be auto-fix branch
    if source_branch.startswith("gatekeeper/"):
        return {
            "should_process": False,
            "skip_reason": f"Source branch '{source_branch}' is an auto-fix branch, skipping review",
            "project_id": project_id,
            "mr_iid": mr_iid
        }

    return {
        "should_process": True,
        "skip_reason": None,
        "project_id": project_id,
        "mr_iid": mr_iid
    }


post_loading_indicator_schema = {
    "name": "post_loading_indicator",
    "description": "Post a loading indicator comment to a GitLab MR. This should be the first step in MR review to show users that analysis is in progress.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "project_id": {"type": "STRING", "description": "GitLab project ID"},
            "mr_iid": {"type": "INTEGER", "description": "Merge request IID"},
            "user_id": {"type": "STRING", "description": "Gatekeeper user ID for GitLab authentication"},
        },
        "required": ["project_id", "mr_iid", "user_id"]
    }
}


async def post_loading_indicator(
    project_id: str,
    mr_iid: int,
    user_id: str = "",
) -> Dict[str, Any]:
    """
    Post a loading indicator comment to a GitLab MR.

    Returns:
        Dict with status, comment_id, message
    """
    from datetime import datetime

    loading_message = (
        "### 🛡️ The Gatekeeper Security Audit\n\n"
        "🔄 **Analysis in progress...**\n\n"
        "This may take a minute or two depending on the size of the changes.\n\n"
        "---\n\n"
        f"*Started: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}*"
    )

    try:
        resolved_user_id, _ = await review_service.resolve_gitlab_token(
            str(project_id),
            user_id or None,
        )
        result = await post_gitlab_mr_comment(
            user_id=resolved_user_id or user_id or "",
            project_id=str(project_id),
            mr_iid=mr_iid,
            comment=loading_message
        )

        return {
            "status": "success",
            "comment_id": result.get("id"),
            "message": f"Loading indicator posted (comment ID: {result.get('id')})"
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to post loading indicator: {str(e)}"
        }


update_review_comment_schema = {
    "name": "update_review_comment",
    "description": "Update an existing MR comment with the full audit report. This replaces the loading indicator with the complete analysis results.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "project_id": {"type": "STRING", "description": "GitLab project ID"},
            "mr_iid": {"type": "INTEGER", "description": "Merge request IID"},
            "comment_id": {"type": "INTEGER", "description": "ID of comment to update"},
            "audit_report": {"type": "STRING", "description": "Full audit report in markdown format"},
            "user_id": {"type": "STRING", "description": "Gatekeeper user ID for GitLab authentication"},
        },
        "required": ["project_id", "mr_iid", "comment_id", "audit_report", "user_id"]
    }
}


async def update_review_comment(
    project_id: str,
    mr_iid: int,
    comment_id: int,
    audit_report: str,
    user_id: str = "",
) -> Dict[str, Any]:
    """
    Update an existing MR comment with the full audit report.

    Returns:
        Dict with status, comment_id, message
    """
    from datetime import datetime

    # Add timestamp to report
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    report_with_timestamp = f"{audit_report}\n\n---\n\n*Last updated: {timestamp}*"

    try:
        resolved_user_id, _ = await review_service.resolve_gitlab_token(
            str(project_id),
            user_id or None,
        )
        result = await post_gitlab_mr_comment(
            user_id=resolved_user_id or user_id or "",
            project_id=str(project_id),
            mr_iid=mr_iid,
            comment=report_with_timestamp,
            note_id=comment_id
        )

        return {
            "status": "success",
            "comment_id": comment_id,
            "message": f"Review comment updated (comment ID: {comment_id})"
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to update review comment: {str(e)}"
        }


update_commit_status_schema = {
    "name": "update_commit_status",
    "description": "Update the commit status badge for a GitLab MR. This shows a visual indicator (success/failed/running) on the commit in GitLab.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "project_id": {"type": "STRING", "description": "GitLab project ID"},
            "commit_sha": {"type": "STRING", "description": "Commit SHA to update status for"},
            "status": {"type": "STRING", "description": "Status value", "enum": ["success", "failed", "running"]},
            "description": {"type": "STRING", "description": "Description text for the status"},
            "user_id": {"type": "STRING", "description": "Gatekeeper user ID for GitLab authentication"},
        },
        "required": ["project_id", "commit_sha", "status", "user_id"]
    }
}


async def update_commit_status(
    project_id: str,
    commit_sha: str,
    status: str,
    description: str = "Security audit completed",
    user_id: str = "",
) -> Dict[str, Any]:
    """
    Update the commit status badge for a GitLab MR.

    Returns:
        Dict with status, message
    """
    # Map our status to GitLab status values
    status_map = {
        "success": "success",
        "failed": "failed",
        "running": "pending"
    }

    gitlab_status = status_map.get(status, "failed")

    try:
        resolved_user_id, _ = await review_service.resolve_gitlab_token(
            str(project_id),
            user_id or None,
        )
        result = await _gitlab_rest_api_call(
            user_id=resolved_user_id or user_id or "",
            project_id=str(project_id),
            method="POST",
            endpoint=f"/projects/{project_id}/statuses/{commit_sha}",
            json_data={
                "state": gitlab_status,
                "context": "gatekeeper/security-review",
                "description": description
            }
        )

        return {
            "status": "success",
            "message": f"Commit status updated to '{gitlab_status}'"
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to update commit status: {str(e)}"
        }


track_progress_schema = {
    "name": "track_progress",
    "description": "Update progress logs in MongoDB for a merge request. This enables real-time progress tracking in the UI.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "project_id": {"type": "STRING", "description": "GitLab project ID"},
            "mr_iid": {"type": "INTEGER", "description": "Merge request IID"},
            "step": {"type": "STRING", "description": "Step name (e.g., 'clone', 'analysis', 'completed')"},
            "message": {"type": "STRING", "description": "Progress message"},
            "status": {"type": "STRING", "description": "Step status", "enum": ["running", "completed", "failed"]}
        },
        "required": ["project_id", "mr_iid", "step", "message"]
    }
}


async def track_progress(
    project_id: str,
    mr_iid: int,
    step: str,
    message: str,
    status: str = "running"
) -> Dict[str, Any]:
    """
    Update progress logs in MongoDB for a merge request.

    Returns:
        Dict with status, message
    """
    try:
        success = await repository_service.add_mr_progress_log(
            repo_id=str(project_id),
            mr_iid=mr_iid,
            step=step,
            message=message,
            status=status
        )

        if success:
            return {
                "status": "success",
                "message": f"Progress updated: {step} - {message}"
            }
        else:
            return {
                "status": "error",
                "message": "Failed to track progress - MR not found in database"
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to track progress: {str(e)}"
        }


# ============================================================================
# GitLab REST API Helper Functions (for direct API calls without MCP)
# ============================================================================

async def _get_gitlab_token_for_user(user_id: str, project_id: str) -> str:
    """Resolve GitLab token via shared review_service resolver."""
    _, token = await review_service.resolve_gitlab_token(
        str(project_id),
        str(user_id) if user_id else None,
    )
    if not token:
        print(f"[WARN] No GitLab token found for user {user_id}, project {project_id}")
    return token or ""


async def _gitlab_rest_api_call(
    user_id: str,
    project_id: str,
    method: str,
    endpoint: str,
    params: Dict = None,
    json_data: Dict = None,
    use_fallback: bool = True
) -> Dict[str, Any]:
    """
    Direct GitLab REST API call using httpx with user token authentication.

    Args:
        user_id: User ID for authentication
        project_id: Project ID for authentication
        method: HTTP method (GET, POST, PUT, DELETE)
        endpoint: API endpoint path (e.g., "/projects/123/repository/branches")
        params: Query parameters
        json_data: Request body for POST/PUT
        use_fallback: If True, fall back to global token on 401

    Returns:
        Response JSON as dict

    Raises:
        Exception: If API call fails or no token available
    """
    gitlab_base_url = os.getenv("GITLAB_BASE_URL", "https://gitlab.com")
    token = await _get_gitlab_token_for_user(user_id, project_id)

    if not token:
        raise Exception(f"No GitLab token found for user {user_id}, project {project_id}")

    url = f"{gitlab_base_url}/api/v4{endpoint}"
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Try with user's token first
        if method.upper() == "GET":
            response = await client.get(url, headers=headers, params=params)
        elif method.upper() == "POST":
            response = await client.post(url, headers=headers, params=params, json=json_data)
        elif method.upper() == "PUT":
            response = await client.put(url, headers=headers, params=params, json=json_data)
        elif method.upper() == "DELETE":
            response = await client.delete(url, headers=headers, params=params)
        else:
            raise ValueError(f"Unsupported method: {method}")

        # If user's token fails with 401, try with global token as fallback
        if response.status_code == 401 and use_fallback:
            print(f"[WARN] User token failed with 401, trying fallback to global token...")
            global_token = os.getenv("GITLAB_PERSONAL_ACCESS_TOKEN")
            if global_token and global_token != token:
                headers["Authorization"] = f"Bearer {global_token}"

                if method.upper() == "GET":
                    response = await client.get(url, headers=headers, params=params)
                elif method.upper() == "POST":
                    response = await client.post(url, headers=headers, params=params, json=json_data)
                elif method.upper() == "PUT":
                    response = await client.put(url, headers=headers, params=params, json=json_data)
                elif method.upper() == "DELETE":
                    response = await client.delete(url, headers=headers, params=params)

                print(f"[INFO] Retried with global token, status: {response.status_code}")
            else:
                print(f"[WARN] No global token available for fallback")

        if response.status_code >= 400:
            error_msg = response.text if response.text else f"HTTP {response.status_code}"
            raise Exception(f"GitLab API error: {error_msg}")

        return response.json() if response.text else {}


# ============================================================================
# GitLab REST API Tool Callbacks
# ============================================================================

async def create_gitlab_branch(
    user_id: str,
    project_id: str,
    branch_name: str,
    ref: str = "main"
) -> Dict[str, Any]:
    """
    Create a new branch in GitLab using direct REST API call.

    Args:
        user_id: User ID for authentication
        project_id: GitLab project ID
        branch_name: Name of the new branch
        ref: Branch name or commit SHA to create from (default: main)

    Returns:
        Dictionary with branch info (name, commit, etc.)
    """
    payload = {
        "branch": branch_name,
        "ref": ref
    }

    result = await _gitlab_rest_api_call(
        user_id=user_id,
        project_id=project_id,
        method="POST",
        endpoint=f"/projects/{project_id}/repository/branches",
        json_data=payload
    )

    return {
        "status": "success",
        "branch_name": result.get("name"),
        "commit": result.get("commit", {}),
        "web_url": result.get("web_url")
    }


async def create_gitlab_merge_request(
    user_id: str,
    project_id: str,
    source_branch: str,
    target_branch: str,
    title: str,
    description: str = ""
) -> Dict[str, Any]:
    """
    Create a merge request in GitLab using direct REST API call.

    Args:
        user_id: User ID for authentication
        project_id: GitLab project ID
        source_branch: Source branch name
        target_branch: Target branch name
        title: MR title
        description: MR description (markdown supported)

    Returns:
        Dictionary with MR info (iid, web_url, etc.)
    """
    payload = {
        "source_branch": source_branch,
        "target_branch": target_branch,
        "title": title,
        "description": description
    }

    result = await _gitlab_rest_api_call(
        user_id=user_id,
        project_id=project_id,
        method="POST",
        endpoint=f"/projects/{project_id}/merge_requests",
        json_data=payload
    )

    return {
        "status": "success",
        "iid": result.get("iid"),
        "web_url": result.get("web_url"),
        "title": result.get("title"),
        "state": result.get("state")
    }


async def commit_file_to_branch(
    user_id: str,
    project_id: str,
    file_path: str,
    branch_name: str,
    content: str,
    commit_message: str
) -> Dict[str, Any]:
    """
    Commit a file to a GitLab branch using direct REST API call.

    This creates or updates a file on the specified branch with a new commit.

    Args:
        user_id: User ID for authentication
        project_id: GitLab project ID
        file_path: Full path to the file in repository (e.g., 'src/app.py')
        branch_name: Branch name to commit to
        content: File content to write
        commit_message: Commit message

    Returns:
        Dictionary with commit info (sha, message, etc.)
    """
    import base64
    import urllib.parse

    # Encode content as base64
    content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")

    # URL-encode the file path for GitLab API (slashes need to be encoded)
    encoded_file_path = urllib.parse.quote(file_path, safe='')

    payload = {
        "branch": branch_name,
        "content": content_b64,
        "commit_message": commit_message,
        "encoding": "base64"
    }

    print(f"[DEBUG] [commit_file_to_branch] Committing to branch: {branch_name}, file: {file_path}")
    print(f"[DEBUG] [commit_file_to_branch] Encoded file path: {encoded_file_path}")

    try:
        result = await _gitlab_rest_api_call(
            user_id=user_id,
            project_id=project_id,
            method="POST",
            endpoint=f"/projects/{project_id}/repository/files/{encoded_file_path}",
            json_data=payload
        )

        return {
            "status": "success",
            "file_path": result.get("file_path"),
            "branch": result.get("branch"),
            "commit_short_id": result.get("commit_short_id"),
            "commit_message": result.get("commit_message")
        }
    except Exception as e:
        # If file already exists (400 error), try updating it instead
        if "400" in str(e) or "already exists" in str(e):
            print(f"[DEBUG] [commit_file_to_branch] File exists, updating instead...")
            # Use PUT to update existing file
            payload["start_branch"] = branch_name

            result = await _gitlab_rest_api_call(
                user_id=user_id,
                project_id=project_id,
                method="PUT",
                endpoint=f"/projects/{project_id}/repository/files/{encoded_file_path}",
                json_data=payload
            )

            return {
                "status": "success",
                "file_path": result.get("file_path"),
                "branch": result.get("branch"),
                "commit_short_id": result.get("commit_short_id"),
                "commit_message": result.get("commit_message"),
                "updated": True
            }
        raise
