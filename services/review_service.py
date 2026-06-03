import os
import sys
import time
import json
import asyncio
import subprocess
from pathlib import Path
import httpx

# Gatekeeper Modules
from atomic_patches import (
    AtomicPatchParser,
    create_patch_summary
)

# Service Imports
from services import mcp_service, repository_service, user_service, mongo_client
from services.gemini_service import run_gemini_review, run_gemini_review_with_gitnexus, run_gemini_fix_analysis
from services.remediation_service import apply_auto_fixes
from services.encryption_service import decrypt_value


# ============================================================================
# Project Access Token Helper
# ============================================================================

async def _get_project_access_token(project_id: str, user_id: str) -> str:
    """
    Get the project access token from MongoDB for a specific project.

    The token is stored in the user document under project_tokens[project_id].token_encrypted.

    Args:
        project_id: GitLab project ID
        user_id: User ID who owns the project

    Returns:
        Decrypted project access token or empty string if not found
    """
    import sys
    try:
        sys.stderr.write(f"[DEBUG] _get_project_access_token called with project_id: {project_id}, user_id: {user_id}\n")
        sys.stderr.flush()

        # Get user document from MongoDB
        if mongo_client.CONNECTION_STRING:
            user_doc = await mongo_client.find_one(
                collection_name="users",
                filter={"_id": user_id}
            )
            sys.stderr.write(f"[DEBUG] User document found: {user_doc is not None}\n")
            sys.stderr.flush()
            if user_doc:
                sys.stderr.write(f"[DEBUG] User document keys: {list(user_doc.keys())}\n")
                sys.stderr.write(f"[DEBUG] project_tokens keys: {list(user_doc.get('project_tokens', {}).keys())}\n")
                sys.stderr.flush()

            if not user_doc:
                sys.stderr.write(f"[WARN] User {user_id} not found in MongoDB\n")
                sys.stderr.flush()
                return ""

            # Get encrypted project token
            project_tokens = user_doc.get("project_tokens", {})
            sys.stderr.write(f"[DEBUG] Looking for project_id: {project_id} (str: '{str(project_id)}')\n")
            sys.stderr.flush()
            project_token_data = project_tokens.get(str(project_id))
            sys.stderr.write(f"[DEBUG] project_token_data with str key: {project_token_data is not None}\n")
            sys.stderr.flush()

            if not project_token_data:
                # Try with integer key as well
                project_token_data = project_tokens.get(int(project_id)) if project_id.isdigit() else None
                sys.stderr.write(f"[DEBUG] project_token_data with int key: {project_token_data is not None}\n")
                sys.stderr.flush()

            if not project_token_data:
                sys.stderr.write(f"[WARN] No project token found for project {project_id} in user {user_id}\n")
                sys.stderr.write(f"[DEBUG] Available project_token keys: {list(project_tokens.keys())}\n")
                sys.stderr.flush()
                return ""

            encrypted_token = project_token_data.get("token_encrypted", "")
            if not encrypted_token:
                sys.stderr.write(f"[WARN] Project token exists but is empty for project {project_id}\n")
                sys.stderr.flush()
                return ""

            # Decrypt the token
            decrypted_token = decrypt_value(encrypted_token)
            sys.stderr.write(f"[OK] Retrieved and decrypted project access token for project {project_id}\n")
            sys.stderr.flush()
            return decrypted_token
        else:
            sys.stderr.write(f"[WARN] MongoDB not configured, cannot retrieve project token\n")
            sys.stderr.flush()
            return ""

    except Exception as e:
        sys.stderr.write(f"[ERROR] Failed to get project access token: {e}\n")
        sys.stderr.flush()
        import traceback
        traceback.print_exc()
        return ""


# ============================================================================
# Repository Clone Helper
# ============================================================================

