"""
User service for Gatekeeper.

Manages user data, settings, and preferences stored in the MongoDB users collection.
Each user has their own Gemini API configuration and policy preferences.
"""

import os
import httpx
from typing import Optional, Dict
from datetime import datetime
from fastapi import HTTPException, status

from dotenv import load_dotenv
from api_models import (
    UserResponse,
    GeminiSettingsResponse,
    GeminiModel,
    ValidateTokenResponse,
    PolicySettingsResponse,
    IntegrationStatusResponse
)
from services.mongo_client import get_database
from services.encryption_service import encrypt_value, decrypt_value

load_dotenv()


# ============================================================================
# User CRUD Operations
# ============================================================================

async def get_user(user_id: str) -> Optional[Dict]:
    """
    Get full user document from MongoDB.

    Args:
        user_id: User ID from GitLab OAuth

    Returns:
        User document or None if not found
    """
    try:
        db = await get_database()
        user = await db.users.find_one({"_id": user_id})
        return user
    except Exception as e:
        print(f"[ERROR] Failed to get user: {e}")
        return None


async def update_user(user_id: str, updates: Dict) -> Dict:
    """
    Update user document in MongoDB.

    Args:
        user_id: User ID
        updates: Dictionary of fields to update

    Returns:
        Updated user document
    """
    try:
        db = await get_database()

        # Always update the updated_at timestamp
        updates["updated_at"] = datetime.utcnow()

        result = await db.users.update_one(
            {"_id": user_id},
            {"$set": updates}
        )

        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        return await get_user(user_id)
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Failed to update user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update user: {str(e)}"
        )


async def create_user(user_id: str, user_info: Dict, gitlab_tokens: Dict = None) -> Dict:
    """
    Create a new user document in MongoDB.

    Args:
        user_id: User ID from GitLab
        user_info: User profile information
        gitlab_tokens: Optional GitLab access tokens

    Returns:
        Created user document
    """
    try:
        db = await get_database()

        # Prepare user document
        user_doc = {
            "_id": user_id,
            "profile": {
                "name": user_info.get("name", ""),
                "username": user_info.get("username", ""),
                "email": user_info.get("email", ""),
                "avatar_url": user_info.get("avatar_url"),
                "created_at": datetime.utcnow()
            },
            "gitlab": {
                "connected": True,
                "access_token_encrypted": encrypt_value(gitlab_tokens.get("access_token", "")) if gitlab_tokens else "",
                "refresh_token_encrypted": encrypt_value(gitlab_tokens.get("refresh_token", "")) if gitlab_tokens else "",
                "instance_url": user_info.get("instance_url", "https://gitlab.com"),
                "connected_at": datetime.utcnow(),
                "last_used": datetime.utcnow()
            } if gitlab_tokens else {"connected": False},
            "gemini": {
                "api_token_encrypted": "",
                "selected_model": GeminiModel.GEMINI_3_5_FLASH,
                "token_configured": False,
                "validated_at": None
            },
            "preferences": {
                "auto_review_enabled": True,
                "strict_mode_enabled": False,
                "email_alerts_enabled": True,
                "max_review_depth": 5,
                "timeout_seconds": 300
            },
            "updated_at": datetime.utcnow()
        }

        await db.users.insert_one(user_doc)
        return user_doc
    except Exception as e:
        print(f"[ERROR] Failed to create user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create user: {str(e)}"
        )


async def ensure_user_exists(user_id: str, user_info: Dict, gitlab_tokens: Dict = None) -> Dict:
    """
    Ensure user exists in MongoDB, create if not exists.

    Args:
        user_id: User ID
        user_info: User profile information
        gitlab_tokens: Optional GitLab access tokens

    Returns:
        User document
    """
    user = await get_user(user_id)
    if not user:
        user = await create_user(user_id, user_info, gitlab_tokens)
    return user


# ============================================================================
# User Profile Operations
# ============================================================================

