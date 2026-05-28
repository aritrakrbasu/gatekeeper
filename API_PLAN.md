# API Implementation Plan for Gatekeeper Frontend

## Context

The Gatekeeper frontend (React app in `frontend/gatekeeper/src/pages/`) currently uses dummy data and has no connected backend APIs. This plan implements all necessary FastAPI endpoints in `main.py` and supporting services to enable full frontend functionality.

The backend already has:
- MCP bridge services (MongoDB, GitLab, GitNexus) via `mcp_service.py`
- Review orchestration via `review_service.py`
- FastAPI app with health check and GitLab webhook endpoints

## Implementation Plan

### Phase 1: Core API Infrastructure

**1. Create API Response Models (`api_models.py`)**
```python
# New file: D:\My space\the-gatekeeper\api_models.py
```

Define Pydantic models for:
- `AlertResponse` - id, severity, type, title, repo, description, time, unread, action
- `RepositoryResponse` - id, name, visibility, last_sync, health_score, status
- `MergeRequestResponse` - id, title, repo, status, time, ai_summary
- `DashboardStatsResponse` - issues_prevented, avg_review_time, code_health
- `BillingUsageResponse` - current_cycle, usage_stats, tokens, mr_count
- `GeminiSettingsResponse` - api_token_configured, model_selection
- `PolicySettingsResponse` - auto_review, strict_mode, email_alerts, slack_enabled
- `UserProfileResponse` - name, email, avatar_url

### Phase 2: Authentication APIs

**2. Create Auth Service (`auth_service.py`)**
```python
# New file: D:\My space\the-gatekeeper\services\auth_service.py
```

Implement:
- `initiate_gitlab_oauth()` - Generates OAuth URL and state
- `handle_oauth_callback(code, state)` - Exchanges code for tokens
- `verify_token(token)` - Validates JWT/session tokens
- `get_current_user()` - Dependency for protected routes

**3. Add Auth Routes to `main.py`**
```python
# Endpoints to add:
@app.post("/api/auth/gitlab")       # Initiate OAuth
@app.get("/api/auth/gitlab/callback")  # OAuth callback
@app.post("/api/auth/verify")       # Verify token
@app.post("/api/auth/logout")       # Logout/clear session
```

### Phase 3: Repository APIs

**4. Create Repository Service (`repository_service.py`)**
```python
# New file: D:\My space\the-gatekeeper\services\repository_service.py
```

Implement using existing MCP GitLab session:
- `get_all_repositories()` - Fetch from GitLab MCP
- `get_repository(repo_id)` - Get detailed repo info
- `get_repository_mrs(repo_id)` - Get merge requests for repo
- `get_repository_policies(repo_id)` - Get active policies
- `search_repositories(query)` - Search by name
- `import_repository(gitlab_path)` - Import new repo via webhook

**5. Add Repository Routes to `main.py`**
```python
# Endpoints to add:
@app.get("/api/repositories")               # List all repos
@app.get("/api/repositories/{id}")          # Get repo details
@app.get("/api/repositories/{id}/mrs")     # Get repo MRs
@app.get("/api/repositories/{id}/policies") # Get repo policies
@app.get("/api/repositories/search")       # Search repos
@app.post("/api/repositories/import")      # Import new repo
```

### Phase 4: Dashboard APIs

**6. Create Dashboard Service (`dashboard_service.py`)**
```python
# New file: D:\My space\the-gatekeeper\services\dashboard_service.py
```

Implement aggregating from multiple sources:
- `get_recent_mrs(limit=10)` - From review_service data
- `get_repos_health()` - Aggregate health scores
- `get_global_stats()` - Calculate issues prevented, review times

**7. Add Dashboard Routes to `main.py`**
```python
# Endpoints to add:
@app.get("/api/dashboard/recent-mrs")
@app.get("/api/dashboard/repos-health")
@app.get("/api/dashboard/stats")
```

### Phase 5: Alerts APIs

**8. Create Alert Service (`alert_service.py`)**
```python
# New file: D:\My space\the-gatekeeper\services\alert_service.py
```

Implement using MongoDB MCP session:
- `get_all_alerts(severity_filter)` - Fetch from MongoDB
- `mark_alert_read(alert_id)` - Update unread status
- `dismiss_alert(alert_id)` - Delete from MongoDB
- `mark_all_read(user_id)` - Bulk update

**9. Add Alert Routes to `main.py`**
```python
# Endpoints to add:
@app.get("/api/alerts")
@app.put("/api/alerts/{id}/read")
@app.delete("/api/alerts/{id}")
@app.put("/api/alerts/mark-all-read")
```

### Phase 6: Billing APIs

**10. Create Billing Service (`billing_service.py`)**
```python
# New file: D:\My space\the-gatekeeper\services\billing_service.py
```

Implement tracking Gemini API usage:
- `get_usage_stats()` - Calculate from review logs
- `get_gemini_costs()` - Track token usage by model
- `get_invoices()` - Mock invoice data (or integrate payment provider)
- `generate_invoice(invoice_id)` - PDF generation

