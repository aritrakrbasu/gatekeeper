"""
Authentication service for Gatekeeper.

Handles GitLab OAuth flow, JWT token generation/validation, and user session management.
Integrates with GitLab MCP to fetch user information.
"""

import os
import json
import secrets
import time
from typing import Optional, Dict
from datetime import datetime, timedelta
import httpx

from dotenv import load_dotenv
from fastapi import HTTPException, status

load_dotenv()

# ============================================================================
# Configuration
# ============================================================================

GITLAB_CLIENT_ID = os.getenv("GITLAB_CLIENT_ID", "")
GITLAB_CLIENT_SECRET = os.getenv("GITLAB_CLIENT_SECRET", "")
GITLAB_REDIRECT_URI = os.getenv("GITLAB_REDIRECT_URI", "http://localhost:5173/auth/callback")
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
GITLAB_BASE_URL = os.getenv("GITLAB_BASE_URL", "https://gitlab.com")

# JWT Configuration
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days
JWT_REFRESH_TOKEN_EXPIRE_DAYS = 30

# OAuth Scopes
GITLAB_SCOPES = ["read_user", "api", "read_repository"]

# In-memory OAuth state storage (in production, use Redis/Database)
_oauth_states: Dict[str, float] = {}
_user_sessions: Dict[str, Dict] = {}
_oauth_results: Dict[str, Dict] = {}  # Cache callback results for idempotency


# ============================================================================
# JWT Token Management
# ============================================================================

def create_jwt_token(payload: Dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT token with the given payload.

    Args:
        payload: Dictionary of claims to include in the token
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token string
    """
    try:
        import jwt
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT library not installed. Run: pip install pyjwt"
        )

    # Copy payload to avoid modifying original
    token_payload = payload.copy()

    # Set expiration time
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    token_payload.update({
        "exp": expire,
        "iat": datetime.utcnow()
    })

    # Encode token
    token = jwt.encode(token_payload, SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token


def decode_jwt_token(token: str) -> Dict:
    """
    Decode and validate a JWT token.

    Args:
        token: JWT token string to decode

    Returns:
        Decoded token payload

    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        import jwt
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT library not installed. Run: pip install pyjwt"
        )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


def create_access_token(user_data: Dict) -> str:
    """Create an access token for a user."""
    payload = {
        "sub": user_data.get("id"),
        "name": user_data.get("name"),
        "email": user_data.get("email"),
        "username": user_data.get("username"),
        "type": "access"
    }
    return create_jwt_token(payload)


def create_refresh_token(user_data: Dict) -> str:
    """Create a refresh token for a user."""
    payload = {
        "sub": user_data.get("id"),
        "type": "refresh"
    }
    return create_jwt_token(payload, timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS))


# ============================================================================
# OAuth State Management
# ============================================================================

def generate_oauth_state() -> str:
    """
    Generate a secure random state string for OAuth CSRF protection.

    Returns:
        Random state string
    """
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = time.time()
    return state


def validate_oauth_state(state: str) -> bool:
    """
    Validate an OAuth state parameter.

    Args:
        state: State string from OAuth callback

    Returns:
        True if state is valid, False otherwise
    """
    if state not in _oauth_states:
        return False

    # State expires after 10 minutes
    state_time = _oauth_states[state]
    if time.time() - state_time > 600:
        del _oauth_states[state]
        return False

    # State is valid - DON'T delete it yet
    # It will be deleted after the entire OAuth flow succeeds
    return True


def consume_oauth_state(state: str) -> bool:
    """
    Consume (delete) an OAuth state parameter after successful OAuth flow.

    Args:
        state: State string to consume

    Returns:
        True if state was found and deleted, False otherwise
    """
    if state in _oauth_states:
        del _oauth_states[state]
        return True
    return False


# ============================================================================
# GitLab OAuth Flow
# ============================================================================

def initiate_gitlab_oauth() -> Dict[str, str]:
    """
    Initiate the GitLab OAuth flow.

    Returns:
        Dictionary with oauth_url and state parameters

    Raises:
        HTTPException: If OAuth is not configured
    """
    if not GITLAB_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GitLab OAuth is not configured. Please set GITLAB_CLIENT_ID"
        )

    state = generate_oauth_state()

    # Build GitLab OAuth URL
    oauth_params = {
        "client_id": GITLAB_CLIENT_ID,
        "redirect_uri": GITLAB_REDIRECT_URI,
        "response_type": "code",
        "state": state,
        "scope": " ".join(GITLAB_SCOPES)
    }

    oauth_url = f"{GITLAB_BASE_URL}/oauth/authorize?{httpx.QueryParams(oauth_params)}"

    return {
        "oauth_url": oauth_url,
        "state": state
    }