async def get_user_profile(user_id: str) -> UserResponse:
    """
    Get user profile information.

    Args:
        user_id: User ID

    Returns:
        User profile response
    """
    user = await get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    profile = user.get("profile", {})
    return UserResponse(
        id=user_id,
        name=profile.get("name", ""),
        username=profile.get("username", ""),
        email=profile.get("email", ""),
        avatar_url=profile.get("avatar_url"),
        created_at=profile.get("created_at", datetime.utcnow())
    )


async def update_user_profile(user_id: str, profile_updates: Dict) -> UserResponse:
    """
    Update user profile information.

    Args:
        user_id: User ID
        profile_updates: Dictionary of profile fields to update

    Returns:
        Updated user profile response
    """
    user = await get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Build update dictionary for profile fields
    profile_updates_filtered = {}
    if "name" in profile_updates:
        profile_updates_filtered["profile.name"] = profile_updates["name"]
    if "email" in profile_updates:
        profile_updates_filtered["profile.email"] = profile_updates["email"]
    if "avatar_url" in profile_updates:
        profile_updates_filtered["profile.avatar_url"] = profile_updates["avatar_url"]

    await update_user(user_id, profile_updates_filtered)
    return await get_user_profile(user_id)


# ============================================================================
# Gemini Settings Operations
# ============================================================================

async def get_gemini_settings(user_id: str) -> GeminiSettingsResponse:
    """
    Get user's Gemini API settings.

    Args:
        user_id: User ID

    Returns:
        Gemini settings response
    """
    user = await get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    gemini_config = user.get("gemini", {})
    return GeminiSettingsResponse(
        api_token_configured=gemini_config.get("token_configured", False),
        selected_model=gemini_config.get("selected_model", GeminiModel.GEMINI_3_5_FLASH),
        model_options=[GeminiModel.GEMINI_3_5_FLASH, GeminiModel.GEMINI_3_1_PRO_PREVIEW]
    )


async def update_gemini_settings(user_id: str, api_token: Optional[str] = None, selected_model: str = None) -> GeminiSettingsResponse:
    """
    Update user's Gemini API settings.

    Args:
        user_id: User ID
        api_token: New Gemini API token (will be encrypted)
        selected_model: Selected Gemini model

    Returns:
        Updated Gemini settings response
    """
    user = await get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
    )

    updates = {}
    if api_token is not None:
        updates["gemini.api_token_encrypted"] = encrypt_value(api_token)
        updates["gemini.token_configured"] = True
        updates["gemini.validated_at"] = datetime.utcnow()
    if selected_model is not None:
        updates["gemini.selected_model"] = selected_model

    await update_user(user_id, updates)
    return await get_gemini_settings(user_id)


async def validate_gemini_token(token: str) -> ValidateTokenResponse:
    """
    Validate a Gemini API token by making a test request.

    Args:
        token: Gemini API token to validate

    Returns:
        Validation response
    """
    if not token:
        return ValidateTokenResponse(
            valid=False,
            message="Token is required"
        )

    try:
        # Make a simple test request to Gemini API to list models
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={token}"
            )

            if response.status_code == 200:
                return ValidateTokenResponse(
                    valid=True,
                    message="Token is valid"
                )
            elif response.status_code == 401 or response.status_code == 403:
                error_text = response.text
                return ValidateTokenResponse(
                    valid=False,
                    message=f"Invalid token or unauthorized: {error_text[:200]}"
                )
            else:
                return ValidateTokenResponse(
                    valid=False,
                    message=f"Validation failed (HTTP {response.status_code}): {response.text[:200]}"
                )
    except httpx.TimeoutException:
        return ValidateTokenResponse(
            valid=False,
            message="Request timed out"
        )
    except Exception as e:
        return ValidateTokenResponse(
            valid=False,
            message=f"Validation error: {str(e)}"
        )


