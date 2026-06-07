# Sentry Webhook Data Flow Diagram

## Key Architecture Decision

**Sentry webhook payload contains all issue details needed - no extra Sentry API calls required!**

The Sentry webhook payload includes:
- `issue_id`, `title`, `level`, `environment`
- `culprit`, `stack_trace` (exception message)
- `tags` (including `sentry.git_commit_sha`)
- `project`, `release`, `platform`

This data is:
1. Stored in `SentryIssueContext` 
2. Passed to the LLM in the planning prompt (agents/planner.py)
3. Used directly for analysis - NO Sentry MCP fetch needed

Sentry MCP is **optional** and only used for additional context like:
- Full event history
- Related issues
- Comments/annotations

## Overview

This document illustrates the complete data flow when a Sentry webhook is received by The Gatekeeper for automated bug fixing.

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           SENTRY WEBHOOK DATA FLOW                                    │
└─────────────────────────────────────────────────────────────────────────────────────┘

  ┌──────────────────┐
  │                  │
  │     Sentry       │
  │  (Error Event)   │
  │                  │
  └────────┬─────────┘
           │
           │ HTTP POST
           │ X-Sentry-Signature header
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 1: WEBHOOK RECEIPT                                                              │
│ Endpoint: POST /webhooks/sentry                                                       │
│ Handler: sentry_webhook() in main.py (lines 356-522)                                 │
└─────────────────────────────────────────────────────────────────────────────────────┘
           │
           ├──► Extract org_slug from payload (multiple paths):
           │    • payload.organization.slug (direct)
           │    • payload.data.issue.web_url (from URL)
           │    • payload.data.error.url (from error URL)
           │
           ├──► Find connected repositories by org_slug
           │    └──► Query MongoDB: connected_repositories collection
           │
           ├──► Update webhook_registered status in MongoDB
           │    • sentry_integration.webhook_registered = true
           │    • sentry_integration.last_webhook_at = timestamp
           │    • sentry_integration.webhook_id (if first webhook)
           │
           ├──► Capture repository owner info:
           │    • repo_owner_user_id (from repository.user_id)
           │    • gitlab_project_id (from repository.id)
           │
           └──► Log webhook to MongoDB collection: sentry_webhooks
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 2: MCP READINESS CHECK                                                           │
│ Location: main.py line 500-504                                                         │
└─────────────────────────────────────────────────────────────────────────────────────┘
           │
           ├──► Check: mcp_service.mcp_ready
           │
           └──► If NOT ready → Return {"status": "mcp_not_ready"}
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 3: WORKFLOW INVOCATION                                                           │
│ Location: main.py line 506-522                                                        │
│ Handler: run_sentry_bug_workflow() in agents/workflows.py (lines 176-262)           │
└─────────────────────────────────────────────────────────────────────────────────────┘
           │
           ├──► Pass parameters:
           │    • payload (Sentry webhook payload)
           │    • user_id (repository owner)
           │    • username (repository owner username)
           │    • target_project_id (GitLab project ID)
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 4: PAYLOAD NORMALIZATION                                                          │
│ Location: agents/workflows.py line 194-195                                            │
│ Function: normalize_sentry_payload() in agents/context.py                            │
└─────────────────────────────────────────────────────────────────────────────────────┘
           │
           ├──► Extract nested data from webhook structure:
           │    • issue_id: from data.error.issue_id OR data.issue.id
           │    • title: from data.issue.title OR data.issue.culprit
           │    • level: from data.level OR data.issue.level
           │    • environment: from data.environment OR data.tags.environment
           │    • culprit: from data.culprit OR data.issue.culprit
           │    • stack_trace: from data.message OR data.issue.message
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 5: BREAKING BUG DETECTION                                                        │
│ Location: agents/workflows.py line 197-204                                            │
│ Function: _is_breaking_bug() (lines 169-173)                                         │
└─────────────────────────────────────────────────────────────────────────────────────┘
           │
           ├──► Check: environment == "production"
           │    AND level in ["error", "fatal"]
           │
           └──► If NOT breaking bug → Return {"status": "ignored"}
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 6: OPEN TELEMETRY CONTEXT CREATION                                              │
│ Location: agents/workflows.py line 209-235                                           │
└─────────────────────────────────────────────────────────────────────────────────────┘
           │
           ├──► Create OTEL span: "sentry_bug_workflow"
           │
           ├──► Set baggage attributes:
           │    • user.id
           │    • sentry.issue_id
           │    • repository.id
           │    • operation.type = "sentry_bug_workflow"
           │
           └──► Set span attributes for observability
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 7: AGENT CONTEXT BUILDING                                                        │
│ Location: agents/workflows.py line 239                                                │
│ Function: ContextBuilder.build_from_sentry_issue() in agents/context.py            │
└─────────────────────────────────────────────────────────────────────────────────────┘
           │
           ├──► Create SentryIssueContext:
           │    • issue_id
           │    • title
           │    • level
           │    • environment
           │    • culprit
           │    • stack_trace
           │    • affected_files (populated later)
           │    • git_commit_sha
           │
           ├──► Create RepositoryContext:
           │    • id: target_project_id
           │    • name: from payload.project
           │
           ├──► Create UserContext:
           │    • user_id: repository owner or "sentry-operator"
           │    • username: repository owner username or "sentry"
           │    • permissions: ["read", "write"]
           │
           └──► Create objective:
                "Analyze and fix Sentry issue {issue_id}. Issue details from webhook,
                 detect problem type, analyze, and create a draft MR with the fix."
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 8: TOOL REGISTRY BUILDING (SENTRY-SPECIFIC)                                     │
│ Location: agents/workflows.py line 242                                                │
│ Function: build_sentry_registry() (lines 265-315)                                   │
└─────────────────────────────────────────────────────────────────────────────────────┘
           │
           ├──► LOCAL PYTHON TOOLS (registered directly):
           │    • clone_repo
           │    • run_impact_analysis
           │    • run_schema_inspection
           │    • get_gitlab_mr_diffs
           │    • post_gitlab_mr_comment
           │    • get_dynatrace_incident_details
           │    • apply_hotfix_patch
           │    • create_hotfix_branch_and_mr
           │    • gitnexus_analyze
           │    • create_gitlab_branch (NEW - REST API)
           │    • create_gitlab_merge_request (NEW - REST API)
           │    • commit_file_to_branch (NEW - REST API)
           │
           ├──► MCP SESSIONS (EXCLUDING GitLab MCP):
           │    • mongodb_session (for memory/storage)
           │    • nexus_session (GitNexus code analysis)
           │    • dynatrace_session (Dynatrace integration)
           │    • sentry_session (OPTIONAL - only for additional context
           │                      beyond webhook payload like event history,
           │                      comments, related issues)
           │
           └──► IMPORTANT: GitLab MCP is NOT used
                Webhook payload contains all basic issue details needed
                → Uses direct GitLab REST API via local tools instead
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 9: WORKFLOW ENGINE EXECUTION                                                     │
│ Location: agents/workflows.py line 245-246                                            │
│ Component: WorkflowEngine in agents/engine.py                                         │
└─────────────────────────────────────────────────────────────────────────────────────┘
           │
           │ The WorkflowEngine runs the planning-execution-reflection loop:
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 10: AI PLANNING (ReAct-style)                                                     │
│ Component: Planner in agents/planner.py (lines 421-429 + Sentry section)           │
└─────────────────────────────────────────────────────────────────────────────────────┘
           │
           ├──► Sentry issue details PASSED TO LLM IN PROMPT:
           │    • ISSUE ID: context.sentry_issue.issue_id
           │    • TITLE: context.sentry_issue.title
           │    • LEVEL: context.sentry_issue.level
           │    • ENVIRONMENT: context.sentry_issue.environment
           │    • CULPRIT: context.sentry_issue.culprit
           │    • STACK TRACE: context.sentry_issue.stack_trace
           │    • GIT COMMIT SHA: context.sentry_issue.git_commit_sha
           │
           ├──► Gemini AI analyzes the issue context from webhook payload
           │
           ├──► Generates execution plan with steps:
           │    1. Clone the GitLab repository
           │    2. Detect problem type (code vs MongoDB vs config)
           │    3a. IF MongoDB problem → Run MongoDB analysis
           │    3b. IF code problem → Run GitNexus analysis for code context
           │    4. Generate fix code based on analysis
           │    5. Create branch via GitLab REST API
           │    6. Commit fix to branch via GitLab REST API
           │    7. Create draft MR via GitLab REST API
           │    8. Store execution trace in MongoDB
           │
           └──► NO Sentry MCP call needed - all issue data already in prompt!
           │
           └──► Plan is passed to Executor
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 11: TOOL EXECUTION (via Executor)                                                │
│ Component: Executor in agents/executor.py                                            │
│ CORRECT ORDER: Clone → Detect Problem Type → Analysis → Branch → Commit → MR          │
└─────────────────────────────────────────────────────────────────────────────────────┘
           │
           │ Tools are called in THIS ORDER:
           │
           ├─► 1. Webhook Payload Data (already available):
           │    └──► issue_id, title, level, environment, culprit,
           │         stack_trace, tags, project info
           │    └──► No Sentry MCP call needed for basic issue details
           │
           ├─► 2. Local tool: clone_repo(project_id)
           │    └──► Clones repository locally to workspace/{repo_name}
           │
           ├─► 3. Gemini AI: detect_problem_type(stack_trace, code_context)
           │    └──► Analyzes stack trace to determine problem type
           │    └──► Returns: "code" or "mongodb" or "config" or "other"
           │
           ├─► 4a. IF MongoDB problem → MongoDB MCP tools:
           │    └──► Query schema, analyze indexes, check queries
           │    └──► Returns MongoDB analysis and fix
           │
           ├─► 4b. IF Code problem → GitNexus MCP tools:
           │    └──► gitnexus_analyze(file_pattern, repo_path)
           │    └──► Returns code analysis, call graphs, affected files
           │
           ├─► 5. Gemini AI: generate_fix(problem_type, analysis, stack_trace)
           │    └──► Generates fix code based on problem type and analysis
           │    └──► Returns: file_path, fixed_code, commit_message
           │
           ├─► 6. create_gitlab_branch(project_id, branch_name, ref)
           │    └──► POST /api/v4/projects/{id}/repository/branches
           │    └──► Returns branch info
           │
           ├─► 7. commit_file_to_branch(project_id, file_path, content, branch, message)
           │    └──► POST /api/v4/projects/{id}/repository/files/{file_path}
           │    └──► Returns commit info
           │
           └─► 8. create_gitlab_merge_request(project_id, source, target, title, description)
                └──► POST /api/v4/projects/{id}/merge_requests
                └──► Returns MR URL and ID
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 12: REFLECTION & VALIDATION                                                      │
│ Component: ReflectionLayer in agents/engine.py                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
           │
           ├──► Analyze execution results
           │
           ├──► Validate MR was created successfully
           │
           └──► Suggest next actions if needed
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 13: STORAGE & OBSERVABILITY                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
           │
           ├──► Store execution trace in MongoDB:
           │    • Collection: agent_execution_traces
           │    • Includes: task_id, issue_id, steps, results, metadata
           │
           ├──► OpenTelemetry span propagation:
           │    • All LLM calls traced via Arize
           │    • Observability data sent to Phoenix Cloud
           │
           └──► Return result to webhook handler
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ FINAL RESPONSE                                                                        │
└─────────────────────────────────────────────────────────────────────────────────────┘
           │
           └──► HTTP Response to Sentry:
                {
                  "status": "completed",
                  "issue_id": "...",
                  "result": {
                    "mr_url": "https://gitlab.com/...",
                    "mr_id": 123,
                    "branch": "fix/sentry-...",
                    "fix_applied": true
                  }
                }
