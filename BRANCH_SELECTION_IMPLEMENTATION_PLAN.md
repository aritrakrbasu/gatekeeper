# Branch Selection & Automatic Webhook Installation Implementation Plan

## Context

This feature enables users to select specific branches when connecting a GitLab repository. When a repository is connected with selected branches, Gatekeeper will automatically install a GitLab webhook that filters events to only process merge requests for those branches. Users can modify the selected branches at any time through repository settings.

### Current State
- Repository connection stores metadata in MongoDB but doesn't configure GitLab webhooks
- Webhooks (`/webhooks/gitlab` endpoint) receive merge request events but must be manually configured in GitLab
- No branch selection UI exists - branches are extracted from webhook payloads
- Webhook processing happens in `services/review_service.py` via `orchestrate_review()`

### Requirements (from user)
- **Webhook Scope**: Filter events for selected branches (one project webhook with server-side filtering)
- **Install Timing**: After connection, user confirms (show summary, then install)
- **Edit Capability**: Full edit capability (add/remove branches anytime)

---

## Implementation Plan

### Phase 1: Backend - Branch Fetching & Storage

#### 1.1 Add Branch Fetching Service (`services/repository_service.py`)

Add a new function to fetch branches from GitLab:

```python
async def get_gitlab_branches(repo_id: str, user_id: str) -> List[Dict]:
    """
    Fetch all branches for a GitLab repository.

    Args:
        repo_id: GitLab project ID
        user_id: User ID for authentication

    Returns:
        List of branches with name, commit info, and default status
    """
```

**Implementation details:**
- Use user's GitLab access token from `auth_service.get_user_session(user_id)`
- Call GitLab API: `GET /api/v4/projects/{repo_id}/repository/branches`
- Return: `[{"name": "main", "commit": {"id": "..."}, "default": true}, ...]`

#### 1.2 Update Repository Data Model

Extend the repository document in MongoDB to store:
- `monitored_branches`: List[str] - Branches selected for monitoring
- `webhook_installed`: bool - Whether webhook is configured
- `webhook_id`: Optional[int] - GitLab webhook ID for management
- `branch_filter_enabled`: bool - Whether branch filtering is active

**Location:** Update the `new_repo` dict in `connect_repository()` and `onboard_repository()` functions.

---

### Phase 2: Backend - Webhook Management Service

#### 2.1 Create Webhook Service (`services/webhook_service.py`)

Create a new service module for GitLab webhook management:

```python
# Key functions:

async def install_gitlab_webhook(
    repo_id: str,
    user_id: str,
    webhook_url: str,
    monitored_branches: List[str]
) -> Dict:
    """
    Install a webhook on a GitLab repository.

    Args:
        repo_id: GitLab project ID
        user_id: User ID for authentication
        webhook_url: The Gatekeeper webhook URL
        monitored_branches: List of branches to monitor (empty = all branches)

    Returns:
        Webhook installation result with webhook ID
    """

async def update_gitlab_webhook(
    repo_id: str,
    user_id: str,
    webhook_id: int,
    monitored_branches: List[str]
) -> Dict:
    """Update existing webhook branch filter."""

async def delete_gitlab_webhook(
    repo_id: str,
    user_id: str,
    webhook_id: int
) -> Dict:
    """Delete a webhook from GitLab repository."""
```

**Implementation details:**
- Use GitLab API: `POST /api/v4/projects/{repo_id}/hooks`
- Configure webhook to trigger on: `merge_requests` events
- **Note:** GitLab webhooks don't support branch filtering at API level
  - We'll store branch filter in our DB and filter server-side
- Store returned `webhook_id` in repository document

#### 2.2 Add Branch Filtering to Webhook Processing

Update `services/review_service.py`:

```python
async def should_process_webhook(payload: dict) -> bool:
    """
    Check if webhook should be processed based on branch filter.

    Args:
        payload: GitLab webhook payload

    Returns:
        True if MR's branch is in monitored list
    """
    source_branch = payload.get("object_attributes", {}).get("source_branch")
    project_id = payload.get("project", {}).get("id")

    # Get repository config
    repo = await repository_service.get_repository(str(project_id))
    monitored_branches = repo.get("monitored_branches", [])
    branch_filter_enabled = repo.get("branch_filter_enabled", True)

    # If no filter or empty list, process all
    if not branch_filter_enabled or not monitored_branches:
        return True

    # Check if source branch is monitored
    return source_branch in monitored_branches
```

**Integration:** Call `should_process_webhook()` at the start of `orchestrate_review()`.

---

### Phase 3: Backend - API Endpoints

#### 3.1 Add New API Endpoints (`main.py`)

