# Migration Plan: `@zereight/mcp-gitlab` + Official GitLab MCP Server (Dual-Mode with Fallback)

## Context

The Gatekeeper application currently uses the third-party `@zereight/mcp-gitlab` npm package (v2.1.16) to interface with GitLab through the Model Context Protocol (MCP). GitLab has released an official MCP server that is built directly into GitLab Premium/Ultimate (Beta feature).

This migration will implement a **dual-mode GitLab MCP integration**:
- **Primary**: Official GitLab MCP server (HTTP transport with OAuth)
- **Fallback**: `@zereight/mcp-gitlab` (stdio transport with PAT) - activates automatically if primary fails

### Why This Change?

1. **Official Support**: The official GitLab MCP server is maintained by GitLab and will receive regular updates
2. **Resilience**: Automatic fallback ensures continued operation if official MCP fails
3. **Better Security**: OAuth 2.0 for primary, with PAT fallback as safety net
4. **Trial Safety**: Fallback provides safety net during/after GitLab Duo trial period
5. **Gradual Transition**: Test official MCP while maintaining full functionality via fallback

## Current Implementation Analysis

### Architecture (Current)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Gatekeeper Application                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌──────────────────┐    ┌──────────────────────────────────────┐ │
│  │ mcp_service.py   │    │         agents/mcp_wrappers.py         │ │
│  │                  │    │                                       │ │
│  │ • boot_mcp_      │───▶│ • GitLabMCPTool                       │ │
│  │   bridge()       │    │ • get_session() - dynamic user tokens │ │
│  │ • Per-user       │    │ • execute() - timeout & retry logic   │ │
│  │   sessions       │    │                                       │ │
│  └────────┬─────────┘    └──────────────────────────────────────┘ │
│           │                                                            │
│           │ stdio_client (Node.js subprocess)                         │
│           ▼                                                            │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │     @zereight/mcp-gitlab/build/index.js                       │  │
│  │     (Local npm package, stdio transport)                      │  │
│  │     • 156 GitLab tools                                         │  │
│  │     • GITLAB_PERSONAL_ACCESS_TOKEN authentication            │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Files Using GitLab MCP

| File | Purpose | GitLab MCP Usage |
|------|---------|------------------|
| `services/mcp_service.py` | MCP initialization | Creates stdio sessions, manages per-user sessions with tokens |
| `agents/mcp_wrappers.py` | GitLabMCPTool wrapper | Dynamic session retrieval, tool execution with retry logic |
| `agents/registry.py` | Tool registration | Registers GitLab MCP tools from session |
| `services/review_service.py` | MR reviews | `get_merge_request`, `get_file_contents` |
| `services/repository_service.py` | Repository operations | `get_project`, `list_merge_requests`, `get_repository_tree` |
| `services/incident_service.py` | Incident response | `get_repository_archive`, `create_branch`, `create_or_update_file` |
| `services/remediation_service.py` | Auto-fixes | `get_file_contents`, `create_or_update_file`, `create_merge_request` |
| `package.json` | Dependencies | `@zereight/mcp-gitlab: ^2.1.16` |

### Current GitLab Tools Used

The application currently uses these GitLab MCP tools (and more):
- `get_project` - Project details
- `list_merge_requests`, `get_merge_request` - MR operations
- `get_repository_tree` - Repository structure
- `get_file_contents` - Read files
- `create_branch` - Branch creation
- `create_or_update_file` - File operations
- `create_merge_request` - MR creation
- `get_repository_archive` - Archive downloads
- `create_merge_request_note` - MR comments

### Current Authentication Pattern

```python
# Current: Static Personal Access Token
gitlab_params = StdioServerParameters(
    command=node_cmd,
    args=[gitlab_js_path],
    env={
        "GITLAB_PERSONAL_ACCESS_TOKEN": token,  # From env or MongoDB
        "GITLAB_URL": "https://gitlab.com"
    }
)
```

## Official GitLab MCP Server

