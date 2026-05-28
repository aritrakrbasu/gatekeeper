import os
import asyncio
import subprocess
import platform
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Implementation

# Global process variables for persistent MCP channels
mongo_session = None
gitlab_session = None
nexus_session = None
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
    """Spins up and maintains persistent stdio pipes to MongoDB, GitLab, and GitNexus MCP servers"""
    global mongo_session, gitlab_session, nexus_session, mcp_ready

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
        print(f"[+] Found local MongoDB MCP: {mongo_js_path}")
    else:
        # Fallback to Windows global path
        mongo_js_path = r"C:\Users\BCSKOL36\AppData\Roaming\npm\node_modules\mongodb-mcp-server\dist\esm\index.js"
        print(f"[ℹ️] Local MongoDB MCP not found. Using fallback path: {mongo_js_path}")

        # Verify fallback path exists
        if not Path(mongo_js_path).exists():
            print(f"[❌] MongoDB MCP not found at fallback path: {mongo_js_path}")
            print(f"[ℹ️] Install with: npm install -g mongodb-mcp-server")
            print(f"[ℹ️] Or install locally: npm install mongodb-mcp-server")

    # GitLab MCP Server path
    local_gitlab = root_dir / "node_modules" / "@zereight" / "mcp-gitlab" / "build" / "index.js"
    if local_gitlab.exists():
        gitlab_js_path = str(local_gitlab.resolve())
        print(f"[+] Found local GitLab MCP: {gitlab_js_path}")
    else:
        # Fallback to Windows global path
        gitlab_js_path = r"C:\Users\BCSKOL36\AppData\Roaming\npm\node_modules\@zereight\mcp-gitlab\build\index.js"
        print(f"[ℹ️] Local GitLab MCP not found. Using fallback path: {gitlab_js_path}")

        # Verify fallback path exists
        if not Path(gitlab_js_path).exists():
            print(f"[❌] GitLab MCP not found at fallback path: {gitlab_js_path}")
            print(f"[ℹ️] Install with: npm install -g @zereight/mcp-gitlab")
            print(f"[ℹ️] Or install locally: npm install @zereight/mcp-gitlab")

    # Check MongoDB connection string configuration
    mongo_connection_string = os.getenv("MDB_MCP_CONNECTION_STRING", "")
    if not mongo_connection_string:
        print("[⚠️] MDB_MCP_CONNECTION_STRING not set - MongoDB storage will not work")
        print("[ℹ️] Set MDB_MCP_CONNECTION_STRING in .env file to enable MongoDB storage")
    else:
        print(f"[✅] MDB_MCP_CONNECTION_STRING found: {mongo_connection_string[:20]}...{mongo_connection_string[-10:]}")

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

    # 3. GitNexus MCP Server Parameters (Code Intelligence & Impact Analysis)
    nexus_params = StdioServerParameters(
        command=npx_cmd,
        args=["-y", "gitnexus@latest", "mcp"],
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
    try:
        test_result = subprocess.run(
            [GITNEXUS_CMD, "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if test_result.returncode == 0:
            print(f"[✅] GitNexus found: {test_result.stdout.strip()}")
        else:
            print("[⚠️] GitNexus command failed - skipping GitNexus MCP")
            print(f"[ℹ️] Error: {test_result.stderr}")
            nexus_ok = False
    except FileNotFoundError:
        print("[⚠️] GitNexus not found - skipping GitNexus MCP")
        print("[ℹ️] Install with: npm install -g gitnexus")
        nexus_ok = False
    except Exception as e:
        print(f"[⚠️] GitNexus test failed: {e}")
        print("[ℹ️] Skipping GitNexus MCP - using built-in analysis")
        nexus_ok = False

    # Skip GitNexus if the test failed
    if not nexus_ok:
        print("[⚠️] GitNexus MCP will be skipped - using built-in analysis")

    try:
        async with stdio_client(mongo_params) as (m_read, m_write):
            print("[✅] MongoDB stdio client connected")
            mongo_ok = True
            async with stdio_client(gitlab_params) as (g_read, g_write):
                print("[✅] GitLab stdio client connected")
                gitlab_ok = True

                # Only try GitNexus if the test passed
                if nexus_ok:
                    try:
                        async with stdio_client(nexus_params) as (n_read, n_write):
                            print("[✅] GitNexus stdio client connected")
                            async with ClientSession(m_read, m_write, client_info=Implementation(name="gk-db", version="1.0.0")) as m_sess, \
                                       ClientSession(g_read, g_write, client_info=Implementation(name="gk-git", version="1.0.0")) as g_sess, \
                                       ClientSession(n_read, n_write, client_info=Implementation(name="gk-nexus", version="1.0.0")) as n_sess:

                                print("[*] Initializing MCP protocol handshakes...")

                                # Initialize MongoDB and GitLab first (critical), GitNexus can be optional
                                try:
                                    print("[*] Initializing MongoDB MCP session...")
                                    await asyncio.wait_for(m_sess.initialize(), timeout=10.0)
                                    print("[✅] MongoDB MCP initialized")

                                    # Verify MongoDB connection by listing tools
                                    try:
                                        mongo_tools = await m_sess.list_tools()
                                        print(f"[✅] MongoDB tools available: {[t.name for t in mongo_tools.tools[:3]]}")
                                    except Exception as tool_err:
                                        print(f"[⚠️] Could not list MongoDB tools: {tool_err}")

                                except asyncio.TimeoutError:
                                    print("[⚠️] MongoDB MCP initialization timed out")
                                    print("[ℹ️] This may indicate MDB_MCP_CONNECTION_STRING is not set or invalid")
                                    raise
                                except Exception as mongo_init_err:
                                    print(f"[❌] MongoDB MCP initialization failed: {mongo_init_err}")
                                    print(f"[ℹ️] Error type: {type(mongo_init_err).__name__}")
                                    import traceback
                                    traceback.print_exc()
                                    raise

                                try:
                                    print("[*] Initializing GitLab MCP session...")
                                    await asyncio.wait_for(g_sess.initialize(), timeout=10.0)
                                    print("[✅] GitLab MCP initialized")
                                except asyncio.TimeoutError:
                                    print("[⚠️] GitLab MCP initialization timed out")
                                    raise

                                # Set sessions as ready for critical services
                                mongo_session = m_sess
                                gitlab_session = g_sess
                                mcp_ready = True
                                print("[✅] CRITICAL MCP SERVICES READY - Can now process webhooks!")

                                # Verify active connectivity by listing available tools
                                try:
                                    git_tools = await g_sess.list_tools()
                                    print(f"[+] GitLab Capabilities: {[t.name for t in git_tools.tools[:2]]} (Total: {len(git_tools.tools)})")
                                except Exception as e:
                                    print(f"[⚠️] GitLab tool listing failed: {e}")

                                # Initialize GitNexus (optional - may fail if no repos indexed)
                                print("[*] Initializing GitNexus MCP session (optional)...")
                                print("[ℹ️] Note: GitNexus requires indexed repositories")
                                try:
                                    await asyncio.wait_for(n_sess.initialize(), timeout=15.0)
                                    print("[✅] GitNexus MCP initialized successfully")
                                    nexus_session = n_sess

                                    # Verify GitNexus has indexed repositories
                                    try:
                                        nexus_tools = await n_sess.list_tools()
                                        print(f"[+] GitNexus Capabilities: {[t.name for t in nexus_tools.tools[:5]]} (Total: {len(nexus_tools.tools)})")

                                        # Try to list repos to verify it's working
                                        try:
                                            list_repos_result = await n_sess.call_tool(name="list_repos", arguments={})
                                            print(f"[✅] GitNexus has indexed repositories available")
                                        except Exception as repo_err:
                                            print(f"[⚠️] GitNexus initialized but no indexed repositories found")
                                            print(f"[ℹ️] Run 'python setup_repos.py index' to index repositories")
                                            nexus_session = None

                                    except Exception as e:
                                        print(f"[⚠️] GitNexus tool listing failed: {e}")
                                        nexus_session = None

                                except asyncio.TimeoutError:
                                    print("[⚠️] GitNexus MCP initialization timed out")
                                    print("[ℹ️] This is normal if GitNexus has no indexed repositories yet")
                                    nexus_session = None
                                except Exception as e:
                                    print(f"[⚠️] GitNexus initialization failed: {type(e).__name__}: {str(e)[:100]}")
                                    print("[ℹ️] This is expected if no repositories are indexed yet")
                                    print("[ℹ️] Run: python setup_repos.py index")
                                    nexus_session = None

                                print("[+] MCP Bridge fully initialized!")
                                if nexus_session:
                                    print("[✅] Full analysis available (MongoDB + GitLab + GitNexus)")
                                else:
                                    print("[ℹ️] Standard analysis available (MongoDB + GitLab + Built-in Impact)")

                                # Keep the background process streams alive indefinitely
                                try:
                                    await asyncio.sleep(float('inf'))
                                except asyncio.CancelledError:
                                    print("[*] MCP connection task terminated cleanly.")
                                    raise

                    except Exception as nexus_err:
                        print(f"[⚠️] GitNexus connection failed: {nexus_err}")
                        print("[ℹ️] Continuing with MongoDB and GitLab only...")
                        print("[DEBUG] Setting nexus_ok=False to trigger fallback path")
                        nexus_ok = False  # Set to False so fallback path will execute

                # If GitNexus is not available, continue with just MongoDB and GitLab
                if not nexus_ok:
                    print("[DEBUG] Entering fallback path (MongoDB + GitLab only)")
                    async with ClientSession(m_read, m_write, client_info=Implementation(name="gk-db", version="1.0.0")) as m_sess, \
                               ClientSession(g_read, g_write, client_info=Implementation(name="gk-git", version="1.0.0")) as g_sess:

                        print("[*] Initializing MCP protocol handshakes (MongoDB + GitLab)...")

                        # Initialize MongoDB and GitLab
                        try:
                            print("[*] Initializing MongoDB MCP session...")
                            await asyncio.wait_for(m_sess.initialize(), timeout=10.0)
                            print("[✅] MongoDB MCP initialized")

                            # Verify MongoDB connection by listing tools
                            try:
                                mongo_tools = await m_sess.list_tools()
                                print(f"[✅] MongoDB tools available: {[t.name for t in mongo_tools.tools[:3]]}")
                            except Exception as tool_err:
                                print(f"[⚠️] Could not list MongoDB tools: {tool_err}")

                        except asyncio.TimeoutError:
                            print("[⚠️] MongoDB MCP initialization timed out")
                            print("[ℹ️] This may indicate MDB_MCP_CONNECTION_STRING is not set or invalid")
                            raise
                        except Exception as mongo_init_err:
                            print(f"[❌] MongoDB MCP initialization failed: {mongo_init_err}")
                            print(f"[ℹ️] Error type: {type(mongo_init_err).__name__}")
                            import traceback
                            traceback.print_exc()
                            raise

                        try:
                            print("[*] Initializing GitLab MCP session...")
                            await asyncio.wait_for(g_sess.initialize(), timeout=10.0)
                            print("[✅] GitLab MCP initialized")
                        except asyncio.TimeoutError:
                            print("[⚠️] GitLab MCP initialization timed out")
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

                        # Keep alive
                        try:
                            await asyncio.sleep(float('inf'))
                        except asyncio.CancelledError:
                            print("[*] MCP connection task terminated cleanly.")
                            raise
    except Exception as e:
        print(f"[x] MCP Bridge initialization failed: {e}")
        print(f"[x] Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()

        # Set at least gitlab_session if possible for basic functionality
        if mongo_ok and gitlab_ok:
            print("[ℹ️] MongoDB and GitLab connected - proceeding without GitNexus")
            mcp_ready = True
            print("[✅] MCP Bridge is READY (MongoDB + GitLab only)")
        else:
            print("[❌] Critical MCP connections failed - webhooks will not be processed")
            mcp_ready = False
        raise
