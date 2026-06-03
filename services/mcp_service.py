import os
import asyncio
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Implementation

# Global process variables for persistent MCP channels
mongo_session = None
gitlab_session = None
mcp_ready = False  # Track when MCP sessions are ready


async def boot_mcp_bridge():
    """Spins up and maintains persistent stdio pipes to MongoDB and GitLab MCP servers"""
    global mongo_session, gitlab_session, mcp_ready

    # Detect platform and configure paths dynamically
    is_windows = Path(__file__).parent.name == "Windows"

    # 1. Determine Node and NPX executables
    if is_windows:
        node_cmd = r"C:\Program Files\nodejs\node.exe" if Path(r"C:\Program Files\nodejs\node.exe").exists() else "node"
    else:
        node_cmd = "node"

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

        # Verify fallback path exists
        if not Path(mongo_js_path).exists():
            print(f"[ERROR] MongoDB MCP not found at fallback path: {mongo_js_path}")
            print(f"[INFO] Install with: npm install -g mongodb-mcp-server")
            print(f"[INFO] Or install locally: npm install mongodb-mcp-server")

    # GitLab MCP Server path
    local_gitlab = root_dir / "node_modules" / "@zereight" / "mcp-gitlab" / "build" / "index.js"
    if local_gitlab.exists():
        gitlab_js_path = str(local_gitlab.resolve())
        print(f"[OK] Found local GitLab MCP: {gitlab_js_path}")
    else:
        # Fallback to Windows global path
        gitlab_js_path = r"C:\Users\BCSKOL36\AppData\Roaming\npm\node_modules\@zereight\mcp-gitlab\build\index.js"
        print(f"[INFO] Local GitLab MCP not found. Using fallback path: {gitlab_js_path}")

        # Verify fallback path exists
        if not Path(gitlab_js_path).exists():
            print(f"[ERROR] GitLab MCP not found at fallback path: {gitlab_js_path}")
            print(f"[INFO] Install with: npm install -g @zereight/mcp-gitlab")
            print(f"[INFO] Or install locally: npm install @zereight/mcp-gitlab")

    # Check MongoDB connection string configuration
    mongo_connection_string = os.getenv("MDB_MCP_CONNECTION_STRING", "")
    if not mongo_connection_string:
        print("[WARN] MDB_MCP_CONNECTION_STRING not set - MongoDB storage will not work")
        print("[INFO] Set MDB_MCP_CONNECTION_STRING in .env file to enable MongoDB storage")
    else:
        print(f"[OK] MDB_MCP_CONNECTION_STRING found: {mongo_connection_string[:20]}...{mongo_connection_string[-10:]}")

    # 1. MongoDB Server Parameters (Direct Binary Mapping)
    mongo_params = StdioServerParameters(
        command=node_cmd,
        args=[mongo_js_path],
        env={**os.environ}
    )

    # 2. GitLab MCP Server Parameters (Direct Binary Mapping supporting PAT auth)
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

    print("[INFO] Igniting MCP Orchestrator Core (MongoDB + GitLab)...")
    print("[INFO] This may take 10-30 seconds to initialize all connections...")

    # Track which connections succeed
    mongo_ok = False
    gitlab_ok = False

    try:
        async with stdio_client(mongo_params) as (m_read, m_write):
            print("[OK] MongoDB stdio client connected")
            mongo_ok = True
            async with stdio_client(gitlab_params) as (g_read, g_write):
                print("[OK] GitLab stdio client connected")
                gitlab_ok = True

                async with ClientSession(m_read, m_write, client_info=Implementation(name="gk-db", version="1.0.0")) as m_sess, \
                           ClientSession(g_read, g_write, client_info=Implementation(name="gk-git", version="1.0.0")) as g_sess:

                    print("[INFO] Initializing MCP protocol handshakes...")

                    # Initialize MongoDB and GitLab (critical services)
                    try:
                        print("[INFO] Initializing MongoDB MCP session...")
                        await asyncio.wait_for(m_sess.initialize(), timeout=10.0)
                        print("[OK] MongoDB MCP initialized")

                        # Verify MongoDB connection by listing tools
                        try:
                            mongo_tools = await m_sess.list_tools()
                            print(f"[OK] MongoDB tools available: {[t.name for t in mongo_tools.tools[:3]]}")
                        except Exception as tool_err:
                            print(f"[WARN] Could not list MongoDB tools: {tool_err}")

                    except asyncio.TimeoutError:
                        print("[WARN] MongoDB MCP initialization timed out")
                        print("[INFO] This may indicate MDB_MCP_CONNECTION_STRING is not set or invalid")
                        raise
                    except Exception as mongo_init_err:
                        print(f"[ERROR] MongoDB MCP initialization failed: {mongo_init_err}")
                        print(f"[INFO] Error type: {type(mongo_init_err).__name__}")
                        import traceback
                        traceback.print_exc()
                        raise

                    try:
                        print("[INFO] Initializing GitLab MCP session...")
                        await asyncio.wait_for(g_sess.initialize(), timeout=10.0)
                        print("[OK] GitLab MCP initialized")
                    except asyncio.TimeoutError:
                        print("[WARN] GitLab MCP initialization timed out")
                        raise

                    # Set sessions as ready
                    mongo_session = m_sess
                    gitlab_session = g_sess
                    mcp_ready = True
                    print("[OK] CRITICAL MCP SERVICES READY - Can now process webhooks!")

                    # Verify active connectivity by listing available tools
                    try:
                        git_tools = await g_sess.list_tools()
                        print(f"[OK] GitLab Capabilities: {[t.name for t in git_tools.tools[:2]]} (Total: {len(git_tools.tools)})")
                    except Exception as e:
                        print(f"[WARN] GitLab tool listing failed: {e}")

                    print("[OK] MCP Bridge fully initialized!")
                    print("[INFO] Standard analysis available (MongoDB + GitLab + Built-in Impact)")

                    # Keep the background process streams alive indefinitely
                    try:
                        await asyncio.sleep(float('inf'))
                    except asyncio.CancelledError:
                        print("[INFO] MCP connection task terminated cleanly.")
                        raise

    except Exception as e:
        print(f"[ERROR] MCP Bridge initialization failed: {e}")
        print(f"[ERROR] Error type: {type(e).__name__}")
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
