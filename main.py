import os
import asyncio
import json
import time
import subprocess
import platform
from pathlib import Path
from fastapi import FastAPI, Request, Header, HTTPException
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Implementation
from dotenv import load_dotenv

# Google Gemini Client
from google import genai
from google.genai import types

# Gatekeeper Modules
from atomic_patches import (
    AtomicPatchParser,
    AtomicPatchManager,
    create_patch_summary,
    extract_hunks_from_gitlab_diff
)
from impact_analysis import (
    GitImpactAnalyzer,
    ImpactLevel,
    run_pre_review_analysis,
    run_post_review_validation,
    ImpactReport
)
from repo_manager import get_repo_manager

# Detect the correct GitNexus command for the platform
root_dir = Path(__file__).parent
local_bin = root_dir / "node_modules" / ".bin"
if platform.system() == "Windows":
    local_gitnexus = local_bin / "gitnexus.cmd"
    GITNEXUS_CMD = str(local_gitnexus) if local_gitnexus.exists() else "gitnexus.cmd"
else:
    local_gitnexus = local_bin / "gitnexus"
    GITNEXUS_CMD = str(local_gitnexus) if local_gitnexus.exists() else "gitnexus"

load_dotenv()

app = FastAPI(title="The Gatekeeper Gemini Orchestrator")

# Initialize the official Google Gen AI Client
# Automatically extracts GEMINI_API_KEY from environment variables
ai_client = genai.Client()

# Global process variables for persistent MCP channels
mongo_session = None
gitlab_session = None
nexus_session = None
mcp_ready = False  # Track when MCP sessions are ready

# Load prompts from prompts directory
PROMPTS_DIR = Path(__file__).parent / "prompts"

def load_prompt(prompt_name: str) -> str:
    """Load a prompt from the prompts directory."""
    prompt_path = PROMPTS_DIR / f"{prompt_name}.md"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    else:
        print(f"[⚠️] Prompt file not found: {prompt_path}, using fallback")
        return "You are a senior code reviewer. Analyze the provided code changes for security, quality, and performance issues."

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

    # 2. Determine paths to MongoDB and GitLab MCP servers
    root_dir = Path(__file__).parent
    
    # MongoDB MCP Server path
    local_mongo = root_dir / "node_modules" / "mongodb-mcp-server" / "dist" / "esm" / "index.js"
    if local_mongo.exists():
        mongo_js_path = str(local_mongo.resolve())
        print(f"[+] Found local MongoDB MCP: {mongo_js_path}")
    else:
        # Fallback to Windows global path
        mongo_js_path = r"C:\Users\BCSKOL36\AppData\Roaming\npm\node_modules\mongodb-mcp-server\dist\esm\index.js"
        print(f"[ℹ️] Local MongoDB MCP not found. Using fallback path: {mongo_js_path}")

    # GitLab MCP Server path
    local_gitlab = root_dir / "node_modules" / "@zereight" / "mcp-gitlab" / "build" / "index.js"
    if local_gitlab.exists():
        gitlab_js_path = str(local_gitlab.resolve())
        print(f"[+] Found local GitLab MCP: {gitlab_js_path}")
    else:
        # Fallback to Windows global path
        gitlab_js_path = r"C:\Users\BCSKOL36\AppData\Roaming\npm\node_modules\@zereight\mcp-gitlab\build\index.js"
        print(f"[ℹ️] Local GitLab MCP not found. Using fallback path: {gitlab_js_path}")

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
                                except asyncio.TimeoutError:
                                    print("[⚠️] MongoDB MCP initialization timed out")
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

                # If GitNexus is not available, continue with just MongoDB and GitLab
                if not nexus_ok:
                    async with ClientSession(m_read, m_write, client_info=Implementation(name="gk-db", version="1.0.0")) as m_sess, \
                               ClientSession(g_read, g_write, client_info=Implementation(name="gk-git", version="1.0.0")) as g_sess:

                        print("[*] Initializing MCP protocol handshakes (MongoDB + GitLab)...")

                        # Initialize MongoDB and GitLab
                        try:
                            print("[*] Initializing MongoDB MCP session...")
                            await asyncio.wait_for(m_sess.initialize(), timeout=10.0)
                            print("[✅] MongoDB MCP initialized")
                        except asyncio.TimeoutError:
                            print("[⚠️] MongoDB MCP initialization timed out")
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

