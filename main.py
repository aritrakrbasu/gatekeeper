import os
import sys
import asyncio
import time
import json
import re
from typing import Optional
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from google.genai import types

# Fix Windows console encoding for emoji characters
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    # Fix Windows subprocess issue with asyncio - MUST be set before event loop is created
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

load_dotenv()

# Import Gatekeeper Services
from services import (
    mcp_service, review_service, auth_service, repository_service,
    mongo_client, user_service, billing_service, incident_service
)
from api_models import (
    OAuthCallbackRequest, TokenResponse, UserResponse,
    VerifyTokenRequest, VerifyTokenResponse, LogoutResponse,
    RepositoryResponse, MergeRequestResponse, ScanRepositoryResponse, ScanRepositoryRequest,
    OnboardRepositoryRequest, UpdateRepositoryRequest, UpdateRepositoryResponse,
    GeminiSettingsResponse, ValidateTokenRequest, ValidateTokenResponse,
    PolicySettingsResponse, UpdateGeminiSettingsRequest, UpdatePolicySettingsRequest,
    UpdateUserProfileRequest, IntegrationStatusResponse,
    SyncRequest, BillingUsageResponse, InvoiceResponse
)

app = FastAPI(title="The Gatekeeper Gemini Orchestrator")

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
    print("[*] MCP Bridge initialization starting in background...")

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

    # Launch Stdio MCP pipes in the background
    asyncio.create_task(mcp_service.boot_mcp_bridge())


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
        "nexus_connected": mcp_service.nexus_session is not None
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
    sys.stderr.write(f"\n[WEBHOOK HIT!] X-GitLab-Event: {x_gitlab_event}\n")
    sys.stderr.flush()

    print(f"[DEBUG] ===== WEBHOOK RECEIVED =====", flush=True)
    print(f"[DEBUG] X-GitLab-Event header: {x_gitlab_event}", flush=True)
    print(f"[DEBUG] MCP ready: {mcp_service.mcp_ready}", flush=True)
    print(f"[DEBUG] GitLab session: {mcp_service.gitlab_session is not None}", flush=True)

    # Check if MCP sessions are ready
    if not mcp_service.mcp_ready or not mcp_service.gitlab_session:
        print("[⚠️] MCP sessions not ready yet - cannot process webhook")
        print("[ℹ️] Please wait a few seconds for the MCP bridge to initialize")
        return {"status": "mcp_not_ready", "message": "MCP sessions still initializing. Please retry in a few seconds."}

    payload = await request.json()

    # 1. Handle GitLab Merge Request Event
    if x_gitlab_event == "Merge Request Hook":
        return await review_service.orchestrate_review(payload)

    # 2. Handle Dynatrace Incident/Production Crash Event
    if not x_gitlab_event:
        if isinstance(payload, dict) and "problem_id" in payload:
            return await incident_service.process_production_crash(payload)

    return {"status": "event_ignored", "event": x_gitlab_event}


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
