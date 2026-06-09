import os
import sys
import asyncio
import time
import json
import re
from typing import Optional
from datetime import datetime
from fastapi import Depends, Depends, FastAPI, Request, Header, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from google.genai import types
from services.gitnexus_manager import gitnexus_manager

# Fix Windows console encoding for emoji characters
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    # Fix Windows subprocess issue with asyncio - MUST be set before event loop is created
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

load_dotenv(verbose=True)  # Enable verbose logging to see if .env is found

# Debug: Print Sentry env vars
import os
print(f"[DEBUG] Working directory: {os.getcwd()}", flush=True)
print(f"[DEBUG] SENTRY_CLIENT_ID: {os.getenv('SENTRY_CLIENT_ID', 'NOT_SET')[:20]}...", flush=True)
print(f"[DEBUG] .env file exists: {os.path.exists('.env')}", flush=True)

# Import Gatekeeper Services
from services import (
    mcp_service, review_service, auth_service, repository_service,
    mongo_client, user_service, billing_service, incident_service
)
from copilot.api import copilot_router
from copilot.resolution.mr_execution import resolve_mr_execution_response
from peil.api.auth import require_jwt_user
from knowledge.api import knowledge_router
from peil.api import aril_router
from copilot.api import copilot_router
from copilot.resolution.mr_execution import resolve_mr_execution_response
from peil.api.auth import require_jwt_user
from knowledge.api import knowledge_router
from peil.api import aril_router
from api_models import (
    OAuthCallbackRequest, TokenResponse, UserResponse,
    VerifyTokenRequest, VerifyTokenResponse, LogoutResponse,
    RepositoryResponse, MergeRequestResponse, ScanRepositoryResponse, ScanRepositoryRequest,
    OnboardRepositoryRequest, UpdateRepositoryRequest, UpdateRepositoryResponse,
    GeminiSettingsResponse, ValidateTokenRequest, ValidateTokenResponse,
    PolicySettingsResponse, UpdateGeminiSettingsRequest, UpdatePolicySettingsRequest,
    UpdateUserProfileRequest, IntegrationStatusResponse,
    SyncRequest, BillingUsageResponse, InvoiceResponse,
    SentryIntegrationInitiateRequest, SentryIntegrationInitiateResponse,
    SentryCallbackRequest, SentryIntegrationResponse, SentryIntegrationDisconnectResponse,
    SentryWebhookSetupStep, SentryWebhookSetupInstructions, SentryWebhookVerifyRequest, SentryWebhookVerifyResponse
)

app = FastAPI(title="The Gatekeeper Gemini Orchestrator")
app.include_router(aril_router)
app.include_router(copilot_router)
app.include_router(knowledge_router)
app.include_router(aril_router)
app.include_router(copilot_router)
app.include_router(knowledge_router)



# ============================================================================
# Background Session Cleanup Task
# ============================================================================

async def run_session_cleanup():
    """Background task to periodically cleanup idle GitLab MCP sessions."""
    while True:
        try:
            await asyncio.sleep(300)  # Check every 5 minutes
            max_idle = int(os.getenv("GITLAB_SESSION_IDLE_TIMEOUT", "3600"))  # Default 1 hour
            cleaned = await mcp_service.cleanup_idle_sessions(max_idle_seconds=max_idle)
            if cleaned > 0:
                print(f"[INFO] Background cleanup: Removed {cleaned} idle GitLab sessions")
        except asyncio.CancelledError:
            print("[INFO] Session cleanup task terminated")
            break
        except Exception as e:
            print(f"[ERROR] Session cleanup task error: {e}")


# ============================================================================
# Background Session Cleanup Task
# ============================================================================

async def run_session_cleanup():
    """Background task to periodically cleanup idle GitLab MCP sessions."""
    while True:
        try:
            await asyncio.sleep(300)  # Check every 5 minutes
            max_idle = int(os.getenv("GITLAB_SESSION_IDLE_TIMEOUT", "3600"))  # Default 1 hour
            cleaned = await mcp_service.cleanup_idle_sessions(max_idle_seconds=max_idle)
            if cleaned > 0:
                print(f"[INFO] Background cleanup: Removed {cleaned} idle GitLab sessions")
        except asyncio.CancelledError:
            print("[INFO] Session cleanup task terminated")
            break
        except Exception as e:
            print(f"[ERROR] Session cleanup task error: {e}")

# ============================================================================
# CORS Configuration
# ============================================================================

