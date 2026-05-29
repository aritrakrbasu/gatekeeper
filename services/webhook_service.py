"""
GitLab Webhook Management Service

Handles installation, updating, and deletion of GitLab webhooks
for Gatekeeper integration. Supports branch-based filtering
for merge request events.
"""

import os
import httpx
from typing import List, Dict, Optional
from fastapi import HTTPException, status
from dotenv import load_dotenv

load_dotenv()

# GitLab configuration
GITLAB_BASE_URL = os.getenv("GITLAB_BASE_URL", "https://gitlab.com")
GITLAB_PERSONAL_ACCESS_TOKEN = os.getenv("GITLAB_PERSONAL_ACCESS_TOKEN", "")

# Webhook events we want to monitor
WEBHOOK_EVENTS = ["merge_requests"]


def _get_webhook_url() -> str:
    """
    Get the webhook URL for Gatekeeper.

    Constructs from environment variables or uses localhost for development.

    Returns:
        Webhook URL string
    """
    base_url = os.getenv("BASE_URL", os.getenv("FRONTEND_URL", "http://localhost:8000"))
    return f"{base_url}/webhooks/gitlab"


async def install_gitlab_webhook(
    repo_id: str,
    user_id: str,
    monitored_branches: List[str],
    custom_webhook_url: Optional[str] = None
) -> Dict:
    """
    Install a webhook on a GitLab repository.

    Args:
        repo_id: GitLab project ID
        user_id: User ID for authentication
        monitored_branches: List of branches to monitor (empty = all branches)
        custom_webhook_url: Optional custom webhook URL

    Returns:
        Webhook installation result with webhook ID

    Raises:
        HTTPException: If installation fails
    """
    from services import auth_service

    # Get user's GitLab token
    gitlab_token = None
    user_session = auth_service.get_user_session(user_id)
    if user_session:
        gitlab_token = user_session.get("gitlab_access_token")

    if not gitlab_token:
        gitlab_token = GITLAB_PERSONAL_ACCESS_TOKEN

    if not gitlab_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No GitLab access token available"
        )

    # Use custom URL or default
    webhook_url = custom_webhook_url or _get_webhook_url()

    headers = {"Authorization": f"Bearer {gitlab_token}"}

    # GitLab webhook payload
    webhook_data = {
        "url": webhook_url,
        "merge_requests_events": True,
        "push_events": False,
        "issues_events": False,
        "wiki_page_events": False,
        "deployment_events": False,
        "releases_events": False,
        "tag_push_events": False,
        "note_events": False,
        "confidential_note_events": False,
        "job_events": False,
        "pipeline_events": False,
        "wiki_page_events": False,
        "wiki_page_events": False,
        "repository_update_events": False,
        "jenkins_events": False,
        "external_status_check_events": False,
        "chat_message_events": False,
        "alert_events": False,
        "vulnerability_events": False,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{GITLAB_BASE_URL}/api/v4/projects/{repo_id}/hooks",
                headers=headers,
                json=webhook_data,
                timeout=30.0
            )
            response.raise_for_status()
            webhook_result = response.json()

            print(f"[✅] Successfully installed webhook for repo {repo_id}")
            print(f"[ℹ️] Webhook ID: {webhook_result.get('id')}")
            print(f"[ℹ️] Webhook URL: {webhook_url}")
            print(f"[ℹ️] Monitored branches: {monitored_branches if monitored_branches else 'All branches'}")

            return {
                "webhook_id": webhook_result.get("id"),
                "webhook_url": webhook_url,
                "monitored_branches": monitored_branches,
                "branch_filter_enabled": bool(monitored_branches),
                "message": "Webhook installed successfully",
                "project_id": repo_id
            }

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository not found or you don't have access"
            )
        elif e.response.status_code == 401 or e.response.status_code == 403:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to install webhook. Requires Maintainer role."
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to install webhook: {e.response.text}"
            )
    except Exception as e:
        print(f"[❌] Failed to install webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


async def update_gitlab_webhook(
    repo_id: str,
    user_id: str,
    webhook_id: int,
    monitored_branches: List[str]
) -> Dict:
    """
    Update webhook branch filter configuration.

    Note: GitLab webhooks don't support branch filtering at the API level
    for merge requests. We store the filter in our database and apply it
    server-side during webhook processing.

    Args:
        repo_id: GitLab project ID
        user_id: User ID for authentication
        webhook_id: GitLab webhook ID
        monitored_branches: List of branches to monitor

    Returns:
        Update result

    Raises:
        HTTPException: If update fails
    """
    # Note: GitLab webhook API doesn't support modifying branch filters for MR events
    # The branch filtering is handled server-side in review_service.py
    # This function exists for future compatibility and webhook URL updates

    print(f"[ℹ️] Updated webhook {webhook_id} branch filter: {monitored_branches if monitored_branches else 'All branches'}")

    return {
        "webhook_id": webhook_id,
        "monitored_branches": monitored_branches,
        "branch_filter_enabled": bool(monitored_branches),
        "message": "Branch filter updated successfully (stored server-side)"
    }


async def delete_gitlab_webhook(
    repo_id: str,
    user_id: str,
    webhook_id: int
) -> Dict:
    """
    Delete a webhook from a GitLab repository.

    Args:
        repo_id: GitLab project ID
        user_id: User ID for authentication
        webhook_id: GitLab webhook ID

    Returns:
        Deletion result

    Raises:
        HTTPException: If deletion fails
    """
    from services import auth_service

    # Get user's GitLab token
    gitlab_token = None
    user_session = auth_service.get_user_session(user_id)
    if user_session:
        gitlab_token = user_session.get("gitlab_access_token")

    if not gitlab_token:
        gitlab_token = GITLAB_PERSONAL_ACCESS_TOKEN

    if not gitlab_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No GitLab access token available"
        )

    headers = {"Authorization": f"Bearer {gitlab_token}"}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{GITLAB_BASE_URL}/api/v4/projects/{repo_id}/hooks/{webhook_id}",
                headers=headers,
                timeout=30.0
            )

            # 404 is acceptable - webhook may have been manually deleted
            if response.status_code == 404:
                print(f"[ℹ️] Webhook {webhook_id} not found (may have been deleted)")
                return {
                    "webhook_id": webhook_id,
                    "message": "Webhook not found or already deleted"
                }

            response.raise_for_status()

            print(f"[✅] Successfully deleted webhook {webhook_id} from repo {repo_id}")

            return {
                "webhook_id": webhook_id,
                "message": "Webhook deleted successfully"
            }

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to delete webhook. Requires Maintainer role."
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete webhook: {e.response.text}"
        )
    except Exception as e:
        print(f"[❌] Failed to delete webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


async def list_gitlab_webhooks(
    repo_id: str,
    user_id: str
) -> List[Dict]:
    """
    List all webhooks for a GitLab repository.

    Args:
        repo_id: GitLab project ID
        user_id: User ID for authentication

    Returns:
        List of webhooks

    Raises:
        HTTPException: If fetch fails
    """
    from services import auth_service

    # Get user's GitLab token
    gitlab_token = None
    user_session = auth_service.get_user_session(user_id)
    if user_session:
        gitlab_token = user_session.get("gitlab_access_token")

    if not gitlab_token:
        gitlab_token = GITLAB_PERSONAL_ACCESS_TOKEN

    if not gitlab_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No GitLab access token available"
        )

    headers = {"Authorization": f"Bearer {gitlab_token}"}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GITLAB_BASE_URL}/api/v4/projects/{repo_id}/hooks",
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            webhooks = response.json()

            print(f"[ℹ️] Found {len(webhooks)} webhooks for repo {repo_id}")

            return webhooks

    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch webhooks: {e.response.text}"
        )
    except Exception as e:
        print(f"[❌] Failed to fetch webhooks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
