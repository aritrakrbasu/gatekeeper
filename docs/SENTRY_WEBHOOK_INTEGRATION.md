# Sentry Webhook Integration - Bug Fix Automation

## Context

The Gatekeeper currently handles GitLab MR webhooks and Dynatrace incident alerts for automated code review and incident remediation. This feature extends the system to receive Sentry bug reports via webhook, automatically detect breaking bugs (production + error/fatal severity), analyze them using AI, and create draft merge requests with fixes.

## Requirements

1. **Breaking Bug Detection**: Process only bugs where `environment=production` AND `level in [error, fatal]`
2. **Sentry MCP Integration**: Use Sentry MCP server to fetch issue details
3. **GitLab Context**: Connect to GitLab MCP for repository context and affected files
4. **AI Analysis**: Use Gemini to analyze stack traces and generate solutions
5. **Draft MR Creation**: Automatically create draft MRs (no human approval required)
6. **Observability**: Store execution traces in MongoDB

## Implementation Plan

### Phase 1: Data Models and Context (api_models.py, agents/context.py)

**1.1 Add Sentry Webhook Models** - `api_models.py`

```python
class SentryIssueSeverity(str, Enum):
    FATAL = "fatal"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

class SentryEnvironment(str, Enum):
    PRODUCTION = "production"
    STAGING = "staging"

class SentryStacktraceFrame(BaseModel):
    filename: str
    function: str
    lineno: int

class SentryWebhookPayload(BaseModel):
    issue_id: str
    title: str
    level: SentryIssueSeverity
    environment: SentryEnvironment
    culprit: Optional[str]
    message: str
    stacktrace: List[SentryStacktraceFrame]
    project: str
    tags: Dict[str, str]
    first_seen: datetime
    last_seen: datetime
```

**1.2 Add SentryIssueContext** - `agents/context.py` (after line 44)

```python
class SentryIssueContext(BaseModel):
    issue_id: str
    title: str
    level: str
    environment: str
    culprit: Optional[str]
    stack_trace: Optional[str]
    affected_files: List[str] = Field(default_factory=list)
    git_commit_sha: Optional[str]
```

Update `AgentContext` to include sentry_issue (after line 67):
```python
sentry_issue: Optional[SentryIssueContext] = None
```

**1.3 Add ContextBuilder Method** - `agents/context.py` (after line 367)

```python
@classmethod
def build_from_sentry_issue(cls, payload: dict, repository_path: Optional[str] = None, target_project_id: Optional[str] = None) -> AgentContext:
    issue_id = str(payload.get("issue_id", "unknown"))
    project_id = str(target_project_id or payload.get("tags", {}).get("gitlab.project_id", "82576405"))

    task_id = f"sentry-bug-{issue_id}-{uuid.uuid4().hex[:8]}"
    objective = f"Analyze and fix Sentry issue {issue_id}. Fetch issue details, identify root cause, and create a draft MR with the fix."

    repo_ctx = RepositoryContext(id=project_id, name=payload.get("project", "unknown"))
    branch_ctx = BranchContext(source_branch="main", target_branch="main")
    user_ctx = UserContext(user_id="sentry-operator", username="sentry", permissions=["read", "write"])
    schema_ctx = SchemaContext(db_name="gatekeeper_dev")

    sentry_ctx = SentryIssueContext(
        issue_id=issue_id,
        title=payload.get("title", ""),
        level=str(payload.get("level", "")),
        environment=str(payload.get("environment", "")),
        culprit=payload.get("culprit"),
        stack_trace=payload.get("message", ""),
        git_commit_sha=payload.get("tags", {}).get("sentry.sha")
    )

    metadata = {
        "trigger_type": "sentry_issue",
        "issue_id": issue_id,
        "severity": str(payload.get("level", ""))
    }

    return AgentContext(
        task_id=task_id,
        objective=objective,
        repository=repo_ctx,
        branch=branch_ctx,
        user=user_ctx,
        schema_ctx=schema_ctx,
        sentry_issue=sentry_ctx,
        metadata=metadata
    )
```