# Get allowed origins from environment or use localhost defaults
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
allowed_origins = [
    frontend_url,
    "http://localhost:3000",
    "http://localhost:5173",  # Vite default
    "http://localhost:5174",  # Alternative Vite port
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    # Defer process execution into a separate background event loop
    print("[*] Starting Gatekeeper service...")
    print("[*] CODE VERSION: WEBHOOK-DEBUG-1.0 - If you see this, new code is loaded!")
    import sys
    sys.stderr.write("[STARTUP] New webhook debugging code loaded!\n")
    sys.stderr.flush()
    sys.stderr.write("[*] MCP Bridge initialization starting (startup waits for MongoDB + GitLab)...\n")
    sys.stderr.flush()
    sys.stderr.write("[*] MCP Bridge initialization starting (startup waits for MongoDB + GitLab)...\n")
    sys.stderr.flush()

    # Initialize Arize observability for LLM usage tracking
    try:
        from config.arize_config import init_arize, instrument_google_genai, init_phoenix_client

        print("[*] Initializing Arize observability...")
        if init_arize(project_name="gatekeeper"):
            print("[✅] Arize observability initialized successfully")
            # Instrument Google GenAI for automatic tracing
            if instrument_google_genai():
                print("[✅] Google GenAI instrumentor registered")
            else:
                print("[⚠️] Failed to instrument Google GenAI")
        else:
            print("[⚠️] Arize initialization failed - LLM usage tracking disabled")

        # Initialize Phoenix client for querying traces
        if init_phoenix_client():
            print("[✅] Phoenix client initialized for billing sync")
        else:
            print("[⚠️] Phoenix client initialization failed")
    except Exception as e:
        print(f"[⚠️] Failed to initialize Arize/Phoenix: {e}")
        print("[ℹ️] LLM usage tracking will be unavailable")

    # Initialize ARIL Mongo collections and indexes (non-fatal)
    try:
        from peil.store import initialize_aril_collections

        aril_summary = await initialize_aril_collections()
        print(f"[OK] ARIL collections initialized: {aril_summary.get('indexes', {})}")
    except Exception as e:
        print(f"[WARN] ARIL collection initialization failed (capture may be degraded): {e}")

    try:
        from copilot.store.init_collections import initialize_copilot_collections

        copilot_summary = await initialize_copilot_collections()
        print(f"[OK] Copilot collections initialized: {copilot_summary.get('indexes', {})}")
    except Exception as e:
        print(f"[WARN] Copilot collection initialization failed: {e}")

    # Initialize ARIL Mongo collections and indexes (non-fatal)

    try:
        from peil.store import initialize_aril_collections

        aril_summary = await initialize_aril_collections()
        print(f"[OK] ARIL collections initialized: {aril_summary.get('indexes', {})}")
    except Exception as e:
        print(f"[WARN] ARIL collection initialization failed (capture may be degraded): {e}")

    try:
        from copilot.store.init_collections import initialize_copilot_collections

        copilot_summary = await initialize_copilot_collections()
        print(f"[OK] Copilot collections initialized: {copilot_summary.get('indexes', {})}")
    except Exception as e:
        print(f"[WARN] Copilot collection initialization failed: {e}")

    # Launch MCP bridge and block startup until MongoDB + GitLab are ready
    def _log_mcp_task_done(task: asyncio.Task) -> None:
        if task.cancelled():
            mcp_service.mark_unready("background task cancelled")
            return
        try:
            task.result()
        except Exception as exc:
            mcp_service.mark_unready(str(exc))
            sys.stderr.write(f"[ERROR] MCP Bridge background task failed: {exc}\n")
            sys.stderr.flush()

    mcp_task = asyncio.create_task(
        mcp_service.boot_mcp_bridge(),
        name="mcp_bridge_boot",
    )
    mcp_task.add_done_callback(_log_mcp_task_done)

    sys.stderr.write("[*] Waiting for MCP critical services (MongoDB + GitLab)...\n")
    sys.stderr.flush()
    if await mcp_service.wait_for_critical_ready(timeout=120.0):
        sys.stderr.write(
            f"[*] MCP ready for webhooks "
            f"(gitlab_session={mcp_service.gitlab_session is not None})\n"
        )
    else:
        sys.stderr.write(
            "[WARN] MCP critical ready timed out after 120s — "
            "webhooks will return mcp_not_ready until bridge completes\n"
        )
    sys.stderr.flush()

    try:
        from copilot.api.router import warm_copilot_tool_registry

        if mcp_service.gitlab_session is not None and mcp_service.mongo_session is not None:
            await warm_copilot_tool_registry()
            sys.stderr.write("[OK] Copilot tool registry pre-warmed\n")
        else:
            sys.stderr.write(
                "[WARN] Copilot tool registry pre-warm skipped "
                f"(gitlab_session={mcp_service.gitlab_session is not None}, "
                f"mongo_session={mcp_service.mongo_session is not None})\n"
            )
    except Exception as exc:
        sys.stderr.write(f"[WARN] Copilot tool registry pre-warm failed: {exc}\n")
    sys.stderr.flush()

    # Launch background task to cleanup idle GitLab sessions
    asyncio.create_task(run_session_cleanup())

    # Launch background task to cleanup idle GitLab sessions
    asyncio.create_task(run_session_cleanup())


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    print("[*] Shutting down Gatekeeper service...")

    # Close MongoDB connection
    try:
        await mongo_client.close_mongo_connection()
    except Exception as e:
        print(f"[⚠️] Error closing MongoDB connection: {e}")

    # Shutdown Arize tracer provider
    try:
        from config.arize_config import shutdown as shutdown_arize
        shutdown_arize()
        print("[✅] Arize tracer provider shut down")
    except Exception as e:
        print(f"[⚠️] Error shutting down Arize: {e}")

    print("[✅] Gatekeeper shutdown complete")


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "mcp_ready": mcp_service.mcp_ready,
        "mongo_connected": mcp_service.mongo_session is not None,
        "gitlab_connected": mcp_service.gitlab_session is not None,
        "nexus_connected": mcp_service.nexus_session is not None,
        "gitlab_session_cache_size": mcp_service.get_session_cache_size()
    }


@app.get("/api/debug/mongodb")
async def test_mongodb_connection():
    """Test MongoDB connection and return detailed status."""
    print("[DEBUG] Testing MongoDB connection...")
    print(f"[DEBUG] MCP ready: {mcp_service.mcp_ready}")
    print(f"[DEBUG] MongoDB session: {mcp_service.mongo_session}")
    print(f"[DEBUG] GitLab session: {mcp_service.gitlab_session}")

    result = await repository_service.test_mongodb_connection()
    print(f"[DEBUG] MongoDB test result: {result}")
    return result