### Architecture (Official)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Gatekeeper Application                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌──────────────────┐    ┌──────────────────────────────────────┐ │
│  │ mcp_service.py  │    │         GitLabMCPTool (Updated)        │ │
│  │                 │    │                                       │ │
│  │ • Primary: HTTP │───▶│ • Try primary first                   │ │
│  │ • Fallback: stdio│    │ • Auto-fallback on failure           │ │
│  │ • Circuit breaker│    │ • Retry with exponential backoff     │ │
│  │ • Health monitor  │    │ • Track success/failure rates         │ │
│  └────────┬─────────┘    └──────────────────────────────────────┘ │
│           │                                                            │
│           ├─────────────┬──────────────────────────────────────┐    │
│           │             │                                      │    │
│           ▼             ▼                                      │    │
│  ┌──────────────────┐  ┌────────────────────────────────────┐  │    │
│  │  Official GitLab│  │  @zereight/mcp-gitlab (Backup)     │  │    │
│  │  MCP (HTTP)      │  │  (stdio)                            │  │    │
│  │  • Primary      │  │  • Fallback                         │  │    │
│  │  • OAuth tokens  │  │  • PAT tokens                       │  │    │
│  └──────────────────┘  └────────────────────────────────────┘  │    │
│                                                               │    │
└───────────────────────────────────────────────────────────────│    │
           Circuit Breaker States:                              │    │
           • CLOSED (use primary) ─────────────────────────────┘    │
           • OPEN (use fallback) ───────────────────────────────┘   │
           • HALF_OPEN (testing primary recovery) ───────────────┘  │
                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Differences

| Aspect | Current (`@zereight/mcp-gitlab`) | Official GitLab MCP |
|--------|----------------------------------|---------------------|
| **Transport** | stdio (Node.js subprocess) | HTTP (recommended) or stdio via `mcp-remote` |
| **Installation** | npm package required | Built into GitLab (no installation) |
| **Authentication** | Personal Access Token (static) | OAuth 2.0 Dynamic Client Registration |
| **Connection** | `StdioServerParameters` | HTTP URL: `https://<instance>/api/v4/mcp` |
| **Tool Prefix** | Not supported | Supported via `X-Gitlab-Mcp-Server-Tool-Name-Prefix` header |
| **Availability** | Any GitLab instance | GitLab Premium/Ultimate only (Beta) |
| **Session Management** | Custom stdio sessions | HTTP client with OAuth token |

### Official Server Configuration

```json
{
  "mcpServers": {
    "GitLab": {
      "type": "http",
      "url": "https://gitlab.com/api/v4/mcp",
      "headers": {
        "Authorization": "Bearer <oauth_token>",
        "X-Gitlab-Mcp-Server-Tool-Name-Prefix": "gitlab_"
      }
    }
  }
}
```

### Available Tools

The official GitLab MCP server provides tools for:
- Project information and management
- Merge requests (read, create, merge)
- Issues and work items
- Repository files and trees
- Branches and commits
- Pipelines and CI/CD
- Wiki pages
- Releases

**Note**: Need to verify the exact tool list matches current functionality.

## Fallback Architecture

### Design Pattern: Primary with Circuit Breaker

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Gatekeeper Application                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌──────────────────┐    ┌──────────────────────────────────────┐ │
│  │ mcp_service.py   │    │         GitLabMCPTool (Updated)        │ │
│  │                  │    │                                       │ │
│  │ • Primary: HTTP  │───▶│ • Try primary first                   │ │
│  │ • Fallback: stdio│    │ • Auto-fallback on failure           │ │
│  │ • Circuit breaker│    │ • Retry with exponential backoff     │ │
│  │ • Health monitor  │    │ • Track success/failure rates         │ │
│  └────────┬─────────┘    └──────────────────────────────────────┘ │
│           │                                                            │
│           ├─────────────┬──────────────────────────────────────┐    │
│           │             │                                      │    │
│           ▼             ▼                                      │    │
│  ┌──────────────────┐  ┌────────────────────────────────────┐  │    │
│  │  Official GitLab│  │  @zereight/mcp-gitlab (Backup)     │  │    │
│  │  MCP (HTTP)      │  │  (stdio)                            │  │    │
│  │  • Primary      │  │  • Fallback                         │  │    │
│  │  • OAuth tokens  │  │  • PAT tokens                       │  │    │
│  └──────────────────┘  └────────────────────────────────────┘  │    │
│                                                               │    │
└───────────────────────────────────────────────────────────────│    │
           Circuit Breaker States:                              │    │
           • CLOSED (use primary) ─────────────────────────────┘    │
           • OPEN (use fallback) ───────────────────────────────┘   │
           • HALF_OPEN (testing primary recovery) ───────────────┘  │
                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