```python
# Get branches for a repository
@app.get("/api/repositories/{repo_id}/branches")
async def get_repository_branches(
    repo_id: str,
    current_user: User = Depends(get_current_user)
) -> List[BranchResponse]:
    """Fetch available branches for a repository."""

# Update monitored branches
@app.put("/api/repositories/{repo_id}/branches")
async def update_monitored_branches(
    repo_id: str,
    request: UpdateBranchesRequest,
    current_user: User = Depends(get_current_user)
) -> RepositoryResponse:
    """
    Update the list of monitored branches.
    If webhook exists, updates webhook configuration.
    """

# Install webhook with branch selection
@app.post("/api/repositories/{repo_id}/webhook")
async def install_webhook(
    repo_id: str,
    request: InstallWebhookRequest,
    current_user: User = Depends(get_current_user)
) -> WebhookResponse:
    """
    Install GitLab webhook for the repository.
    Called after user confirms branch selection.
    """
```

#### 3.2 Update Connection Flow

Modify `onboard_repository()` to optionally include monitored branches:

```python
async def onboard_repository(
    user_id: str,
    repo_id: str,
    data: OnboardRepositoryRequest  # Add monitored_branches field
) -> Dict:
    # ... existing code ...

    # Add monitored branches to repository document
    new_repo["monitored_branches"] = data.monitored_branches or []
    new_repo["branch_filter_enabled"] = bool(data.monitored_branches)
    new_repo["webhook_installed"] = False  # Webhook installed separately after confirmation

    # ... rest of function ...
```

---

### Phase 4: Frontend - Branch Selection UI

#### 4.1 Update ConnectRepositoryModal

Add a new step between "list" and "onboard" for branch selection:

**New state:** `step = "list" | "branches" | "webhook-confirm" | "onboard"`

**Step: branches**
- Fetch branches using new API: `GET /api/repositories/{repo_id}/branches`
- Display branches with checkboxes
- Show default branch pre-selected
- Search/filter branches input
- "Continue" button proceeds to webhook confirmation

**Step: webhook-confirm**
- Show summary card:
  - Repository name and URL
  - Selected branches count and list (truncated if many)
  - Webhook URL to be installed
- Information: "Gatekeeper will install a webhook on this repository"
- Two buttons:
  - "Install Webhook & Connect" (primary)
  - "Connect Without Webhook" (secondary)

**Updated flow:**
1. User selects repository from list
2. **NEW:** User selects branches to monitor
3. **NEW:** User confirms webhook installation
4. User optionally configures credentials (existing onboarding step)

#### 4.2 Add Branch Selection Component

Create `components/BranchSelector.jsx`:

```jsx
// Props:
// - branches: List of branch objects
// - selectedBranches: Set of selected branch names
// - onToggleBranch: Callback for branch selection
// - defaultBranch: Name of default branch

// Features:
// - Checkbox list of branches
// - Default branch highlighted
// - Search/filter input
// - "Select All" / "Deselect All" buttons
// - Show commit info (optional)
```

#### 4.3 Update React Query Hooks (`services/queries.js`)

```javascript
// New hooks:
export function useRepositoryBranches(repoId, isOpen) {
  return useQuery({
    queryKey: ["repository-branches", repoId],
    queryFn: () => api.get(`/api/repositories/${repoId}/branches`),
    enabled: !!repoId && isOpen
  });
}

export function useInstallWebhook() {
  return useMutation({
    mutationFn: ({ repoId, monitoredBranches, webhookUrl }) =>
      api.post(`/api/repositories/${repoId}/webhook`, {
        monitored_branches: monitoredBranches,
        webhook_url: webhookUrl
      })
  });
}

export function useUpdateBranches() {
  return useMutation({
    mutationFn: ({ repoId, monitoredBranches }) =>
      api.put(`/api/repositories/${repoId}/branches`, {
        monitored_branches: monitoredBranches
      })
  });
}
```

---

### Phase 5: Frontend - Repository Settings

#### 5.1 Add Branch Management to Repository Settings

Create or update repository settings page/component:

**Location:** New component `components/RepositoryBranchSettings.jsx` or integrate into existing repository detail view

**Features:**
- Show currently monitored branches
- "Edit Branches" button opens modal
- Branch filter toggle (enable/disable filtering)
- Webhook status indicator (installed/not installed)

**Edit Branches Modal:**
- Reuse `BranchSelector` component
- Show current selection
- Save button calls `useUpdateBranches` mutation
- If webhook exists, automatically updates webhook

---

### Phase 6: API Models

#### 6.1 Add New Pydantic Models (`api_models.py`)