async def handle_oauth_callback(code: str, state: str) -> Dict:
    """
    Handle the OAuth callback from GitLab.

    Args:
        code: Authorization code from GitLab
        state: State parameter for CSRF validation

    Returns:
        Dictionary with access_token, refresh_token, and user info

    Raises:
        HTTPException: If OAuth flow fails
    """
    # Check if we already have a cached result for this code (idempotency)
    cache_key = f"{code}:{state}"
    if cache_key in _oauth_results:
        print(f"[INFO] Returning cached OAuth result for {cache_key[:20]}...")
        return _oauth_results[cache_key]

    # Validate state (but don't consume it yet)
    if not validate_oauth_state(state):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state"
        )

    try:
        # Exchange authorization code for access token
        # Use longer timeout for GitLab OAuth (30 seconds)
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                token_response = await client.post(
                    f"{GITLAB_BASE_URL}/oauth/token",
                    data={
                        "client_id": GITLAB_CLIENT_ID,
                        "client_secret": GITLAB_CLIENT_SECRET,
                        "code": code,
                        "grant_type": "authorization_code",
                        "redirect_uri": GITLAB_REDIRECT_URI
                    },
                    headers={"Accept": "application/json"}
                )
                token_response.raise_for_status()
                token_data = token_response.json()

                # Fetch user information
                user_response = await client.get(
                    f"{GITLAB_BASE_URL}/api/v4/user",
                    headers={"Authorization": f"Bearer {token_data['access_token']}"}
                )
                user_response.raise_for_status()
                user_data = user_response.json()

            except httpx.HTTPStatusError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to exchange authorization code: {e.response.text}"
                )
            except httpx.RequestError as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to connect to GitLab: {str(e)}"
                )

        # Create user session
        user_info = {
            "id": str(user_data["id"]),
            "name": user_data.get("name", ""),
            "username": user_data.get("username", ""),
            "email": user_data.get("email", ""),
            "avatar_url": user_data.get("avatar_url"),
            "created_at": user_data.get("created_at", datetime.utcnow().isoformat())
        }

        # Store GitLab access token for later use
        gitlab_tokens = {
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token")
        }
        _user_sessions[user_info["id"]] = {
            "user": user_info,
            "gitlab_access_token": gitlab_tokens["access_token"],
            "gitlab_refresh_token": gitlab_tokens["refresh_token"],
            "gitlab_token_expires_at": datetime.utcnow() + timedelta(seconds=token_data.get("expires_in", 7200))
        }

        # Create user in MongoDB (if not exists)
        try:
            from services.user_service import ensure_user_exists
            await ensure_user_exists(user_info["id"], user_info, gitlab_tokens)
            print(f"[OK] User {user_info['id']} ensured in MongoDB")
        except Exception as e:
            # Don't block login if MongoDB fails
            print(f"[WARN] Failed to create user in MongoDB: {e}")

        # Create JWT tokens
        access_token = create_access_token(user_info)
        refresh_token = create_refresh_token(user_info)

        result = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user": user_info
        }

        # Cache the result for idempotency (expires in 5 minutes)
        _oauth_results[cache_key] = result
        # Clean up old cache entries
        for key in list(_oauth_results.keys()):
            if key != cache_key:  # Keep only current, remove old ones
                del _oauth_results[key]

        # Consume the OAuth state only after everything succeeds
        consume_oauth_state(state)
        print(f"[INFO] OAuth flow completed successfully for user {user_info['id']}")

        return result

    except Exception as e:
        # Log the error for debugging
        print(f"[ERROR] OAuth callback failed: {e}")
        import traceback
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        raise


# ============================================================================
# Token Verification
# ============================================================================

def verify_token(token: str) -> Dict:
    """
    Verify a JWT access token and return user information.

    Args:
        token: JWT access token

    Returns:
        Dictionary with user information if token is valid

    Raises:
        HTTPException: If token is invalid
    """
    payload = decode_jwt_token(token)

    # Check if it's an access token
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type"
        )

    # Get user ID from token
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )

    # Check if user session exists
    if user_id not in _user_sessions:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User session not found. Please login again"
        )

    user_info = _user_sessions[user_id]["user"]
    return user_info


# ============================================================================
# Session Management
# ============================================================================

def logout_user(token: str) -> Dict:
    """
    Logout a user by invalidating their session.

    Args:
        token: JWT access token

    Returns:
        Dictionary with logout confirmation
    """
    try:
        payload = decode_jwt_token(token)
        user_id = payload.get("sub")

        if user_id and user_id in _user_sessions:
            del _user_sessions[user_id]

        return {"message": "Successfully logged out"}
    except Exception:
        # Even if token is invalid, return success
        return {"message": "Successfully logged out"}


def get_user_session(user_id: str) -> Optional[Dict]:
    """
    Get a user's session data including GitLab tokens.

    Args:
        user_id: User ID

    Returns:
        Session data or None if not found
    """
    return _user_sessions.get(user_id)


# ============================================================================
# Health Check
# ============================================================================

def is_configured() -> bool:
    """Check if OAuth is properly configured."""
    return bool(GITLAB_CLIENT_ID and GITLAB_CLIENT_SECRET)