### Fallback Logic Flow

```python
async def execute_gitlab_tool(tool_name: str, arguments: dict, context: AgentContext):
    """
    Execute GitLab tool with automatic fallback.

    Flow:
    1. Try official GitLab MCP (HTTP)
    2. If fails with specific errors (503, timeout, auth):
       - Increment failure counter
       - If failures > threshold, open circuit breaker
       - Fall back to @zereight/mcp-gitlab
    3. If fallback succeeds:
       - Log fallback usage
       - Continue operation
    4. Periodically test primary recovery (half-open state)
    5. If primary recovers: close circuit breaker
    """

    # Try primary first
    if circuit_breaker_is_closed():
        try:
            return await execute_with_http_mcp(tool_name, arguments, context)
        except (TimeoutError, HTTP503Error, AuthError) as e:
            record_failure()
            if should_open_circuit_breaker():
                open_circuit_breaker()
                log.warn("Switching to fallback MCP")

    # Use fallback
    return await execute_with_stdio_mcp(tool_name, arguments, context)
```

### Circuit Breaker States

| State | Description | Behavior |
|-------|-------------|----------|
| **CLOSED** | Primary is healthy | Use official GitLab MCP, count failures |
| **OPEN** | Primary is failing | Use `@zereight/mcp-gitlab`, skip primary |
| **HALF_OPEN** | Testing recovery | Try primary on request, fallback if fails |

### Configuration Options

```bash
# Environment variables
GITLAB_MCP_PRIMARY_MODE=http        # http or stdio
GITLAB_MCP_FALLBACK_ENABLED=true    # Enable fallback
GITLAB_MCP_FAILURE_THRESHOLD=5      # Failures before opening circuit
GITLAB_MCP_TIMEOUT_SECONDS=30       # Timeout for MCP calls
GITLAB_MCP_RETRY_DELAY_SECONDS=60   # Delay before testing recovery
```

## Migration Plan

### Phase 1: Dependency Changes

**File: `package.json`**

```diff
{
  "devDependencies": {
    "@zereight/mcp-gitlab": "^2.1.16",  # Keep for fallback
    "mongodb-mcp-server": "^1.11.0"
  }
}
```

**Action**: Keep `@zereight/mcp-gitlab` as fallback dependency. No changes to package.json needed.

### Phase 2: MCP Service Redesign with Fallback

**File: `services/mcp_service.py`**

#### Changes Required:

1. **Add HTTP-based GitLab MCP client (Primary)**
   ```python
   from mcp.client.http import http_client  # New import

   # New global variables for dual-mode
   gitlab_http_client = None          # Primary: Official GitLab MCP
   gitlab_stdio_session = None        # Fallback: @zereight/mcp-gitlab
   gitlab_mode = "unknown"            # "http", "stdio", or "fallback"
   circuit_breaker = {
       "state": "closed",             # closed, open, half_open
       "failures": 0,
       "last_failure_time": None,
       "last_test_time": None
   }
   ```

2. **Implement boot sequence with fallback**
   ```python
   async def boot_mcp_bridge():
       """
       Initialize both MCP clients:
       1. Try official GitLab MCP (HTTP) first
       2. Initialize @zereight/mcp-gitlab as fallback
       3. Set initial mode based on availability
       """
       global gitlab_http_client, gitlab_stdio_session, gitlab_mode

       # Initialize official GitLab MCP (HTTP)
       try:
           gitlab_http_client = await boot_gitlab_http_client()
           gitlab_mode = "http"
           mcp_log("[OK] Official GitLab MCP initialized (primary)")
       except Exception as e:
           mcp_log(f"[WARN] Official GitLab MCP failed: {e}")
           gitlab_mode = "fallback"

       # Initialize @zereight/mcp-gitlab (stdio) as fallback
       try:
           gitlab_stdio_session = await boot_gitlab_stdio_client()
           mcp_log("[OK] @zereight/mcp-gitlab initialized (fallback)")
       except Exception as e:
           mcp_log(f"[ERROR] Fallback MCP also failed: {e}")

       # Determine final mode
       if gitlab_http_client:
           gitlab_mode = "http"
       elif gitlab_stdio_session:
           gitlab_mode = "stdio"
       else:
           gitlab_mode = "unavailable"
           mcp_log("[ERROR] No GitLab MCP available!")

       mark_gitlab_ready()
   ```

