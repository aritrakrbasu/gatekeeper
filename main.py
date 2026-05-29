import os
import asyncio
from typing import Optional
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

# Import Gatekeeper Services
from services import mcp_service, review_service, auth_service, repository_service, mongo_client, webhook_service
from api_models import (
    OAuthCallbackRequest, TokenResponse, UserResponse,
    VerifyTokenRequest, VerifyTokenResponse, LogoutResponse,
    RepositoryResponse, MergeRequestResponse, ScanRepositoryResponse,
    OnboardRepositoryRequest, UpdateRepositoryRequest, UpdateRepositoryResponse,
    BranchListResponse, UpdateBranchesRequest, InstallWebhookRequest, WebhookResponse
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
    print("[*] MCP Bridge initialization starting in background...")

    # Check if GitNexus is installed
    try:
        import subprocess
        from services.mcp_service import GITNEXUS_CMD
        result = subprocess.run(
            [GITNEXUS_CMD, "--version"],
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

    # Close Phoenix MCP bridge (if initialized)
    try:
        if 'phoenix_bridge' in globals() and phoenix_bridge:
            await close_phoenix_bridge()
            phoenix_bridge = None
            print("[✅] Phoenix MCP bridge closed")
    except Exception as e:
        print(f"[⚠️] Error closing Phoenix bridge: {e}")

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
    """Health check endpoint to verify MCP bridge status."""
    phoenix_connected = False
    if 'phoenix_bridge' in globals() and phoenix_bridge:
        phoenix_connected = phoenix_bridge.is_connected()

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
    # Check if MCP sessions are ready
    if not mcp_service.mcp_ready or not mcp_service.gitlab_session:
        print("[⚠️] MCP sessions not ready yet - cannot process webhook")
        print("[ℹ️] Please wait a few seconds for the MCP bridge to initialize")
        return {"status": "mcp_not_ready", "message": "MCP sessions still initializing. Please retry in a few seconds."}

    if not x_gitlab_event:
        raise HTTPException(status_code=400, detail="Missing X-GitLab-Event header")

    payload = await request.json()

    if x_gitlab_event == "Merge Request Hook":
        # Run review pipeline
        return await review_service.orchestrate_review(payload)

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

        mrs = await repository_service.get_repository_mrs_from_db(repo_id, limit)
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
async def scan_repo_credentials(repo_id: str, authorization: str = Header(None)):
    """Scans the repository's configuration files for MongoDB and Fivetran credentials."""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        result = await repository_service.scan_repository(user_id, repo_id)
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


@app.post("/api/repositories/{repo_id}/connect")
async def connect_repository(repo_id: str, authorization: str = Header(None)):
    """Connect a GitLab repository."""
    try:
        # Extract user from token
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        result = await repository_service.connect_repository(user_id, repo_id)
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
# Branch & Webhook Endpoints
# ============================================================================


@app.get("/api/repositories/{repo_id}/branches", response_model=BranchListResponse)
async def get_repository_branches(
    repo_id: str,
    q: str = "",
    authorization: str = Header(None)
):
    """Fetch all branches for a repository."""
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        branches = await repository_service.get_gitlab_branches(repo_id, user_id, q)

        # Find default branch
        default_branch = "main"
        for branch in branches:
            if branch.get("is_default"):
                default_branch = branch["name"]
                break

        return BranchListResponse(
            branches=branches,
            default_branch=default_branch,
            total_count=len(branches)
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to fetch repository branches: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/repositories/{repo_id}/branches")
async def update_monitored_branches(
    repo_id: str,
    request: UpdateBranchesRequest,
    authorization: str = Header(None)
):
    """
    Update the list of monitored branches for a repository.
    Branch filtering is applied server-side during webhook processing.
    """
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Update repository document with new monitored branches
        if repository_service.MONGO_CONNECTION_STRING:
            await repository_service.mongo_client.update_one(
                collection_name=repository_service.REPOS_COLLECTION,
                filter={"id": repo_id},
                update={
                    "$set": {
                        "monitored_branches": request.monitored_branches,
                        "branch_filter_enabled": request.branch_filter_enabled
                    }
                }
            )
            print(f"[✅] Updated monitored branches for repo {repo_id}: {request.monitored_branches if request.monitored_branches else 'All branches'}")

            # Update webhook if exists (currently just updates DB, webhook doesn't support branch filtering at API level)
            # The filtering is applied server-side in review_service.py

            return {
                "message": "Branch filter updated successfully",
                "monitored_branches": request.monitored_branches,
                "branch_filter_enabled": request.branch_filter_enabled
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="MongoDB connection not available"
            )
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to update monitored branches: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/repositories/{repo_id}/webhook", response_model=WebhookResponse)
async def install_webhook(
    repo_id: str,
    request: InstallWebhookRequest,
    authorization: str = Header(None)
):
    """
    Install a GitLab webhook for the repository.
    The webhook will send merge request events to Gatekeeper.
    """
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Install webhook via GitLab API
        result = await webhook_service.install_gitlab_webhook(
            repo_id=repo_id,
            user_id=user_id,
            monitored_branches=request.monitored_branches,
            custom_webhook_url=request.webhook_url
        )

        # Update repository document with webhook info
        if repository_service.MONGO_CONNECTION_STRING:
            await repository_service.mongo_client.update_one(
                collection_name=repository_service.REPOS_COLLECTION,
                filter={"id": repo_id},
                update={
                    "$set": {
                        "webhook_installed": True,
                        "webhook_id": result.get("webhook_id"),
                        "monitored_branches": request.monitored_branches,
                        "branch_filter_enabled": request.branch_filter_enabled
                    }
                }
            )
            print(f"[✅] Updated repo {repo_id} with webhook info")

        return WebhookResponse(**result)

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to install webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/repositories/{repo_id}/webhook")
async def delete_webhook(
    repo_id: str,
    authorization: str = Header(None)
):
    """
    Delete the GitLab webhook for a repository.
    """
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")

        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        user_info = auth_service.verify_token(token)
        user_id = user_info.get("id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Get webhook_id from repository
        repo = await repository_service.get_repository(repo_id)
        webhook_id = repo.get("webhook_id")

        if not webhook_id:
            raise HTTPException(
                status_code=404,
                detail="No webhook found for this repository"
            )

        # Delete webhook via GitLab API
        result = await webhook_service.delete_gitlab_webhook(
            repo_id=repo_id,
            user_id=user_id,
            webhook_id=webhook_id
        )

        # Update repository document
        if repository_service.MONGO_CONNECTION_STRING:
            await repository_service.mongo_client.update_one(
                collection_name=repository_service.REPOS_COLLECTION,
                filter={"id": repo_id},
                update={
                    "$set": {
                        "webhook_installed": False,
                        "webhook_id": None
                    }
                }
            )
            print(f"[✅] Removed webhook info from repo {repo_id}")

        return result

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] Failed to delete webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))