@app.on_event("startup")
async def startup_event():
    # Defer process execution into a separate background event loop
    print("[*] Starting Gatekeeper service...")
    print("[*] MCP Bridge initialization starting in background...")

    # Check if GitNexus is installed
    try:
        result = subprocess.run(
            ["gitnexus", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print(f"[✅] GitNexus found: {result.stdout.strip()}")
            print("[ℹ️] To enable GitNexus analysis, run: python setup_repos.py index")
        else:
            print("[ℹ️] GitNexus not found - using built-in impact analysis")
            print("[ℹ️] Install GitNexus: npm install -g gitnexus")
    except FileNotFoundError:
        print("[ℹ️] GitNexus not installed - using built-in impact analysis")
        print("[ℹ️] Install GitNexus for enhanced analysis: npm install -g gitnexus")
    except Exception as e:
        print(f"[ℹ️] Could not check GitNexus status: {e}")

    asyncio.create_task(boot_mcp_bridge())


@app.get("/health")
async def health_check():
    """Health check endpoint to verify MCP bridge status."""
    return {
        "status": "healthy",
        "mcp_ready": mcp_ready,
        "mongo_connected": mongo_session is not None,
        "gitlab_connected": gitlab_session is not None,
        "nexus_connected": nexus_session is not None
    }

@app.post("/webhooks/gitlab")
async def gitlab_webhook(request: Request, x_gitlab_event: str = Header(None)):
    global mongo_session, gitlab_session, nexus_session, mcp_ready

    # Check if MCP sessions are ready
    if not mcp_ready or not gitlab_session:
        print("[⚠️] MCP sessions not ready yet - cannot process webhook")
        print("[ℹ️] Please wait a few seconds for the MCP bridge to initialize")
        return {"status": "mcp_not_ready", "message": "MCP sessions still initializing. Please retry in a few seconds."}

    if not x_gitlab_event:
        raise HTTPException(status_code=400, detail="Missing X-GitLab-Event header")

    payload = await request.json()

    if x_gitlab_event == "Merge Request Hook":
        object_attrs = payload.get("object_attributes", {})
        state = object_attrs.get("state")

        if state == "opened":
            mr_title = object_attrs.get("title")
            source_branch = object_attrs.get("source_branch")
            project_id = payload.get("project", {}).get("id")
            mr_iid = object_attrs.get("iid")

            # Get commit SHA for status updates - try multiple possible locations
            # GitLab webhook structure for merge requests
            commit_sha = (
                object_attrs.get("last_commit", {}).get("id") or
                object_attrs.get("sha") or
                object_attrs.get("merge_request_sha") or
                None
            )

            print(f"[+] Webhook caught MR !{mr_iid} on Project {project_id}")
            print(f"[+] Commit SHA: {commit_sha}")
            print(f"[+] Starting Gatekeeper analysis pipeline...")

            if not commit_sha:
                print("[⚠️] Warning: No commit SHA found in webhook!")
                print(f"[DEBUG] object_attrs keys: {list(object_attrs.keys())}")
                print(f"[DEBUG] last_commit: {object_attrs.get('last_commit')}")

                # Fallback: Try to get the MR details from GitLab MCP to find the commit SHA
                if gitlab_session:
                    try:
                        print("[*] Fetching MR details from GitLab to get commit SHA...")
                        mr_details = await gitlab_session.call_tool(
                            name="get_merge_request",
                            arguments={
                                "project_id": str(project_id),
                                "merge_request_iid": int(mr_iid)
                            }
                        )
                        # The response should contain the merge request details with SHA
                        print(f"[DEBUG] MR details response type: {type(mr_details)}")
                        if hasattr(mr_details, 'content'):
                            print(f"[DEBUG] MR details content preview: {str(mr_details.content)[:300]}...")
                    except Exception as e:
                        print(f"[x] Failed to fetch MR details: {e}")

            # 🔒 Skip audit for Gatekeeper auto-generated branches to prevent infinite loops
            if source_branch.startswith("gatekeeper/"):
                print(f"[⏭️] Skipping audit for auto-generated branch: {source_branch}")
                return {"status": "skipped_auto_branch"}

            # 1. Store Request Signature in MongoDB Cluster via MCP
            if mongo_session:
                try:
                    await mongo_session.call_tool(
                        name="insert-many",
                        arguments={
                            "database": "gatekeeper_dev",
                            "collection": "intercepted_mrs",
                            "documents": [{"title": mr_title, "project_id": project_id, "mr_iid": mr_iid, "status": "gemini_auditing"}]
                        }
                    )
                    print("[+] Metadata logged to local MongoDB cluster.")
                except Exception as e:
                    print(f"[x] DB Log failed: {e}")
            else:
                print("[⚠️] MongoDB session not available - skipping DB log")

            # 2. Prepare Repository for GitNexus (Option 2 → Option 1)
            print("[*] ===== PREPARING REPOSITORY FOR ANALYSIS =====")
            repo_manager = get_repo_manager()
            repo_local_path = None

            # Debug: Check if token is available
            gitlab_token = os.getenv("GITLAB_PERSONAL_ACCESS_TOKEN")
            if gitlab_token:
                print(f"[✅] GitLab token found (length: {len(gitlab_token)})")
            else:
                print("[⚠️] GitLab token NOT found in environment!")

            # Try to get project URL from GitLab
            gitlab_url = None
            try:
                project_result = await gitlab_session.call_tool(
                    name="get_project",
                    arguments={"project_id": str(project_id)}
                )
                if hasattr(project_result, 'content') and project_result.content:
                    project_data = json.loads(project_result.content[0].text)
                    gitlab_url = project_data.get("http_url_to_repo")
            except Exception as e:
                print(f"[⚠️] Could not fetch project URL: {e}")

            # Ensure repository is ready (Option 2: Pre-indexed → Option 1: Auto-index)
            if gitlab_url:
                print(f"[*] Ensuring repository {project_id} is ready...")
                print("[ℹ️] Checking for pre-indexed repository (Option 2)...")

                try:
                    repo_local_path = await repo_manager.ensure_repository_ready(
                        project_id=str(project_id),
                        gitlab_url=gitlab_url,
                        private_token=gitlab_token,
                        gitlab_session=gitlab_session
                    )

                    if repo_local_path:
                        print(f"[✅] Repository ready at: {repo_local_path}")
                    else:
                        print("[⚠️] Repository preparation failed - using fallback analysis")
                except Exception as repo_err:
                    print(f"[⚠️] Repository preparation error: {repo_err}")
                    print("[ℹ️] Impact analysis will use built-in AST-based analysis")
            else:
                print("[⚠️] No repository URL available - skipping GitNexus integration")

            # 3. Extract Comprehensive Diffs via GitLab MCP and Process using Gemini
            print("[*] ===== STARTING GATEKEEPER ANALYSIS PIPELINE =====")
            print("[*] Step 1: Posting loading indicator to MR...")
            if gitlab_session:
                loading_note_id = None
                try:
                    # 🔄 Post a loading comment (will be updated with results)
                    print("[*] Posting loading indicator to MR...")
                    loading_note = await gitlab_session.call_tool(
                        name="create_merge_request_note",
                        arguments={
                            "project_id": str(project_id),
                            "merge_request_iid": int(mr_iid),
                            "body": """### 🔄 Gatekeeper Review In Progress

**The Gatekeeper** is analyzing your code changes for security vulnerabilities, code quality issues, and performance improvements.

This may take 30-60 seconds depending on the size of the changes.

---
*⏳ Status: Analyzing...*"""
                        }
                    )
                    # Extract note ID from the response
                    # The response is: CallToolResult(content=[TextContent(type='text', text='{JSON string}')])
                    if hasattr(loading_note, 'content') and loading_note.content:
                        # Get the text from the first TextContent item
                        text_content = loading_note.content[0].text if hasattr(loading_note.content[0], 'text') else str(loading_note.content[0])
                        # Parse the JSON to get the note ID
                        try:
                            note_data = json.loads(text_content)
                            loading_note_id = note_data.get("id")
                            if loading_note_id:
                                print(f"[+] Loading indicator posted! Note ID: {loading_note_id}")
                            else:
                                print("[+] Loading indicator posted! (No ID in response)")
                        except json.JSONDecodeError:
                            print("[+] Loading indicator posted! (Could not parse JSON)")
                    else:
                        print("[+] Loading indicator posted!")

                    print("[*] Step 2: Fetching comprehensive MR diff text via GitLab MCP...")

                    # Using list_merge_request_diffs to pull actual raw line changes
                    changes = await gitlab_session.call_tool(
                        name="list_merge_request_diffs",
                        arguments={
                            "project_id": str(project_id),
                            "merge_request_iid": int(mr_iid)
                        }
                    )

                    # Extract actual diff text from MCP response
                    # GitLab MCP returns JSON array of diff objects
                    raw_diff_content = ""
                    if hasattr(changes, 'content') and changes.content:
                        for item in changes.content:
                            if hasattr(item, 'text'):
                                try:
                                    # Try to parse as JSON array of diff objects
                                    diff_data = json.loads(item.text)
                                    if isinstance(diff_data, list):
                                        # Build unified diff format from GitLab diff objects
                                        for diff_obj in diff_data:
                                            if isinstance(diff_obj, dict):
                                                # Add diff header
                                                old_path = diff_obj.get('old_path', diff_obj.get('old_path', ''))
                                                new_path = diff_obj.get('new_path', diff_obj.get('new_path', ''))
                                                diff_text = diff_obj.get('diff', '')

                                                if old_path and new_path:
                                                    raw_diff_content += f"diff --git a/{old_path} b/{new_path}\n"
                                                    raw_diff_content += diff_text + "\n"
                                        print(f"[DEBUG] Parsed {len(diff_data)} diff objects from GitLab MCP")
                                    else:
                                        # Not JSON, use as-is
                                        raw_diff_content += item.text
                                except json.JSONDecodeError:
                                    # Not JSON, use as-is
                                    raw_diff_content += item.text

                    # Fallback: if still empty, try converting to string
                    if not raw_diff_content:
                        raw_diff_content = str(changes.content)

                    print(f"[✅] Step 2 complete: Raw code diffs retrieved ({len(raw_diff_content)} chars)")

                    # Debug: Show first 500 chars of diff for debugging
                    if raw_diff_content:
                        print(f"[DEBUG] Diff preview: {raw_diff_content[:500]}")
                    else:
                        print("[⚠️] WARNING: Diff content is empty!")

                    # --- 🎯 PRE-REVIEW IMPACT ANALYSIS ---
                    print("[*] Step 3: Running pre-review impact analysis to identify affected code...")
                    impact_report = None
                    impact_context = ""

                    try:
                        # Extract changed files from the diff
                        print("[DEBUG] Starting AtomicPatchParser...")
                        print(f"[DEBUG] Diff content length: {len(raw_diff_content)} chars")
                        print(f"[DEBUG] Diff line count: {len(raw_diff_content.split(chr(10)))} lines")
                        print(f"[DEBUG] First 200 chars of diff: {repr(raw_diff_content[:200])}")

                        # Run parser in a thread with timeout to prevent blocking
                        def parse_diff():
                            parser = AtomicPatchParser()
                            return parser.parse_unified_diff(raw_diff_content)

                        print("[DEBUG] Calling parse_unified_diff (with 10s timeout)...")
                        atomic_patches = await asyncio.wait_for(
                            asyncio.to_thread(parse_diff),
                            timeout=10.0
                        )
                        print(f"[DEBUG] Parser returned {len(atomic_patches)} patches")

                        changed_files = list(set(
                            hunk.file_path for patch in atomic_patches for hunk in patch.hunks
                        ))

                        print(f"[ℹ️] Identified {len(changed_files)} changed files for impact analysis")

                        # Run impact analysis
                        impact_report, impact_context = await run_pre_review_analysis(
                            project_id=str(project_id),
                            mr_iid=int(mr_iid),
                            source_branch=source_branch,
                            target_branch="main",  # Could be configurable
                            changed_files=changed_files,
                            gitlab_session=gitlab_session,
                            nexus_session=nexus_session
                        )

                        print(f"[✅] Step 3 complete: Impact analysis found {len(impact_report.findings)} findings")

                        # Post impact analysis as a comment for visibility
                        if impact_report.findings:
                            impact_summary = impact_report.to_markdown()
                            await gitlab_session.call_tool(
                                name="create_merge_request_note",
                                arguments={
                                    "project_id": str(project_id),
                                    "merge_request_iid": int(mr_iid),
                                    "body": f"""### 🎯 Pre-Review Impact Analysis

{impact_summary}

*This analysis helps identify potential ripple effects from the proposed changes.*"""
                                }
                            )
                            print("[+] Impact analysis posted to MR")

                    except asyncio.TimeoutError:
                        print("[⏱️] Parser timeout after 10s - using fallback file extraction")
                        # Fallback: extract files using simple regex
                        import re
                        changed_files = re.findall(r'diff --git a/(.+?) b/', raw_diff_content)
                        print(f"[ℹ️] Fallback extracted {len(changed_files)} files: {changed_files}")
                        impact_context = ""
                    except Exception as impact_err:
                        print(f"[⚠️] Impact analysis failed (continuing anyway): {impact_err}")
                        impact_context = ""

                    # --- 🧠 THE GEMINI COGNITIVE CORE ENGINE ---
                    print("[*] Step 4: Shipping code diff to Gemini Pro Core for automated security review...")
                    print("[ℹ️] This may take 30-60 seconds depending on diff size...")

                    # Load comprehensive Senior PR Reviewer prompt
                    system_instruction = load_prompt("senior_pr_reviewer")

                    # Include impact context in the review prompt
                    review_prompt = f"""Review this raw pull request diff change stream:

{raw_diff_content}

{impact_context}
"""

                    response = await asyncio.to_thread(
                        ai_client.models.generate_content,
                        model='gemini-3.5-flash',
                        contents=review_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.1
                        )
                    )

                    audit_report = response.text
                    print(f"[✅] Step 4 complete: Gemini analysis compiled ({len(audit_report)} chars)")

                    # --- 🔍 POST-REVIEW VALIDATION ---
                    print("[*] Running post-review validation to catch issues outside changed code...")
                    validation_findings = []

                    if impact_report:
                        try:
                            # Parse audit findings from the report
                            review_findings = [{"description": audit_report}]  # Simplified

                            validation_findings = await run_post_review_validation(
                                pre_review_report=impact_report,
                                ai_review_findings=review_findings,
                                gitlab_session=gitlab_session,
                                nexus_session=nexus_session
                            )

                            if validation_findings:
                                print(f"[!] Post-review validation found {len(validation_findings)} additional concerns")

                                # Add validation findings to the report
                                validation_section = "\n\n### 🔍 Post-Review Validation Findings\n\n"
                                validation_section += "The following potential impacts were identified outside the directly changed code:\n\n"

                                for finding in validation_findings[:10]:  # Limit to 10
                                    emoji = {
                                        ImpactLevel.CRITICAL: "🔴",
                                        ImpactLevel.HIGH: "🟠",
                                        ImpactLevel.MEDIUM: "🟡"
                                    }.get(finding.level, "ℹ️")

                                    validation_section += f"- {emoji} **{finding.file_path}:{finding.line_number}**: {finding.description}\n"

                                audit_report += validation_section

                        except Exception as validation_err:
                            print(f"[⚠️] Post-review validation failed: {validation_err}")

                    # 3. Update the loading comment with the full report
                    print("[*] Updating review with findings...")
                    final_report = f"""### 🛡️ The Gatekeeper Security Audit

{audit_report}

---
*✅ Review completed at {time.strftime('%Y-%m-%d %H:%M:%S UTC')}*"""

                    # Try to update the existing note, otherwise create a new one
                    if loading_note_id:
                        try:
                            await gitlab_session.call_tool(
                                name="update_merge_request_note",
                                arguments={
                                    "project_id": str(project_id),
                                    "merge_request_iid": int(mr_iid),
                                    "note_id": loading_note_id,
                                    "body": final_report
                                }
                            )
                            print("[+] Review report updated in place!")
                        except Exception as update_err:
                            print(f"[⚠️] Could not update note (ID: {loading_note_id}): {update_err}")
                            print("[*] Creating new comment instead...")
                            await gitlab_session.call_tool(
                                name="create_merge_request_note",
                                arguments={
                                    "project_id": str(project_id),
                                    "merge_request_iid": int(mr_iid),
                                    "body": final_report
                                }
                            )
                            print("[+] Review report published as new comment!")
                    else:
                        await gitlab_session.call_tool(
                            name="create_merge_request_note",
                            arguments={
                                "project_id": str(project_id),
                                "merge_request_iid": int(mr_iid),
                                "body": final_report
                            }
                        )
                        print("[+] Review report published!")

                    # 🎉 Set commit status to SUCCESS (shows green checkmark in GitLab)
                    # Only if we have a valid commit SHA
                    if commit_sha:
                        print(f"[*] Setting commit status to SUCCESS...")
                        try:
                            await gitlab_session.call_tool(
                                name="create_commit_status",
                                arguments={
                                    "project_id": str(project_id),
                                    "sha": commit_sha,
                                    "state": "success",
                                    "name": "gatekeeper/security-review",
                                    "description": "✅ Gatekeeper review completed"
                                }
                            )
                            print("[+] Status set to SUCCESS!")
                        except Exception as status_err:
                            print(f"[⚠️] Could not set commit status: {status_err}")

                    # --- 🤖 AUTO-FIX FEATURE: Atomic Hunk-Level Patches ---
                    print("[*] Checking if issues can be auto-fixed via atomic patches...")

                    # Parse the diff into atomic patches for granular fixes
                    print("[*] Parsing diff into atomic hunk-level patches...")
                    patch_parser = AtomicPatchParser(context_lines=3)
                    atomic_patches = patch_parser.parse_unified_diff(raw_diff_content)

                    print(f"[+] Parsed {len(atomic_patches)} atomic patches with "
                          f"{sum(len(p.hunks) for p in atomic_patches)} total hunks")

                    fix_prompt = (
                        f"Review this software engineering audit report:\n\n{audit_report}\n\n"
                        f"ANALYZE THESE ATOMIC PATCHES FOR FIXABLE ISSUES:\n\n"
                        f"{create_patch_summary(atomic_patches)}\n\n"
                        "TASK: Determine if the identified problems can be resolved automatically at the HUNK level.\n\n"
                        "FIXABLE ISSUES INCLUDE (but are not limited to):\n"
                        "- Hardcoded secrets, API keys, passwords, tokens -> Extract to environment variables\n"
                        "- Hardcoded configuration values -> Extract to environment variables\n"
                        "- Insecure default values -> Replace with secure defaults or env vars\n"
                        "- SQL injection vulnerabilities -> Use parameterized queries\n"
                        "- Missing input validation -> Add validation logic\n"
                        "- Insecure cryptographic algorithms -> Use secure alternatives\n"
                        "- Sensitive data in logs -> Remove or sanitize\n\n"
                        "For each fixable issue, provide:\n"
                        "- hunk_id: The ID of the hunk to fix (from the patch summary above)\n"
                        "- issue: Brief description of the problem\n"
                        "- original_lines: The EXACT lines from the hunk that need to be fixed (preserve formatting)\n"
                        "- fixed_lines: The corrected replacement lines\n"
                        "- extracted_env_vars: If secrets/configs are extracted, map them as {\"VAR_NAME\": \"value\"}\n\n"
                        "IMPORTANT RULES:\n"
                        "1. Use the EXACT hunk_id from the patch summary above\n"
                        "2. original_lines must match the hunk content exactly\n"
                        "3. For hardcoded values, extract to environment variables using format: process.env.VAR_NAME (JavaScript) or os.getenv('VAR_NAME') (Python)\n"
                        "4. If no issues are fixable, return {\"fixable\": false, \"fixes\": []}\n\n"
                        "Respond ONLY with valid JSON in this exact format:\n"
                        '{"fixable": true/false, "fixes": [{"hunk_id": "id", "issue": "description", "original_lines": ["line1", "line2"], "fixed_lines": ["line1_fixed", "line2_fixed"], "extracted_env_vars": {"KEY": "value"}}]}'
                    )

                    # Using JSON output mode (Developer API compatible)
                    print("[DEBUG] Preparing to call Gemini for fix analysis...")
                    print(f"[DEBUG] Fix prompt length: {len(fix_prompt)} chars")

                    fix_analysis = await asyncio.wait_for(
                        asyncio.to_thread(
                            ai_client.models.generate_content,
                            model='gemini-3.5-flash',
                            contents=fix_prompt,
                            config=types.GenerateContentConfig(
                                system_instruction="You are a strict automated code repair system. Output only valid JSON with no markdown formatting.",
                                temperature=0.1,
                                response_mime_type="application/json"
                            )
                        ),
                        timeout=60.0  # 60 second timeout for fix analysis
                    )

                    print("[DEBUG] Waiting for fix analysis response (60s timeout)...")

                    try:
                        # Clean up the response - remove markdown code blocks if present
                        response_text = fix_analysis.text.strip()
                        print(f"[DEBUG] Fix analysis response: {response_text[:500]}")

                        if response_text.startswith("```"):
                            response_text = response_text.split("```")[1]
                            if response_text.startswith("json"):
                                response_text = response_text[4:]
                        response_text = response_text.strip()

                        fix_data = json.loads(response_text)
                        print(f"[DEBUG] Parsed fix_data: fixable={fix_data.get('fixable')}, fixes count={len(fix_data.get('fixes', []))}")

                        if fix_data.get("fixable") and fix_data.get("fixes"):
                            print(f"[🔧] Found {len(fix_data['fixes'])} fixable hunks! Creating atomic patch branch...")

                            timestamp = int(time.time())
                            fix_branch_name = f"gatekeeper/atomic-fix-mr{mr_iid}-{timestamp}"

                            print(f"[*] Creating atomic fix branch: {fix_branch_name}")
                            await asyncio.wait_for(
                                gitlab_session.call_tool(
                                    name="create_branch",
                                    arguments={
                                        "project_id": str(project_id),
                                        "branch": fix_branch_name,
                                        "ref": source_branch
                                    }
                                ),
                                timeout=30.0
                            )
                            print(f"[+] Branch {fix_branch_name} created!")

                            # Create patch manager for this MR
                            patch_manager = AtomicPatchManager(
                                storage_path=Path(__file__).parent / "patches" / f"mr_{mr_iid}"
                            )
                            patch_manager.add_patches(str(project_id), atomic_patches)

                            fixes_applied = []
                            all_env_vars = {}  # Collect all extracted environment variables
                            modified_files = {}  # Track file modifications

                            for fix in fix_data["fixes"]:
                                hunk_id = fix.get("hunk_id")
                                fix_description = fix.get("issue")
                                original_lines = fix.get("original_lines", [])
                                fixed_lines = fix.get("fixed_lines", [])
                                extracted_envs = fix.get("extracted_env_vars", {})

                                # Find the original hunk
                                original_hunk = None
                                for patch in atomic_patches:
                                    for hunk in patch.hunks:
                                        if hunk.hunk_id == hunk_id:
                                            original_hunk = hunk
                                            break
                                    if original_hunk:
                                        break

                                if not original_hunk:
                                    print(f"[⚠️] Could not find hunk {hunk_id}, skipping fix")
                                    continue

                                # Collect environment variables from this fix
                                if extracted_envs:
                                    all_env_vars.update(extracted_envs)

                                file_path = original_hunk.file_path

                                # Track file modifications (accumulate changes per file)
                                if file_path not in modified_files:
                                    modified_files[file_path] = []

                                modified_files[file_path].append({
                                    "hunk_id": hunk_id,
                                    "old_start": original_hunk.old_start,
                                    "new_start": original_hunk.new_start,
                                    "original_lines": original_lines,
                                    "fixed_lines": fixed_lines,
                                    "description": fix_description
                                })

                                fixes_applied.append(f"- ✅ **{file_path}:{original_hunk.old_start}**: {fix_description}")
                                print(f"[+] Queued atomic fix for {file_path} hunk {hunk_id}")

                            # Apply all fixes file by file using atomic patch application
                            print(f"[*] Applying {len(modified_files)} file(s) with atomic hunk fixes...")

                            for file_path, file_fixes in modified_files.items():
                                try:
                                    # Get the original file content from the source branch
                                    # For new files, this will fail, so we start with empty content
                                    file_content = ""
                                    try:
                                        file_result = await gitlab_session.call_tool(
                                            name="get_file_contents",
                                            arguments={
                                                "project_id": str(project_id),
                                                "file_path": file_path,
                                                "ref": source_branch
                                            }
                                        )

                                        # Decode file content (GitLab returns base64)
                                        import base64

                                        print(f"[DEBUG] Raw file_result type: {type(file_result)}")
                                        print(f"[DEBUG] Raw file_result.content type: {type(file_result.content)}")
                                        if hasattr(file_result.content, '__iter__') and len(file_result.content) > 0:
                                            print(f"[DEBUG] First content item type: {type(file_result.content[0])}")
                                            if hasattr(file_result.content[0], 'text'):
                                                print(f"[DEBUG] First 200 chars of raw text: {repr(file_result.content[0].text[:200])}")

                                        if hasattr(file_result.content[0], 'text'):
                                            file_content_json = json.loads(file_result.content[0].text)
                                            content = file_content_json.get('content', '')
                                            encoding = file_content_json.get('encoding', 'utf8')

                                            print(f"[DEBUG] File encoding: {encoding}, content length: {len(content)}")

                                            # Only decode if the encoding is base64
                                            if encoding == 'base64':
                                                content_b64 = content
                                                # Fix base64 padding
                                                padding_needed = (4 - len(content_b64) % 4) % 4
                                                if padding_needed:
                                                    content_b64 += '=' * padding_needed

                                                # Handle URL-safe base64 encoding
                                                content_b64 = content_b64.replace('-', '+').replace('_', '/')

                                                # Decode base64
                                                try:
                                                    decoded_bytes = base64.b64decode(content_b64)
                                                    file_content = decoded_bytes.decode('utf-8')
                                                except UnicodeDecodeError:
                                                    file_content = decoded_bytes.decode('latin-1')
                                            else:
                                                # Content is already plain text (utf8, text, etc.)
                                                file_content = content
                                        else:
                                            file_content = str(file_result.content)

                                        print(f"[DEBUG] Fetched existing file content: {len(file_content)} chars")
                                    except Exception as fetch_err:
                                        # File doesn't exist (new file) - start with empty content
                                        print(f"[ℹ️] New file detected ({file_path}), starting with empty content")
                                        file_content = ""

                                    # Normalize line endings to LF and split into lines
                                    # Remove trailing carriage returns that can cause issues
                                    file_content = file_content.replace('\r\n', '\n').replace('\r', '\n')

                                    # Apply atomic fixes line by line
                                    # For new files, start with empty lines list
                                    file_lines = file_content.split('\n') if file_content else []

                                    # Sort fixes by line number in reverse order to maintain line positions
                                    file_fixes.sort(key=lambda x: x['old_start'], reverse=True)

                                    for fix_data in file_fixes:
                                        original_lines = fix_data['original_lines']
                                        fixed_lines = fix_data['fixed_lines']

                                        # For new files (where file_lines was empty before fetching),
                                        # we need to find and replace the lines by content, not position
                                        if not original_lines:
                                            # No original lines to replace - this is a new addition
                                            print(f"[ℹ️] New file fix for {file_path} - appending fixed content")
                                            file_lines.extend(fixed_lines)
                                        else:
                                            # Search for the original lines in the file by content
                                            # This handles cases where line positions may have shifted
                                            found_index = -1

                                            # Try to find the exact sequence of lines
                                            for i in range(len(file_lines) - len(original_lines) + 1):
                                                if file_lines[i:i + len(original_lines)] == original_lines:
                                                    found_index = i
                                                    break

                                            if found_index == -1:
                                                # Try a more flexible search - check if lines exist (ignoring trailing whitespace)
                                                for i in range(len(file_lines) - len(original_lines) + 1):
                                                    match = True
                                                    for j, orig_line in enumerate(original_lines):
                                                        current_line = file_lines[i + j] if i + j < len(file_lines) else ""
                                                        # Strip trailing whitespace for comparison
                                                        if current_line.rstrip() != orig_line.rstrip():
                                                            match = False
                                                            break
                                                    if match:
                                                        found_index = i
                                                        break

                                            if found_index == -1:
                                                print(f"[⚠️] Could not find matching lines for {file_path}, skipping atomic fix")
                                                print(f"[DEBUG] Looking for: {original_lines}")
                                                continue

                                            # Apply the fix at the found position
                                            file_lines[found_index:found_index + len(original_lines)] = fixed_lines
                                            print(f"[+] Applied atomic fix to {file_path}:{found_index + 1}")

                                    # Write the modified file
                                    # Remove trailing empty line if present (from split)
                                    if file_lines and file_lines[-1] == '':
                                        file_lines = file_lines[:-1]

                                    new_content = '\n'.join(file_lines)
                                    # Ensure file ends with newline (standard practice)
                                    if not new_content.endswith('\n'):
                                        new_content += '\n'

                                    print(f"[DEBUG] Sending {len(new_content)} bytes to GitLab for {file_path}")
                                    print(f"[DEBUG] Content preview: {repr(new_content[:200])}")

                                    await gitlab_session.call_tool(
                                        name="create_or_update_file",
                                        arguments={
                                            "project_id": str(project_id),
                                            "file_path": file_path,
                                            "content": new_content,
                                            "branch": fix_branch_name,
                                            "commit_message": f"🔧 Gatekeeper atomic fix: {len(file_fixes)} hunk(s) in {file_path}"
                                        }
                                    )
                                    print(f"[+] Committed atomic fixes to {file_path}")

                                except Exception as file_err:
                                    print(f"[x] Failed to apply atomic fixes to {file_path}: {file_err}")

                            # Create or update .env file with extracted secrets
                            if all_env_vars:
                                print(f"[🔐] Creating .env file with {len(all_env_vars)} extracted environment variables...")
                                env_content = "# Gatekeeper Auto-Generated Environment Variables\n"
                                env_content += "# These values were extracted from hardcoded secrets in the codebase\n\n"
                                for key, value in all_env_vars.items():
                                    env_content += f"{key}={value}\n"

                                try:
                                    await gitlab_session.call_tool(
                                        name="create_or_update_file",
                                        arguments={
                                            "project_id": str(project_id),
                                            "file_path": ".env",
                                            "content": env_content,
                                            "branch": fix_branch_name,
                                            "commit_message": "🔐 Gatekeeper: Add .env file with extracted secrets"
                                        }
                                    )
                                    fixes_applied.append(f"- 🔐 **.env**: Created with {len(all_env_vars)} environment variable(s)")
                                    print(f"[+] Created .env file with environment variables")

                                    # Also ensure .env is in .gitignore
                                    print(f"[*] Ensuring .env is in .gitignore...")
                                    try:
                                        # Try to get current .gitignore content
                                        gitignore_result = await gitlab_session.call_tool(
                                            name="get_file_contents",
                                            arguments={
                                                "project_id": str(project_id),
                                                "file_path": ".gitignore",
                                                "ref": source_branch
                                            }
                                        )
                                        current_gitignore = str(gitignore_result.content)
                                    except Exception:
                                        current_gitignore = ""

                                    if ".env" not in current_gitignore:
                                        updated_gitignore = current_gitignore.rstrip() + "\n\n# Gatekeeper: Ignore environment files\n.env\n.env.local\n.env.*\n"
                                        await gitlab_session.call_tool(
                                            name="create_or_update_file",
                                            arguments={
                                                "project_id": str(project_id),
                                                "file_path": ".gitignore",
                                                "content": updated_gitignore,
                                                "branch": fix_branch_name,
                                                "commit_message": "🔐 Gatekeeper: Add .env to .gitignore"
                                            }
                                        )
                                        fixes_applied.append("- 🔒 **.gitignore**: Added .env to prevent secret leaks")
                                        print(f"[+] Added .env to .gitignore")
                                    else:
                                        print(f"[ℹ️] .env already in .gitignore")

                                except Exception as env_err:
                                    print(f"[x] Failed to create .env file: {env_err}")

                            if fixes_applied:
                                formatted_fixes_list = "\n".join(fixes_applied)
                                
                                print(f"[*] Creating MR with auto-fixes...")
                                fix_mr_title = f"🔧 Gatekeeper Auto-Fix for MR !{mr_iid}"
                                fix_mr_description = f"### 🛡️ Gatekeeper Auto-Fix\n\nThis MR was automatically created by **The Gatekeeper** to resolve auditing issues found in MR !{mr_iid}.\n\n**Original MR:** {mr_title}\n**Source Branch:** {source_branch}\n\n**Remediations Applied:**\n{formatted_fixes_list}\n\n---\n*This patch was generated autonomously by the Gatekeeper Schema Enforced Remediation Core.*"

                                await gitlab_session.call_tool(
                                    name="create_merge_request",
                                    arguments={
                                        "project_id": str(project_id),
                                        "source_branch": fix_branch_name,
                                        "target_branch": source_branch,
                                        "title": fix_mr_title,
                                        "description": fix_mr_description
                                    }
                                )
                                print("[+] Auto-fix MR created!")

                                original_mr_comment = f"### 🤖 Gatekeeper Auto-Fix Created\n\nI found functional remediation paths for the issues flagged during my audit. A separate layout patch has been opened against your branch.\n\n**Target Branch:** `{fix_branch_name}`\n\n**Remediations Applied:**\n{formatted_fixes_list}\n\nPlease merge the tracking correction PR if the structural alterations match your specification layout."
                                
                                await gitlab_session.call_tool(
                                    name="create_merge_request_note",
                                    arguments={
                                        "project_id": str(project_id),
                                        "merge_request_iid": int(mr_iid),
                                        "body": original_mr_comment
                                    }
                                )
                                print("[+] Notified original MR about auto-fix!")
                        else:
                            print("[ℹ️] Issues found but require manual review or are not auto-fixable.")

                    except asyncio.TimeoutError:
                        print("[⏱️] Fix analysis timed out after 60 seconds - skipping auto-fix")
                        print("[ℹ️] The security review was completed, but atomic fixes could not be generated in time.")
                    except json.JSONDecodeError as parse_err:
                        print(f"[x] Failed to parse fix analysis JSON structure: {parse_err}")
                    except Exception as loop_err:
                        print(f"[x] Auto-fix execution loop broken: {loop_err}")

                except Exception as e:
                    print(f"[x] Intelligent Gemini Audit loop failed: {e}")

                    # ❌ Set commit status to FAILED on error
                    if commit_sha and gitlab_session:
                        try:
                            await gitlab_session.call_tool(
                                name="create_commit_status",
                                arguments={
                                    "project_id": str(project_id),
                                    "sha": commit_sha,
                                    "state": "failed",
                                    "name": "gatekeeper/security-review",
                                    "description": f"❌ Gatekeeper review failed: {str(e)[:100]}"
                                }
                            )
                            print("[+] Status set to FAILED")
                        except Exception as status_err:
                            print(f"[x] Failed to set error status: {status_err}")
                        
    return {"status": "event_processed"}