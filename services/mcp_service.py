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
mcp_ready = False  # Track when MCP sessions are ready

# Detect the correct GitNexus command for the platform
root_dir = Path(__file__).parent.parent
local_bin = root_dir / "node_modules" / ".bin"
if platform.system() == "Windows":
    local_gitnexus = local_bin / "gitnexus.cmd"
    GITNEXUS_CMD = str(local_gitnexus) if local_gitnexus.exists() else "gitnexus.cmd"
else:
    local_gitnexus = local_bin / "gitnexus"
    GITNEXUS_CMD = str(local_gitnexus) if local_gitnexus.exists() else "gitnexus"


async def boot_mcp_bridge():
    """Spins up and maintains persistent stdio pipes to MongoDB, GitLab, GitNexus, and Dynatrace MCP servers"""
    global mongo_session, gitlab_session, nexus_session, dynatrace_session, fivetran_session, mcp_ready

    # Detect platform and configure paths dynamically
    is_windows = platform.system() == "Windows"

    # 1. Determine Node and NPX executables
    if is_windows:
        node_cmd = r"C:\Program Files\nodejs\node.exe" if Path(r"C:\Program Files\nodejs\node.exe").exists() else "node"
        npx_cmd = "npx.cmd"
    else:
        node_cmd = "node"
        npx_cmd = "npx"

    print(f"[DEBUG] Using node_cmd: {node_cmd}")
    print(f"[DEBUG] Platform: {platform.system()}")

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

    # 3. GitNexus MCP Server Parameters (Code Intelligence & Impact Analysis)
    nexus_params = StdioServerParameters(
        command=npx_cmd,
        args=["-y", "gitnexus@latest", "mcp"],
        env={**os.environ}
    )
    fivetran_params = StdioServerParameters(
        command=npx_cmd,
        args=["-y", "fivetran-mcp"],
        env={**os.environ}
    )

    print("[*] Igniting Triple MCP Orchestrator Core (MongoDB + GitLab + GitNexus)...")
    print("[*] This may take 10-30 seconds to initialize all connections...")

    # Track which connections succeed
    mongo_ok = False
    gitlab_ok = False
    nexus_ok = True  # Start optimistic, set to False if test fails

    # Test if GitNexus works before starting MCP
    print("[*] Testing GitNexus installation...")
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

    print("[INFO] Igniting MCP Orchestrator Core (MongoDB + GitLab + optional GitNexus + optional Dynatrace)...")
    print("[INFO] This may take 10-30 seconds to initialize all connections...")

    try:
        async with AsyncExitStack() as stack:
            # 1. Connect MongoDB stdio client (critical)
            try:
                m_read, m_write = await stack.enter_async_context(stdio_client(mongo_params))
                print("[OK] MongoDB stdio client connected")
            except Exception as e:
                print(f"[ERROR] Failed to connect to MongoDB MCP: {e}")
                raise

            # 2. Connect GitLab stdio client (critical)
            try:
                g_read, g_write = await stack.enter_async_context(stdio_client(gitlab_params))
                print("[OK] GitLab stdio client connected")
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

            print("[OK] MCP Bridge fully initialized!")

                                if os.getenv("FIVETRAN_MCP_ENABLED", "false").lower() == "true":
                                    print("[*] Attempting optional Fivetran MCP initialization...")
                                    try:
                                        async with stdio_client(fivetran_params) as (f_read, f_write):
                                            async with ClientSession(
                                                f_read,
                                                f_write,
                                                client_info=Implementation(name="gk-fivetran", version="1.0.0")
                                            ) as f_sess:
                                                await asyncio.wait_for(f_sess.initialize(), timeout=10.0)
                                                fivetran_session = f_sess
                                                print("[✅] Fivetran MCP initialized")
                                                await asyncio.sleep(float('inf'))
                                    except Exception as fivetran_err:
                                        print(f"[ℹ️] Fivetran MCP unavailable, using REST fallback: {fivetran_err}")
                                        fivetran_session = None

            # Keep the background process streams alive indefinitely
            try:
                await asyncio.sleep(float('inf'))
            except asyncio.CancelledError:
                print("[INFO] MCP connection task terminated cleanly.")
                raise

                        # Set sessions as ready
                        mongo_session = m_sess
                        gitlab_session = g_sess
                        mcp_ready = True
                        print("[✅] CRITICAL MCP SERVICES READY - Can now process webhooks!")

                        # Verify GitLab tools
                        try:
                            git_tools = await g_sess.list_tools()
                            print(f"[+] GitLab Capabilities: {[t.name for t in git_tools.tools[:2]]} (Total: {len(git_tools.tools)})")
                        except Exception as e:
                            print(f"[⚠️] GitLab tool listing failed: {e}")

                        print("[+] MCP Bridge fully initialized!")
                        print("[ℹ️] Standard analysis available (MongoDB + GitLab + Built-in Impact)")

                        if os.getenv("FIVETRAN_MCP_ENABLED", "false").lower() == "true":
                            print("[*] Attempting optional Fivetran MCP initialization...")
                            try:
                                async with stdio_client(fivetran_params) as (f_read, f_write):
                                    async with ClientSession(
                                        f_read,
                                        f_write,
                                        client_info=Implementation(name="gk-fivetran", version="1.0.0")
                                    ) as f_sess:
                                        await asyncio.wait_for(f_sess.initialize(), timeout=10.0)
                                        fivetran_session = f_sess
                                        print("[✅] Fivetran MCP initialized")
                                        await asyncio.sleep(float('inf'))
                            except Exception as fivetran_err:
                                print(f"[ℹ️] Fivetran MCP unavailable, using REST fallback: {fivetran_err}")
                                fivetran_session = None

                        # Keep alive
                        try:
                            await asyncio.sleep(float('inf'))
                        except asyncio.CancelledError:
                            print("[*] MCP connection task terminated cleanly.")
                            raise
    except Exception as e:
        print(f"[ERROR] MCP Bridge initialization failed: {e}")
        import traceback
        traceback.print_exc()
        raise