@app.post("/webhooks/gitlab")
async def gitlab_webhook(request: Request, x_gitlab_event: str = Header(None)):
    """API endpoint to receive and delegate GitLab webhook payloads."""
    import sys
    sys.stderr.write(
        f"\n[WEBHOOK HIT!] X-GitLab-Event: {x_gitlab_event} "
        f"mcp_ready={mcp_service.mcp_ready} "
        f"gitlab_session={mcp_service.gitlab_session is not None}\n"
    )
    sys.stderr.flush()

    # Check if MCP sessions are ready
    if not mcp_service.mcp_ready or not mcp_service.gitlab_session:
        sys.stderr.write(
            "[WARN] MCP sessions not ready — retry after /health shows mcp_ready=true\n"
        )
        sys.stderr.flush()
        return {"status": "mcp_not_ready", "message": "MCP sessions still initializing. Please retry in a few seconds."}

    body = await request.body()
    if not body.strip():
        return {
            "status": "invalid_payload",
            "message": "Webhook body must be non-empty JSON.",
        }

    payload = await request.json()

    # Dynamic delegation based on agentic mode environment flag
    agentic_mode = os.getenv("AGENTIC_MODE_ENABLED", "false").lower() == "true"
    print(f"[DEBUG] Agentic mode: {agentic_mode}", flush=True)

    if agentic_mode:
        from agents import ContextBuilder, build_default_registry, WorkflowEngine
        from agents import tools  # Import tools module for pre-step functions

        # 1. Handle GitLab Merge Request Event
        if x_gitlab_event == "Merge Request Hook":
            print(f"[DEBUG] Processing MR webhook in agentic mode...", flush=True)

            # Extract basic info
            obj_attrs = payload.get("object_attributes", {})
            mr_iid = obj_attrs.get("iid", "unknown")
            project_id = str(payload.get("project", {}).get("id", "unknown"))
            user_id = str(payload.get("user", {}).get("id", "unknown"))
            source_branch = obj_attrs.get("source_branch", "main")
            target_branch = obj_attrs.get("target_branch", "main")
            mr_state = obj_attrs.get("state", "unknown")
            action = obj_attrs.get("action", "unknown")
            repo_http_url = payload.get("project", {}).get("http_url", "")

            print(f"[DEBUG] ===== PRE-STEPS BEFORE LLM PLANNER =====", flush=True)

            # Pre-step 0: Validate webhook
            print(f"[DEBUG] Pre-step 0: Validating webhook...", flush=True)
            validation_result = await tools.validate_mr_webhook(
                project_id=project_id,
                mr_iid=int(mr_iid),
                target_branch=target_branch,
                source_branch=source_branch,
                mr_state=mr_state,
                action=action
            )
            if not validation_result.get("should_process", True):
                skip_reason = validation_result.get("skip_reason", "Validation failed")
                print(f"[INFO] MR validation failed: {skip_reason}", flush=True)
                return {
                    "status": "skipped",
                    "reason": skip_reason,
                    "project_id": project_id,
                    "mr_iid": mr_iid
                }
            print(f"[OK] Webhook validation passed", flush=True)

            # Build context with validated info
            print(f"[DEBUG] Step 1: Building context from webhook payload...", flush=True)
            context = await ContextBuilder.build_from_gitlab_mr(payload)
            if context is None:
                print(f"[DEBUG] Context building failed", flush=True)
                return {
                    "status": "skipped",
                    "reason": "Context building failed",
                    "project_id": project_id,
                    "mr_iid": mr_iid
                }
            print(f"[OK] Context built successfully", flush=True)

            # Pre-step 1: Clone repository
            print(f"[DEBUG] Pre-step 1: Cloning repository...", flush=True)
            try:
                repo_path = await tools.clone_repo(
                    project_id=project_id,
                    source_branch=source_branch,
                    repo_http_url=repo_http_url,
                    user_id=user_id,
                    target_branch=target_branch
                )
                context.repository.repo_path = repo_path  # Store repo path in context
                print(f"[OK] Repository cloned to: {repo_path}", flush=True)
            except Exception as e:
                print(f"[ERROR] Clone failed: {e}", flush=True)
                return {
                    "status": "error",
                    "message": f"Clone failed: {str(e)}",
                    "project_id": project_id,
                    "mr_iid": mr_iid
                }

            # Pre-step 2: Run GitNexus analyze
            print(f"[DEBUG] Pre-step 2: Running GitNexus analyze...", flush=True)
            try:
                gitnexus_result = await tools.gitnexus_analyze(repo_path=repo_path)
                context.metadata["gitnexus_analyze_result"] = gitnexus_result
                print(f"[OK] GitNexus analyze completed", flush=True)
            except Exception as e:
                print(f"[WARN] GitNexus analyze failed: {e}", flush=True)
                context.metadata["gitnexus_analyze_result"] = {"error": str(e)}

            # Pre-step 3: Fetch MR diffs
            print(f"[DEBUG] Pre-step 3: Fetching MR diffs...", flush=True)
            try:
                from services import review_service
                mr_diff_content = await review_service._gitlab_get_mr_diffs(
                    user_id=user_id,
                    project_id=project_id,
                    mr_iid=int(mr_iid)
                )
                if mr_diff_content:
                    context.metadata["mr_diff_content"] = mr_diff_content
                    print(f"[OK] MR diffs fetched ({len(mr_diff_content)} chars)", flush=True)
                else:
                    print(f"[WARN] MR diff content is empty", flush=True)
            except Exception as e:
                print(f"[WARN] Failed to fetch MR diffs: {e}", flush=True)

            print(f"[DEBUG] ===== PRE-STEPS COMPLETED =====", flush=True)

            # Ingest MR into MongoDB for progress tracking
            print(f"[DEBUG] Ingesting MR into MongoDB...", flush=True)
            ingest_result = await review_service.ingest_mr_from_webhook(payload)
            if ingest_result.get("skipped"):
                print(f"[WARN] MR ingestion skipped: {ingest_result.get('reason')}", flush=True)
            else:
                print(f"[OK] MR ingested into MongoDB", flush=True)

            print(f"[DEBUG] Step 2: Building tool registry (without pre-step tools)...", flush=True)
            registry = await build_default_registry()

            engine = WorkflowEngine(registry)
            print(f"[INFO] [Agentic Mode] Executing agentic workflow for Merge Request: {context.task_id}", flush=True)
            print(f"[DEBUG] Starting workflow execution...", flush=True)

            result = await engine.run_task(context)
            print(f"[DEBUG] Workflow execution completed: {result.get('status')}", flush=True)

            # Normalize response to match standard format
            return {
                "status": result.get("status", "event_processed"),
                "message": f"MR review completed with task_id={result.get('task_id', context.task_id)}"
            }

        # 2. Handle Dynatrace Incident/Production Crash Event
        if not x_gitlab_event:
            if isinstance(payload, dict) and "problem_id" in payload:
                context = ContextBuilder.build_from_dynatrace_crash(payload)
                engine = WorkflowEngine(await build_default_registry())
                print(f"[INFO] [Agentic Mode] Executing agentic workflow for Production Incident: {context.task_id}", flush=True)
                result = await engine.run_task(context)
                return result
    else:
        # 1. Handle GitLab Merge Request Event
        if x_gitlab_event == "Merge Request Hook":
            return await review_service.orchestrate_review(payload)

        # 2. Handle Dynatrace Incident/Production Crash Event
        if not x_gitlab_event:
            if isinstance(payload, dict) and "problem_id" in payload:
                return await incident_service.process_production_crash(payload)

    return {"status": "event_ignored", "event": x_gitlab_event}