### Phase 2: Sentry MCP Integration (services/mcp_service.py, agents/mcp_wrappers.py)

**2.1 Add Sentry Session** - `services/mcp_service.py`

Add global session variable (after line 23):
```python
sentry_session = None
```

Initialize in `boot_mcp_bridge()` function:
```python
# Sentry MCP initialization
sentry_org_slug = os.getenv("SENTRY_ORGANIZATION_SLUG", "")
if sentry_org_slug:
    try:
        from mcp import stdio_server
        sentry_command = ["npx", "-y", "@sentryio/mcp-server"]
        sentry_env = {
            "SENTRY_AUTH_TOKEN": os.getenv("SENTRY_AUTH_TOKEN", ""),
            "SENTRY_ORGANIZATION_SLUG": sentry_org_slug
        }
        sentry_session = await stdio_server.create_server(sentry_command, env=sentry_env)
        print("[OK] Sentry MCP session initialized")
    except Exception as e:
        print(f"[WARN] Failed to initialize Sentry MCP: {e}")
```

**2.2 Add SentryMCPTool** - `agents/mcp_wrappers.py` (after line 210)

```python
class SentryMCPTool(BaseMCPTool):
    """Wrapper for Sentry MCP tools."""
    def __init__(self, name: str, description: str, schema: Dict[str, Any]):
        super().__init__(
            name=name,
            description=description,
            schema=schema,
            session_name="sentry",
            session_getter=lambda: mcp_service.sentry_session
        )
```

**2.3 Update Tool Registry** - `agents/registry.py`

Import SentryMCPTool (after line 4):
```python
from agents.mcp_wrappers import GitLabMCPTool, MongoMCPTool, DynatraceMCPTool, GitNexusMCPTool, SentryMCPTool
```

Add Sentry session registration (after line 54):
```python
elif session_name == "sentry":
    wrapper = SentryMCPTool(name=tool.name, description=tool.description, schema=schema)
```

Register Sentry session in `build_default_registry()` (after line 143):
```python
if mcp_service.sentry_session:
    await registry.register_mcp_session("sentry", mcp_service.sentry_session)
```

### Phase 3: Sentry Workflow (agents/workflows.py)

**3.1 Add Breaking Bug Detection Helper** (after line 80)

```python
def _is_breaking_bug(payload: Dict[str, Any]) -> bool:
    """Detect if Sentry issue is a breaking bug (production + error/fatal)."""
    environment = str(payload.get("environment", "")).lower()
    level = str(payload.get("level", "")).lower()
    return environment == "production" and level in ["error", "fatal"]
```

**3.2 Add Sentry Bug Workflow** (after line 80)

```python
async def run_sentry_bug_workflow(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sentry Bug Workflow:
    Breaking Bug Detection -> Context Build -> Sentry MCP -> GitLab MCP -> Gemini Analysis -> Draft MR Creation
    """
    # 1. Check if breaking bug
    if not _is_breaking_bug(payload):
        return {
            "status": "ignored",
            "reason": "Not a breaking bug",
            "environment": payload.get("environment"),
            "level": payload.get("level")
        }

    issue_id = payload.get("issue_id", "unknown")

    # 2. Build context
    context = ContextBuilder.build_from_sentry_issue(payload)
    registry = await build_default_registry()

    # 3. Execute workflow
    engine = WorkflowEngine(registry)
    result = await engine.run_task(context)

    return result
```

### Phase 4: Webhook Endpoint (main.py)

**4.1 Add Sentry Webhook Handler** (after line 206)