3. **Implement circuit breaker logic**
   ```python
   async def execute_gitlab_tool_with_fallback(tool_name: str, arguments: dict, context: AgentContext):
       """Execute tool with automatic fallback."""

       # Try primary (HTTP) if circuit breaker is closed
       if circuit_breaker["state"] in ["closed", "half_open"]:
           try:
               result = await execute_with_http_client(tool_name, arguments, context)
               # Success: reset circuit breaker if we were testing
               if circuit_breaker["state"] == "half_open":
                   circuit_breaker["state"] = "closed"
                   circuit_breaker["failures"] = 0
                   mcp_log("[OK] Primary MCP recovered, circuit breaker closed")
               return result
           except Exception as e:
               circuit_breaker["failures"] += 1
               circuit_breaker["last_failure_time"] = time.time()
               mcp_log(f"[WARN] Primary MCP failed: {e} (failures: {circuit_breaker['failures']})")

               # Check if we should open circuit breaker
               if circuit_breaker["failures"] >= FAILURE_THRESHOLD:
                   circuit_breaker["state"] = "open"
                   mcp_log("[WARN] Circuit breaker opened, switching to fallback")

       # Use fallback (@zereight/mcp-gitlab)
       if gitlab_stdio_session:
           return await execute_with_stdio_session(tool_name, arguments, context)
       else:
           raise RuntimeError("Both primary and fallback MCP unavailable")
   ```

4. **Keep existing stdio initialization for fallback**
   - Keep lines 125-138 (GitLab path detection) - move to fallback function
   - Keep lines 157-165 (GitLab stdio parameters) - move to fallback function
   - Create separate `boot_gitlab_stdio_client()` function for fallback

5. **Add OAuth 2.0 token management for primary**
   ```python
   async def get_gitlab_oauth_token(user_id: str) -> str:
       """Get OAuth token for user from MongoDB or trigger OAuth flow."""
       # For primary HTTP client
       pass
   ```

### Phase 3: MCP Wrapper Updates with Fallback

**File: `agents/mcp_wrappers.py`**

#### Changes Required:

1. **Update `GitLabMCPTool` for dual-mode with fallback**
   ```python
   class GitLabMCPTool(BaseMCPTool):
       """Wrapper for GitLab MCP tools with automatic fallback support."""

       async def get_primary_session(self, context: Optional[AgentContext] = None) -> Any:
           """Get GitLab HTTP client for the current user (primary)."""
           if context and context.user and context.user.user_id:
               # Get user's OAuth token
               token = await get_user_oauth_token(context.user.user_id)
               # Return HTTP client configured with user's token
               return mcp_service.get_gitlab_http_client_for_token(token)
           return mcp_service.gitlab_http_client  # Global client

       async def get_fallback_session(self, context: Optional[AgentContext] = None) -> Any:
           """Get GitLab stdio session (fallback)."""
           if context and context.user and context.user.user_id:
               # Get user's PAT from MongoDB
               return await mcp_service.get_gitlab_session_for_user(context.user.user_id)
           return mcp_service.gitlab_stdio_session  # Global session

       async def execute(self, arguments: Dict[str, Any], context: Optional[AgentContext] = None) -> ToolResult:
           """Execute with automatic fallback."""

           # Try primary first (HTTP client)
           primary_session = await self.get_primary_session(context)
           if primary_session and mcp_service.circuit_breaker["state"] in ["closed", "half_open"]:
               try:
                   return await self._execute_with_session(primary_session, arguments, context, mode="primary")
               except Exception as e:
                   # Record failure and check circuit breaker
                   mcp_service.circuit_breaker["failures"] += 1
                   if mcp_service.circuit_breaker["failures"] >= FAILURE_THRESHOLD:
                       mcp_service.circuit_breaker["state"] = "open"
                       logger.warn(f"[GitLabMCPTool] Primary failed, opening circuit breaker: {e}")

           # Use fallback (stdio session)
           fallback_session = await self.get_fallback_session(context)
           if fallback_session:
               logger.info(f"[GitLabMCPTool] Using fallback session for {self.name}")
               return await self._execute_with_session(fallback_session, arguments, context, mode="fallback")

           # Both failed
           return ToolResult(status="error", error_message="No GitLab MCP session available", ...)

       async def _execute_with_session(self, session, arguments, context, mode):
           """Common execution logic for both primary and fallback."""
           # ... validation, timeout, retry logic ...
           result = await session.call_tool(name=self.name, arguments=arguments)
           # ... normalize and return result ...
   ```

