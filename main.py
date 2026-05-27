import os
import asyncio
from fastapi import FastAPI, Request, Header, HTTPException
from dotenv import load_dotenv

load_dotenv()

# Import Gatekeeper Services
from services import mcp_service, review_service

app = FastAPI(title="The Gatekeeper Gemini Orchestrator")


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
    global phoenix_bridge

    print("[*] Shutting down Gatekeeper service...")

    # Close Phoenix MCP bridge
    if phoenix_bridge:
        try:
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
    if phoenix_bridge:
        phoenix_connected = phoenix_bridge.is_connected()

    return {
        "status": "healthy",
        "mcp_ready": mcp_service.mcp_ready,
        "mongo_connected": mcp_service.mongo_session is not None,
        "gitlab_connected": mcp_service.gitlab_session is not None,
        "nexus_connected": mcp_service.nexus_session is not None
    }


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