```

## Data Storage Points

| Collection | Purpose | When Written |
|------------|---------|--------------|
| `sentry_webhooks` | Log all incoming webhook payloads | On webhook receipt |
| `connected_repositories` | Store Sentry integration status | On webhook receipt (auto-mark configured) |
| `agent_execution_traces` | Store workflow execution logs | After workflow completion |
| `sentry_oauth_states` | Store OAuth state tokens (temporary) | During OAuth flow |

## GitLab REST API vs MCP Decision

The Sentry workflow intentionally uses **direct GitLab REST API calls** instead of GitLab MCP for branch/MR creation:

```
┌─────────────────────────────────────────────────────────────────────┐
│ Why GitLab REST API instead of GitLab MCP for Sentry?              │
├─────────────────────────────────────────────────────────────────────┤
│ ✓ More predictable behavior for automated workflows                 │
│ ✓ Direct access token management (user/project/global fallback)    │
│ ✓ Better error handling for authentication failures                 │
│ ✓ Lightweight - no MCP bridge dependency for GitLab operations      │
│ ✓ Consistent pattern with review_service.py token handling         │
└─────────────────────────────────────────────────────────────────────┘
```

## Environment Variables Required

```bash
# Sentry OAuth
SENTRY_CLIENT_ID=your_sentry_client_id
SENTRY_CLIENT_SECRET=your_sentry_client_secret
SENTRY_REDIRECT_URI=http://localhost:3000/auth/sentry/callback
SENTRY_WEBHOOK_URL=https://your-domain.com/webhooks/sentry