2. **Keep stdio session management for fallback**
   - Keep existing `get_gitlab_session_for_user()` for fallback
   - Keep existing session cache for stdio fallback
   - Add mode logging to track which MCP is being used

### Phase 4: Tool Registration Updates

**File: `agents/registry.py`**

#### Changes Required:

1. **Update `register_mcp_session()` for HTTP**
   ```python
   async def register_mcp_session(self, session_name: str, mcp_client: Any) -> None:
       """Register tools from HTTP MCP client."""
       if not mcp_client:
           return

       tools_resp = await mcp_client.list_tools()
       # ... rest of registration logic (same as before)
   ```

2. **Update `build_default_registry()`**
   ```python
   if mcp_service.gitlab_http_client:
       await registry.register_mcp_session("gitlab", mcp_service.gitlab_http_client)

   # Fallback tools are automatically available if primary fails
   ```

### Phase 5: Environment Configuration

**File: `.env`**

```bash
# Primary: Official GitLab MCP (OAuth)
GITLAB_URL=https://gitlab.com
GITLAB_CLIENT_ID=<your_oauth_app_id>
GITLAB_CLIENT_SECRET=<your_oauth_secret>
GITLAB_REDIRECT_URI=http://localhost:8000/auth/gitlab/callback

# Fallback: @zereight/mcp-gitlab (PAT) - keep existing
GITLAB_PERSONAL_ACCESS_TOKEN=glpat-...

# Fallback configuration
GITLAB_MCP_FALLBACK_ENABLED=true
GITLAB_MCP_FAILURE_THRESHOLD=5
GITLAB_MCP_TIMEOUT_SECONDS=30
```

### Phase 6: OAuth Flow Implementation

**File: `services/auth_service.py`** (or new file)

```python
"""
GitLab OAuth 2.0 service for MCP server authentication.
Implements the OAuth flow required by the official GitLab MCP server.
"""

async def initiate_gitlab_oauth(user_id: str) -> str:
    """Generate OAuth authorization URL for user."""
    # Redirect user to GitLab's OAuth authorization page
    pass

async def handle_gitlab_callback(code: str, state: str) -> str:
    """Exchange authorization code for access token."""
    # Exchange code for token and store in MongoDB
    pass

async def get_user_gitlab_oauth_token(user_id: str) -> Optional[str]:
    """Retrieve stored OAuth token for user."""
    # Get encrypted token from MongoDB
    pass

async def refresh_oauth_token(user_id: str) -> str:
    """Refresh expired OAuth token."""
    # Implement token refresh if refresh tokens are used
    pass
```

### Phase 7: Circuit Breaker & Health Monitoring

**File: `services/mcp_service.py`** (additions)

```python
async def monitor_circuit_breaker():
    """Background task to test primary recovery when circuit is open."""
    while True:
        await asyncio.sleep(GITLAB_MCP_RETRY_DELAY_SECONDS)

        if circuit_breaker["state"] == "open":
            # Try to close circuit by testing primary
            try:
                await test_primary_mcp()
                circuit_breaker["state"] = "half_open"
                mcp_log("[INFO] Circuit breaker -> half_open, testing primary")
            except Exception:
                pass  # Keep circuit open

async def test_primary_mcp():
    """Test if primary MCP is available."""
    if not gitlab_http_client:
        raise Exception("Primary MCP not initialized")
    await gitlab_http_client.list_tools()
```