async def get_user_gemini_config(user_id: str) -> Dict:
    """
    Get user's decrypted Gemini API token and model preference.
    Used by review_service for making Gemini API calls.

    Args:
        user_id: User ID

    Returns:
        Dictionary with decrypted API token and model

    Raises:
        HTTPException: If Gemini not configured for user
    """
    user = await get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    gemini_config = user.get("gemini", {})
    encrypted_token = gemini_config.get("api_token_encrypted", "")

    if not encrypted_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gemini API not configured for user. Please configure it in Settings."
        )

    decrypted_token = decrypt_value(encrypted_token)
    if not decrypted_token or decrypted_token == encrypted_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gemini API token is invalid or corrupted"
        )

    return {
        "api_token": decrypted_token,
        "model": gemini_config.get("selected_model", "gemini-3.5-flash"),
        "user_id": user_id
    }


async def get_user_gitlab_token(user_id: str, project_id: str) -> Optional[str]:
    """
    Get user's project-specific GitLab access token from project_tokens.

    Args:
        user_id: User ID
        project_id: Project ID to get project-specific token from project_tokens

    Returns:
        GitLab access token or None if not found
    """
    try:
        # Try to get from in-memory session first (most reliable for active users)
        from services import auth_service
        user_session = auth_service.get_user_session(user_id)
        if user_session and user_session.get("project_tokens", {}).get(project_id):
            token = user_session.get("project_tokens", {}).get(project_id)
            return token

        # Fall back to decrypting from MongoDB (for webhook processing when session not active)
        print(f"[INFO] No in-memory session for user {user_id}, trying MongoDB...")
        user = await get_user(user_id)
        if not user:
            print(f"[WARN] User {user_id} not found when fetching GitLab token")
            return None

        # Get project-specific token from project_tokens
        project_tokens = user.get("project_tokens", {})
        project_token_data = project_tokens.get(project_id, {})
        encrypted_token = project_token_data.get("token_encrypted", "")
        if not encrypted_token:
            print(f"[WARN] No project token found for user {user_id}, project {project_id}")
            return None

        decrypted_token = decrypt_value(encrypted_token)
        if not decrypted_token or decrypted_token == encrypted_token:
            print(f"[WARN] Project token decryption failed for user {user_id}, project {project_id}")
            return None

        print(f"[OK] Retrieved project-specific GitLab token for user {user_id}, project {project_id}")
        return decrypted_token
    except Exception as e:
        print(f"[ERROR] Failed to get GitLab token for user {user_id}, project {project_id}: {e}")
        return None


async def refresh_gitlab_token(user_id: str) -> Optional[Dict]:
    """
    Refresh the user's GitLab access token using their refresh token.

    Args:
        user_id: User ID

    Returns:
        Dictionary with new access_token and refresh_token, or None if refresh fails
    """
    import httpx
    from dotenv import load_dotenv
    load_dotenv()

    try:
        user = await get_user(user_id)
        if not user:
            print(f"[WARN] User {user_id} not found when refreshing GitLab token")
            return None

        gitlab_config = user.get("gitlab", {})
        if not gitlab_config.get("connected", False):
            print(f"[WARN] GitLab not connected for user {user_id}")
            return None

        encrypted_refresh_token = gitlab_config.get("refresh_token_encrypted", "")
        if not encrypted_refresh_token:
            print(f"[WARN] No GitLab refresh token found for user {user_id}")
            return None

        refresh_token = decrypt_value(encrypted_refresh_token)
        if not refresh_token or refresh_token == encrypted_refresh_token:
            print(f"[WARN] GitLab refresh token decryption failed for user {user_id}")
            return None

        # Get OAuth credentials
        client_id = os.getenv("GITLAB_CLIENT_ID", "")
        client_secret = os.getenv("GITLAB_CLIENT_SECRET", "")
        redirect_uri = os.getenv("GITLAB_REDIRECT_URI", "")
        gitlab_base_url = os.getenv("GITLAB_BASE_URL", "https://gitlab.com")

        if not client_id or not client_secret:
            print(f"[ERROR] GitLab OAuth credentials not configured")
            return None

        # Refresh the token
        print(f"[INFO] Refreshing GitLab token for user {user_id}...")
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{gitlab_base_url}/oauth/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri
                },
                headers={"Accept": "application/json"}
            )

            if response.status_code != 200:
                print(f"[ERROR] GitLab token refresh failed: {response.text}")
                return None

            token_data = response.json()

            # Update user's tokens in MongoDB
            new_access_token = token_data.get("access_token")
            new_refresh_token = token_data.get("refresh_token", refresh_token)  # Use old refresh token if not returned

            updates = {
                "gitlab.access_token_encrypted": encrypt_value(new_access_token),
                "gitlab.refresh_token_encrypted": encrypt_value(new_refresh_token),
                "gitlab.last_used": datetime.utcnow()
            }

            await update_user(user_id, updates)
            print(f"[OK] GitLab token refreshed successfully for user {user_id}")

            return {
                "access_token": new_access_token,
                "refresh_token": new_refresh_token
            }

    except Exception as e:
        print(f"[ERROR] Failed to refresh GitLab token for user {user_id}: {e}")
        return None