# GitLab API (for direct REST API calls)
GITLAB_BASE_URL=https://gitlab.com
GITLAB_PERSONAL_ACCESS_TOKEN=your_global_pat

# MongoDB
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=gatekeeper

# MCP Sessions
MCP_READY_TIMEOUT=120

# Agentic Mode
AGENTIC_MODE_ENABLED=true
```

## Mermaid Diagram

```mermaid
sequenceDiagram
    participant Sentry as Sentry
    participant Webhook as /webhooks/sentry
    participant MongoDB as MongoDB
    participant Workflow as Sentry Workflow
    participant Engine as WorkflowEngine
    participant Gemini as Gemini AI
    participant GitLabAPI as GitLab REST API
    participant GitNexus as GitNexus MCP
    participant MongoDBMCP as MongoDB MCP

    Sentry->>Webhook: HTTP POST (Error Event)
    Webhook->>MongoDB: Find repo by org_slug
    MongoDB-->>Webhook: Repository data
    Webhook->>MongoDB: Update webhook_registered=true
    Webhook->>MongoDB: Log webhook to sentry_webhooks
    Webhook->>Workflow: run_sentry_bug_workflow()

    Workflow->>Workflow: Normalize payload
    Workflow->>Workflow: Check if breaking bug
    alt Not breaking bug
        Workflow-->>Webhook: {status: "ignored"}
    else Is breaking bug
        Workflow->>Workflow: Build context
        Workflow->>Workflow: build_sentry_registry()
        Workflow->>Engine: Execute workflow

        Engine->>Gemini: Plan execution
        Gemini-->>Engine: Execution plan

        Note over Engine: Issue details already in webhook payload
        (no Sentry MCP call needed)

        Engine->>GitLabAPI: clone_repo()
        GitLabAPI-->>Engine: Repository cloned

        Engine->>Gemini: detect_problem_type(stack_trace)
        Gemini-->>Engine: "code" or "mongodb" or "other"

        alt MongoDB problem
            Engine->>MongoDBMCP: Analyze schema/queries
            MongoDBMCP-->>Engine: MongoDB analysis
        else Code problem
            Engine->>GitNexus: gitnexus_analyze()
            GitNexus-->>Engine: Code analysis
        end

        Engine->>Gemini: generate_fix(analysis)
        Gemini-->>Engine: Fix code

        Engine->>GitLabAPI: create_gitlab_branch()
        GitLabAPI-->>Engine: Branch created

        Engine->>GitLabAPI: commit_file_to_branch()
        GitLabAPI-->>Engine: File committed

        Engine->>GitLabAPI: create_gitlab_merge_request()
        GitLabAPI-->>Engine: MR created

        Engine->>MongoDB: Store execution trace
        Engine-->>Workflow: Result

        Workflow-->>Webhook: {status: "completed", mr_url: "..."}
    end

    Webhook-->>Sentry: HTTP 200 Response
```

## Key Files Reference

| File | Purpose | Lines |
|------|---------|-------|
| `main.py` | Webhook endpoint handler | 356-522 |
| `agents/workflows.py` | Sentry workflow orchestration | 169-315 |
| `agents/context.py` | Payload normalization & context building | - |
| `agents/registry.py` | Tool registry management | - |
| `agents/tools.py` | GitLab REST API tools | - |
| `services/mcp_service.py` | MCP session management | - |
| `services/sentry_oauth_service.py` | Sentry OAuth flow | - |
