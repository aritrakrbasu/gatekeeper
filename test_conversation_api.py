"""
Simple test script for /api/copilot/conversations endpoint
Uses test infrastructure with dependency overrides
"""
import sys
sys.path.insert(0, '.')

from fastapi import FastAPI
from fastapi.testclient import TestClient
from copilot.api.router import copilot_router, _copilot_service
from peil.api.auth import require_jwt_user
from peil.store.execution_repository import ExecutionRepository
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()

# MongoDB setup
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "gatekeeper")

# Create app
app = FastAPI()
app.include_router(copilot_router)

# Test data
USER_ID = "test-user-123"

def mock_user():
    return {"id": USER_ID, "username": "test"}

def mock_service():
    """Create a mock service with real database connection"""
    from copilot.api.service import CopilotService
    from motor.motor_asyncio import AsyncIOMotorClient
    import os

    client = AsyncIOMotorClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017"))
    db = client[os.getenv("MONGODB_DB", "gatekeeper")]
    return CopilotService(db)

# Override dependencies
app.dependency_overrides[require_jwt_user] = mock_user
app.dependency_overrides[_copilot_service] = mock_service

# Test payload
payload = {
    "repository_id": "82677447",
    "execution_id": "59b09581-e48c-42a2-9292-5332ab33aebc",
    "mr_iid": 1
}

print("Testing POST /api/copilot/conversations")
print(f"Payload: {payload}")
print("-" * 50)

with TestClient(app) as client:
    try:
        response = client.post(
            "/api/copilot/conversations",
            json=payload
        )
        print(f"Status Code: {response.status_code}")
        print(f"Response Body:")
        print(response.text)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
