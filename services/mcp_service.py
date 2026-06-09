import os
import asyncio
import subprocess
import platform
from pathlib import Path
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Implementation


# Global process variables for persistent MCP channels
mongo_session = None
gitlab_session = None
nexus_session = None
dynatrace_session = None
fivetran_session = None
mcp_ready = False


# Detect the correct GitNexus command for the platform
root_dir = Path(__file__).parent.parent
local_bin = root_dir / "node_modules" / ".bin"
if platform.system() == "Windows":
    local_gitnexus = local_bin / "gitnexus.cmd"
    GITNEXUS_CMD = str(local_gitnexus) if local_gitnexus.exists() else "gitnexus.cmd"
else:
    local_gitnexus = local_bin / "gitnexus"
    GITNEXUS_CMD = str(local_gitnexus) if local_gitnexus.exists() else "gitnexus"
HAS_LOCAL_GITNEXUS = local_gitnexus.exists()


async def boot_mcp_bridge():
    """Spins up and maintains persistent stdio pipes to MongoDB, GitLab, GitNexus, and Dynatrace MCP servers."""
    global mongo_session, gitlab_session, nexus_session, dynatrace_session, fivetran_session, mcp_ready

    is_windows = platform.system() == "Windows"
    node_cmd = r"C:\Program Files\nodejs\node.exe" if is_windows and Path(r"C:\Program Files\nodejs\node.exe").exists() else "node"
    npx_cmd = "npx.cmd" if is_windows else "npx"

    print(f"[DEBUG] Using node_cmd: {node_cmd}")
    print(f"[DEBUG] Platform: {platform.system()}")

    root_dir = Path(__file__).parent.parent

    local_mongo = root_dir / "node_modules" / "mongodb-mcp-server" / "dist" / "esm" / "index.js"
    if local_mongo.exists():
        mongo_js_path = str(local_mongo.resolve())
        print(f"[OK] Found local MongoDB MCP: {mongo_js_path}")
    else:
        mongo_js_path = r"C:\Users\BCSKOL36\AppData\Roaming\npm\node_modules\mongodb-mcp-server\dist\esm\index.js"
        print(f"[INFO] Local MongoDB MCP not found. Using fallback path: {mongo_js_path}")

    local_gitlab = root_dir / "node_modules" / "@zereight" / "mcp-gitlab" / "build" / "index.js"
    if local_gitlab.exists():
        gitlab_js_path = str(local_gitlab.resolve())
        print(f"[OK] Found local GitLab MCP: {gitlab_js_path}")
    else:
        gitlab_js_path = r"C:\Users\BCSKOL36\AppData\Roaming\npm\node_modules\@zereight\mcp-gitlab\build\index.js"
        print(f"[INFO] Local GitLab MCP not found. Using fallback path: {gitlab_js_path}")

    mongo_connection_string = os.getenv("MDB_MCP_CONNECTION_STRING", "")
    if not mongo_connection_string:
        print("[WARN] MDB_MCP_CONNECTION_STRING not set - MongoDB storage will not work")
    else:
        print(
            f"[OK] MDB_MCP_CONNECTION_STRING found: "
            f"{mongo_connection_string[:20]}...{mongo_connection_string[-10:]}"
        )

    mongo_params = StdioServerParameters(
        command=node_cmd,
        args=[mongo_js_path],
        env={**os.environ},
    )
    gitlab_params = StdioServerParameters(
        command=node_cmd,
        args=[gitlab_js_path],
        env={
            **os.environ,
            "GITLAB_PERSONAL_ACCESS_TOKEN": os.getenv("GITLAB_PERSONAL_ACCESS_TOKEN", ""),
            "GITLAB_URL": "https://gitlab.com",
        },
    )
    if HAS_LOCAL_GITNEXUS:
        nexus_params = StdioServerParameters(
            command=GITNEXUS_CMD,
            args=["mcp"],
            env={**os.environ},
        )
    else:
        nexus_params = StdioServerParameters(
            command=npx_cmd,
            args=["-y", "gitnexus@latest", "mcp"],
            env={**os.environ},
        )
    fivetran_params = StdioServerParameters(
        command=npx_cmd,
        args=["-y", "fivetran-mcp"],
        env={**os.environ},
    )

    print("[*] Igniting MCP Orchestrator Core (MongoDB + GitLab + optional GitNexus + optional Dynatrace)...")
    print("[INFO] This may take 10-30 seconds to initialize all connections...")

    nexus_ok = False
    print("[INFO] Testing GitNexus installation...")
    try:
        test_result = subprocess.run(
            [GITNEXUS_CMD, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if test_result.returncode == 0:
            print(f"[OK] GitNexus found: {test_result.stdout.strip()}")
            nexus_ok = True
        else:
            print(f"[WARN] GitNexus command failed with code {test_result.returncode}")
    except Exception as exc:
        print(f"[WARN] GitNexus test failed: {exc}")

    dt_env = os.getenv("DT_ENVIRONMENT", "")
    dt_token = os.getenv("DT_PLATFORM_TOKEN", "") or os.getenv("DT_API_TOKEN", "")
    dynatrace_configured = bool(dt_env and dt_token)
    if dynatrace_configured:
        print(f"[OK] Dynatrace configured: {dt_env}")
    else:
        print(
            "[WARN] Dynatrace not configured. "
            "(DT_ENVIRONMENT and DT_PLATFORM_TOKEN/DT_API_TOKEN environment variables missing)"
        )

    try:
        async with AsyncExitStack() as stack:
            try:
                mongo_read, mongo_write = await stack.enter_async_context(stdio_client(mongo_params))
                print("[OK] MongoDB stdio client connected")
            except Exception as exc:
                print(f"[ERROR] Failed to connect to MongoDB MCP: {exc}")
                raise

            try:
                gitlab_read, gitlab_write = await stack.enter_async_context(stdio_client(gitlab_params))
                print("[OK] GitLab stdio client connected")
            except Exception as exc:
                print(f"[ERROR] Failed to connect to GitLab MCP: {exc}")
                raise

            nexus_read = nexus_write = None
            if nexus_ok:
                try:
                    nexus_read, nexus_write = await stack.enter_async_context(stdio_client(nexus_params))
                    print("[OK] GitNexus stdio client connected")
                except Exception as exc:
                    print(f"[WARN] Failed to connect to GitNexus MCP: {exc}")
                    nexus_ok = False

            dynatrace_read = dynatrace_write = None
            if dynatrace_configured:
                try:
                    dynatrace_params = StdioServerParameters(
                        command=npx_cmd,
                        args=["-y", "@dynatrace-oss/dynatrace-mcp-server@latest"],
                        env={
                            **os.environ,
                            "DT_ENVIRONMENT": dt_env,
                            "DT_PLATFORM_TOKEN": dt_token,
                        },
                    )
                    dynatrace_read, dynatrace_write = await stack.enter_async_context(stdio_client(dynatrace_params))
                    print("[OK] Dynatrace stdio client connected")
                except Exception as exc:
                    print(f"[WARN] Failed to connect to Dynatrace MCP: {exc}")
                    dynatrace_configured = False

            mongo_sess = await stack.enter_async_context(
                ClientSession(mongo_read, mongo_write, client_info=Implementation(name="gk-db", version="1.0.0"))
            )
            gitlab_sess = await stack.enter_async_context(
                ClientSession(gitlab_read, gitlab_write, client_info=Implementation(name="gk-git", version="1.0.0"))
            )

            nexus_sess = None
            if nexus_read and nexus_write:
                nexus_sess = await stack.enter_async_context(
                    ClientSession(nexus_read, nexus_write, client_info=Implementation(name="gk-nexus", version="1.0.0"))
                )

            dynatrace_sess = None
            if dynatrace_read and dynatrace_write:
                dynatrace_sess = await stack.enter_async_context(
                    ClientSession(
                        dynatrace_read,
                        dynatrace_write,
                        client_info=Implementation(name="gk-dynatrace", version="1.0.0"),
                    )
                )

            print("[INFO] Initializing MongoDB MCP session...")
            await asyncio.wait_for(mongo_sess.initialize(), timeout=10.0)
            print("[OK] MongoDB MCP initialized")

            print("[INFO] Initializing GitLab MCP session...")
            await asyncio.wait_for(gitlab_sess.initialize(), timeout=10.0)
            print("[OK] GitLab MCP initialized")

            mongo_session = mongo_sess
            gitlab_session = gitlab_sess
            mcp_ready = True
            print("[OK] CRITICAL MCP SERVICES READY - Can now process webhooks!")

            try:
                git_tools = await gitlab_sess.list_tools()
                print(f"[OK] GitLab Capabilities: {[t.name for t in git_tools.tools[:2]]} (Total: {len(git_tools.tools)})")
            except Exception as exc:
                print(f"[WARN] GitLab tool listing failed: {exc}")

            if nexus_sess:
                print("[INFO] Initializing GitNexus MCP session (optional)...")
                try:
                    await asyncio.wait_for(nexus_sess.initialize(), timeout=15.0)
                    try:
                        await nexus_sess.call_tool(name="list_repos", arguments={})
                        nexus_session = nexus_sess
                        print("[OK] GitNexus MCP initialized successfully")
                    except Exception:
                        print("[WARN] GitNexus initialized but no indexed repositories found")
                except Exception as exc:
                    print(f"[WARN] GitNexus initialization failed: {exc}")

            if dynatrace_sess:
                print("[INFO] Initializing Dynatrace MCP session (optional)...")
                try:
                    await asyncio.wait_for(dynatrace_sess.initialize(), timeout=15.0)
                    try:
                        dt_tools = await dynatrace_sess.list_tools()
                        dynatrace_session = dynatrace_sess
                        print(f"[OK] Dynatrace MCP initialized successfully: {[t.name for t in dt_tools.tools[:3]]}")
                    except Exception as exc:
                        print(f"[WARN] Dynatrace tool verification failed: {exc}")
                except Exception as exc:
                    print(f"[WARN] Dynatrace initialization failed: {exc}")

            if os.getenv("FIVETRAN_MCP_ENABLED", "false").lower() == "true":
                print("[*] Attempting optional Fivetran MCP initialization...")
                try:
                    fivetran_read, fivetran_write = await stack.enter_async_context(stdio_client(fivetran_params))
                    fivetran_sess = await stack.enter_async_context(
                        ClientSession(
                            fivetran_read,
                            fivetran_write,
                            client_info=Implementation(name="gk-fivetran", version="1.0.0"),
                        )
                    )
                    await asyncio.wait_for(fivetran_sess.initialize(), timeout=10.0)
                    fivetran_session = fivetran_sess
                    print("[OK] Fivetran MCP initialized")
                except Exception as fivetran_err:
                    print(f"[INFO] Fivetran MCP unavailable, using REST fallback: {fivetran_err}")
                    fivetran_session = None

            print("[OK] MCP Bridge fully initialized!")

            try:
                await asyncio.sleep(float("inf"))
            except asyncio.CancelledError:
                print("[INFO] MCP connection task terminated cleanly.")
                raise
    except Exception as exc:
        print(f"[ERROR] MCP Bridge initialization failed: {exc}")
        import traceback

        traceback.print_exc()
        raise