@app.post("/webhooks/sentry")
async def sentry_webhook(request: Request, x_sentry_signature: str = Header(None)):
    """API endpoint to receive Sentry issue events for automated bug fix."""
    import sys
    sys.stderr.write(f"\n[WEBHOOK HIT!] Sentry webhook received\n")
    sys.stderr.flush()

    print(f"[DEBUG] ===== SENTRY WEBHOOK RECEIVED =====", flush=True)
    print(f"[DEBUG] X-Sentry-Signature header: {x_sentry_signature}", flush=True)
    print(f"[DEBUG] MCP ready: {mcp_service.mcp_ready}", flush=True)

    # Extract project/org info from payload to auto-mark webhook as configured
    payload = await request.json()

    # Variables to store repository owner and GitLab project info for workflow
    repo_owner_user_id = None
    repo_owner_username = None
    gitlab_project_id = None  # The actual GitLab project ID to use for cloning

    # Auto-mark webhook as configured when we receive the first webhook
    try:
        # Extract org slug from the webhook payload
        # Sentry webhook structure has org slug in data.issue.web_url (e.g., https://gatekeeper-nj.sentry.io/...)
        org_slug = None

        if isinstance(payload, dict):
            # Try multiple paths to find the organization slug
            # Path 1: Direct organization field (some webhook types)
            org_slug = payload.get("organization", {}).get("slug")

            # Path 2: From issue web_url (issue.created events)
            if not org_slug and payload.get("data", {}).get("issue", {}).get("web_url"):
                web_url = payload["data"]["issue"]["web_url"]
                # Extract org slug from URL like "https://gatekeeper-nj.sentry.io/issues/..."
                if "sentry.io" in web_url:
                    org_slug = web_url.split("//")[1].split(".sentry.io")[0]
                    print(f"[DEBUG] Extracted org_slug from web_url: {org_slug}", flush=True)

            # Path 2.5: From error.url (error.created events) - NEW
            if not org_slug and payload.get("data", {}).get("error", {}).get("url"):
                error_url = payload["data"]["error"]["url"]
                # Extract org slug from URL like "https://sentry.io/api/0/projects/gatekeeper-nj/gitnexus-demo/events/..."
                if "sentry.io" in error_url and "/projects/" in error_url:
                    # Format: https://sentry.io/api/0/projects/{org_slug}/{project_slug}/events/...
                    url_parts = error_url.split("/projects/")
                    if len(url_parts) > 1:
                        org_slug = url_parts[1].split("/")[0]
                        print(f"[DEBUG] Extracted org_slug from error.url: {org_slug}", flush=True)

            # Path 3: From project slug as fallback (find repo by project slug instead)
            project_slug = None
            if not org_slug and payload.get("data", {}).get("issue", {}).get("project", {}).get("slug"):
                project_slug = payload["data"]["issue"]["project"]["slug"]
                print(f"[DEBUG] Using project_slug as fallback: {project_slug}", flush=True)

        if org_slug:
            # Find all repositories with this Sentry organization and mark webhook as configured
            connected_repos = await mongo_client.find(
                collection_name="connected_repositories",
                filter={"sentry_integration.organizations.slug": org_slug}
            )

            for repo in connected_repos:
                # Always update webhook_registered to true when data is reported
                print(f"[DEBUG] Updating webhook_registered for repo: {repo.get('id')}", flush=True)

                # Check if this is the first webhook or a subsequent one
                is_first_webhook = repo.get("sentry_integration", {}).get("webhook_registered") is False

                update_data = {
                    "sentry_integration.webhook_registered": True,
                    "sentry_integration.last_webhook_at": datetime.utcnow().isoformat()
                }

                # Set first_webhook_at and webhook_id only on first webhook
                if is_first_webhook:
                    update_data["sentry_integration.webhook_id"] = f"auto-{org_slug}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
                    update_data["sentry_integration.first_webhook_at"] = datetime.utcnow().isoformat()
                    print(f"[DEBUG] First webhook received for repo: {repo.get('id')}", flush=True)
                else:
                    print(f"[DEBUG] Subsequent webhook received for repo: {repo.get('id')}", flush=True)

                await mongo_client.update_one(
                    collection_name="connected_repositories",
                    filter={"id": repo.get("id")},
                    update={"$set": update_data}
                )
                print(f"[DEBUG] webhook_registered updated to true for repo: {repo.get('id')}", flush=True)

                # Capture repository owner info for workflow (use first repo found)
                if repo_owner_user_id is None:
                    repo_owner_user_id = repo.get("user_id")
                    gitlab_project_id = repo.get("id")  # GitLab project ID
                    print(f"[DEBUG] Using repo owner user_id: {repo_owner_user_id}, GitLab project: {gitlab_project_id}", flush=True)

        elif project_slug:
            # Fallback: Try to find repositories by project slug (in case org slug wasn't available)
            # This matches repositories that might have this Sentry project connected
            connected_repos = await mongo_client.find(
                collection_name="connected_repositories",
                filter={"sentry_integration.organizations.slug": {"$exists": True}}  # Has Sentry integration
            )

            for repo in connected_repos:
                # Check if this repo might be related (same org could have multiple projects)
                sentry_org = repo.get("sentry_integration", {}).get("organizations", [{}])[0].get("slug") if repo.get("sentry_integration", {}).get("organizations") else None

                if sentry_org:
                    # We found a repo with Sentry integration, update it
                    print(f"[DEBUG] Found repo with Sentry integration for project: {project_slug}, org: {sentry_org}", flush=True)

                    is_first_webhook = repo.get("sentry_integration", {}).get("webhook_registered") is False

                    update_data = {
                        "sentry_integration.webhook_registered": True,
                        "sentry_integration.last_webhook_at": datetime.utcnow().isoformat()
                    }

                    if is_first_webhook:
                        update_data["sentry_integration.webhook_id"] = f"auto-{sentry_org}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
                        update_data["sentry_integration.first_webhook_at"] = datetime.utcnow().isoformat()
                        print(f"[DEBUG] First webhook received for repo: {repo.get('id')} (via project_slug)", flush=True)

                    await mongo_client.update_one(
                        collection_name="connected_repositories",
                        filter={"id": repo.get("id")},
                        update={"$set": update_data}
                    )
                    print(f"[DEBUG] webhook_registered updated to true for repo: {repo.get('id')} (via project_slug)", flush=True)

                    # Capture repository owner info for workflow (use first repo found)
                    if repo_owner_user_id is None:
                        repo_owner_user_id = repo.get("user_id")
                        gitlab_project_id = repo.get("id")  # GitLab project ID
                        print(f"[DEBUG] Using repo owner user_id: {repo_owner_user_id}, GitLab project: {gitlab_project_id}", flush=True)
    except Exception as e:
        print(f"[WARN] Failed to auto-mark webhook as configured: {e}", flush=True)

    # Log webhook to MongoDB
    await mongo_client.insert_one(
        collection_name="sentry_webhooks",
        document={**payload, "received_at": datetime.utcnow().isoformat()}
    )

    # Check MCP readiness
    if not mcp_service.mcp_ready:
        print("[⚠️] MCP sessions not ready yet - cannot process webhook")
        print("[ℹ️] Please wait a few seconds for the MCP bridge to initialize")
        return {"status": "mcp_not_ready", "message": "MCP sessions still initializing. Please retry in a few seconds."}

    # Invoke Sentry workflow with Gemini AI and full tool access
    import logging
    logger = logging.getLogger(__name__)
    from agents.workflows import run_sentry_bug_workflow

    # Extract issue_id for logging
    issue_id = payload.get("data", {}).get("error", {}).get("issue_id", "unknown")
    logger.info(f"Invoking Sentry workflow for issue {issue_id}")

    # Pass repository owner info and GitLab project ID if available
    if repo_owner_user_id:
        logger.info(f"Using repository owner: {repo_owner_username} ({repo_owner_user_id}), GitLab project: {gitlab_project_id}")
        result = await run_sentry_bug_workflow(payload, user_id=repo_owner_user_id, username=repo_owner_username, target_project_id=gitlab_project_id)
    else:
        logger.warning("No repository owner found, using default sentry-operator user")
        result = await run_sentry_bug_workflow(payload)
    return result


# ============================================================================
# Authentication Endpoints
# ============================================================================