**11. Add Billing Routes to `main.py`**
```python
# Endpoints to add:
@app.get("/api/billing/usage")
@app.get("/api/billing/gemini-cost")
@app.get("/api/billing/invoices")
@app.post("/api/billing/invoices/{id}/download")
```

### Phase 7: Settings APIs

**12. Create Settings Service (`settings_service.py`)**
```python
# New file: D:\My space\the-gatekeeper\services\settings_service.py
```

Implement using MongoDB for persistence:
- `get_gemini_settings()` - Get from config/env
- `update_gemini_settings(token, model)` - Update .env/config
- `validate_gemini_token(token)` - Test API call
- `get_global_policies()` - Get from MongoDB
- `update_global_policies(settings)` - Update MongoDB
- `get_user_profile()` - Get from GitLab MCP
- `update_user_profile(data)` - Update MongoDB

**13. Add Settings Routes to `main.py`**
```python
# Endpoints to add:
@app.get("/api/settings/gemini")
@app.put("/api/settings/gemini")
@app.post("/api/settings/gemini/validate")
@app.get("/api/settings/policies")
@app.put("/api/settings/policies")
@app.get("/api/user/profile")
@app.put("/api/user/profile")
```

### Phase 8: Integration & Feedback APIs

**14. Extend Settings Service for Integrations**

Add to `settings_service.py`:
- `connect_gitlab(token)` - Store GitLab token
- `disconnect_gitlab()` - Clear GitLab credentials
- `connect_slack(token)` - Store Slack webhook
- `disconnect_slack()` - Clear Slack webhook

**15. Add Integration Routes to `main.py`**
```python
# Endpoints to add:
@app.post("/api/integrations/gitlab")
@app.delete("/api/integrations/gitlab")
@app.post("/api/integrations/slack")
@app.put("/api/integrations/slack")
```

**16. Add Feedback Route to `main.py`**
```python
# Endpoint to add:
@app.post("/api/repositories/{id}/feedback")
```

Store feedback in MongoDB linked to MR/repo.

---

## Critical Files to Create/Modify

### New Files (8 services + models):
1. `D:\My space\the-gatekeeper\api_models.py` - Pydantic response models
2. `D:\My space\the-gatekeeper\services\auth_service.py`
3. `D:\My space\the-gatekeeper\services\repository_service.py`
4. `D:\My space\the-gatekeeper\services\dashboard_service.py`
5. `D:\My space\the-gatekeeper\services\alert_service.py`
6. `D:\My space\the-gatekeeper\services\billing_service.py`
7. `D:\My space\the-gatekeeper\services\settings_service.py`
8. `D:\My space\the-gatekeeper\services\feedback_service.py` (optional - can be in repo_service)

### Files to Modify:
1. `D:\My space\the-gatekeeper\main.py` - Add all new API routes
2. `D:\My space\the-gatekeeper\.env` - Add OAuth/config variables

---

## Environment Variables to Add

```env
# OAuth
GITLAB_CLIENT_ID=
GITLAB_CLIENT_SECRET=
GITLAB_REDIRECT_URI=http://localhost:3000/auth/callback
SECRET_KEY=  # For JWT tokens

# Slack (optional)
SLACK_WEBHOOK_URL=
```

---

## Verification Steps

1. **Start backend**: `python main.py`
2. **Test health endpoint**: `curl http://localhost:8000/health`
3. **Test each API endpoint** with curl or frontend
4. **Verify OAuth flow** works end-to-end
5. **Check MCP sessions** remain healthy during API calls
6. **Test error handling** with invalid requests

---

## Implementation Order Recommendation

1. **Phase 1** (Models) → **Phase 2** (Auth) → **Phase 3** (Repositories)
2. Then **Phase 4** (Dashboard) and **Phase 5** (Alerts) in parallel
3. Finally **Phase 6-8** (Billing, Settings, Integrations)

This order ensures:
- Auth is available for protected routes
- Repository APIs (core data) are available first
- Dashboard and Alerts can consume repository data
- Settings can configure everything

---

## API Summary by Frontend Page

| Page | APIs Required |
|------|---------------|
| **Login.jsx** | `/api/auth/gitlab`, `/api/auth/gitlab/callback`, `/api/auth/verify` |
| **Dashboard.jsx** | `/api/dashboard/recent-mrs`, `/api/dashboard/repos-health`, `/api/dashboard/stats` |
| **Repositories.jsx** | `/api/repositories`, `/api/repositories/search`, `/api/repositories/import` |
| **RepoDetails.jsx** | `/api/repositories/{id}`, `/api/repositories/{id}/mrs`, `/api/repositories/{id}/policies`, `/api/repositories/{id}/feedback` |
| **Alerts.jsx** | `/api/alerts`, `/api/alerts/{id}/read`, `/api/alerts/{id}`, `/api/alerts/mark-all-read` |
| **Billing.jsx** | `/api/billing/usage`, `/api/billing/gemini-cost`, `/api/billing/invoices`, `/api/billing/invoices/{id}/download` |
| **Settings.jsx** | `/api/settings/gemini`, `/api/settings/gemini/validate`, `/api/settings/policies`, `/api/user/profile`, `/api/integrations/gitlab`, `/api/integrations/slack` |

**Total: ~30 API endpoints** across 7 frontend pages.