async def _clone_repository_to_temp_workspace(
    project_id: str,
    source_branch: str,
    repo_http_url: str,
    user_id: str,
    target_branch: str,
    checkout_source: bool = False
) -> Path:
    """
    Clone a GitLab repository to a temporary workspace folder.

    Workflow:
    1. Clone target branch with depth 1 and single-branch (baseline)
    2. Optionally: Fetch source branch and checkout (for diff detection)

    Uses the project access token from MongoDB for authentication.

    Args:
        project_id: GitLab project ID
        source_branch: Source branch to optionally fetch and checkout (contains changes)
        repo_http_url: HTTP URL of the repository (e.g., https://gitlab.com/group/project.git)
        user_id: User ID who owns the project
        target_branch: Target branch to clone (baseline branch)
        checkout_source: If True, fetch and checkout source_branch. If False, stay on target_branch.

    Returns:
        Path to the cloned repository

    Raises:
        Exception: If clone fails
    """
    try:
        # Create temp_workspace directory in project root
        temp_workspace = Path(__file__).parent.parent / "temp_workspace"
        temp_workspace.mkdir(exist_ok=True)

        # Unique folder for this clone (using project_id)
        repo_path = temp_workspace / f"project_{project_id}"

        # Clean up existing clone if present
        if repo_path.exists():
            print(f"[INFO] Removing existing clone at {repo_path}")
            if sys.platform == "win32":
                subprocess.run(["rd", "/s", "/q", str(repo_path)], shell=True, check=False)
            else:
                subprocess.run(["rm", "-rf", str(repo_path)], shell=False, check=True)

        # Get project access token from MongoDB
        print(f"[DEBUG] About to call _get_project_access_token...", flush=True)
        project_token = await _get_project_access_token(project_id, user_id)
        print(f"[DEBUG] Got project token: {'*' * len(project_token) if project_token else 'None'}", flush=True)

        if not project_token:
            raise Exception(f"No project access token found for project {project_id}")

        # Parse the HTTP URL and inject the token
        # Format: https://gitlab.com/group/project.git
        # Token format: https://oauth2:TOKEN@gitlab.com/group/project.git
        if "://" in repo_http_url:
            # Remove protocol and inject token
            url_parts = repo_http_url.split("://", 1)
            protocol = url_parts[0]
            rest = url_parts[1] if len(url_parts) > 1 else ""

            # Build authenticated URL
            clone_url = f"{protocol}://oauth2:{project_token}@{rest}"
        else:
            raise Exception(f"Invalid repository URL format: {repo_http_url}")

        # Step 1: Clone the target branch (baseline) with depth 1 and single-branch
        print(f"[INFO] Step 1: Cloning target branch '{target_branch}' (depth 1, single-branch)...", flush=True)
        print(f"[DEBUG] Clone URL (token masked): {clone_url.replace(project_token, '***') if project_token else clone_url}", flush=True)
        print(f"[DEBUG] Target path: {repo_path}", flush=True)

        result = subprocess.run(
            ["git", "clone", "--single-branch", "--depth", "1", "--branch", target_branch, clone_url, str(repo_path)],
            capture_output=True,
            text=True,
            check=False
        )

        print(f"[DEBUG] Git clone exit code: {result.returncode}", flush=True)
        if result.stdout:
            print(f"[DEBUG] Git clone stdout: {result.stdout}", flush=True)
        if result.stderr:
            print(f"[DEBUG] Git clone stderr: {result.stderr}", flush=True)

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            print(f"[ERROR] Git clone command failed", flush=True)
            raise Exception(f"Git clone failed: {error_msg}")

        print(f"[OK] Target branch cloned to {repo_path}", flush=True)

        # Step 2: Fetch only the latest commit of source branch from remote
        print(f"[INFO] Step 2: Fetching source branch '{source_branch}' from remote (depth 1)...", flush=True)

        # Add the source branch to remote configuration
        set_branch_result = subprocess.run(
            ["git", "remote", "set-branches", "--add", "origin", source_branch],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(repo_path)
        )

        print(f"[DEBUG] Git set-branches exit code: {set_branch_result.returncode}", flush=True)
        if set_branch_result.stdout:
            print(f"[DEBUG] Git set-branches stdout: {set_branch_result.stdout}", flush=True)
        if set_branch_result.stderr:
            print(f"[DEBUG] Git set-branches stderr: {set_branch_result.stderr}", flush=True)

        # Fetch only the latest commit of the source branch
        fetch_result = subprocess.run(
            ["git", "fetch", "--depth", "1", "origin", source_branch],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(repo_path)
        )

        print(f"[DEBUG] Git fetch exit code: {fetch_result.returncode}", flush=True)
        if fetch_result.stdout:
            print(f"[DEBUG] Git fetch stdout: {fetch_result.stdout}", flush=True)
        if fetch_result.stderr:
            print(f"[DEBUG] Git fetch stderr: {fetch_result.stderr}", flush=True)

        if fetch_result.returncode != 0:
            print(f"[WARN] Could not fetch source branch '{source_branch}'", flush=True)
        else:
            print(f"[OK] Source branch '{source_branch}' fetched successfully", flush=True)

        # Step 3: Optionally checkout source branch
        if checkout_source:
            print(f"[INFO] Step 3: Creating local tracking branch for '{source_branch}'...", flush=True)

            checkout_result = subprocess.run(
                ["git", "checkout", "-b", source_branch, f"origin/{source_branch}"],
                capture_output=True,
                text=True,
                check=False,
                cwd=str(repo_path)
            )

            print(f"[DEBUG] Git checkout exit code: {checkout_result.returncode}", flush=True)
            if checkout_result.stdout:
                print(f"[DEBUG] Git checkout stdout: {checkout_result.stdout}", flush=True)
            if checkout_result.stderr:
                print(f"[DEBUG] Git checkout stderr: {checkout_result.stderr}", flush=True)

            if checkout_result.returncode != 0:
                print(f"[WARN] Could not checkout source branch '{source_branch}'", flush=True)
            else:
                print(f"[OK] Local tracking branch '{source_branch}' created successfully", flush=True)
        else:
            print(f"[INFO] Staying on target branch '{target_branch}' for baseline analysis", flush=True)

        print(f"[OK] Repository ready with both branches available", flush=True)
        return repo_path

    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Git clone CalledProcessError: {e}", flush=True)
        print(f"[ERROR] stderr: {e.stderr if hasattr(e, 'stderr') else 'N/A'}", flush=True)
        raise Exception(f"Repository clone failed: {e.stderr}")
    except Exception as e:
        print(f"[ERROR] Clone failed with exception: {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()
        raise Exception(f"Clone failed: {e}")


# ============================================================================
# GitLab API Helper with User Token
# ============================================================================

async def _gitlab_api_call(
    user_id: str,
    project_id: str,
    method: str,
    endpoint: str,
    gitlab_base_url: str = "https://gitlab.com",
    data: dict = None,
    params: dict = None,
    use_fallback: bool = True
) -> dict:
    """
    Make a direct GitLab API call using the user's project-specific token.

    This bypasses the global gitlab_session which uses a fixed token,
    allowing per-user authentication for private projects.

    Args:
        user_id: User ID to get the GitLab token for
        project_id: Project ID to get project-specific token
        method: HTTP method (GET, POST, PUT, DELETE)
        endpoint: API endpoint path (e.g., "/projects/123/merge_requests/1")
        gitlab_base_url: GitLab instance URL
        data: Request body for POST/PUT
        params: Query parameters
        use_fallback: If True, fall back to global token on 401

    Returns:
        Response JSON as dict

    Raises:
        Exception: If API call fails or user has no token
    """
    # Get user's project-specific GitLab token
    user_token = await user_service.get_user_gitlab_token(str(user_id), str(project_id))
    if not user_token:
        raise Exception(f"No GitLab token found for user {user_id}, project {project_id}")

    url = f"{gitlab_base_url}/api/v4{endpoint}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Try with user's token first
        headers = {
            "Authorization": f"Bearer {user_token}",
            "Content-Type": "application/json"
        }

        if method.upper() == "GET":
            response = await client.get(url, headers=headers, params=params)
        elif method.upper() == "POST":
            response = await client.post(url, headers=headers, json=data, params=params)
        elif method.upper() == "PUT":
            response = await client.put(url, headers=headers, json=data, params=params)
        elif method.upper() == "DELETE":
            response = await client.delete(url, headers=headers, params=params)
        else:
            raise ValueError(f"Unsupported method: {method}")

        # If user's token fails with 401, try with global token as fallback
        if response.status_code == 401 and use_fallback:
            print(f"[WARN] User token failed with 401, trying fallback to global token...")
            global_token = os.getenv("GITLAB_PERSONAL_ACCESS_TOKEN")
            if global_token:
                headers["Authorization"] = f"Bearer {global_token}"

                if method.upper() == "GET":
                    response = await client.get(url, headers=headers, params=params)
                elif method.upper() == "POST":
                    response = await client.post(url, headers=headers, json=data, params=params)
                elif method.upper() == "PUT":
                    response = await client.put(url, headers=headers, json=data, params=params)
                elif method.upper() == "DELETE":
                    response = await client.delete(url, headers=headers, params=params)

                print(f"[INFO] Retried with global token, status: {response.status_code}")
            else:
                print(f"[WARN] No global token available for fallback")

        if response.status_code >= 400:
            error_msg = response.text if response.text else f"HTTP {response.status_code}"
            raise Exception(f"GitLab API error: {error_msg}")

        return response.json() if response.text else {}


async def _gitlab_get_mr_diffs(user_id: str, project_id: str, mr_iid: int) -> str:
    """
    Get merge request diffs using the user's GitLab token.

    Args:
        user_id: User ID to get the GitLab token for
        project_id: GitLab project ID
        mr_iid: Merge request IID

    Returns:
        Raw diff content as string
    """
    try:
        diffs = await _gitlab_api_call(
            user_id=user_id,
            project_id=str(project_id),
            method="GET",
            endpoint=f"/projects/{project_id}/merge_requests/{mr_iid}/diffs"
        )

        raw_diff_content = ""
        if isinstance(diffs, list):
            for diff_obj in diffs:
                if isinstance(diff_obj, dict):
                    old_path = diff_obj.get('old_path', '')
                    new_path = diff_obj.get('new_path', '')
                    diff_text = diff_obj.get('diff', '')

                    if old_path and new_path:
                        raw_diff_content += f"diff --git a/{old_path} b/{new_path}\n"
                        raw_diff_content += diff_text + "\n"

        return raw_diff_content
    except Exception as e:
        print(f"[ERROR] Failed to get MR diffs: {e}")
        return ""


async def get_user_config_from_repo(project_id: str) -> dict:
    """
    Get user's Gemini configuration from the repository owner.

    Args:
        project_id: GitLab project/repository ID

    Returns:
        User's Gemini config dict or empty dict if not found
    """
    try:
        # Look up repository to get user_id
        repo = await repository_service.get_repository(str(project_id))
        if repo and repo.get("user_id"):
            user_id = repo["user_id"]
            print(f"[INFO] Found repository owner: {user_id}")
            # Get user's Gemini config
            return await user_service.get_user_gemini_config(user_id)
        else:
            print(f"[WARN] Repository {project_id} not found or has no owner")
            return {}
    except Exception as e:
        print(f"[WARN] Failed to get user config from repository: {e}")
        return {}


async def should_process_webhook(repo_id: str, target_branch: str) -> bool:
    """
    Check if webhook should be processed based on repository's target branches.

    Args:
        repo_id: Repository ID
        target_branch: Target branch of the MR

    Returns:
        True if webhook should be processed, False otherwise
    """
    try:
        repo = await repository_service.get_repository(str(repo_id))
        target_branches = repo.get("target_branches", ["main", "master", "develop"])

        # If no target branches specified, process all
        if not target_branches:
            return True

        # Check if target branch is in the monitored list
        should_process = target_branch in target_branches

        if not should_process:
            print(f"[INFO] Skipping MR for branch '{target_branch}' - not in monitored branches: {target_branches}")

        return should_process
    except Exception as e:
        print(f"[WARN] Failed to check target branches, processing anyway: {e}")
        return True  # Default to processing on error


async def orchestrate_review(payload: dict) -> dict:
    """
    Orchestrates the entire webhook auditing pipeline.

    1. Logs signature to MongoDB
    2. Fetches MR diffs from GitLab
    3. Submits code diff to Gemini Pro Core
    4. Posts final review report & commit status
    5. Runs hunk-level auto-fix generation & MR creation
    """
    # Grab sessions dynamically from connection manager module
    mongo_session = mcp_service.mongo_session
    gitlab_session = mcp_service.gitlab_session

    object_attrs = payload.get("object_attributes", {})

    # Helper function to add progress logs
    async def add_log(step: str, message: str, status: str = "running"):
        """Add a progress log entry to the MR document"""
        try:
            await repository_service.add_mr_progress_log(
                repo_id=str(project_id),
                mr_iid=int(mr_iid),
                step=step,
                message=message,
                status=status
            )
        except Exception as log_err:
            print(f"[WARN] Failed to add progress log: {log_err}")
    state = object_attrs.get("state")

    if state != "opened":
        print(f"[ℹ] MR state is '{state}' - skipping audit")
        return {"status": "skipped_state", "state": state}

    mr_title = object_attrs.get("title")
    source_branch = object_attrs.get("source_branch")
    target_branch = object_attrs.get("target_branch", "main")
    project_id = payload.get("project", {}).get("id")
    mr_iid = object_attrs.get("iid")
    mr_internal_id = object_attrs.get("id")
    author = payload.get("user", {}).get("username", "unknown")
    # Extract user_id from webhook payload for billing attribution
    user_id = payload.get("user", {}).get("id")
    web_url = object_attrs.get("url", "")
    created_at = object_attrs.get("created_at", "")
    updated_at = object_attrs.get("updated_at", "")
    description = object_attrs.get("description", "")

    # Check if we should process this webhook based on target branches
    if not await should_process_webhook(str(project_id), target_branch):
        return {"status": "skipped_branch_not_monitored", "target_branch": target_branch}

    # Extract changes statistics from webhook payload
    # GitLab MR hook provides this in object_attributes.stats
    stats = object_attrs.get("stats", {})
    additions = stats.get("additions", 0)
    deletions = stats.get("deletions", 0)
    files_changed = stats.get("total", 0)  # 'total' is the key for total files changed in GitLab

    # If stats are missing or all zeros, fetch from GitLab API
    if not stats or (additions == 0 and deletions == 0 and files_changed == 0):
        print("[INFO] Stats missing from webhook payload, fetching from GitLab API...")
        try:
            mr_details = await gitlab_session.call_tool(
                name="get_merge_request",
                arguments={
                    "project_id": str(project_id),
                    "merge_request_iid": int(mr_iid)
                }
            )
            if hasattr(mr_details, 'content') and mr_details.content:
                try:
                    mr_data = json.loads(mr_details.content[0].text)

                    # Try different possible locations for stats
                    # GitLab API may provide stats in different fields
                    if "diff_stats" in mr_data:
                        diff_stats = mr_data.get("diff_stats", {})
                        additions = diff_stats.get("additions", 0)
                        deletions = diff_stats.get("deletions", 0)

                    files_changed = mr_data.get("changed_files_count", 0)
                    if files_changed == 0:
                        # Try alternative field names
                        files_changed = mr_data.get("changes_count", 0)

                    print(f"[INFO] Fetched stats from GitLab API: +{additions} -{deletions} ({files_changed} files)")
                except json.JSONDecodeError:
                    print("[WARN] Could not parse MR details JSON")
        except Exception as e:
            print(f"[WARN] Failed to fetch stats from GitLab API: {e}")
            print(f"[WARN] Using default values (all zeros) for changes statistics")

    print(f"[INFO] MR changes: +{additions} -{deletions} ({files_changed} files)")

    # Ensure consistent types for database queries
    mr_iid_int = int(mr_iid) if mr_iid else 0
    project_id_str = str(project_id)

    # Store MR in MongoDB for frontend retrieval
    analysis_start_time = time.time()  # Track when we received the MR
    try:
        # Detect if this is an auto-fix MR (branch starts with "gatekeeper/")
        is_auto_fix = source_branch.startswith("gatekeeper/")
        auto_fix_for = None

        # If it's an auto-fix MR, try to extract the original MR ID from the branch name
        # Pattern: gatekeeper/atomic-fix-mr{original_mr_iid}-{timestamp}
        if is_auto_fix:
            import re
            match = re.search(r'gatekeeper/atomic-fix-mr(\d+)', source_branch)
            if match:
                auto_fix_for = int(match.group(1))
                print(f"[INFO] Detected auto-fix MR !{mr_iid_int} for original MR !{auto_fix_for}")

        mr_data = {
            "gitlab_mr_id": mr_iid_int,
            "gitlab_mr_internal_id": mr_internal_id,
            "repository_id": project_id_str,
            "repository_name": payload.get("project", {}).get("path_with_namespace", ""),
            "title": mr_title,
            "description": description,
            "author": author,
            "source_branch": source_branch,
            "target_branch": target_branch,
            "status": "open",
            "web_url": web_url,
            "created_at": created_at,
            "updated_at": updated_at,
            "changes": {
                "additions": additions,
                "deletions": deletions,
                "files_changed": files_changed
            },
            "analysis_status": "skipped" if is_auto_fix else "pending",
            "is_auto_fix": is_auto_fix,
            "auto_fix_for": auto_fix_for,
            "auto_fix_mrs": [],
            "auto_fix_status": "applied" if is_auto_fix else None,
            "progress_logs": [],  # Initialize empty progress logs
            "analysis_started_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(analysis_start_time))
        }

        action = object_attrs.get("action")
        if action == "open":
            print(f"[INFO] New MR opened: {mr_title}")

        await repository_service.store_mr_in_mongodb(mr_data)

        # Add initial log
        await add_log("received", "Merge request received and queued for analysis", "completed")
        print(f"[OK] MR {mr_iid} stored in MongoDB with changes data")

    except Exception as e:
        print(f"[WARN] Failed to store MR in MongoDB: {e}")
        # Continue with review even if storage fails

    # Get commit SHA for status updates
    commit_sha = (
        object_attrs.get("last_commit", {}).get("id") or
        object_attrs.get("sha") or
        object_attrs.get("merge_request_sha") or
        None
    )

    print(f"[OK] Webhook caught MR !{mr_iid} on Project {project_id}")
    print(f"[OK] Commit SHA: {commit_sha}")
    print(f"[OK] Starting Gatekeeper analysis pipeline...")

    if not commit_sha:
        print("[WARN] Warning: No commit SHA found in webhook!")
        # Fallback: Try to get the MR details from GitLab MCP to find the commit SHA
        if gitlab_session:
            try:
                print("[INFO] Fetching MR details from GitLab to get commit SHA...")
                mr_details = await gitlab_session.call_tool(
                    name="get_merge_request",
                    arguments={
                        "project_id": str(project_id),
                        "merge_request_iid": int(mr_iid)
                    }
                )
            except Exception as e:
                print(f"[ERROR] Failed to fetch MR details: {e}")

    # 🔒 Skip audit for Gatekeeper auto-generated branches to prevent infinite loops
    if source_branch.startswith("gatekeeper/"):
        print(f"[⏭️] Skipping audit for auto-generated branch: {source_branch}")

        # Add this auto-fix MR to the original MR's auto_fix_mrs list
        # This ensures the linkage is recorded even if link_auto_fix_to_original_mr hasn't run yet
        if auto_fix_for:
            try:
                if mongo_client.CONNECTION_STRING:
                    await mongo_client.update_one(
                        collection_name="merge_requests",
                        filter={
                            "repository_id": project_id_str,
                            "gitlab_mr_id": auto_fix_for
                        },
                        update={
                            "$push": {"auto_fix_mrs": mr_iid_int}
                        }
                    )
                    print(f"[OK] Added auto-fix MR !{mr_iid_int} to original MR !{auto_fix_for}'s auto_fix_mrs list")
                else:
                    print(f"[INFO] MongoDB not configured - skipping auto_fix_mrs update")
            except Exception as update_err:
                print(f"[WARN] Failed to update original MR's auto_fix_mrs list: {update_err}")

        return {"status": "skipped_auto_branch", "auto_fix_for": auto_fix_for}

    # Initialize variables for impact and schema analysis (scoped outside try blocks)
    impact_gemini_prompt = ""
    impact_report = None

    # ============================================================================
    # CLONE REPOSITORY TO TEMP WORKSPACE
    # ============================================================================
    # Clone the repository to temp_workspace for local analysis
    # Uses project access token from MongoDB for authentication
    print(f"[DEBUG] ===== CLONE STEP STARTING =====")
    print(f"[DEBUG] project_id: {project_id}, source_branch: {source_branch}")
    try:
        # Get HTTP URL from webhook payload or construct from project info
        project_http_url = payload.get("project", {}).get("http_url", "")
        print(f"[DEBUG] project_http_url from payload: {project_http_url}")
        if not project_http_url:
            # Construct HTTP URL from path_with_namespace and GitLab base URL
            gitlab_base_url = os.getenv("GITLAB_BASE_URL", "https://gitlab.com").rstrip("/")
            path_with_namespace = payload.get("project", {}).get("path_with_namespace", "")
            print(f"[DEBUG] path_with_namespace: {path_with_namespace}")
            if path_with_namespace:
                project_http_url = f"{gitlab_base_url}/{path_with_namespace}.git"

        print(f"[DEBUG] Final project_http_url: {project_http_url}")
        if not project_http_url:
            print("[WARN] Could not determine repository HTTP URL for cloning")
        else:
            print(f"[INFO] Cloning repository to temp_workspace...")
            cloned_repo_path = await _clone_repository_to_temp_workspace(
                project_id=str(project_id),
                source_branch=source_branch,
                repo_http_url=project_http_url,
                user_id=str(user_id),
                target_branch=target_branch,
                checkout_source=False  # Stay on target_branch for gitnexus analyze
            )
            print(f"[OK] Repository cloned successfully to {cloned_repo_path} (on target branch: {target_branch})", flush=True)

            # Get repo_name early - needed for gitnexus analyze and baseline query
            path_with_namespace = payload.get("project", {}).get("path_with_namespace", "")
            repo_name = path_with_namespace.split("/")[-1] if "/" in path_with_namespace else path_with_namespace or "project"
            print(f"[DEBUG] Repository name for GitNexus: {repo_name}", flush=True)

            # Run gitnexus analyze on the cloned repository (at target branch - baseline)
            print(f"[INFO] Running gitnexus analyze on cloned repository...", flush=True)
            print(f"[DEBUG] gitnexus working directory: {cloned_repo_path}", flush=True)
            print(f"[DEBUG] gitnexus command: npx gitnexus analyze", flush=True)
            print(f"[DEBUG] Current branch: {target_branch} (baseline)", flush=True)
            try:
                if sys.platform == "win32":
                    # Windows: find npm first, then look for npx in same directory
                    print(f"[DEBUG] Detecting npm path on Windows...", flush=True)
                    npm_result = subprocess.run(
                        ["where", "npm"],
                        capture_output=True,
                        text=True,
                        shell=False
                    )

                    if npm_result.returncode == 0:
                        npm_path = npm_result.stdout.strip().split('\n')[0].strip()
                        print(f"[DEBUG] Found npm at: {npm_path}", flush=True)

                        # Get the directory and look for npx files
                        nodejs_dir = Path(npm_path).parent
                        print(f"[DEBUG] Node.js directory: {nodejs_dir}", flush=True)

                        # Check for npx.cmd, npx.ps1, or npx
                        npx_cmd = nodejs_dir / "npx.cmd"
                        npx_ps1 = nodejs_dir / "npx.ps1"
                        npx_sh = nodejs_dir / "npx"

                        if npx_cmd.exists():
                            print(f"[DEBUG] Using npx.cmd", flush=True)
                            npx_executable = str(npx_cmd)
                            gitnexus_result = subprocess.run(
                                [npx_executable, "gitnexus", "analyze"],
                                cwd=str(cloned_repo_path),
                                capture_output=True,
                                text=True,
                                check=False,
                                shell=False
                            )
                        elif npx_ps1.exists():
                            print(f"[DEBUG] Using npx.ps1 with PowerShell", flush=True)
                            # Run PowerShell script
                            gitnexus_result = subprocess.run(
                                ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(npx_ps1), "gitnexus", "analyze"],
                                cwd=str(cloned_repo_path),
                                capture_output=True,
                                text=True,
                                check=False,
                                shell=False
                            )
                        elif npx_sh.exists():
                            print(f"[DEBUG] Using npx (bash script) with bash", flush=True)
                            # Try running with bash if available
                            gitnexus_result = subprocess.run(
                                ["bash", str(npx_sh), "gitnexus", "analyze"],
                                cwd=str(cloned_repo_path),
                                capture_output=True,
                                text=True,
                                check=False,
                                shell=False
                            )
                        else:
                            print(f"[WARN] No npx executable found", flush=True)
                            raise Exception(f"No npx executable found in {nodejs_dir}")
                    else:
                        print(f"[WARN] npm not found via 'where' command", flush=True)
                        raise Exception("npm not found, cannot locate npx")
                else:
                    # Unix: use shell=False with command as list
                    print(f"[DEBUG] Using Unix command", flush=True)
                    gitnexus_result = subprocess.run(
                        ["npx", "gitnexus", "analyze"],
                        cwd=str(cloned_repo_path),
                        capture_output=True,
                        text=True,
                        check=False,
                        shell=False
                    )

                print(f"[INFO] gitnexus exit code: {gitnexus_result.returncode}", flush=True)
                if gitnexus_result.stdout:
                    print(f"[INFO] gitnexus stdout:\n{gitnexus_result.stdout}", flush=True)
                if gitnexus_result.stderr:
                    print(f"[INFO] gitnexus stderr:\n{gitnexus_result.stderr}", flush=True)

                if gitnexus_result.returncode == 0:
                    print(f"[OK] gitnexus analyze completed successfully", flush=True)
                else:
                    print(f"[WARN] gitnexus analyze failed with return code {gitnexus_result.returncode}", flush=True)
            except Exception as gitnexus_err:
                print(f"[WARN] Failed to run gitnexus analyze: {gitnexus_err}", flush=True)
                import traceback
                traceback.print_exc()

            # ============================================================================
            # IMPACT ANALYSIS (Blast Radius Detection)
            # ============================================================================
            # Run gitnexus detect_changes and impact analysis to identify breaking changes

            # Step 1: Checkout source_branch for diff detection
            print(f"[INFO] Checking out source branch '{source_branch}' for diff analysis...", flush=True)
            checkout_source_result = subprocess.run(
                ["git", "checkout", "-b", source_branch, f"origin/{source_branch}"],
                capture_output=True,
                text=True,
                check=False,
                cwd=str(cloned_repo_path)
            )
            if checkout_source_result.returncode == 0:
                print(f"[OK] Checked out source branch '{source_branch}'", flush=True)
            else:
                # Branch might already exist locally, try regular checkout
                print(f"[INFO] Source branch may already exist, trying regular checkout...", flush=True)
                checkout_source_result = subprocess.run(
                    ["git", "checkout", source_branch],
                    capture_output=True,
                    text=True,
                    check=False,
                    cwd=str(cloned_repo_path)
                )
                if checkout_source_result.returncode == 0:
                    print(f"[OK] Checked out source branch '{source_branch}'", flush=True)
                else:
                    print(f"[WARN] Failed to checkout source branch: {checkout_source_result.stderr}", flush=True)

            print(f"[INFO] Running impact analysis to detect breaking changes...", flush=True)
            impact_markdown = None
            try:
                from services.impact_measurement_service import run_impact_analysis, format_impact_report_to_markdown, format_impact_report_for_gemini_prompt

                # repo_name is already defined above (before gitnexus analyze)

                impact_report = await run_impact_analysis(
                    repo_path=str(cloned_repo_path),
                    repo_name=repo_name,
                    source_branch=source_branch,
                    target_branch=target_branch,
                    changed_symbols=[],  # Changed symbols should be detected externally
                    max_symbols_to_analyze=3  # Limit to 3 symbols to avoid excessive API calls
                )

                if impact_report:
                    print(f"[OK] Impact analysis complete:", flush=True)
                    print(f"     - Changed symbols: {len(impact_report.changed_symbols)}", flush=True)
                    print(f"     - Total impacted dependencies: {len(impact_report.impacted_dependencies)}", flush=True)
                    print(f"     - High risk dependencies: {impact_report.high_risk_count}", flush=True)
                    print(f"     - Medium risk dependencies: {impact_report.medium_risk_count}", flush=True)

                    if impact_report.skipped_reason:
                        print(f"[INFO] Impact analysis skipped: {impact_report.skipped_reason}")
                    else:
                        # Format for display (markdown)
                        impact_markdown = format_impact_report_to_markdown(impact_report)

                        # Format for Gemini prompt (more detailed)
                        impact_gemini_prompt = format_impact_report_for_gemini_prompt(impact_report)
                        print(f"[OK] Impact analysis results formatted for Gemini ({len(impact_gemini_prompt)} chars)", flush=True)
                        if not impact_gemini_prompt:
                            print(f"[DEBUG] impact_gemini_prompt is empty - no impacted dependencies found", flush=True)

                    # Log to MongoDB for tracking
                    if mongo_client.CONNECTION_STRING:
                        from datetime import datetime, timezone
                        impact_dict = {
                            "analyzed_at": impact_report.analyzed_at.isoformat() if impact_report.analyzed_at else None,
                            "source_branch": impact_report.source_branch,
                            "target_branch": impact_report.target_branch,
                            "changed_symbols": [
                                {"name": s.name, "id": s.id, "kind": s.kind, "file_path": s.file_path}
                                for s in impact_report.changed_symbols
                            ],
                            "impacted_dependencies": [
                                {
                                    "name": d.name,
                                    "file_path": d.file_path,
                                    "depth": d.depth,
                                    "has_context": bool(d.source_code_context)
                                }
                                for d in impact_report.impacted_dependencies
                            ],
                            "total_impacted_files": impact_report.total_impacted_files,
                            "high_risk_count": impact_report.high_risk_count,
                            "medium_risk_count": impact_report.medium_risk_count
                        }

                        await mongo_client.insert_one(
                            collection_name="impact_reports",
                            document={
                                "mr_id": mr_iid,
                                "project_id": project_id,
                                "source_branch": source_branch,
                                "target_branch": target_branch,
                                "report": impact_dict,
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            }
                        )
                        print("[OK] Impact report logged to MongoDB")
                else:
                    print("[INFO] No impact analysis results or skipped")

            except Exception as impact_err:
                print(f"[WARN] Failed to run impact analysis: {impact_err}", flush=True)
                import traceback
                traceback.print_exc()

    except Exception as clone_err:
        print(f"[ERROR] Failed to clone repository: {clone_err}")
        import traceback
        traceback.print_exc()
        print(f"[WARN] Continuing with analysis without local clone...")
        await add_log("clone_failed", f"⚠️ Failed to clone repository locally: {str(clone_err)}", "completed")

    # 1. Store Request Signature in MongoDB Cluster via MCP
    if mongo_session:
        try:
            await mongo_session.call_tool(
                name="insert-many",
                arguments={
                    "database": "gatekeeper_dev",
                    "collection": "intercepted_mrs",
                    "documents": [{"title": mr_title, "project_id": project_id, "mr_iid": mr_iid, "status": "gemini_auditing"}]
                }
            )
            print("[OK] Metadata logged to local MongoDB cluster.")
        except Exception as e:
            print(f"[ERROR] DB Log failed: {e}")
    else:
        print("[WARN] MongoDB session not available - skipping DB log")

    # 2. Extract Comprehensive Diffs via GitLab MCP and Process using Gemini
    print("[INFO] ===== STARTING GATEKEEPER ANALYSIS PIPELINE =====")

    # Update status to "reviewing"
    try:
        await repository_service.update_mr_analysis(
            repo_id=str(project_id),
            mr_iid=mr_iid_int,
            analysis_data={"status": "reviewing", "analysis_status": "in_progress"}
        )
        await add_log("starting", "🚀 Starting Gatekeeper security analysis", "completed")
        print(f"[OK] Updated MR {mr_iid} status to 'reviewing'")
    except Exception as status_err:
        print(f"[WARN] Failed to update MR status to 'reviewing': {status_err}")

    print("[INFO] Step 1: Posting loading indicator to MR...")
    await add_log("fetching", "📡 Fetching merge request details and code changes", "running")

    if user_id:
        loading_note_id = None
        try:
            # 🔄 Post a loading comment (will be updated with results)
            print("[INFO] Posting loading indicator to MR...")
            loading_note = await _gitlab_api_call(
                user_id=user_id,
                project_id=str(project_id),
                method="POST",
                endpoint=f"/projects/{project_id}/merge_requests/{mr_iid}/notes",
                data={
                    "body": """### 🔄 Gatekeeper Review In Progress

**The Gatekeeper** is analyzing your code changes for security vulnerabilities, code quality issues, and performance improvements.

This may take 30-60 seconds depending on the size of the changes.

---
*⏳ Status: Analyzing...*"""
                }
            )
            loading_note_id = loading_note.get("id")
            
            if hasattr(loading_note, 'content') and loading_note.content:
                text_content = loading_note.content[0].text if hasattr(loading_note.content[0], 'text') else str(loading_note.content[0])
                try:
                    note_data = json.loads(text_content)
                    loading_note_id = note_data.get("id")
                    if loading_note_id:
                        print(f"[OK] Loading indicator posted! Note ID: {loading_note_id}")
                    else:
                        print("[OK] Loading indicator posted! (No ID in response)")
                except json.JSONDecodeError:
                    print("[OK] Loading indicator posted! (Could not parse JSON)")
            else:
                print("[OK] Loading indicator posted!")

            print("[INFO] Step 2: Fetching comprehensive MR diff text via GitLab API...")

            # Fetch MR diffs using user's GitLab token
            raw_diff_content = await _gitlab_get_mr_diffs(
                user_id=user_id,
                project_id=str(project_id),
                mr_iid=int(mr_iid)
            )

            print(f"[OK] Step 2 complete: Raw code diffs retrieved ({len(raw_diff_content)} chars)")

            if raw_diff_content:
                await add_log("diff_fetched", f"📥 Retrieved {len(raw_diff_content)} characters of code changes", "completed")
            else:
                print("[WARN] WARNING: Diff content is empty!")
                await add_log("diff_fetched", "⚠️ No code changes found in this merge request", "completed")

            # --- 🔍 SCHEMA INSPECTION SERVICE (Step 3.5) ---
            print("[INFO] Step 3.5: Checking for backend-touching changes and database schema inspection...")
            await add_log("schema_check", "🗄️ Checking for MongoDB schema changes", "running")

            schema_report = None
            schema_markdown = None
            try:
                from services.schema_inspection_service import run_schema_inspection, format_schema_report_to_markdown
                schema_report = await run_schema_inspection(raw_diff_content, mcp_service.mongo_session, project_id=project_id, target_branch=target_branch)
                if schema_report:
                    print(f"[OK] Schema inspection complete. Found {len(schema_report.collections)} collections. Confidence: {schema_report.confidence}")
                    await add_log("schema_check", f"✅ Schema analysis complete - {len(schema_report.collections)} collections examined", "completed")
                else:
                    await add_log("schema_check", "ℹ️ No database schema changes detected", "completed")

                # 1. Format and attach schema_report summary to raw_diff_content passed to run_gemini_review
                schema_markdown = format_schema_report_to_markdown(schema_report)
                if schema_markdown:
                    raw_diff_content += f"\n\n{schema_markdown}"
                        
                    # 2. Log schema_report to MongoDB collection "schema_snapshots"
                    if mcp_service.mongo_session:
                        delta_list = []
                        if schema_report.delta:
                            for change in schema_report.delta.changes:
                                delta_list.append({
                                    "collection": change.collection,
                                    "change_type": change.change_type,
                                    "field_name": change.field_name,
                                    "old_value": change.old_value,
                                    "new_value": change.new_value
                                })
                        else:
                            delta_list = None
                            
                        schema_dict = {
                            "inspected_at": schema_report.inspected_at.isoformat() if schema_report.inspected_at else None,
                            "triggered_by_files": schema_report.triggered_by_files,
                            "triggered_by_content": schema_report.triggered_by_content,
                            "confidence": schema_report.confidence,
                            "scoped": schema_report.scoped,
                            "skipped_reason": schema_report.skipped_reason,
                            "delta": delta_list,
                            "collections": [
                                {
                                    "name": col.name,
                                    "fields": col.fields,
                                    "indexes": col.indexes,
                                    "sample_document_keys": col.sample_document_keys
                                } for col in schema_report.collections
                            ]
                        }
                        
                        from datetime import datetime, timezone
                        await mcp_service.mongo_session.call_tool(
                            name="insert-many",
                            arguments={
                                "database": "gatekeeper_dev",
                                "collection": "schema_snapshots",
                                "documents": [{
                                    "mr_id": mr_iid,
                                    "project_id": project_id,
                                    "branch_name": source_branch,
                                    "report": schema_dict,
                                    "timestamp": datetime.now(timezone.utc).isoformat()
                                }]
                            }
                        )
                        print("[OK] Schema snapshot logged to MongoDB collection: schema_snapshots")
            except Exception as schema_err:
                print(f"[WARN] Schema inspection failed (continuing anyway): {schema_err}")
                await add_log("schema_check", "⚠️ Schema check encountered an error, continuing analysis", "completed")

            # Attach impact analysis results to the diff content for Gemini review
            if impact_gemini_prompt:
                print(f"[INFO] Attaching impact analysis results to diff content...")
                raw_diff_content += f"\n\n{impact_gemini_prompt}"

            # --- 🧠 THE GEMINI COGNITIVE CORE ENGINE ---
            print("[INFO] Step 4: Shipping code diff to Gemini Pro Core for automated security review...")
            await add_log("ai_analysis", "🤖 Running AI-powered security and code quality analysis", "running")

            # Get user's Gemini config from repository owner (user_id from webhook payload)
            user_config = await get_user_config_from_repo(str(project_id))

            # Run Gemini review with user context for usage tracking
            # user_id is extracted from webhook payload at the beginning of the function

            # Get repo name for GitNexus - use path_with_namespace from payload
            path_with_namespace = payload.get("project", {}).get("path_with_namespace", "")
            gitnexus_repo_name = path_with_namespace.split("/")[-1] if "/" in path_with_namespace else path_with_namespace or None
            if gitnexus_repo_name:
                print(f"[INFO] GitNexus repository name: {gitnexus_repo_name}")

            # Use GitNexus-enabled review if we have a cloned repository
            if 'cloned_repo_path' in locals() and cloned_repo_path:
                print(f"[INFO] Using GitNexus-enabled Gemini review with repository at {cloned_repo_path}")
                gemini_result = await run_gemini_review_with_gitnexus(
                    raw_diff_content=raw_diff_content,
                    impact_context=impact_gemini_prompt or "",
                    repo_path=cloned_repo_path,
                    repo_name=gitnexus_repo_name,
                    user_config=user_config,
                    user_id=user_id,
                    mr_id=mr_iid,
                    repository_id=project_id,
                    target_branch_name=target_branch,
                    source_branch_name=source_branch
                )
                tools_called = gemini_result.get("tools_called", [])
                if tools_called:
                    print(f"[INFO] GitNexus tools called during review: {', '.join(tools_called)}")
            else:
                print(f"[INFO] Using standard Gemini review (no local clone available)")
                gemini_result = await run_gemini_review(raw_diff_content, "", user_config, user_id=user_id, mr_id=mr_iid, repository_id=project_id)
            audit_report = gemini_result.get("review_text", "")
            review_usage = gemini_result.get("usage", {})
            captured_trace_id = gemini_result.get("trace_id")
            captured_span_id = gemini_result.get("span_id")  # Capture LLM span ID for Arize annotations

            if captured_span_id:
                print(f"[INFO] Storing span_id {captured_span_id[:16]}... with MR {mr_iid} for Arize annotations")
                # Store span_id with MR data for annotations (works with annotate_spans API)
                try:
                    await repository_service.update_mr_analysis(
                        repo_id=str(project_id),
                        mr_iid=int(mr_iid),
                        analysis_data={"span_id": captured_span_id}
                    )
                    print(f"[OK] Stored span_id with MR {mr_iid}")
                except Exception as span_err:
                    print(f"[WARN] Failed to store span_id: {span_err}")
            elif captured_trace_id:
                print(f"[INFO] Storing trace_id {captured_trace_id[:16]}... with MR {mr_iid} for feedback linkage (fallback)")
                # Store trace_id as fallback for backwards compatibility
                try:
                    await repository_service.update_mr_analysis(
                        repo_id=str(project_id),
                        mr_iid=int(mr_iid),
                        analysis_data={"trace_id": captured_trace_id}
                    )
                    print(f"[OK] Stored trace_id with MR {mr_iid}")
                except Exception as trace_err:
                    print(f"[WARN] Failed to store trace_id: {trace_err}")
            else:
                print(f"[WARN] No trace_id or span_id returned from Gemini review")

            print(f"[OK] Step 4 complete: Gemini analysis compiled ({len(audit_report)} chars)")
            if review_usage:
                print(f"[ℹ] Review usage: {review_usage.get('total_tokens', 0)} tokens ({review_usage.get('model_name', 'unknown')})")
            await add_log("ai_analysis", f"✅ AI analysis complete - {len(audit_report)} characters of findings generated", "completed")

            # 3. Update the loading comment with the final report
            print("[INFO] Updating review with findings...")
            final_report = f"""### 🛡️ The Gatekeeper Security Audit

{audit_report}

---
*✅ Review completed at {time.strftime('%Y-%m-%d %H:%M:%S UTC')}*"""

            # 3.5 Update MongoDB with AI analysis results
            try:
                # Calculate review duration
                review_duration_seconds = int(time.time() - analysis_start_time)

                # Extract issues from audit_report for frontend display
                ai_issues = []
                lines = audit_report.split('\n')
                for line in lines:
                    line = line.strip()
                    # Look for lines with issue indicators
                    if any(marker in line for marker in ['❌', '⚠️', '🔴', '🟠', '**ERROR**', '**WARNING**', '**Issue**']):
                        # Clean up the line for display
                        clean_line = line
                        # Remove markdown formatting
                        for marker in ['❌', '⚠️', '🔴', '🟠', '**', '*', '`']:
                            clean_line = clean_line.replace(marker, '').strip()
                        if clean_line and len(clean_line) > 5:  # Only meaningful lines
                            ai_issues.append(clean_line[:200])  # Limit length

                # Calculate health score based on issues found
                health_score = 100
                error_count = audit_report.count('❌') + audit_report.count('ERROR')
                warning_count = audit_report.count('⚠️') + audit_report.count('WARNING')

                if error_count > 0:
                    health_score -= min(error_count * 20, 60)
                if warning_count > 0:
                    health_score -= min(warning_count * 5, 30)

                health_score = max(health_score, 0)

                # Store the full audit report as the summary
                update_data = {
                    "ai_summary": audit_report,
                    "ai_issues": ai_issues[:10],  # Store first 10 issues
                    "health_score": health_score,
                    "status": "reviewed",  # Final status after review completion
                    "analysis_status": "completed",
                    "reviewed_at": time.strftime('%Y-%m-%dT%H:%M:%SZ'),
                    "review_duration_seconds": review_duration_seconds
                }

                print(f"[INFO] Review completed in {review_duration_seconds} seconds ({review_duration_seconds / 60:.2f} minutes)")

                await repository_service.update_mr_analysis(
                    repo_id=str(project_id),
                    mr_iid=mr_iid,
                    analysis_data=update_data
                )
                print(f"[OK] Updated MR {mr_iid} in MongoDB with AI analysis")

                # Update repository's running average review time
                await repository_service.update_repository_avg_review_time(
                    repo_id=str(project_id),
                    new_duration_seconds=review_duration_seconds
                )

                await add_log("completed", "🎉 Review completed successfully - Report published to merge request", "completed")
            except Exception as update_err:
                print(f"[WARN] Failed to update MongoDB with AI analysis: {update_err}")

            if loading_note_id:
                try:
                    await _gitlab_api_call(
                        user_id=user_id,
                        project_id=str(project_id),
                        method="PUT",
                        endpoint=f"/projects/{project_id}/merge_requests/{mr_iid}/notes/{loading_note_id}",
                        data={"body": final_report}
                    )
                    print("[OK] Review report updated in place!")
                except Exception as update_err:
                    print(f"[WARN] Could not update note (ID: {loading_note_id}): {update_err}")
                    await _gitlab_api_call(
                        user_id=user_id,
                        project_id=str(project_id),
                        method="POST",
                        endpoint=f"/projects/{project_id}/merge_requests/{mr_iid}/notes",
                        data={"body": final_report}
                    )
                    print("[OK] Review report published as new comment!")
            else:
                await _gitlab_api_call(
                    user_id=user_id,
                    project_id=str(project_id),
                    method="POST",
                    endpoint=f"/projects/{project_id}/merge_requests/{mr_iid}/notes",
                    data={"body": final_report}
                )
                print("[OK] Review report published!")

            # 🎉 Set commit status to SUCCESS
            if commit_sha:
                print(f"[INFO] Setting commit status to SUCCESS...")
                try:
                    await _gitlab_api_call(
                        user_id=user_id,
                        project_id=str(project_id),
                        method="POST",
                        endpoint=f"/projects/{project_id}/statuses/{commit_sha}",
                        data={
                            "state": "success",
                            "name": "gatekeeper/security-review",
                            "description": "✅ Gatekeeper review completed"
                        }
                    )
                    print("[OK] Status set to SUCCESS!")
                except Exception as status_err:
                    print(f"[WARN] Could not set commit status: {status_err}")

            # --- 🤖 AUTO-FIX FEATURE ---
            print("[INFO] Checking if issues can be auto-fixed via atomic patches...")
            await add_log("auto_fix", "🔧 Analyzing issues for potential auto-fix generation", "running")
            try:
                # Re-parse diff and create patch summary
                patch_parser = AtomicPatchParser(context_lines=3)
                atomic_patches = patch_parser.parse_unified_diff(raw_diff_content)
                patch_summary = create_patch_summary(atomic_patches)

                # No timeout - rely on retry logic inside run_gemini_fix_analysis
                fix_result = await run_gemini_fix_analysis(
                    audit_report,
                    patch_summary,
                    schema_context=schema_markdown,
                    user_config=user_config,
                    user_id=user_id,
                    mr_id=mr_iid,
                    repository_id=project_id
                )

                # Extract fix data and usage from result
                fix_usage = fix_result.pop("usage", {})
                fix_data = fix_result

                print(f"[ℹ] Fix analysis usage: {fix_usage.get('total_tokens', 0)} tokens ({fix_usage.get('model_name', 'unknown')})")

                # Delegate auto-fix branch application to remediation service
                await apply_auto_fixes(
                    project_id=str(project_id),
                    mr_iid=int(mr_iid),
                    mr_title=mr_title,
                    source_branch=source_branch,
                    atomic_patches=atomic_patches,
                    fix_data=fix_data,
                    user_id=user_id,
                    gitlab_session=gitlab_session
                )
                await add_log("auto_fix", "✅ Auto-fix analysis complete - generating fix branches", "completed")

            except json.JSONDecodeError as parse_err:
                print(f"[ERROR] Failed to parse fix analysis JSON structure: {parse_err}")
                await add_log("auto_fix", "⚠️ Failed to parse fix analysis - skipping", "completed")
            except Exception as loop_err:
                print(f"[ERROR] Auto-fix execution loop broken: {loop_err}")
                await add_log("auto_fix", "⚠️ Auto-fix encountered an error - skipping", "completed")

        except Exception as e:
            print(f"[ERROR] Intelligent Gemini Audit loop failed: {e}")
            import traceback
            traceback.print_exc()

            # Update MR status to failed
            try:
                await repository_service.update_mr_analysis(
                    repo_id=str(project_id),
                    mr_iid=mr_iid,
                    analysis_data={"status": "failed", "analysis_status": "error"}
                )
                print(f"[WARN] Updated MR {mr_iid} status to 'failed'")
            except Exception as status_err:
                print(f"[WARN] Failed to update MR status to 'failed': {status_err}")

            # ❌ Set commit status to FAILED on error
            if commit_sha and user_id:
                try:
                    await _gitlab_api_call(
                        user_id=user_id,
                        project_id=str(project_id),
                        method="POST",
                        endpoint=f"/projects/{project_id}/statuses/{commit_sha}",
                        data={
                            "state": "failed",
                            "name": "gatekeeper/security-review",
                            "description": f"❌ Gatekeeper review failed: {str(e)[:100]}"
                        }
                    )
                    print("[OK] Status set to FAILED")
                except Exception as status_err:
                    print(f"[ERROR] Failed to set error status: {status_err}")

    return {"status": "event_processed"}