@app.get("/api/auth/config")
async def get_auth_config():
    """Get OAuth configuration status."""
    return {
        "gitlab_oauth_enabled": auth_service.is_configured(),
        "gitlab_base_url": os.getenv("GITLAB_BASE_URL", "https://gitlab.com")
    }


@app.post("/api/auth/gitlab")
async def initiate_gitlab_oauth():
    """Initiate GitLab OAuth flow."""
    try:
        result = auth_service.initiate_gitlab_oauth()
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to initiate OAuth: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/auth/gitlab/callback")
async def gitlab_oauth_callback(code: str, state: str):
    """Handle GitLab OAuth callback."""
    try:
        result = await auth_service.handle_oauth_callback(code, state)
        return TokenResponse(**result)
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] OAuth callback failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/sentry/init")
async def initiate_sentry_oauth(request: SentryIntegrationInitiateRequest):
    """Initiate Sentry OAuth flow for a repository."""
    try:
        import os
        print(f"[DEBUG /api/auth/sentry/init] SENTRY_CLIENT_ID from os.getenv: {os.getenv('SENTRY_CLIENT_ID', 'NOT_SET')[:20]}...", flush=True)

        from services.sentry_oauth_service import get_sentry_oauth_service
        service = get_sentry_oauth_service()
        print(f"[DEBUG /api/auth/sentry/init] service.client_id: {service.client_id[:20] if service.client_id else 'EMPTY'}", flush=True)

        result = await service.initiate_oauth(request.user_id, request.repo_id)
        print(f"[DEBUG /api/auth/sentry/init] result oauth_url: {result.get('oauth_url', 'NO_URL')[:100]}...", flush=True)
        return SentryIntegrationInitiateResponse(**result)
    except Exception as e:
        print(f"[ERROR] Failed to initiate Sentry OAuth: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/sentry/callback")
async def sentry_oauth_callback(request: SentryCallbackRequest):
    """Handle Sentry OAuth callback and auto-register webhook."""
    try:
        from services.sentry_oauth_service import get_sentry_oauth_service
        service = get_sentry_oauth_service()
        result = await service.handle_callback(request.code, request.state)
        return result
    except ValueError as e:
        print(f"[ERROR] Sentry OAuth callback failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[ERROR] Sentry OAuth callback error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/auth/sentry/status/{repo_id}", response_model=SentryIntegrationResponse)
async def get_sentry_integration_status(repo_id: str):
    """Get Sentry integration status for a repository, including webhook setup instructions."""
    try:
        from services.sentry_oauth_service import get_sentry_oauth_service
        service = get_sentry_oauth_service()
        status = await service.get_integration_status(repo_id)

        # Transform the response to match the expected format
        return SentryIntegrationResponse(
            connected=status.get("connected", False),
            org_slug=status.get("org_slug"),
            webhook_registered=status.get("webhook_registered", False),
            connected_at=status.get("connected_at"),
            webhook_id=status.get("webhook_id"),
            webhook_config=status.get("webhook_setup_instructions")
        )
    except Exception as e:
        print(f"[ERROR] Failed to get Sentry integration status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/sentry/verify-webhook", response_model=SentryWebhookVerifyResponse)
async def verify_sentry_webhook(request: SentryWebhookVerifyRequest):
    """Verify if Sentry webhook is properly configured and working."""
    try:
        from services.sentry_oauth_service import get_sentry_oauth_service
        service = get_sentry_oauth_service()
        result = await service.verify_webhook(request.repo_id)
        return SentryWebhookVerifyResponse(**result)
    except Exception as e:
        print(f"[ERROR] Failed to verify Sentry webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/sentry/confirm-webhook")
async def confirm_sentry_webhook(request: SentryWebhookVerifyRequest):
    """Confirm that the Sentry webhook is working after manual verification."""
    try:
        from services.sentry_oauth_service import get_sentry_oauth_service
        service = get_sentry_oauth_service()
        result = await service.confirm_webhook(request.repo_id)
        return result
    except Exception as e:
        print(f"[ERROR] Failed to confirm Sentry webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/verify", response_model=VerifyTokenResponse)
async def verify_token(request: VerifyTokenRequest):
    """Verify a JWT access token."""
    try:
        user_info = auth_service.verify_token(request.token)
        return VerifyTokenResponse(
            valid=True,
            user=UserResponse(**user_info),
            message="Token is valid"
        )
    except HTTPException as e:
        return VerifyTokenResponse(
            valid=False,
            message=str(e.detail)
        )


@app.post("/api/auth/logout", response_model=LogoutResponse)
async def logout(request: VerifyTokenRequest):
    """Logout user and invalidate session."""
    result = auth_service.logout_user(request.token)
    return LogoutResponse(**result)


# ============================================================================
# Dashboard & Alerts Endpoints (Phase 8)
# ============================================================================

@app.get("/api/dashboard/recent-mrs")
async def get_dashboard_recent_mrs(
    limit: int = Query(default=10, ge=1),
    user: dict = Depends(require_jwt_user)
):
    """Get recent merge requests across all connected repositories for the logged-in user."""
    try:
        user_id = str(user["id"])
        mrs = await repository_service.get_recent_mrs_for_user(user_id, limit)
        return mrs
    except Exception as e:
        print(f"[ERROR] Failed to fetch recent MRs for dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard/stats")
async def get_dashboard_stats(
    user: dict = Depends(require_jwt_user)
):
    """Get aggregated dashboard stats for the logged-in user."""
    try:
        user_id = str(user["id"])
        stats = await repository_service.get_dashboard_stats(user_id)
        return stats
    except Exception as e:
        print(f"[ERROR] Failed to fetch dashboard stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard/repos-health")
async def get_dashboard_repos_health(
    user: dict = Depends(require_jwt_user)
):
    """Get health stats of user's repositories for the dashboard."""
    try:
        user_id = str(user["id"])
        health = await repository_service.get_repos_health(user_id)
        return health
    except Exception as e:
        print(f"[ERROR] Failed to fetch repositories health score: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/alerts")
async def get_alerts(
    severity: Optional[str] = Query(default=None),
    user: dict = Depends(require_jwt_user)
):
    """Get alerts for the logged-in user, optionally filtered by severity."""
    try:
        user_id = str(user["id"])
        alerts = await repository_service.get_alerts_for_user(user_id, severity)
        return alerts
    except Exception as e:
        print(f"[ERROR] Failed to fetch alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/alerts/{id}/read")
