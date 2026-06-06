import os
import sys
import asyncio
import subprocess
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Implementation


def mcp_log(message: str) -> None:
    """Write MCP startup lines to stderr so they appear under uvicorn immediately."""
    sys.stderr.write(f"{message}\n")
    sys.stderr.flush()


# Global process variables for persistent MCP channels
mongo_session = None
gitlab_session = None
nexus_session = None
dynatrace_session = None
mcp_ready = False  # Track when MCP sessions are ready
_critical_ready_event = asyncio.Event()


def mark_unready(reason: str = "") -> None:
    """Reset readiness when the MCP bridge task stops or crashes."""
    global mongo_session, gitlab_session, nexus_session, dynatrace_session, mcp_ready
    mcp_ready = False
    mongo_session = None
    gitlab_session = None
    nexus_session = None
    dynatrace_session = None
    _critical_ready_event.clear()
    if reason:
        mcp_log(f"[WARN] MCP bridge offline: {reason}")


async def wait_for_critical_ready(timeout: float = 120.0) -> bool:
    """Block until MongoDB + GitLab MCP sessions are ready."""
    try:
        await asyncio.wait_for(_critical_ready_event.wait(), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        return False


async def boot_mcp_bridge():
    """Spins up and maintains persistent stdio pipes to MongoDB, GitLab, GitNexus, and Dynatrace MCP servers"""
    global mongo_session, gitlab_session, nexus_session, dynatrace_session, mcp_ready

    mark_unready()
    mcp_log("[*] MCP Bridge boot starting...")

    is_windows = sys.platform == "win32"
    npm_global = Path(os.environ.get("APPDATA", "")) / "npm"

    # 1. Determine Node and NPX executables
    if is_windows:
        node_cmd = (
            r"C:\Program Files\nodejs\node.exe"
            if Path(r"C:\Program Files\nodejs\node.exe").exists()
            else "node"
        )
        npx_cmd = (
            r"C:\Program Files\nodejs\npx.cmd"
            if Path(r"C:\Program Files\nodejs\npx.cmd").exists()
            else "npx.cmd"
        )
        gitnexus_cmd = npm_global / "gitnexus.cmd"
        GITNEXUS_CMD = str(gitnexus_cmd) if gitnexus_cmd.exists() else "gitnexus"
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
        mcp_log(f"[OK] Found local MongoDB MCP: {mongo_js_path}")
    else:
        mongo_js_path = str(
            npm_global / "node_modules" / "mongodb-mcp-server" / "dist" / "esm" / "index.js"
        )
        mcp_log(f"[INFO] Local MongoDB MCP not found. Using fallback path: {mongo_js_path}")

    # GitLab MCP Server path
    local_gitlab = root_dir / "node_modules" / "@zereight" / "mcp-gitlab" / "build" / "index.js"
    if local_gitlab.exists():
        gitlab_js_path = str(local_gitlab.resolve())
        mcp_log(f"[OK] Found local GitLab MCP: {gitlab_js_path}")
    else:
        gitlab_js_path = str(
            npm_global
            / "node_modules"
            / "@zereight"
            / "mcp-gitlab"
            / "build"
            / "index.js"
        )
        mcp_log(f"[INFO] Local GitLab MCP not found. Using fallback path: {gitlab_js_path}")

    # Check MongoDB connection string configuration
    mongo_connection_string = os.getenv("MDB_MCP_CONNECTION_STRING", "")
    if not mongo_connection_string:
        mcp_log("[WARN] MDB_MCP_CONNECTION_STRING not set - MongoDB storage will not work")
    else:
        mcp_log(
            f"[OK] MDB_MCP_CONNECTION_STRING found: {mongo_connection_string[:20]}...{mongo_connection_string[-10:]}"
        )

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
    mcp_log("[INFO] Testing GitNexus installation...")
    try:
        test_result = subprocess.run(
            [GITNEXUS_CMD, "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if test_result.returncode == 0:
            mcp_log(f"[OK] GitNexus found: {test_result.stdout.strip()}")
            nexus_ok = True
        else:
            mcp_log(f"[WARN] GitNexus command failed with code {test_result.returncode}")
    except Exception as e:
        mcp_log(f"[WARN] GitNexus test failed: {e}")

    # Check if Dynatrace is configured
    dt_env = os.getenv("DT_ENVIRONMENT", "")
    dt_token = os.getenv("DT_PLATFORM_TOKEN", "") or os.getenv("DT_API_TOKEN", "")
    dynatrace_configured = bool(dt_env and dt_token)
    if dynatrace_configured:
        mcp_log(f"[OK] Dynatrace configured: {dt_env}")
    else:
        mcp_log(
            "[WARN] Dynatrace not configured. (DT_ENVIRONMENT and DT_PLATFORM_TOKEN/DT_API_TOKEN environment variables missing)"
        )

    mcp_log(
        "[INFO] Igniting MCP Orchestrator Core (MongoDB + GitLab + optional GitNexus + optional Dynatrace)..."
    )
    mcp_log("[INFO] This may take 10-30 seconds to initialize all connections...")


    try:
        async with AsyncExitStack() as stack:
            # 1. Connect MongoDB stdio client (critical)
            try:
                m_read, m_write = await stack.enter_async_context(stdio_client(mongo_params))
                mcp_log("[OK] MongoDB stdio client connected")
                mongo_ok = True
            except Exception as e:
                mcp_log(f"[ERROR] Failed to connect to MongoDB MCP: {e}")
                raise

            # 2. Connect GitLab stdio client (critical)
            try:
                g_read, g_write = await stack.enter_async_context(stdio_client(gitlab_params))
                mcp_log("[OK] GitLab stdio client connected")
                gitlab_ok = True
            except Exception as e:
                mcp_log(f"[ERROR] Failed to connect to GitLab MCP: {e}")
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
                    mcp_log("[OK] GitNexus stdio client connected")
                except Exception as e:
                    mcp_log(f"[WARN] Failed to connect to GitNexus MCP: {e}")
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
                    mcp_log("[OK] Dynatrace stdio client connected")
                except Exception as e:
                    mcp_log(f"[WARN] Failed to connect to Dynatrace MCP: {e}")
                    dynatrace_configured = False

            # 5. Initialize client sessions
            m_sess = await stack.enter_async_context(ClientSession(m_read, m_write, client_info=Implementation(name="gk-db", version="1.0.0")))
            g_sess = await stack.enter_async_context(ClientSession(g_read, g_write, client_info=Implementation(name="gk-git", version="1.0.0")))
            
            n_sess = None
            if n_read and n_write:
                n_sess = await stack.enter_async_context(ClientSession(n_read, n_write, client_info=Implementation(name="gk-nexus", version="1.0.0")))

            d_sess = None
            if d_read and d_write:
                d_sess = await stack.enter_async_context(ClientSession(d_read, d_write, client_info=Implementation(name="gk-dynatrace", version="1.0.0")))

            # 6. Initialize protocol handshakes
            mcp_log("[INFO] Initializing MongoDB MCP session...")
            await asyncio.wait_for(m_sess.initialize(), timeout=10.0)
            mcp_log("[OK] MongoDB MCP initialized")

            mcp_log("[INFO] Initializing GitLab MCP session...")
            await asyncio.wait_for(g_sess.initialize(), timeout=10.0)
            mcp_log("[OK] GitLab MCP initialized")

            # Set critical sessions as ready
            mongo_session = m_sess
            gitlab_session = g_sess
            mcp_ready = True
            _critical_ready_event.set()
            mcp_log("[OK] CRITICAL MCP SERVICES READY - Can now process webhooks!")

            # Verify active connectivity by listing tools
            try:
                git_tools = await g_sess.list_tools()
                mcp_log(f"[OK] GitLab Capabilities: {[t.name for t in git_tools.tools[:2]]} (Total: {len(git_tools.tools)})")
            except Exception as e:
                mcp_log(f"[WARN] GitLab tool listing failed: {e}")

            # Initialize GitNexus (optional)
            if n_sess:
                mcp_log("[INFO] Initializing GitNexus MCP session (optional)...")
                try:
                    await asyncio.wait_for(n_sess.initialize(), timeout=15.0)
                    try:
                        await n_sess.call_tool(name="list_repos", arguments={})
                        nexus_session = n_sess
                        mcp_log("[OK] GitNexus MCP initialized successfully")
                    except Exception:
                        mcp_log("[WARN] GitNexus initialized but no indexed repositories found")
                except Exception as e:
                    mcp_log(f"[WARN] GitNexus initialization failed: {e}")

            # Initialize Dynatrace (optional)
            if d_sess:
                mcp_log("[INFO] Initializing Dynatrace MCP session (optional)...")
                try:
                    await asyncio.wait_for(d_sess.initialize(), timeout=15.0)
                    try:
                        dt_tools = await d_sess.list_tools()
                        dynatrace_session = d_sess
                        mcp_log(f"[OK] Dynatrace MCP initialized successfully: {[t.name for t in dt_tools.tools[:3]]}")
                    except Exception as e:
                        mcp_log(f"[WARN] Dynatrace tool verification failed: {e}")
                except Exception as e:
                    mcp_log(f"[WARN] Dynatrace initialization failed: {e}")

            mcp_log("[OK] MCP Bridge fully initialized!")

            # Keep the background process streams alive indefinitely
            try:
                await asyncio.sleep(float('inf'))
            except asyncio.CancelledError:
                mcp_log("[INFO] MCP connection task terminated cleanly.")
                mark_unready("task cancelled (server reload/shutdown)")
                raise

    except Exception as e:
        mcp_log(f"[ERROR] MCP Bridge initialization failed: {e}")
        import traceback
        traceback.print_exc()

        # Set at least gitlab_session if possible for basic functionality
        if mongo_ok and gitlab_ok:
            mcp_log("[INFO] MongoDB and GitLab connected - proceeding")
            mcp_ready = True
            _critical_ready_event.set()
            mcp_log("[OK] MCP Bridge is READY (MongoDB + GitLab)")
        else:
            mark_unready("critical MCP connections failed")
            mcp_log("[ERROR] Critical MCP connections failed - webhooks will not be processed")
        raise

