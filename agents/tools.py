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
    "description": "Clones a GitLab repository branch to a local temporary workspace.",
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
    "description": "Performs static call-graph impact analysis on the codebase to identify blast radius and breaking change risks for changed symbols.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "repo_path": {"type": "STRING", "description": "Absolute path to the cloned repository workspace."},
            "repo_name": {"type": "STRING", "description": "Repository identifier / directory name."},
            "source_branch": {"type": "STRING", "description": "The branch containing code modifications (e.g. feature-branch)."},
            "target_branch": {"type": "STRING", "description": "The base branch to compare against (default 'main')."}
        },
        "required": ["repo_path", "repo_name", "source_branch"]
    }
}

run_schema_inspection_schema = {
    "name": "run_schema_inspection",
    "description": "Scans modified files to detect schema definition drift in MongoDB schemas and computes schema delta.",
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
    "description": "Get merge request diffs as a raw unified diff string.",
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
    "description": "Runs npx gitnexus analyze on the local repository to build call graphs.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "repo_path": {"type": "STRING", "description": "Absolute path to the cloned repository workspace."}
        },
        "required": ["repo_path"]
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
    target_branch: str = "main"
) -> Dict[str, Any]:
    """Runs static impact analysis and returns a dictionary payload representing the report."""
    report = await impact_measurement_service.run_impact_analysis(
        repo_path=repo_path,
        repo_name=repo_name,
        source_branch=source_branch,
        target_branch=target_branch,
        changed_symbols=[],
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
    if sys.platform == "win32":
        npm_result = subprocess.run(["where", "npm"], capture_output=True, text=True)
        if npm_result.returncode == 0:
            npm_path = npm_result.stdout.strip().split('\n')[0].strip()
            nodejs_dir = Path(npm_path).parent
            npx_cmd = nodejs_dir / "npx.cmd"
            if npx_cmd.exists():
                npx_executable = str(npx_cmd)

    try:
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


# ============================================================================
# GitLab REST API Helper Functions (for direct API calls without MCP)
# ============================================================================

async def _get_gitlab_token_for_user(user_id: str, project_id: str) -> str:
    """
    Get GitLab token for a user and project.
    Priority:
    1. User's project-specific token (from user_service)
    2. Global GITLAB_PERSONAL_ACCESS_TOKEN

    Args:
        user_id: User ID
        project_id: Project ID

    Returns:
        GitLab access token or empty string if not found
    """
    # Try project-specific token first
    project_token = await user_service.get_user_gitlab_token(str(user_id), str(project_id))
    if project_token:
        return project_token

    # Fallback to global token
    global_token = os.getenv("GITLAB_PERSONAL_ACCESS_TOKEN", "")
    if global_token:
        print(f"[INFO] Using global GitLab token for user {user_id}, project {project_id}")
        return global_token

    print(f"[WARN] No GitLab token found for user {user_id}, project {project_id}")
    return ""


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

    # Encode content as base64
    content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")

    payload = {
        "branch": branch_name,
        "content": content_b64,
        "commit_message": commit_message,
        "encoding": "base64"
    }

    try:
        result = await _gitlab_rest_api_call(
            user_id=user_id,
            project_id=project_id,
            method="POST",
            endpoint=f"/projects/{project_id}/repository/files/{file_path}",
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
            # Use PUT to update existing file
            payload["start_branch"] = branch_name

            result = await _gitlab_rest_api_call(
                user_id=user_id,
                project_id=project_id,
                method="PUT",
                endpoint=f"/projects/{project_id}/repository/files/{file_path}",
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