```python
class BranchInfo(BaseModel):
    """Information about a GitLab branch."""
    name: str
    commit_id: str
    commit_short_id: str
    is_default: bool
    can_push: bool = False
    web_url: Optional[str] = None


class BranchResponse(BaseModel):
    """Response with branch list."""
    branches: List[BranchInfo]
    default_branch: str


class UpdateBranchesRequest(BaseModel):
    """Request to update monitored branches."""
    monitored_branches: List[str] = Field(..., description="List of branch names to monitor")
    branch_filter_enabled: bool = True


class InstallWebhookRequest(BaseModel):
    """Request to install webhook."""
    monitored_branches: List[str] = Field(default_factory=list, description="Branches to monitor (empty = all)")
    webhook_url: Optional[str] = Field(None, description="Custom webhook URL (uses default if not provided)")


class WebhookResponse(BaseModel):
    """Webhook installation response."""
    webhook_id: int
    webhook_url: str
    monitored_branches: List[str]
    branch_filter_enabled: bool
    message: str
```

---

## Critical Files to Modify

### Backend Files
1. **`services/repository_service.py`**
   - Add `get_gitlab_branches()` function
   - Update `connect_repository()` to handle monitored_branches
   - Update `onboard_repository()` to accept monitored_branches

2. **`services/webhook_service.py`** (NEW FILE)
   - Create webhook management service
   - Implement install/update/delete webhook functions

3. **`services/review_service.py`**
   - Add `should_process_webhook()` function
   - Update `orchestrate_review()` to check branch filter

4. **`api_models.py`**
   - Add BranchInfo, BranchResponse, UpdateBranchesRequest, InstallWebhookRequest, WebhookResponse models

5. **`main.py`**
   - Add GET /api/repositories/{repo_id}/branches endpoint
   - Add PUT /api/repositories/{repo_id}/branches endpoint
   - Add POST /api/repositories/{repo_id}/webhook endpoint
   - Update POST /api/repositories/onboard to accept monitored_branches

### Frontend Files
1. **`frontend/gatekeeper/src/components/ConnectRepositoryModal.jsx`**
   - Add "branches" step
   - Add "webhook-confirm" step
   - Integrate BranchSelector component

2. **`frontend/gatekeeper/src/components/BranchSelector.jsx`** (NEW FILE)
   - Branch selection component with search and checkboxes

3. **`frontend/gatekeeper/src/services/queries.js`**
   - Add useRepositoryBranches hook
   - Add useInstallWebhook hook
   - Add useUpdateBranches hook
   - Update useOnboardRepository to include monitored_branches

4. **`frontend/gatekeeper/src/pages/Repositories.jsx`** or new detail view
   - Add branch management UI
   - Display monitored branches
   - Edit branches modal

---

## Verification Steps

### 1. Backend Testing
```bash
# Test branch fetching
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/repositories/<repo_id>/branches

# Test webhook installation
curl -X POST -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"monitored_branches": ["main", "develop"]}' \
  http://localhost:8000/api/repositories/<repo_id>/webhook

# Test branch filter in webhook processing
# Send test webhook payload with different branches and verify filtering works
```

### 2. Frontend Testing
1. Open "Connect Repository" modal
2. Select a repository
3. **NEW:** Select branches from the list
4. **NEW:** Confirm webhook installation on summary screen
5. Verify webhook is created in GitLab project settings
6. Create MR for monitored branch → should trigger review
7. Create MR for non-monitored branch → should be filtered out

### 3. Edit Branches Testing
1. Go to repository settings/branches page
2. Click "Edit Branches"
3. Add/remove branches
4. Save changes
5. Verify filter behavior updates immediately

### 4. Edge Cases
- Empty branch selection (all branches monitored)
- All branches selected (equivalent to no filter)
- Default branch removed from selection (should warn)
- Repository disconnected (webhook should be deleted)

---

## Notes

### Webhook URL Configuration
- Default webhook URL: Construct from `FRONTEND_URL` or `BASE_URL` env var
- Pattern: `{BASE_URL}/webhooks/gitlab`
- For local dev: Use ngrok or similar for external access
- Consider adding webhook URL to system settings

### GitLab API Limitations
- GitLab webhooks don't support push_event_branch_filter parameter for MR events
- Solution: Store filter in our database, filter server-side in `orchestrate_review()`
- This is more flexible and allows runtime filter changes

### Security Considerations
- Validate user has access to repository before installing webhook
- Validate branch names (prevent injection)
- Store webhook_id for cleanup on disconnect
- Consider webhook signature verification (future enhancement)

### Performance
- Branch list is cached per repository in React Query
- Webhook filter check is fast (in-memory set lookup)
- No significant performance impact expected
