# Plan: Replace GitLab MCP with Direct GitLab API Calls for Sentry Webhook Handling

> **Status**: ✅ Completed

This document describes the implementation to replace GitLab MCP calls with direct GitLab REST API calls for Sentry webhook handling.

## Context

When a Sentry webhook is received, the current implementation (`run_sentry_bug_workflow` in `agents/workflows.py`) uses GitLab MCP to create merge requests. The user wants to replace these GitLab MCP calls with direct GitLab REST API calls using PAT tokens, following the same pattern used by the GitLab webhook handler.

**Problem**: Sentry webhook handling relies on GitLab MCP to create MRs. This adds unnecessary MCP dependency for what could be simple API calls.

**Solution**: Create GitLab API tools that use direct HTTP calls with PAT tokens, similar to `_gitlab_api_call` in `review_service.py`.

## Implementation Plan

### 1. Create GitLab API Tools in `agents/tools.py`

Add new local tools for GitLab MR operations (similar to existing `get_gitlab_mr_diffs`, `post_gitlab_mr_comment`):

```python
# New schemas and tools to add:

create_gitlab_branch_schema = {
    "type": "object",
    "properties": {
        "user_id": {"type": "string"},
        "project_id": {"type": "string"},
        "branch_name": {"type": "string"},
        "ref": {"type": "string"}
    },
    "required": ["user_id", "project_id", "branch_name"]
}

async def create_gitlab_branch(user_id: str, project_id: str, branch_name: str, ref: str = "main") -> Dict:
    """Create a new branch in GitLab using direct API call"""
    # Uses _get_project_access_token for authentication
    # POST /api/v4/projects/{id}/repository/branches

create_gitlab_merge_request_schema = {
    "type": "object",
    "properties": {
        "user_id": {"type": "string"},
        "project_id": {"type": "string"},
        "source_branch": {"type": "string"},
        "target_branch": {"type": "string"},
        "title": {"type": "string"},
        "description": {"type": "string"}
    },
    "required": ["user_id", "project_id", "source_branch", "target_branch", "title"]
}

async def create_gitlab_merge_request(
    user_id: str,
    project_id: str,
    source_branch: str,
    target_branch: str,
    title: str,
    description: str = ""
) -> Dict:
    """Create a merge request in GitLab using direct API call"""
    # Uses _get_project_access_token for authentication
    # POST /api/v4/projects/{id}/merge_requests

commit_file_to_branch_schema = {
    "type": "object",
    "properties": {
        "user_id": {"type": "string"},
        "project_id": {"type": "string"},
        "file_path": {"type": "string"},
        "branch_name": {"type": "string"},
        "content": {"type": "string"},
        "commit_message": {"type": "string"}
    },
    "required": ["user_id", "project_id", "file_path", "branch_name", "content", "commit_message"]
}

async def commit_file_to_branch(
    user_id: str,
    project_id: str,
    file_path: str,
    branch_name: str,
    content: str,
    commit_message: str
) -> Dict:
    """Commit a file to a branch using direct API call"""
    # Uses _get_project_access_token for authentication
    # POST /api/v4/projects/{id}/repository/files
```

### 2. Helper Function for GitLab API Authentication

Add to `agents/tools.py` or create a shared helper:

```python
async def _get_gitlab_token_for_user(user_id: str, project_id: str) -> str:
    """
    Get GitLab token for a user and project.
    Priority:
    1. User's session token (from auth_service)
    2. Project-specific token from MongoDB (users.project_tokens)
    3. Global GITLAB_PERSONAL_ACCESS_TOKEN
    """
    from services import auth_service, mongo_client
    from services.encryption_service import decrypt_value
    import os

    # 1. Check user session
    session = auth_service.get_user_session(user_id)
    if session and session.get("gitlab_access_token"):
        return session["gitlab_access_token"]

    # 2. Check project-specific token from MongoDB
    user = await mongo_client.find_one(
        collection_name="users",
        filter={"_id": user_id}
    )
    if user and user.get("project_tokens", {}).get(project_id):
        token_data = user["project_tokens"][project_id]
        return decrypt_value(token_data.get("token_encrypted", ""))

    # 3. Fallback to global token
    return os.getenv("GITLAB_PERSONAL_ACCESS_TOKEN", "")

async def _gitlab_rest_api_call(
    user_id: str,
    project_id: str,
    method: str,
    endpoint: str,
    params: Dict = None,
    json_data: Dict = None
) -> Dict:
    """Direct GitLab REST API call using httpx"""
    import httpx
    import os

    gitlab_base_url = os.getenv("GITLAB_BASE_URL", "https://gitlab.com")
    token = await _get_gitlab_token_for_user(user_id, project_id)

    url = f"{gitlab_base_url}/api/v4{endpoint}"
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        if method.upper() == "GET":
            response = await client.get(url, headers=headers, params=params)
        elif method.upper() == "POST":
            response = await client.post(url, headers=headers, params=params, json=json_data)
        elif method.upper() == "PUT":
            response = await client.put(url, headers=headers, params=params, json=json_data)
        elif method.upper() == "DELETE":
            response = await client.delete(url, headers=headers, params=params)

        response.raise_for_status()
        return response.json()
```

### 3. Update `agents/registry.py`

Add the new GitLab tools to the default tool registry:

```python
from agents.tools import (
    # ... existing imports
    create_gitlab_branch,
    create_gitlab_merge_request,
    commit_file_to_branch
)

# In build_default_registry(), add:
registry.register_tool(
    name="create_gitlab_branch",
    schema=create_gitlab_branch_schema,
    handler=create_gitlab_branch,
    description="Create a new branch in GitLab repository"
)

registry.register_tool(
    name="create_gitlab_merge_request",
    schema=create_gitlab_merge_request_schema,
    handler=create_gitlab_merge_request,
    description="Create a merge request in GitLab"
)

registry.register_tool(
    name="commit_file_to_branch",
    schema=commit_file_to_branch_schema,
    handler=commit_file_to_branch,
    description="Commit a file to a GitLab branch"
)
```

### 4. Update `agents/workflows.py` - `run_sentry_bug_workflow`

Modify the workflow to build a registry WITHOUT GitLab MCP:

```python
async def run_sentry_bug_workflow(
    issue_id: str,
    title: str,
    level: str,
    culprit: str,
    stack_trace: str,
    repo_id: str,
    user_id: str = "sentry-operator"
) -> Dict:
    """Execute Sentry bug workflow using direct GitLab API (not MCP)"""

    # Build registry with all tools EXCEPT GitLab MCP
    # Instead, register the new local GitLab tools
    registry = ToolRegistry()

    # Add Sentry tools (if Sentry MCP is still used for issue details)
    # or add local Sentry tools if those are also direct API

    # Add LOCAL GitLab tools (not MCP)
    registry.register_tool("create_gitlab_branch", ..., handler=create_gitlab_branch)
    registry.register_tool("create_gitlab_merge_request", ..., handler=create_gitlab_merge_request)
    registry.register_tool("commit_file_to_branch", ..., handler=commit_file_to_branch)

    # Add other tools (MongoDB, etc.)
    ...

    # Run workflow
    engine = WorkflowEngine(registry)
    return await engine.run_task(context)
```

### 5. Keep Sentry MCP (Optional)

The Sentry MCP can still be used for fetching issue details from Sentry, or we can also replace that with direct API calls. For now, the focus is on replacing GitLab MCP with direct API calls.

### 6. Update `.env.example`

No changes needed - GitLab PAT configuration already exists.

## Files to Modify

| File | Change |
|------|--------|
| `agents/tools.py` | Add `create_gitlab_branch`, `create_gitlab_merge_request`, `commit_file_to_branch`, and helper functions |
| `agents/registry.py` | Register new GitLab tools |
| `agents/workflows.py` | Update `run_sentry_bug_workflow` to use local tools instead of GitLab MCP |

## Verification Steps

1. **Test GitLab token retrieval** - Verify `_get_gitlab_token_for_user` returns valid tokens
2. **Test branch creation** - Verify `create_gitlab_branch` creates a branch via API
3. **Test MR creation** - Verify `create_gitlab_merge_request` creates an MR via API
4. **Test file commit** - Verify `commit_file_to_branch` commits files via API
5. **End-to-end test** - Send a Sentry webhook and verify:
   - Branch is created
   - Fix file is committed
   - MR is created
   - No GitLab MCP was used

## Notes

- **GitLab MCP stays for GitLab webhooks** - The GitLab webhook handler can continue using GitLab MCP or also be migrated later
- **Only Sentry webhook changes** - This change only affects how Sentry webhooks create GitLab MRs
- **Token priority** - User session → Project token → Global token (same as `review_service.py`)
- **Sentry MCP optional** - Can keep Sentry MCP for Sentry issue fetching, or also replace with direct API

## Implementation Summary

### Changes Made

1. **`agents/tools.py`** - Added:
   - `create_gitlab_branch_schema` and `create_gitlab_branch()` - Creates branches via GitLab REST API
   - `create_gitlab_merge_request_schema` and `create_gitlab_merge_request()` - Creates MRs via GitLab REST API
   - `commit_file_to_branch_schema` and `commit_file_to_branch()` - Commits files via GitLab REST API
   - `_get_gitlab_token_for_user()` - Helper to get user's GitLab token with fallback
   - `_gitlab_rest_api_call()` - Generic HTTP client for GitLab API calls

2. **`agents/registry.py`** - Updated:
   - Added registration of the three new GitLab REST API tools to `build_default_registry()`

3. **`agents/workflows.py`** - Updated:
   - Modified `run_sentry_bug_workflow()` to use `build_sentry_registry()` instead of `build_default_registry()`
   - Created `build_sentry_registry()` - Custom registry that:
     - Includes all local tools (including new GitLab REST API tools)
     - Includes Sentry, MongoDB, Dynatrace, GitNexus MCP sessions
     - **Excludes GitLab MCP** - uses local GitLab REST API tools instead

### API Endpoints Used

| Tool | GitLab API Endpoint |
|------|-------------------|
| `create_gitlab_branch` | `POST /api/v4/projects/{id}/repository/branches` |
| `create_gitlab_merge_request` | `POST /api/v4/projects/{id}/merge_requests` |
| `commit_file_to_branch` | `POST/PUT /api/v4/projects/{id}/repository/files/{file_path}` |

### Token Authentication Flow

```
_get_gitlab_token_for_user(user_id, project_id)
    │
    ├─> user_service.get_user_gitlab_token()  # Project-specific token from MongoDB
    │   └─> SUCCESS: return token
    │   └─> FAILURE: continue
    │
    └─> os.getenv("GITLAB_PERSONAL_ACCESS_TOKEN")  # Global fallback
        └─> return token or ""
```