### Phase 8: Testing & Validation

#### Test Coverage Needed:

1. **HTTP MCP Connection**
   - Verify HTTP client connects to GitLab MCP endpoint
   - Test tool listing and execution

2. **OAuth Flow**
   - Test authorization URL generation
   - Test callback handling and token exchange
   - Test token retrieval and refresh

3. **Fallback Activation**
   - Simulate primary failure (503, timeout)
   - Verify circuit breaker opens
   - Verify fallback activates automatically

4. **Circuit Recovery**
   - Test half-open state
   - Verify primary recovery detection
   - Verify circuit closes on recovery

5. **Tool Functionality**
   - Test all currently used GitLab tools
   - Verify tool schemas match expected format
   - Test error handling for HTTP failures

6. **Per-User Sessions**
   - Test dynamic OAuth token injection
   - Test PAT fallback for stdio
   - Test user isolation

7. **Health Monitoring**
   - Test `/health` endpoint shows both MCPs
   - Verify metrics tracking (primary vs fallback usage)

## Critical Considerations

### 1. GitLab Edition Requirement

**Current Status**: You have GitLab Duo available during trial period.

**Risk**: The official GitLab MCP server requires GitLab Duo to be enabled (Premium/Ultimate). After trial ends, may lose access.

**Mitigation**:
- Fallback to `@zereight/mcp-gitlab` ensures continued operation
- Add GitLab Duo availability check in `/health` endpoint
- Monitor trial expiration and plan accordingly
- Consider upgrading to Premium/Ultimate before trial ends

### 2. Dual Authentication Complexity

**Risk**: Primary uses OAuth, fallback uses PAT. Different token management flows.

**Mitigation**:
- Keep existing PAT retrieval for `@zereight/mcp-gitlab` fallback
- Implement new OAuth flow for official MCP (primary)
- Store both token types in MongoDB with clear labels
- Graceful degradation if one auth method fails

### 3. Tool Parity

**Risk**: Official server may have different tools than `@zereight/mcp-gitlab`.

**Mitigation**:
- Audit both tool lists before migration
- Map tool names between implementations (if different)
- Use fallback if a tool is missing from primary
- Fallback provides 100% tool coverage

### 4. Fallback Reliability

**Risk**: If `@zereight/mcp-gitlab` is not properly maintained as fallback, system may fail.

**Mitigation**:
- Keep fallback initialized alongside primary
- Regular health checks on both MCP implementations
- Automatic re-initialization if fallback crashes
- Clear logging indicating which MCP is in use

### 5. Breaking Changes During Migration

**Risk**: Migration may break existing functionality during fallback integration.

**Mitigation**:
- Comprehensive testing in development environment first
- Test fallback activation by simulating primary failures
- Document rollback procedure clearly
- Test all critical workflows (MR review, remediation, incidents) with both MCPs

## Files to Modify

| File | Changes | Complexity |
|------|---------|------------|
| `package.json` | Keep `@zereight/mcp-gitlab` (no change) | None |
| `services/mcp_service.py` | Add HTTP client + circuit breaker + fallback logic | High |
| `agents/mcp_wrappers.py` | Update `GitLabMCPTool` for dual-mode with fallback | Medium |
| `agents/registry.py` | Register tools from primary, fallback auto-available | Low |
| `.env` | Add OAuth variables (keep PAT for fallback) | Low |
| `services/auth_service.py` | Add OAuth flow (keep PAT flow for fallback) | Medium |
| `services/user_service.py` | Support both OAuth and PAT retrieval | Low |
| `main.py` | Update health check to show both MCP status | Low |

## Estimated Effort

