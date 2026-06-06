"""
Sentry OAuth Service - Handles Sentry authorization flow and webhook registration.

This service provides:
1. OAuth initiation with state parameter for CSRF protection
2. OAuth callback handling with token exchange
3. Automatic webhook registration after successful OAuth
4. Token encryption and storage
"""

import os
import secrets
import hashlib
import httpx
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from services import mongo_client
from services.encryption_service import encrypt_value as encrypt_data, decrypt_value as decrypt_data


# Sentry OAuth Configuration
SENTRY_CLIENT_ID = os.getenv("SENTRY_CLIENT_ID", "")
SENTRY_CLIENT_SECRET = os.getenv("SENTRY_CLIENT_SECRET", "")
SENTRY_REDIRECT_URI = os.getenv("SENTRY_REDIRECT_URI", "http://localhost:3000/auth/sentry/callback")
SENTRY_BASE_URL = "https://sentry.io"
SENTRY_API_BASE = "https://sentry.io/api/0"
SENTRY_TOKEN_URL = os.getenv("SENTRY_TOKEN_URI", "https://sentry.io/oauth/token/")

# Debug logging
print(f"[DEBUG SENTRY] SENTRY_CLIENT_ID loaded: {SENTRY_CLIENT_ID[:10] if SENTRY_CLIENT_ID else 'EMPTY'}", flush=True)
print(f"[DEBUG SENTRY] SENTRY_REDIRECT_URI loaded: {SENTRY_REDIRECT_URI}", flush=True)

# Required scopes for webhook registration
# Using only the basic scopes that are guaranteed to work
SENTRY_SCOPES = [
    "org:read",
    "project:read",
    "event:read",
    "event:write",
    "team:read"
]

# Webhook events to subscribe to
SENTRY_WEBHOOK_EVENTS = ["issue.created", "issue.resolved"]