# ============================================================================
# Policy Settings Operations
# ============================================================================

async def get_policy_settings(user_id: str) -> PolicySettingsResponse:
    """
    Get user's global policy settings.

    Args:
        user_id: User ID

    Returns:
        Policy settings response
    """
    user = await get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    preferences = user.get("preferences", {})
    return PolicySettingsResponse(
        auto_review_enabled=preferences.get("auto_review_enabled", True),
        strict_mode_enabled=preferences.get("strict_mode_enabled", False),
        email_alerts_enabled=preferences.get("email_alerts_enabled", True),
        slack_integration_enabled=preferences.get("slack_integration_enabled", False),
        max_review_depth=preferences.get("max_review_depth", 5),
        timeout_seconds=preferences.get("timeout_seconds", 300)
    )


async def update_policy_settings(
    user_id: str,
    auto_review_enabled: bool = None,
    strict_mode_enabled: bool = None,
    email_alerts_enabled: bool = None,
    slack_integration_enabled: bool = None,
    max_review_depth: int = None,
    timeout_seconds: int = None
) -> PolicySettingsResponse:
    """
    Update user's global policy settings.

    Args:
        user_id: User ID
        auto_review_enabled: Auto-review toggle
        strict_mode_enabled: Strict mode toggle
        email_alerts_enabled: Email alerts toggle
        slack_integration_enabled: Slack integration toggle
        max_review_depth: Maximum review depth
        timeout_seconds: Review timeout

    Returns:
        Updated policy settings response
    """
    user = await get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Build update dictionary for provided fields
    updates = {}
    if auto_review_enabled is not None:
        updates["preferences.auto_review_enabled"] = auto_review_enabled
    if strict_mode_enabled is not None:
        updates["preferences.strict_mode_enabled"] = strict_mode_enabled
    if email_alerts_enabled is not None:
        updates["preferences.email_alerts_enabled"] = email_alerts_enabled
    if slack_integration_enabled is not None:
        updates["preferences.slack_integration_enabled"] = slack_integration_enabled
    if max_review_depth is not None:
        updates["preferences.max_review_depth"] = max_review_depth
    if timeout_seconds is not None:
        updates["preferences.timeout_seconds"] = timeout_seconds

    await update_user(user_id, updates)
    return await get_policy_settings(user_id)


# ============================================================================
# Integration Status Operations
# ============================================================================

async def get_gitlab_integration_status(user_id: str) -> IntegrationStatusResponse:
    """
    Get user's GitLab integration status.

    Args:
        user_id: User ID

    Returns:
        Integration status response
    """
    user = await get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    gitlab_config = user.get("gitlab", {})
    return IntegrationStatusResponse(
        provider="gitlab",
        connected=gitlab_config.get("connected", False),
        configured_at=gitlab_config.get("connected_at"),
        last_used=gitlab_config.get("last_used")
    )


async def disconnect_gitlab_integration(user_id: str) -> Dict:
    """
    Disconnect user's GitLab integration.

    Args:
        user_id: User ID

    Returns:
        Disconnect confirmation
    """
    user = await get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
    )

    updates = {
        "gitlab.connected": False,
        "gitlab.access_token_encrypted": "",
        "gitlab.refresh_token_encrypted": ""
    }
    await update_user(user_id, updates)

    return {"message": "GitLab integration disconnected successfully"}