| Phase | Estimated Time |
|-------|----------------|
| Phase 1: Dependency changes (none - keep fallback) | 0 hours |
| Phase 2: MCP service redesign with fallback | 10-14 hours |
| Phase 3: MCP wrapper updates with fallback logic | 6-8 hours |
| Phase 4: Tool registration updates | 2 hours |
| Phase 5: Environment config (OAuth + PAT) | 1 hour |
| Phase 6: OAuth implementation | 6-8 hours |
| Phase 7: Circuit breaker & health monitoring | 4-6 hours |
| Phase 8: Testing (both primary & fallback) | 10-14 hours |
| **Total** | **39-53 hours** |

**Additional effort for fallback**: +6-8 hours (circuit breaker, dual-mode testing)

## Verification Steps

### After Migration:

1. **Start the application** and verify no import errors
2. **Check `/health` endpoint** shows both GitLab MCP statuses:
   - Primary (official GitLab MCP): connected/unavailable
   - Fallback (@zereight/mcp-gitlab): connected/unavailable
   - Current mode: http/stdio/fallback
   - Circuit breaker state: closed/open/half_open
3. **Test primary MCP** - Execute tools via official GitLab MCP
4. **Test fallback activation** - Simulate primary failure, verify fallback kicks in
5. **Test OAuth flow** - Authenticate a test user via OAuth
6. **Test PAT fallback** - Verify existing PAT authentication still works
7. **Execute GitLab tools** through agent workflows with both MCPs
8. **Test webhook processing** for MR events
9. **Verify per-user sessions** work with both OAuth and PAT
10. **Test circuit breaker** - Trigger failures, verify state transitions
11. **Load test** with multiple concurrent users
12. **Monitor logs** for fallback usage indicators

### Test Commands:

```bash
# Test MCP connection (both primary and fallback)
python -c "import asyncio; from services.mcp_service import boot_mcp_bridge; asyncio.run(boot_mcp_bridge())"

# Test tool listing (from primary)
python -c "import asyncio; from agents.registry import build_default_registry; asyncio.run(build_default_registry())"

# Test OAuth flow
curl -X POST http://localhost:8000/auth/gitlab/authorize

# Test fallback activation
curl -X POST http://localhost:8000/test/trigger-fallback  # Simulate primary failure

# Check health status
curl http://localhost:8000/health | jq .mcp_status

# Test webhook processing
python test_sentry_workflow.py  # Adapt for GitLab MCP
```

## Rollback Plan

Since fallback is built-in, rollback options are:

### Option A: Disable Primary (Keep Fallback Active)

Set environment variable:
```bash
GITLAB_MCP_PRIMARY_ENABLED=false
```

This forces all traffic to use `@zereight/mcp-gitlab` fallback.

### Option B: Code Rollback (If Critical Bug)

1. Revert `services/mcp_service.py` to remove HTTP client and circuit breaker
2. Revert `agents/mcp_wrappers.py` to original `GitLabMCPTool`
3. Keep `@zereight/mcp-gitlab` (never removed)
4. Restart application

### Option C: Graceful Degradation

The fallback system should automatically handle failures. Manual rollback only needed if:
- Fallback also fails
- Performance issues with circuit breaker
- Unexpected behavior in dual-mode

## Next Steps

1. **Verify GitLab Duo access** - Confirm MCP endpoint is accessible at `https://gitlab.com/api/v4/mcp`
2. **Audit tool lists** - Compare official server tools vs `@zereight/mcp-gitlab` tools
3. **Set up OAuth app** - Create GitLab OAuth application for Gatekeeper (or use existing)
4. **Verify fallback available** - Confirm `@zereight/mcp-gitlab@2.1.16` is installed and working
5. **Begin Phase 2** - Implement HTTP client alongside existing stdio client
6. **Implement circuit breaker** - Add automatic fallback logic
7. **Test dual-mode** - Verify both primary and fallback work correctly
8. **Deploy and monitor** - Track which MCP is being used in production

## References

- **Official GitLab MCP Documentation**: https://docs.gitlab.com/user/gitlab_duo/model_context_protocol/mcp_server/
- **DevPost Project**: https://rapid-agent.devpost.com/details/gitlab-resources
- **Current Package**: `@zereight/mcp-gitlab@2.1.16` (kept as fallback)
- **MCP Python SDK**: https://github.com/modelcontextprotocol/python-sdk