```python
@app.post("/webhooks/sentry")
async def sentry_webhook(request: Request, x_sentry_signature: str = Header(None)):
    """API endpoint to receive Sentry issue events for automated bug fix."""
    import sys
    sys.stderr.write(f"\n[WEBHOOK HIT!] Sentry webhook received\n")
    sys.stderr.flush()

    # Check MCP readiness
    if not mcp_service.mcp_ready:
        return {"status": "mcp_not_ready", "message": "MCP sessions initializing"}

    payload = await request.json()

    # Log webhook
    await mongo_client.insert_one(
        collection_name="sentry_webhooks",
        document={**payload, "received_at": datetime.utcnow().isoformat()}
    )

    # Check agentic mode
    agentic_mode = os.getenv("AGENTIC_MODE_ENABLED", "false").lower() == "true"

    if agentic_mode:
        from agents.workflows import run_sentry_bug_workflow
        return await run_sentry_bug_workflow(payload)
    else:
        return {"status": "not_implemented", "message": "Agentic mode required for Sentry"}
```

### Phase 5: Gemini Integration (services/gemini_service.py)

**5.1 Add Sentry Analysis Function** - `services/gemini_service.py`

Add function for stack trace analysis:
```python
async def analyze_sentry_stack_trace(stack_trace: str, context: str) -> dict:
    """Analyze Sentry stack trace and generate fix using Gemini."""
    prompt = f"""Analyze this stack trace and generate a fix:

Stack Trace:
{stack_trace}

Context:
{context}

Output JSON with:
- root_cause: Description
- affected_file: File path
- original_code: Problematic snippet
- fixed_code: Corrected code
- confidence: 0.0-1.0
"""
    # Implement using Gemini with structured output
```

### Phase 6: Environment Configuration

**6.1 Add to .env**

```bash
# Sentry Configuration
SENTRY_AUTH_TOKEN=your_sentry_auth_token
SENTRY_ORGANIZATION_SLUG=your_org_slug
SENTRY_WEBHOOK_SECRET=your_webhook_secret

# Agentic Mode
AGENTIC_MODE_ENABLED=true
```

**6.2 Install Sentry MCP Server**

```bash
npm install -g @sentryio/mcp-server
```

## Critical Files to Modify

| File | Changes |
|------|----------|
| `main.py` | Add `/webhooks/sentry` endpoint (after line 206) |
| `agents/workflows.py` | Add `run_sentry_bug_workflow()` and `_is_breaking_bug()` |
| `agents/mcp_wrappers.py` | Add `SentryMCPTool` class |
| `agents/context.py` | Add `SentryIssueContext` and `build_from_sentry_issue()` |
| `agents/registry.py` | Import and register `SentryMCPTool`, add sentry session registration |
| `services/mcp_service.py` | Initialize `sentry_session` in `boot_mcp_bridge()` |
| `api_models.py` | Add `SentryWebhookPayload` and related models |
| `services/gemini_service.py` | Add `analyze_sentry_stack_trace()` function |

## Verification Steps

1. **Unit Tests**:
   - Test `_is_breaking_bug()` with various combinations of environment and level
   - Test `ContextBuilder.build_from_sentry_issue()` context creation
   - Test SentryMCPTool execution

2. **Integration Tests**:
   - Send mock Sentry webhook payload to `/webhooks/sentry`
   - Verify breaking bug triggers workflow
   - Verify non-breaking bug is ignored
   - Check MongoDB for trace storage

3. **Manual Testing**:
   - Use ngrok to expose local endpoint
   - Configure Sentry webhook to ngrok URL
   - Trigger test error in production environment
   - Verify:
     - Webhook received and logged
     - Breaking bug detection works
     - Sentry MCP fetches issue details
     - GitLab MCP retrieves repository context
     - Gemini analyzes stack trace
     - Draft MR is created

4. **Dashboard Verification**:
   - Check traces in `agent_execution_traces` collection
   - Verify progress logs are visible
   - Confirm MR link is stored in metadata

## Error Handling

- **Sentry MCP unavailable**: Log error and return 503
- **GitLab project not found**: Use default project ID from tags
- **Gemini API failure**: Retry with backoff, fallback to manual resolution
- **MR creation failed**: Store fix in MongoDB for manual application
- **Invalid payload**: Return 400 with validation errors

## Security Considerations

- Implement webhook signature verification using `x-sentry-signature` header
- Store Sentry tokens securely in environment variables
- Ensure traces don't expose sensitive data
- Rate limit webhook endpoint to prevent abuse
