import os
import asyncio
import time
from pathlib import Path
from contextlib import AsyncExitStack
from typing import Dict, Tuple, Optional, Any
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Implementation
import subprocess
# Global process variables for persistent MCP channels
mongo_session = None
gitlab_session = None
nexus_session = None
dynatrace_session = None
sentry_session = None
mcp_ready = False  # Track when MCP sessions are ready

# Session cache for per-user GitLab MCP sessions
# {user_id: (session, stdio_read, stdio_write, last_used_timestamp, background_task)}
_gitlab_session_cache: Dict[str, Tuple[ClientSession, Any, Any, float, asyncio.Task]] = {}
_cache_lock = asyncio.Lock()


async def boot_mcp_bridge():
    """Spins up and maintains persistent stdio pipes to MongoDB, GitLab, GitNexus, Dynatrace, and Sentry MCP servers"""
    global mongo_session, gitlab_session, nexus_session, dynatrace_session, sentry_session, mcp_ready

    # Detect platform and configure paths dynamically
    is_windows = Path(__file__).parent.name == "Windows"

    # 1. Determine Node and NPX executables
    if is_windows:
        node_cmd = r"C:\Program Files\nodejs\node.exe" if Path(r"C:\Program Files\nodejs\node.exe").exists() else "node"
        npx_cmd = r"C:\Program Files\nodejs\npx.cmd" if Path(r"C:\Program Files\nodejs\npx.cmd").exists() else "npx.cmd"
        GITNEXUS_CMD = r"C:\Users\BCSKOL36\AppData\Roaming\npm\gitnexus.cmd" if Path(r"C:\Users\BCSKOL36\AppData\Roaming\npm\gitnexus.cmd").exists() else "gitnexus"
    else:
        node_cmd = "node"
        npx_cmd = "npx"
        GITNEXUS_CMD = "gitnexus"

    # 2. Determine paths to MongoDB and GitLab MCP servers
    root_dir = Path(__file__).parent.parent

    # MongoDB MCP Server path
    local_mongo = root_dir / "node_modules" / "mongodb-mcp-server" / "dist" / "esm" / "index.js"
    if local_mongo.exists():
        mongo_js_path = str(local_mongo.resolve())
        print(f"[OK] Found local MongoDB MCP: {mongo_js_path}")
    else:
        # Fallback to Windows global path
        mongo_js_path = r"C:\Users\BCSKOL36\AppData\Roaming\npm\node_modules\mongodb-mcp-server\dist\esm\index.js"
        print(f"[INFO] Local MongoDB MCP not found. Using fallback path: {mongo_js_path}")

    # GitLab MCP Server path
    local_gitlab = root_dir / "node_modules" / "@zereight" / "mcp-gitlab" / "build" / "index.js"
    if local_gitlab.exists():
        gitlab_js_path = str(local_gitlab.resolve())
        print(f"[OK] Found local GitLab MCP: {gitlab_js_path}")
    else:
        # Fallback to Windows global path
        gitlab_js_path = r"C:\Users\BCSKOL36\AppData\Roaming\npm\node_modules\@zereight\mcp-gitlab\build\index.js"
        print(f"[INFO] Local GitLab MCP not found. Using fallback path: {gitlab_js_path}")

    # Check MongoDB connection string configuration
    mongo_connection_string = os.getenv("MDB_MCP_CONNECTION_STRING", "")
    if not mongo_connection_string:
        print("[WARN] MDB_MCP_CONNECTION_STRING not set - MongoDB storage will not work")
    else:
        print(f"[OK] MDB_MCP_CONNECTION_STRING found: {mongo_connection_string[:20]}...{mongo_connection_string[-10:]}")

    # Configure server parameters
    mongo_params = StdioServerParameters(
        command=node_cmd,
        args=[mongo_js_path],
        env={**os.environ}
    )

    gitlab_token = os.getenv("GITLAB_PERSONAL_ACCESS_TOKEN", "")
    gitlab_params = StdioServerParameters(
        command=node_cmd,
        args=[gitlab_js_path],
        env={
            **os.environ,
            "GITLAB_PERSONAL_ACCESS_TOKEN": gitlab_token,
            "GITLAB_URL": "https://gitlab.com"
        }
    )

    # Track which connections succeed
    mongo_ok = False
    gitlab_ok = False
    # Test if GitNexus works
    nexus_ok = False
    print("[INFO] Testing GitNexus installation...")
    try:
        test_result = subprocess.run(
            [GITNEXUS_CMD, "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if test_result.returncode == 0:
            print(f"[OK] GitNexus found: {test_result.stdout.strip()}")
            nexus_ok = True
        else:
            print(f"[WARN] GitNexus command failed with code {test_result.returncode}")
    except Exception as e:
        print(f"[WARN] GitNexus test failed: {e}")

    # Check if Dynatrace is configured
    dt_env = os.getenv("DT_ENVIRONMENT", "")
    dt_token = os.getenv("DT_PLATFORM_TOKEN", "") or os.getenv("DT_API_TOKEN", "")
    dynatrace_configured = bool(dt_env and dt_token)
    if dynatrace_configured:
        print(f"[OK] Dynatrace configured: {dt_env}")
    else:
        print("[WARN] Dynatrace not configured. (DT_ENVIRONMENT and DT_PLATFORM_TOKEN/DT_API_TOKEN environment variables missing)")

    # Check if Sentry is configured
    sentry_org_slug = os.getenv("SENTRY_ORGANIZATION_SLUG", "")
    sentry_token = os.getenv("SENTRY_AUTH_TOKEN", "")
    sentry_configured = bool(sentry_org_slug and sentry_token)
    if sentry_configured:
        print(f"[OK] Sentry configured: {sentry_org_slug}")
    else:
        print("[WARN] Sentry not configured. (SENTRY_ORGANIZATION_SLUG and SENTRY_AUTH_TOKEN environment variables missing)")

    print("[INFO] Igniting MCP Orchestrator Core (MongoDB + GitLab + optional GitNexus + optional Dynatrace + optional Sentry)...")
    print("[INFO] This may take 10-30 seconds to initialize all connections...")


    try:
        async with AsyncExitStack() as stack:
            # 1. Connect MongoDB stdio client (critical)
            try:
                m_read, m_write = await stack.enter_async_context(stdio_client(mongo_params))
                print("[OK] MongoDB stdio client connected")
                mongo_ok = True
            except Exception as e:
                print(f"[ERROR] Failed to connect to MongoDB MCP: {e}")
                raise

            # 2. Connect GitLab stdio client (critical)
            try:
                g_read, g_write = await stack.enter_async_context(stdio_client(gitlab_params))
                print("[OK] GitLab stdio client connected")
                gitlab_ok = True
            except Exception as e:
                print(f"[ERROR] Failed to connect to GitLab MCP: {e}")
                raise
            # 3. Connect GitNexus stdio client (optional)
            n_read, n_write = None, None
            if nexus_ok:
                try:
                    nexus_params = StdioServerParameters(
                        command=npx_cmd,
                        args=["-y", "gitnexus@latest", "mcp"],
                        env={**os.environ}
                    )
                    n_read, n_write = await stack.enter_async_context(stdio_client(nexus_params))
                    print("[OK] GitNexus stdio client connected")
                except Exception as e:
                    print(f"[WARN] Failed to connect to GitNexus MCP: {e}")
                    nexus_ok = False

            # 4. Connect Dynatrace stdio client (optional)
            d_read, d_write = None, None
            if dynatrace_configured:
                try:
                    dt_params = StdioServerParameters(
                        command=npx_cmd,
                        args=["-y", "@dynatrace-oss/dynatrace-mcp-server@latest"],
                        env={
                            **os.environ,
                            "DT_ENVIRONMENT": dt_env,
                            "DT_PLATFORM_TOKEN": dt_token
                        }
                    )
                    d_read, d_write = await stack.enter_async_context(stdio_client(dt_params))
                    print("[OK] Dynatrace stdio client connected")
                except Exception as e:
                    print(f"[WARN] Failed to connect to Dynatrace MCP: {e}")
                    dynatrace_configured = False

            # 5. Connect Sentry stdio client (optional)
            s_read, s_write = None, None
            if sentry_configured:
                try:
                    sentry_params = StdioServerParameters(
                        command=npx_cmd,
                        args=["-y", "@sentryio/mcp-server@latest"],
                        env={
                            **os.environ,
                            "SENTRY_AUTH_TOKEN": sentry_token,
                            "SENTRY_ORGANIZATION_SLUG": sentry_org_slug
                        }
                    )
                    s_read, s_write = await stack.enter_async_context(stdio_client(sentry_params))
                    print("[OK] Sentry stdio client connected")
                except Exception as e:
                    print(f"[WARN] Failed to connect to Sentry MCP: {e}")
                    sentry_configured = False

            # 5. Initialize client sessions
            m_sess = await stack.enter_async_context(ClientSession(m_read, m_write, client_info=Implementation(name="gk-db", version="1.0.0")))
            g_sess = await stack.enter_async_context(ClientSession(g_read, g_write, client_info=Implementation(name="gk-git", version="1.0.0")))
            
            n_sess = None
            if n_read and n_write:
                n_sess = await stack.enter_async_context(ClientSession(n_read, n_write, client_info=Implementation(name="gk-nexus", version="1.0.0")))

            d_sess = None
            if d_read and d_write:
                d_sess = await stack.enter_async_context(ClientSession(d_read, d_write, client_info=Implementation(name="gk-dynatrace", version="1.0.0")))

            s_sess = None
            if s_read and s_write:
                s_sess = await stack.enter_async_context(ClientSession(s_read, s_write, client_info=Implementation(name="gk-sentry", version="1.0.0")))

            # 6. Initialize protocol handshakes
            print("[INFO] Initializing MongoDB MCP session...")
            await asyncio.wait_for(m_sess.initialize(), timeout=10.0)
            print("[OK] MongoDB MCP initialized")

            print("[INFO] Initializing GitLab MCP session...")
            await asyncio.wait_for(g_sess.initialize(), timeout=10.0)
            print("[OK] GitLab MCP initialized")

            # Set critical sessions as ready
            mongo_session = m_sess
            gitlab_session = g_sess
            mcp_ready = True
            print("[OK] CRITICAL MCP SERVICES READY - Can now process webhooks!")

            # Verify active connectivity by listing tools
            try:
                git_tools = await g_sess.list_tools()
                print(f"[OK] GitLab Capabilities: {[t.name for t in git_tools.tools[:2]]} (Total: {len(git_tools.tools)})")
            except Exception as e:
                print(f"[WARN] GitLab tool listing failed: {e}")

            # Initialize GitNexus (optional)
            if n_sess:
                print("[INFO] Initializing GitNexus MCP session (optional)...")
                try:
                    await asyncio.wait_for(n_sess.initialize(), timeout=15.0)
                    try:
                        await n_sess.call_tool(name="list_repos", arguments={})
                        nexus_session = n_sess
                        print("[OK] GitNexus MCP initialized successfully")
                    except Exception:
                        print("[WARN] GitNexus initialized but no indexed repositories found")
                except Exception as e:
                    print(f"[WARN] GitNexus initialization failed: {e}")

            # Initialize Dynatrace (optional)
            if d_sess:
                print("[INFO] Initializing Dynatrace MCP session (optional)...")
                try:
                    await asyncio.wait_for(d_sess.initialize(), timeout=15.0)
                    try:
                        dt_tools = await d_sess.list_tools()
                        dynatrace_session = d_sess
                        print(f"[OK] Dynatrace MCP initialized successfully: {[t.name for t in dt_tools.tools[:3]]}")
                    except Exception as e:
                        print(f"[WARN] Dynatrace tool verification failed: {e}")
                except Exception as e:
                    print(f"[WARN] Dynatrace initialization failed: {e}")

            # Initialize Sentry (optional)
            if s_sess:
                print("[INFO] Initializing Sentry MCP session (optional)...")
                try:
                    await asyncio.wait_for(s_sess.initialize(), timeout=15.0)
                    try:
                        sentry_tools = await s_sess.list_tools()
                        sentry_session = s_sess
                        print(f"[OK] Sentry MCP initialized successfully: {[t.name for t in sentry_tools.tools[:3]]}")
                    except Exception as e:
                        print(f"[WARN] Sentry tool verification failed: {e}")
                except Exception as e:
                    print(f"[WARN] Sentry initialization failed: {e}")

            print("[OK] MCP Bridge fully initialized!")

            # Keep the background process streams alive indefinitely
            try:
                await asyncio.sleep(float('inf'))
            except asyncio.CancelledError:
                print("[INFO] MCP connection task terminated cleanly.")
                raise

    except Exception as e:
        print(f"[ERROR] MCP Bridge initialization failed: {e}")
        import traceback
        traceback.print_exc()

        # Set at least gitlab_session if possible for basic functionality
        if mongo_ok and gitlab_ok:
            print("[INFO] MongoDB and GitLab connected - proceeding")
            mcp_ready = True
            print("[OK] MCP Bridge is READY (MongoDB + GitLab)")
        else:
            print("[ERROR] Critical MCP connections failed - webhooks will not be processed")
            mcp_ready = False
        raise


# ============================================================================
# Dynamic GitLab Session Management (Token Refresh Pattern)
# ============================================================================

async def get_gitlab_session_for_user(user_id: str, project_id: Optional[str] = None) -> Optional[ClientSession]:
    """
    Get or create a GitLab MCP session for a specific user with their token.
    Implements Token Refresh Pattern with caching.

    Args:
        user_id: User ID to get session for
        project_id: Optional project ID for project-specific tokens

    Returns:
        ClientSession for GitLab MCP or None if unavailable
    """
    # Check cache first (thread-safe)
    async with _cache_lock:
        if user_id in _gitlab_session_cache:
            sess, r, w, last_used, task = _gitlab_session_cache[user_id]
            _gitlab_session_cache[user_id] = (sess, r, w, time.time(), task)  # Update last used
            print(f"[INFO] Using cached GitLab session for user {user_id}")
            return sess

    # Get user's GitLab token from MongoDB
    from services.user_service import get_user_gitlab_token
    token = await get_user_gitlab_token(user_id, project_id or "")

    if not token:
        # Fallback to env token (for system operations)
        token = os.getenv("GITLAB_PERSONAL_ACCESS_TOKEN", "")
        if not token:
            print(f"[WARN] No GitLab token available for user {user_id}")
            return None
        print(f"[INFO] Using fallback env token for user {user_id}")
    else:
        print(f"[INFO] Retrieved project-specific token from MongoDB for user {user_id}")

    # Create new session with user's token
    return await _create_gitlab_session_with_token(user_id, token)


async def _create_gitlab_session_with_token(user_id: str, token: str) -> Optional[ClientSession]:
    """
    Create a new GitLab MCP session with a specific token and cache it.
    Creates a background task to keep the stdio client alive.

    Args:
        user_id: User ID for cache key
        token: GitLab PAT token

    Returns:
        ClientSession or None if creation fails
    """
    # Detect platform and configure paths
    is_windows = Path(__file__).parent.name == "Windows"

    if is_windows:
        node_cmd = r"C:\Program Files\nodejs\node.exe" if Path(r"C:\Program Files\nodejs\node.exe").exists() else "node"
    else:
        node_cmd = "node"

    # Find GitLab MCP server path
    root_dir = Path(__file__).parent.parent
    local_gitlab = root_dir / "node_modules" / "@zereight" / "mcp-gitlab" / "build" / "index.js"
    if local_gitlab.exists():
        gitlab_js_path = str(local_gitlab.resolve())
    else:
        gitlab_js_path = r"C:\Users\BCSKOL36\AppData\Roaming\npm\node_modules\@zereight\mcp-gitlab\build\index.js"

    # Validate that the MCP server file exists
    if not Path(gitlab_js_path).exists():
        print(f"[ERROR] GitLab MCP server not found at: {gitlab_js_path}")
        return None

    # Validate that Node.js exists
    if not Path(node_cmd).exists() and node_cmd != "node":
        print(f"[ERROR] Node.js not found at: {node_cmd}")
        return None

    print(f"[INFO] Creating new GitLab MCP session for user {user_id}...")
    print(f"[DEBUG] Using Node.js: {node_cmd}")
    print(f"[DEBUG] Using MCP server: {gitlab_js_path}")

    # Create stdio server parameters with user's token
    gitlab_params = StdioServerParameters(
        command=node_cmd,
        args=[gitlab_js_path],
        env={
            **os.environ,
            "GITLAB_PERSONAL_ACCESS_TOKEN": token,
            "GITLAB_URL": "https://gitlab.com"
        }
    )

    # Create an event to signal when the session is ready
    ready_event = asyncio.Event()
    init_result = {"session": None, "error": None}

    async def keep_session_alive():
        """Background task to keep the stdio client alive."""
        try:
            print(f"[DEBUG] User {user_id}: Starting stdio_client...")
            async with stdio_client(gitlab_params) as (read, write):
                print(f"[DEBUG] User {user_id}: stdio_client connected, creating ClientSession...")

                # Small delay to let subprocess fully start
                await asyncio.sleep(0.5)

                # Create session
                sess = ClientSession(read, write, client_info=Implementation(name="gk-git-dynamic", version="1.0.0"))

                # Initialize with timeout
                try:
                    print(f"[DEBUG] User {user_id}: Calling sess.initialize()...")
                    await asyncio.wait_for(sess.initialize(), timeout=30.0)
                    print(f"[DEBUG] User {user_id}: sess.initialize() completed")

                    # Verify by listing tools
                    tools = await sess.list_tools()
                    print(f"[OK] GitLab session created for user {user_id}. Tools: {[t.name for t in tools.tools[:2]]}")

                    # Signal that session is ready
                    init_result["session"] = sess
                    ready_event.set()

                    # Cache the session (with this background task)
                    current_task = asyncio.current_task()
                    async with _cache_lock:
                        _gitlab_session_cache[user_id] = (sess, read, write, time.time(), current_task)

                    # Keep the stdio client alive indefinitely
                    print(f"[DEBUG] User {user_id}: Session cached, keeping alive...")
                    await asyncio.sleep(float('inf'))

                except asyncio.TimeoutError:
                    print(f"[ERROR] User {user_id}: Session initialization timed out after 30 seconds")
                    init_result["error"] = asyncio.TimeoutError("Initialization timed out")
                    ready_event.set()
                    raise
                except asyncio.CancelledError:
                    print(f"[INFO] GitLab session for user {user_id} cancelled during initialization")
                    init_result["error"] = asyncio.CancelledError("Cancelled during initialization")
                    ready_event.set()
                    raise
                except Exception as e:
                    print(f"[ERROR] User {user_id}: Failed to initialize session: {type(e).__name__}: {e}")
                    import traceback
                    traceback.print_exc()
                    init_result["error"] = e
                    ready_event.set()
                    raise

        except asyncio.CancelledError:
            print(f"[INFO] GitLab session task for user {user_id} cancelled")
            if not ready_event.is_set():
                ready_event.set()
        except Exception as e:
            print(f"[ERROR] GitLab session task for user {user_id} failed: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            if not ready_event.is_set():
                init_result["error"] = e
                ready_event.set()

    # Start the background task
    task = asyncio.create_task(keep_session_alive())

    # Wait for the session to be ready or timeout
    try:
        await asyncio.wait_for(ready_event.wait(), timeout=20.0)

        if init_result["error"]:
            raise init_result["error"]

        session = init_result["session"]
        if not session:
            raise RuntimeError("Session initialization failed")

        return session

    except asyncio.TimeoutError:
        print(f"[ERROR] Timeout waiting for GitLab session for user {user_id}")
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return None
    except Exception as e:
        print(f"[ERROR] Failed to create GitLab session for user {user_id}: {e}")
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return None


async def cleanup_gitlab_session(user_id: str) -> bool:
    """
    Close and remove a user's GitLab session from cache.
    Cancels the background task keeping the session alive.

    Args:
        user_id: User ID whose session to cleanup

    Returns:
        True if session was found and cleaned up
    """
    global _gitlab_session_cache

    async with _cache_lock:
        if user_id not in _gitlab_session_cache:
            return False

        sess, read, write, last_used, task = _gitlab_session_cache.pop(user_id)

    try:
        # Cancel the background task
        if task and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        print(f"[INFO] Cleaned up GitLab session for user {user_id}")
        return True
    except Exception as e:
        print(f"[WARN] Error cleaning up session for user {user_id}: {e}")
        return False


async def cleanup_idle_sessions(max_idle_seconds: int = 3600) -> int:
    """
    Background task to cleanup idle sessions.

    Args:
        max_idle_seconds: Maximum idle time before cleanup (default: 1 hour)

    Returns:
        Number of sessions cleaned up
    """
    global _gitlab_session_cache

    current_time = time.time()
    idle_users = []

    async with _cache_lock:
        for user_id, (sess, read, write, last_used, task) in _gitlab_session_cache.items():
            idle_time = current_time - last_used
            if idle_time > max_idle_seconds:
                idle_users.append((user_id, task))

    cleaned_count = 0
    for user_id, task in idle_users:
        try:
            # Cancel the background task
            if task and not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=5.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

            async with _cache_lock:
                _gitlab_session_cache.pop(user_id, None)

            cleaned_count += 1
            print(f"[INFO] Cleaned up idle session for user {user_id}")
        except Exception as e:
            print(f"[WARN] Error cleaning up idle session for user {user_id}: {e}")

    if cleaned_count > 0:
        print(f"[INFO] Cleaned up {cleaned_count} idle GitLab sessions")

    return cleaned_count


def get_session_cache_size() -> int:
    """Get the current size of the GitLab session cache."""
    return len(_gitlab_session_cache)