async def mark_alert_as_read(
    id: str,
    user: dict = Depends(require_jwt_user)
):
    """Mark a specific alert as read."""
    try:
        user_id = str(user["id"])
        success = await repository_service.mark_alert_read(user_id, id)
        if not success:
            raise HTTPException(status_code=404, detail="Alert not found or already read")
        return {"success": True}
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[ERROR] Failed to mark alert as read: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/alerts/{id}")
async def delete_alert(
    id: str,
    user: dict = Depends(require_jwt_user)
):
    """Dismiss/delete a specific alert."""
    try:
        user_id = str(user["id"])
        success = await repository_service.dismiss_alert(user_id, id)
        if not success:
            raise HTTPException(status_code=404, detail="Alert not found")
        return {"success": True}
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[ERROR] Failed to dismiss alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/alerts/mark-all-read")
async def mark_all_alerts_as_read(
    user: dict = Depends(require_jwt_user)
):
    """Mark all unread alerts for the user as read."""
    try:
        user_id = str(user["id"])
        await repository_service.mark_all_alerts_read(user_id)
        return {"success": True}
    except Exception as e:
        print(f"[ERROR] Failed to mark all alerts read: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Repository Endpoints
# ============================================================================

@app.get("/api/repositories", response_model=list[RepositoryResponse])
async def get_repositories(limit: Optional[int] = None, authorization: str = Header(None)):
    """Get all connected repositories."""
    try:
        # Extract user from token if available
        user_id = None
        if authorization:
            token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
            try:
                user_info = auth_service.verify_token(token)
                user_id = user_info.get("id")
            except:
                pass  # Token invalid, continue without user context

        repos = await repository_service.get_all_repositories(user_id=user_id, limit=limit)
        return repos
    except Exception as e:
        print(f"[ERROR] Failed to fetch repositories: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Specific routes must come BEFORE parameterized routes
@app.get("/api/repositories/search")
async def search_repositories(q: str = ""):
    """Search repositories by name or description."""
    try:
        if not q:
            return []
        results = repository_service.search_repositories(q)
        return results
    except Exception as e:
        print(f"[ERROR] Failed to search repositories: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/repositories/available")
async def get_available_repositories(
    q: str = "",
    authorization: str = Header(None)
):
    """Get user's GitLab repositories that are not yet connected."""
    try:
        # Extract user from token
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        repos = await repository_service.get_available_gitlab_repositories(user_id, q)
        return repos
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to fetch available repositories: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/repositories/import")
async def import_repository(request: dict, authorization: str = Header(None)):
    """Import a new GitLab repository."""
    try:
        gitlab_path = request.get("gitlab_path")
        if not gitlab_path:
            raise HTTPException(status_code=400, detail="Missing gitlab_path")

        # Extract user from token
        user_id = None
        if authorization:
            token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
            try:
                user_info = auth_service.verify_token(token)
                user_id = user_info.get("id")
            except:
                pass

        result = await repository_service.import_repository(gitlab_path, user_id)
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to import repository: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Parameterized routes must come AFTER specific routes
@app.get("/api/repositories/{repo_id}")
async def get_repository_details(repo_id: str, authorization: str = Header(None)):
    """Get detailed information about a specific repository."""
    try:
        # Extract user from token (optional for repo details)
        user_id = None
        if authorization:
            token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
            try:
                user_info = auth_service.verify_token(token)
                user_id = user_info.get("id")
            except:
                pass  # Token invalid, continue without user context

        repo = await repository_service.get_repository(repo_id)
        return repo
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to fetch repository details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/repositories/{repo_id}/mrs")
async def get_repository_merge_requests(
    repo_id: str,
    limit: int = 50,
    authorization: str = Header(None)
):
    """Get merge requests for a repository from MongoDB."""
    try:
        # Extract user from token (optional)
        user_id = None
        if authorization:
            token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
            try:
                user_info = auth_service.verify_token(token)
                user_id = user_info.get("id")
            except:
                pass

        mrs = await repository_service.get_repository_mrs_from_db(repo_id, limit, user_id=user_id)
        return mrs
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to fetch repository MRs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/repositories/{repo_id}/policies")
async def get_repository_policies(repo_id: str, authorization: str = Header(None)):
    """Get active policies for a repository."""
    try:
        policies = repository_service.get_repository_policies(repo_id)
        return policies
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to fetch repository policies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/repositories/{repo_id}/feedback")
async def submit_mr_feedback(
    repo_id: str,
    request: dict,
    authorization: str = Header(None)
):
    """Submit feedback on AI analysis for a merge request."""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        mr_id = request.get("mr_id")
        vote = request.get("vote")
        comment = request.get("comment", "")

        if not mr_id or not vote:
            raise HTTPException(status_code=400, detail="Missing mr_id or vote")

        result = await repository_service.submit_mr_feedback(repo_id, mr_id, vote, comment, user_id)
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to submit feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/repositories/{repository_id}/mrs/{mr_iid}/execution")
async def get_mr_execution(
    repository_id: str,
    mr_iid: int,
    user: dict = Depends(require_jwt_user),
):
    """Resolve graph-backed ARIL execution for an MR (Copilot entry point)."""
    return await resolve_mr_execution_response(
        repository_id,
        mr_iid,
        str(user["id"]),
    )


@app.get("/api/repositories/{repo_id}/mrs/{mr_iid}/progress")
async def get_mr_progress_logs(repo_id: str, mr_iid: int, authorization: str = Header(None)):
    """Get progress logs for a specific merge request."""
    try:
        # Optional user verification
        if authorization:
            token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
            try:
                user_info = auth_service.verify_token(token)
            except:
                pass  # Token invalid, continue without user context

        logs = await repository_service.get_mr_progress_logs(repo_id, mr_iid)
        return {"logs": logs}
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to fetch progress logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/repositories/{repo_id}/scan", response_model=ScanRepositoryResponse)
async def scan_repo_credentials(
    repo_id: str,
    request: Optional[ScanRepositoryRequest] = None,
    authorization: str = Header(None)
):
    """Scans the repository's configuration files for MongoDB and Fivetran credentials."""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        branches = request.branches if request else None
        result = await repository_service.scan_repository(user_id, repo_id, branches)
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to scan repository: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/repositories/{repo_id}/onboard")
async def onboard_repo(repo_id: str, request: OnboardRepositoryRequest, authorization: str = Header(None)):
    """Saves repository connection details and connects it."""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        result = await repository_service.onboard_repository(user_id, repo_id, request.dict())
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to onboard repository: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/repositories/{repo_id}/credentials")
async def update_repository_credentials(repo_id: str, request: UpdateRepositoryRequest, authorization: str = Header(None)):
    """Updates repository credentials (MongoDB URI, Fivetran API keys, etc.)."""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        result = await repository_service.update_repository_credentials(repo_id, request.dict())
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to update repository credentials: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/repositories/{repo_id}/branches")
async def get_repository_branches(repo_id: str, authorization: str = Header(None)):
    """Get branches for a repository."""
    try:
        # Extract user from token
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Get user's GitLab token
        gitlab_token = None
        user_session = auth_service.get_user_session(user_id)
        if user_session:
            gitlab_token = user_session.get("gitlab_access_token")

        if not gitlab_token:
            # Fallback to env token
            gitlab_token = os.getenv("GITLAB_PERSONAL_ACCESS_TOKEN", "")

        branches = await repository_service.get_repository_branches(repo_id, gitlab_token)
        return {"branches": branches}
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to fetch branches: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/repositories/{repo_id}/install-webhook")
async def install_webhook_manually(repo_id: str, authorization: str = Header(None)):
    """Manually install or re-install webhook on a repository."""
    try:
        # Extract user from token
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Get user's GitLab token
        gitlab_token = None
        user_session = auth_service.get_user_session(user_id)
        if user_session:
            gitlab_token = user_session.get("gitlab_access_token")

        if not gitlab_token:
            gitlab_token = os.getenv("GITLAB_PERSONAL_ACCESS_TOKEN", "")

        # Install webhook (user_id passed to create and store project access token)
        result = await repository_service.install_gitlab_webhook(repo_id, gitlab_token, user_id)
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to install webhook manually: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/repositories/{repo_id}/connect")
async def connect_repository(repo_id: str, request: dict, authorization: str = Header(None)):
    """Connect a GitLab repository with optional branch selection."""
    try:
        # Extract user from token
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        target_branches = request.get("target_branches")

        result = await repository_service.connect_repository(user_id, repo_id, target_branches)
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to connect repository: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/repositories/{repo_id}/disconnect")
async def disconnect_repository(repo_id: str, authorization: str = Header(None)):
    """Disconnect a repository."""
    try:
        # Extract user from token
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        result = await repository_service.disconnect_repository(user_id, repo_id)
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to disconnect repository: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Settings Endpoints
# ============================================================================

@app.get("/api/settings/gemini", response_model=GeminiSettingsResponse)
async def get_gemini_settings(authorization: str = Header(None)):
    """Get user's Gemini API settings."""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Ensure user exists in MongoDB
        await user_service.ensure_user_exists(user_id, user_info)

        return await user_service.get_gemini_settings(user_id)
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to get Gemini settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/settings/gemini", response_model=GeminiSettingsResponse)
async def update_gemini_settings(request: UpdateGeminiSettingsRequest, authorization: str = Header(None)):
    """Update user's Gemini API settings."""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        return await user_service.update_gemini_settings(
            user_id,
            api_token=request.api_token,
            selected_model=request.selected_model
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to update Gemini settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/settings/gemini/validate", response_model=ValidateTokenResponse)
async def validate_gemini_token(request: ValidateTokenRequest):
    """Validate a Gemini API token."""
    try:
        return await user_service.validate_gemini_token(request.token)
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to validate Gemini token: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/settings/policies", response_model=PolicySettingsResponse)
async def get_policy_settings(authorization: str = Header(None)):
    """Get user's global policy settings."""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Ensure user exists in MongoDB
        await user_service.ensure_user_exists(user_id, user_info)

        return await user_service.get_policy_settings(user_id)
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to get policy settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/settings/policies", response_model=PolicySettingsResponse)
async def update_policy_settings(request: UpdatePolicySettingsRequest, authorization: str = Header(None)):
    """Update user's global policy settings."""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        return await user_service.update_policy_settings(
            user_id,
            auto_review_enabled=request.auto_review_enabled,
            strict_mode_enabled=request.strict_mode_enabled,
            email_alerts_enabled=request.email_alerts_enabled,
            slack_integration_enabled=request.slack_integration_enabled,
            max_review_depth=request.max_review_depth,
            timeout_seconds=request.timeout_seconds
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to update policy settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# User Profile Endpoints
# ============================================================================

@app.get("/api/user/profile", response_model=UserResponse)
async def get_user_profile(authorization: str = Header(None)):
    """Get user profile information."""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Ensure user exists in MongoDB
        await user_service.ensure_user_exists(user_id, user_info)

        return await user_service.get_user_profile(user_id)
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to get user profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/user/profile", response_model=UserResponse)
async def update_user_profile(request: UpdateUserProfileRequest, authorization: str = Header(None)):
    """Update user profile information."""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        profile_updates = {}
        if request.name:
            profile_updates["name"] = request.name
        if request.email:
            profile_updates["email"] = request.email
        if request.avatar_url:
            profile_updates["avatar_url"] = request.avatar_url

        return await user_service.update_user_profile(user_id, profile_updates)
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to update user profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Integrations Endpoints
# ============================================================================

@app.get("/api/integrations/gitlab", response_model=IntegrationStatusResponse)
async def get_gitlab_integration_status(authorization: str = Header(None)):
    """Get user's GitLab integration status."""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        return await user_service.get_gitlab_integration_status(user_id)
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to get GitLab integration status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/integrations/gitlab")
async def disconnect_gitlab_integration(authorization: str = Header(None)):
    """Disconnect user's GitLab integration."""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        return await user_service.disconnect_gitlab_integration(user_id)
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to disconnect GitLab integration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/debug/env")
async def debug_env():
    """Debug endpoint to check environment variables."""
    import os
    from dotenv import load_dotenv
    load_dotenv()
    return {
        "SENTRY_CLIENT_ID": os.getenv("SENTRY_CLIENT_ID", "NOT_SET"),
        "SENTRY_CLIENT_SECRET": os.getenv("SENTRY_CLIENT_SECRET", "NOT_SET")[:20] + "..." if os.getenv("SENTRY_CLIENT_SECRET") else "NOT_SET",
        "SENTRY_REDIRECT_URI": os.getenv("SENTRY_REDIRECT_URI", "NOT_SET"),
        "FRONTEND_URL": os.getenv("FRONTEND_URL", "NOT_SET"),
        "env_file_loaded": "YES"
    }

@app.get("/api/integrations/sentry/{repo_id}", response_model=SentryIntegrationResponse)
async def get_sentry_integration_status(repo_id: str, authorization: str = Header(None)):
    """Get Sentry integration status for a repository."""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)

        if not user_info:
            raise HTTPException(status_code=401, detail="Invalid token")

        from services.sentry_oauth_service import get_sentry_oauth_service
        service = get_sentry_oauth_service()
        status = await service.get_integration_status(repo_id)

        return SentryIntegrationResponse(**status)
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to get Sentry integration status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/integrations/sentry/{repo_id}/disconnect", response_model=SentryIntegrationDisconnectResponse)
async def disconnect_sentry_integration(repo_id: str, authorization: str = Header(None)):
    """Disconnect Sentry integration for a repository."""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)

        if not user_info:
            raise HTTPException(status_code=401, detail="Invalid token")

        from services.sentry_oauth_service import get_sentry_oauth_service
        service = get_sentry_oauth_service()
        result = await service.disconnect(repo_id)

        return SentryIntegrationDisconnectResponse(**result)
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to disconnect Sentry integration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Billing Endpoints
# ============================================================================

@app.get("/api/billing/usage", response_model=BillingUsageResponse)
async def get_billing_usage(authorization: str = Header(None)):
    """Get billing usage statistics for current user."""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Get billing data (using optimized single-document query)
        data = await billing_service.get_billing_dashboard_data_optimized(user_id)

        # Auto-sync if no usage data found (first visit or empty state)
        if data.get("total_tokens", 0) == 0 and data.get("estimated_cost", 0) == 0:
            print(f"[INFO] No billing data found for user {user_id}, triggering auto-sync from Arize...")
            sync_result = await billing_service.sync_user_billing_optimized(user_id=user_id)
            if sync_result.get("success"):
                print(f"[INFO] Auto-sync complete: {sync_result.get('synced', 0)} records synced")
                # Fetch updated data after sync
                data = await billing_service.get_billing_dashboard_data_optimized(user_id)

        return BillingUsageResponse(**data)

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Failed to get billing usage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/billing/sync")
async def sync_billing_data(
    request: SyncRequest,
    authorization: str = Header(None)
):
    """Sync billing data from Arize Cloud."""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        print(f"[INFO] /api/billing/sync called with user_id: {user_id} (type: {type(user_id).__name__})")

        # Sync from Arize Cloud (using optimized sync)
        result = await billing_service.sync_user_billing_optimized(
            user_id=user_id,
            force_resync=request.force_resync
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Failed to sync billing data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/billing/invoices")
async def get_invoices(
    limit: int = 12,
    authorization: str = Header(None)
):
    """Get invoice history."""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Get invoices (using optimized single-document query)
        invoices = await billing_service.get_user_invoices_optimized(user_id, limit)

        return [InvoiceResponse(**inv) for inv in invoices]

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Failed to get invoices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/billing/debug")
async def debug_billing(authorization: str = Header(None)):
    """Debug endpoint to check Phoenix connection and trace data."""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Check Arize status
        from config.arize_config import is_arize_initialized, is_phoenix_configured
        arize_status = {
            "arize_initialized": is_arize_initialized(),
            "phoenix_configured": is_phoenix_configured()
        }

        # Try to get Arize Cloud traces
        arize_data = {}
        try:
            from config.arize_client import get_arize_client
            client = await get_arize_client()
            arize_data["connected"] = client.is_connected()

            if client.is_connected():
                # Get recent traces
                traces = await client.get_recent_traces(limit=10, hours_ago=24)
                arize_data["trace_count"] = len(traces)
                arize_data["sample_traces"] = []

                for trace in traces[:3]:  # First 3 traces as samples
                    trace_id = trace.get("trace_id", "")
                    attributes = trace.get("attributes", {})
                    arize_data["sample_traces"].append({
                        "trace_id": trace_id[:16] + "..." if trace_id else "unknown",
                        "user_id": attributes.get("user_id"),
                        "mr_id": attributes.get("mr_id"),
                        "repository_id": attributes.get("repository_id"),
                        "operation_type": attributes.get("operation_type"),
                        "has_llm_input_tokens": "llm_input_tokens" in attributes,
                        "llm_input_tokens": attributes.get("llm_input_tokens"),
                        "llm_output_tokens": attributes.get("llm_output_tokens"),
                        "llm_model_name": attributes.get("llm_model_name"),
                        "attribute_keys": list(attributes.keys())
                    })
        except Exception as e:
            arize_data["error"] = str(e)

        # Check MongoDB for existing data
        mongo_data = {}
        try:
            from services import mongo_client
            cycles = await mongo_client.find(
                "billing_cycles",
                {"user_id": user_id},
                limit=5
            )
            mongo_data["billing_cycles_found"] = len(cycles)
            mongo_data["cycles"] = cycles

            usage_records = await mongo_client.find(
                "llm_usage_records",
                {"user_id": user_id},
                limit=5
            )
            mongo_data["usage_records_found"] = len(usage_records)
        except Exception as e:
            mongo_data["error"] = str(e)

        return {
            "user_id": user_id,
            "arize_status": arize_status,
            "arize_data": arize_data,
            "mongo_data": mongo_data
        }

    except Exception as e:
        import traceback
        return {"error": str(e), "trace": traceback.format_exc()}


@app.post("/api/billing/migrate")
async def migrate_billing_data(authorization: str = Header(None)):
    """
    Migrate legacy billing data to new single-document format.

    This is a one-time migration that should be run during deployment
    or manually by an admin.
    """
    try:
        # Require admin authorization (simplified - in production use proper admin check)
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)

        if not user_info:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Run migration
        result = await billing_service.migrate_billing_data_to_new_format()

        return result

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Failed to migrate billing data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/billing/summary-debug")
async def get_billing_summary_debug(authorization: str = Header(None)):
    """
    Debug endpoint to view the new billing summary document structure.

    Useful for verifying migration and debugging billing issues.
    """
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Get billing summary document
        from services import mongo_client
        doc = await mongo_client.find_one("billing_summaries", {"user_id": user_id})

        if not doc:
            return {
                "user_id": user_id,
                "message": "No billing summary found - may need to sync or migrate",
                "document": None
            }

        # Return clean version without internal _id
        return {
            "user_id": user_id,
            "document": {
                "sync_state": doc.get("sync_state", {}),
                "months_count": len(doc.get("months", {})),
                "months": list(doc.get("months", {}).keys()),
                "created_at": doc.get("created_at"),
                "updated_at": doc.get("updated_at")
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Failed to get billing summary debug: {e}")
        raise HTTPException(status_code=500, detail=str(e))
# ============================================================================
# GitNexus API Proxy Endpoints
# ============================================================================

@app.get("/api/grep")
async def gitnexus_grep_proxy(
    pattern: str = Query(...),
    repo: Optional[str] = None,
    limit: int = Query(100)
):
    """
    Proxy for GitNexus grep API.
    Converts GET /api/grep to GitNexus MCP tool call.
    """
    try:
        result = await gitnexus_manager.grep(pattern=pattern, repo=repo, limit=limit)
        return result
    except Exception as e:
        print(f"[ERROR] GitNexus grep proxy error: {e}")
        return {"error": str(e), "results": []}


@app.get("/api/file")
async def gitnexus_file_proxy(
    path: str = Query(...),
    repo: Optional[str] = None,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None
):
    """
    Proxy for GitNexus file read API.
    Converts GET /api/file to GitNexus MCP tool call.
    """
    try:
        result = await gitnexus_manager.file(
            path=path,
            repo=repo,
            start_line=start_line,
            end_line=end_line
        )
        return result
    except Exception as e:
        print(f"[ERROR] GitNexus file proxy error: {e}")
        return {"error": str(e)}


# ============================================================================