class SentryOAuthService:
    """Service for handling Sentry OAuth flow and webhook registration."""

    def __init__(self):
        self.client_id = SENTRY_CLIENT_ID
        self.client_secret = SENTRY_CLIENT_SECRET
        self.redirect_uri = SENTRY_REDIRECT_URI
        self.base_url = SENTRY_BASE_URL
        self.api_base = SENTRY_API_BASE
        self.token_url = SENTRY_TOKEN_URL

    async def initiate_oauth(self, user_id: str, repo_id: str) -> Dict[str, str]:
        """
        Initiate Sentry OAuth flow.

        Args:
            user_id: The user ID initiating the OAuth flow
            repo_id: The repository ID to connect Sentry to

        Returns:
            Dict with oauth_url and state parameters
        """
        # Generate state parameter for CSRF protection
        state = self._generate_state(user_id, repo_id)

        # Store state in MongoDB for validation
        await self._store_state(state, user_id, repo_id)

        # Build OAuth URL
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "state": state,
            "scope": " ".join(SENTRY_SCOPES)
        }

        import urllib.parse
        query_string = urllib.parse.urlencode(params)
        oauth_url = f"{self.base_url}/oauth/authorize/?{query_string}"

        print(f"[DEBUG] OAuth URL params: {params}", flush=True)
        print(f"[DEBUG] Full OAuth URL: {oauth_url}", flush=True)

        return {
            "oauth_url": oauth_url,
            "state": state
        }

    async def handle_callback(self, code: str, state: str) -> Dict[str, Any]:
        """
        Handle Sentry OAuth callback and exchange code for access token.

        Args:
            code: Authorization code from Sentry
            state: State parameter for CSRF validation

        Returns:
            Dict with access token, user info, and org info
        """
        # Validate state
        state_data = await self._validate_and_consume_state(state)
        if not state_data:
            raise ValueError("Invalid or expired OAuth state")

        user_id = state_data.get("user_id")
        repo_id = state_data.get("repo_id")

        # Exchange code for access token
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Token exchange
            print(f"[DEBUG] Exchanging code for token at: {self.token_url}", flush=True)
            print(f"[DEBUG] Using redirect_uri: {self.redirect_uri}", flush=True)

            token_response = await client.post(
                self.token_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": self.redirect_uri
                },
                headers={"Accept": "application/json"}
            )

            print(f"[DEBUG] Token exchange response status: {token_response.status_code}", flush=True)
            print(f"[DEBUG] Token exchange response body: {token_response.text[:500]}", flush=True)

            if token_response.status_code != 200:
                raise ValueError(f"Token exchange failed: {token_response.text}")

            token_data = token_response.json()
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in", 7200)

            print(f"[DEBUG] Got access_token: {access_token[:20] if access_token else 'NONE'}...", flush=True)

            # Get user and organization info
            user_response = await client.get(
                f"{self.api_base}/",
                headers={"Authorization": f"Bearer {access_token}"}
            )

            if user_response.status_code != 200:
                raise ValueError(f"Failed to fetch user info: {user_response.text}")

            user_info = user_response.json()

            # Get organizations
            orgs_response = await client.get(
                f"{self.api_base}/organizations/",
                headers={"Authorization": f"Bearer {access_token}"}
            )

            organizations = []
            if orgs_response.status_code == 200:
                orgs_data = orgs_response.json()
                organizations = [
                    {"slug": org.get("slug"), "name": org.get("name")}
                    for org in orgs_data
                ]

            # Calculate token expiry
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

            print(f"[DEBUG] Creating integration data for repo_id: {repo_id}", flush=True)

            # Prepare integration data (will be updated after webhook registration)
            integration_data = {
                "connected": True,
                "user_id": user_id,
                "repo_id": repo_id,
                "access_token_encrypted": encrypt_data(access_token),
                "refresh_token_encrypted": encrypt_data(refresh_token) if refresh_token else None,
                "token_expires_at": expires_at.isoformat(),
                "user_email": user_info.get("email"),
                "user_name": user_info.get("name"),
                "organizations": organizations,
                "connected_at": datetime.utcnow().isoformat(),
                "webhook_registered": False,
                "webhook_id": None
            }

            print(f"[DEBUG] Storing integration in MongoDB", flush=True)
            try:
                # Store in MongoDB
                await self._store_integration(repo_id, integration_data)
                print(f"[DEBUG] Integration stored successfully", flush=True)
            except Exception as e:
                print(f"[ERROR] Failed to store integration: {e}", flush=True)
                raise

            # Attempt automatic webhook registration
            webhook_result = None
            if organizations:
                print(f"[DEBUG] Attempting automatic webhook registration for org: {organizations[0]['slug']}", flush=True)
                try:
                    webhook_result = await self.register_webhook(
                        organizations[0]["slug"],
                        access_token
                    )

                    # Update integration data with webhook registration result
                    integration_data["webhook_registered"] = webhook_result.get("webhook_registered", False)
                    integration_data["webhook_id"] = webhook_result.get("webhook_id")

                    # Store the updated integration with webhook info
                    await self._store_integration(repo_id, integration_data)
                    print(f"[DEBUG] Integration stored with webhook status: {webhook_result.get('webhook_registered')}", flush=True)
                except Exception as e:
                    print(f"[WARN] Exception during webhook registration: {e}", flush=True)
                    webhook_result = {
                        "success": False,
                        "error": str(e),
                        "manual_setup_required": True
                    }

            return {
                "status": "success",
                "repo_id": repo_id,
                "organizations": organizations,
                "webhook_result": webhook_result
            }

    async def register_webhook(self, org_slug: str, access_token: str) -> Dict[str, Any]:
        """
        Automatically register a webhook in Sentry for the organization.

        Uses Sentry's Internal Integration API to create a webhook programmatically.

        Args:
            org_slug: Organization slug in Sentry
            access_token: Sentry access token

        Returns:
            Dict with webhook registration result (webhook_id, status, etc.)
        """
        webhook_url = os.getenv("SENTRY_WEBHOOK_URL", os.getenv("GATEKEEPER_WEBHOOK_URL", "http://localhost:8000/webhooks/sentry"))

        print(f"[DEBUG] Attempting to register webhook for org: {org_slug}", flush=True)
        print(f"[DEBUG] Webhook URL: {webhook_url}", flush=True)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Try to create webhook via Sentry API
                # Sentry's API uses different endpoints for different integration types
                # Try multiple possible endpoints
                endpoints = [
                    f"{self.api_base}/organizations/{org_slug}/hooks/",  # Legacy endpoint
                    f"{self.api_base}/organizations/{org_slug}/webhooks/",  # Newer endpoint
                ]

                response = None
                for endpoint in endpoints:
                    print(f"[DEBUG] Trying webhook creation endpoint: {endpoint}", flush=True)
                    response = await client.post(
                        endpoint,
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "url": webhook_url,
                            "events": SENTRY_WEBHOOK_EVENTS
                        }
                    )

                    if response.status_code in [200, 201, 202]:
                        print(f"[DEBUG] Webhook creation succeeded with endpoint: {endpoint}", flush=True)
                        break
                    else:
                        print(f"[DEBUG] Webhook creation failed with endpoint: {endpoint}, status: {response.status_code}", flush=True)

                print(f"[DEBUG] Final webhook creation response status: {response.status_code}", flush=True)
                print(f"[DEBUG] Final webhook creation response: {response.text[:500] if response.text else 'empty'}", flush=True)

                if response and response.status_code in [200, 201, 202]:
                    webhook_data = response.json()
                    webhook_id = webhook_data.get("id") or webhook_data.get("uuid")  # Handle different response formats

                    print(f"[DEBUG] Webhook registered successfully with ID: {webhook_id}", flush=True)

                    return {
                        "success": True,
                        "webhook_id": webhook_id,
                        "webhook_registered": True,
                        "url": webhook_url,
                        "events": SENTRY_WEBHOOK_EVENTS,
                        "message": "Webhook registered successfully"
                    }
                else:
                    # If automatic creation fails, provide manual setup instructions
                    error_msg = response.text if response else "No response from Sentry"
                    print(f"[WARN] Failed to auto-create webhook: {error_msg}", flush=True)
                    return {
                        "success": False,
                        "webhook_registered": False,
                        "webhook_id": None,
                        "error": error_msg,
                        "manual_setup_required": True,
                        "setup_instructions": f"""
Automatic webhook registration failed. Manual setup required:

1. Go to: https://sentry.io/settings/{org_slug}/webhooks/
2. Click "Add New webhook"
3. Configure:
   - URL: {webhook_url}
   - Events: {', '.join(SENTRY_WEBHOOK_EVENTS)}
4. Save the webhook
                        """.strip()
                    }

        except Exception as e:
            print(f"[ERROR] Exception during webhook registration: {e}", flush=True)
            return {
                "success": False,
                "webhook_registered": False,
                "webhook_id": None,
                "error": str(e),
                "manual_setup_required": True
            }

    async def get_integration_status(self, repo_id: str) -> Dict[str, Any]:
        """
        Get Sentry integration status for a repository.

        Args:
            repo_id: Repository ID

        Returns:
            Dict with integration status
        """
        integration = await self._get_integration(repo_id)

        if not integration:
            return {
                "connected": False,
                "org_slug": None,
                "webhook_registered": False,
                "webhook_id": None,
                "connected_at": None,
                "webhook_setup_instructions": None,
                "webhook_url": None
            }

        organizations = integration.get("organizations", [])
        org_slug = organizations[0].get("slug") if organizations else None

        # Get webhook setup instructions if webhook is not registered
        setup_instructions = None
        webhook_url = None
        if not integration.get("webhook_registered", False) and org_slug:
            setup_instructions = self.get_webhook_setup_instructions(org_slug)
            webhook_url = os.getenv("SENTRY_WEBHOOK_URL", os.getenv("GATEKEEPER_WEBHOOK_URL", "http://localhost:8000/webhooks/sentry"))

        return {
            "connected": integration.get("connected", False),
            "org_slug": org_slug,
            "webhook_registered": integration.get("webhook_registered", False),
            "webhook_id": integration.get("webhook_id"),
            "connected_at": integration.get("connected_at"),
            "webhook_setup_instructions": setup_instructions,
            "webhook_url": webhook_url
        }

    def get_webhook_setup_instructions(self, org_slug: str) -> Dict[str, Any]:
        """
        Get detailed webhook setup instructions for manual configuration.

        Args:
            org_slug: Organization slug in Sentry

        Returns:
            Dict with step-by-step setup instructions
        """
        webhook_url = os.getenv("SENTRY_WEBHOOK_URL", os.getenv("GATEKEEPER_WEBHOOK_URL", "http://localhost:8000/webhooks/sentry"))

        return {
            "webhook_url": webhook_url,
            "events": SENTRY_WEBHOOK_EVENTS,
            "steps": [
                {
                    "step": 1,
                    "title": "Navigate to Integrations Settings",
                    "description": f"Go to your Sentry organization's integrations settings page. IMPORTANT: You must select Internal Integration for webhook functionality.",
                    "url": f"https://{org_slug}.sentry.io/settings/integrations/",
                    "action_text": "Open Sentry Integrations"
                },
                {
                    "step": 2,
                    "title": "Select 'Internal Integration'",
                    "description": "In the integrations page, you'll see options like 'Internal Integration', 'Sentry App', etc. Select 'Internal Integration' as it supports webhooks.",
                    "url": f"https://{org_slug}.sentry.io/settings/integrations/",
                    "action_text": "Click on 'Internal Integration'"
                },
                {
                    "step": 3,
                    "title": "Create New Internal Integration",
                    "description": "Click 'Add New Integration' or 'Create Integration' to create a new internal integration for Gatekeeper.",
                    "url": None,
                    "action_text": "Click 'Add New Integration'"
                },
                {
                    "step": 4,
                    "title": "Configure Integration Details",
                    "description": "Name your integration (e.g., 'Gatekeeper Auto-Fix') and give it appropriate permissions like 'Event Admin' to access error data.",
                    "config_value": "Gatekeeper Auto-Fix",
                    "config_label": "Integration Name",
                    "url": None,
                    "action_text": "Enter integration name"
                },
                {
                    "step": 5,
                    "title": "Configure Webhook URL",
                    "description": f"In the webhook section, enter the URL where Sentry will send error events",
                    "config_value": webhook_url,
                    "config_label": "Webhook URL",
                    "url": None,
                    "action_text": f"Enter: {webhook_url}"
                },
                {
                    "step": 6,
                    "title": "Select Events to Monitor",
                    "description": "Choose which events should trigger the webhook. For automated bug fixes, you need issue events.",
                    "config_value": ", ".join(SENTRY_WEBHOOK_EVENTS),
                    "config_label": "Events to monitor",
                    "url": None,
                    "action_text": f"Select: {', '.join(SENTRY_WEBHOOK_EVENTS)}"
                },
                {
                    "step": 7,
                    "title": "Save and Verify",
                    "description": "Save the integration configuration. Return to Gatekeeper and click the 'Verify Webhook' button to confirm it's working.",
                    "url": None,
                    "action_text": "Click 'Save Integration'"
                }
            ],
            "verification_note": "After setting up the webhook, click the 'Verify Webhook' button below to confirm it's working correctly.",
            "troubleshooting": [
                "IMPORTANT: Select 'Internal Integration' NOT 'Sentry App' or 'Public Integration'",
                "Ensure the webhook URL is publicly accessible (not localhost)",
                "Check that your integration has 'Event Admin' permissions",
                "Verify the events selected match: issue.created, issue.resolved",
                "Test by triggering a test error in your application",
                "If webhook verification fails, check Sentry's integration status page for errors"
            ],
            "important_note": "Internal Integrations are required for webhook functionality. Sentry Apps and Public Integrations do not support the same webhook capabilities."
        }

    async def verify_webhook(self, repo_id: str) -> Dict[str, Any]:
        """
        Verify if the Sentry webhook is properly configured and working.

        This method checks:
        1. Integration exists and is connected
        2. Organization is available
        3. Webhook URL is accessible (basic connectivity check)

        Note: OAuth tokens from Sentry Apps cannot list Internal Integration webhooks
        due to API permission limitations. Users should manually verify their webhook
        by triggering a test error in Sentry.

        Args:
            repo_id: Repository ID

        Returns:
            Dict with verification result
        """
        integration = await self._get_integration(repo_id)

        if not integration or not integration.get("connected", False):
            return {
                "verified": False,
                "message": "Sentry integration not connected",
                "steps_required": ["Connect Sentry integration first"]
            }

        organizations = integration.get("organizations", [])
        if not organizations:
            return {
                "verified": False,
                "message": "No Sentry organization found",
                "steps_required": ["Reconnect Sentry to get organization information"]
            }

        org_slug = organizations[0].get("slug")
        webhook_url = os.getenv("SENTRY_WEBHOOK_URL", os.getenv("GATEKEEPER_WEBHOOK_URL", "http://localhost:8000/webhooks/sentry"))

        print(f"[DEBUG] Verifying webhook for org: {org_slug}", flush=True)
        print(f"[DEBUG] Expected webhook URL: {webhook_url}", flush=True)

        # Check if webhook was already verified before
        if integration.get("webhook_registered", False):
            return {
                "verified": True,
                "message": "Webhook was previously verified and configured",
                "webhook_id": integration.get("webhook_id"),
                "webhook": {
                    "id": integration.get("webhook_id"),
                    "url": webhook_url,
                    "events": SENTRY_WEBHOOK_EVENTS,
                    "active": True
                }
            }

        # Since OAuth tokens can't list Internal Integration webhooks, we'll do a connectivity check
        # and guide the user to verify manually
        try:
            # Basic connectivity check to ensure webhook URL is accessible
            async with httpx.AsyncClient(timeout=10.0) as client:
                try:
                    # Try to ping the webhook endpoint (it should return 405 or similar for GET requests)
                    webhook_test_response = await client.get(webhook_url, follow_redirects=True)
                    print(f"[DEBUG] Webhook URL connectivity check: {webhook_test_response.status_code}", flush=True)

                    # If we get any response (even error), the URL is reachable
                    webhook_accessible = True
                except Exception as e:
                    print(f"[DEBUG] Webhook URL not accessible: {e}", flush=True)
                    webhook_accessible = False

            if not webhook_accessible:
                return {
                    "verified": False,
                    "message": "Webhook URL is not publicly accessible",
                    "steps_required": [
                        f"Your webhook URL ({webhook_url}) must be publicly accessible",
                        "If using localhost/ngrok, ensure the tunnel is running",
                        "Check your firewall allows inbound connections"
                    ],
                    "setup_instructions": self.get_webhook_setup_instructions(org_slug)
                }

            # Webhook URL is accessible, but we can't verify the Sentry side with OAuth token
            # Provide manual verification instructions
            return {
                "verified": False,
                "message": "Webhook URL is accessible, but Sentry-side verification requires manual confirmation",
                "manual_verification_required": True,
                "steps_required": [
                    f"1. Go to https://{org_slug}.sentry.io/settings/integrations/",
                    f"2. Find your 'Gatekeeper' Internal Integration",
                    f"3. Verify the webhook URL is set to: {webhook_url}",
                    f"4. Verify events are selected: {', '.join(SENTRY_WEBHOOK_EVENTS)}",
                    "5. Trigger a test error in your application",
                    "6. Check if Gatekeeper receives the webhook (look for activity in your Gatekeeper logs)",
                    "7. If you see webhook activity, click 'I confirm webhook is working' below"
                ],
                "setup_instructions": self.get_webhook_setup_instructions(org_slug),
                "confirm_button": {
                    "text": "I confirm webhook is working",
                    "action": "confirm_webhook"
                }
            }

        except Exception as e:
            print(f"[ERROR] Webhook verification failed: {e}", flush=True)
            return {
                "verified": False,
                "message": f"Verification failed: {str(e)}",
                "steps_required": [
                    "Ensure your Sentry integration is properly connected",
                    "Check your webhook URL is publicly accessible",
                    "Try reconnecting your Sentry integration"
                ]
            }

    async def confirm_webhook(self, repo_id: str) -> Dict[str, Any]:
        """
        Manually confirm that the webhook is working (after user verification).

        This is called when users have manually verified their webhook is working
        by triggering a test error in Sentry.

        Args:
            repo_id: Repository ID

        Returns:
            Dict with confirmation result
        """
        integration = await self._get_integration(repo_id)

        if not integration or not integration.get("connected", False):
            return {
                "success": False,
                "message": "Sentry integration not connected"
            }

        webhook_url = os.getenv("SENTRY_WEBHOOK_URL", os.getenv("GATEKEEPER_WEBHOOK_URL", "http://localhost:8000/webhooks/sentry"))

        # Update integration to mark webhook as registered
        await self._store_integration(repo_id, {
            **integration,
            "webhook_registered": True,
            "webhook_id": f"manual-{repo_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        })

        return {
            "success": True,
            "message": "Webhook confirmed as working",
            "webhook_registered": True
        }

    async def disconnect(self, repo_id: str) -> Dict[str, Any]:
        """
        Disconnect Sentry integration for a repository and remove the webhook.

        Args:
            repo_id: Repository ID

        Returns:
            Dict with status message
        """
        integration = await self._get_integration(repo_id)

        if integration and integration.get("webhook_registered") and integration.get("webhook_id"):
            # Delete webhook from Sentry
            try:
                organizations = integration.get("organizations", [])
                if not organizations:
                    print(f"[WARN] No organizations found for repo: {repo_id}")
                else:
                    org_slug = organizations[0].get("slug")
                    webhook_id = integration.get("webhook_id")
                    access_token = decrypt_data(integration.get("access_token_encrypted", ""))

                    if not org_slug or not webhook_id:
                        print(f"[WARN] Missing org_slug or webhook_id for repo: {repo_id}")
                    else:
                        print(f"[DEBUG] Deleting webhook {webhook_id} from org {org_slug}", flush=True)
                        async with httpx.AsyncClient(timeout=30.0) as client:
                            # Try multiple possible deletion endpoints
                            endpoints = [
                                f"{self.api_base}/organizations/{org_slug}/hooks/{webhook_id}/",
                                f"{self.api_base}/organizations/{org_slug}/webhooks/{webhook_id}/",
                            ]

                            for endpoint in endpoints:
                                print(f"[DEBUG] Trying webhook deletion endpoint: {endpoint}", flush=True)
                                delete_response = await client.delete(
                                    endpoint,
                                    headers={"Authorization": f"Bearer {access_token}"}
                                )
                                if delete_response.status_code in [200, 204, 202]:
                                    print(f"[DEBUG] Webhook deleted successfully with endpoint: {endpoint}", flush=True)
                                    break
            except Exception as e:
                print(f"[WARN] Failed to delete webhook from Sentry: {e}", flush=True)

        # Delete integration from MongoDB
        await self._delete_integration(repo_id)

        return {"status": "success", "message": "Sentry integration disconnected"}

    def _generate_state(self, user_id: str, repo_id: str) -> str:
        """Generate a cryptographically secure state parameter."""
        raw = f"{user_id}:{repo_id}:{secrets.token_urlsafe(32)}"
        return hashlib.sha256(raw.encode()).hexdigest()

    async def _store_state(self, state: str, user_id: str, repo_id: str) -> None:
        """Store OAuth state in MongoDB."""
        await mongo_client.insert_one(
            collection_name="sentry_oauth_states",
            document={
                "state": state,
                "user_id": user_id,
                "repo_id": repo_id,
                "created_at": datetime.utcnow().isoformat(),
                "expires_at": (datetime.utcnow() + timedelta(minutes=10)).isoformat()
            }
        )

    async def _validate_and_consume_state(self, state: str) -> Optional[Dict[str, str]]:
        """Validate and consume OAuth state."""
        state_data = await mongo_client.find_one(
            collection_name="sentry_oauth_states",
            filter={"state": state}
        )

        if not state_data:
            return None

        # Check if expired
        expires_at = datetime.fromisoformat(state_data.get("expires_at", ""))
        if datetime.utcnow() > expires_at:
            await mongo_client.delete_one(
                collection_name="sentry_oauth_states",
                filter={"state": state}
            )
            return None

        # Consume state (delete after use)
        await mongo_client.delete_one(
            collection_name="sentry_oauth_states",
            filter={"state": state}
        )

        return {
            "user_id": state_data.get("user_id"),
            "repo_id": state_data.get("repo_id")
        }

    async def _store_integration(self, repo_id: str, integration_data: Dict[str, Any]) -> None:
        """Store Sentry integration data in MongoDB."""
        print(f"[DEBUG _store_integration] Storing integration for repo_id: {repo_id}", flush=True)

        # Check if repository exists
        existing_repo = await mongo_client.find_one(
            collection_name="connected_repositories",
            filter={"id": repo_id}
        )

        print(f"[DEBUG _store_integration] Existing repo found: {existing_repo is not None}", flush=True)

        if existing_repo:
            # Update existing repository
            print(f"[DEBUG _store_integration] Updating repository with Sentry integration", flush=True)
            await mongo_client.update_one(
                collection_name="connected_repositories",
                filter={"id": repo_id},
                update={"$set": {"sentry_integration": integration_data}}
            )
            print(f"[DEBUG _store_integration] Update completed", flush=True)
        else:
            # Repository doesn't exist, this shouldn't happen in normal flow
            print(f"[WARN] Repository {repo_id} not found, cannot store Sentry integration", flush=True)

    async def _get_integration(self, repo_id: str) -> Optional[Dict[str, Any]]:
        """Get Sentry integration data from MongoDB."""
        print(f"[DEBUG _get_integration] Fetching integration for repo_id: {repo_id}", flush=True)

        repo = await mongo_client.find_one(
            collection_name="connected_repositories",
            filter={"id": repo_id}
        )

        print(f"[DEBUG _get_integration] Repo found: {repo is not None}", flush=True)
        if repo:
            print(f"[DEBUG _get_integration] Has sentry_integration field: {'sentry_integration' in repo}", flush=True)
            integration = repo.get("sentry_integration")
            print(f"[DEBUG _get_integration] Integration connected: {integration.get('connected') if integration else 'N/A'}", flush=True)

        if not repo:
            return None

        return repo.get("sentry_integration")

    async def _delete_integration(self, repo_id: str) -> None:
        """Delete Sentry integration data from MongoDB."""
        await mongo_client.update_one(
            collection_name="connected_repositories",
            filter={"id": repo_id},
            update={"$unset": {"sentry_integration": ""}}
        )


# Singleton instance
_sentry_oauth_service = None


def get_sentry_oauth_service() -> SentryOAuthService:
    """Get the singleton Sentry OAuth service instance."""
    global _sentry_oauth_service
    if _sentry_oauth_service is None:
        _sentry_oauth_service = SentryOAuthService()
    return _sentry_oauth_service
