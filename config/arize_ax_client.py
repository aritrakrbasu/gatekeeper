"""
Arize AX (Prompt Management) Client.

This module enables The Gatekeeper to fetch prompts from Arize AX
for centralized prompt management and A/B testing.

Uses direct REST API calls to Arize AX.
"""

import os
import logging
import json
from typing import Optional, Dict, Any, List
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Import httpx for HTTP requests
try:
    import httpx
except ImportError:
    httpx = None
    logging.warning("[WARNING] httpx not installed. Install with: pip install httpx")

from config.arize_config import API_KEY as ARIZE_API_KEY

logger = logging.getLogger(__name__)


class ArizeAXClient:
    """
    Client for fetching prompts from Arize AX using direct REST API calls.

    This class provides methods to retrieve prompts from Arize AX
    with fallback to local files.

    Usage:
        ax_client = await get_ax_client()
        prompt = await ax_client.get_prompt("senior_pr_reviewer_v1", label="production")
    """

    # Arize AX REST API endpoints
    API_BASE_URL = "https://api.arize.com/v2"

    def __init__(
        self,
        api_key: Optional[str] = None,
        space_id: Optional[str] = None,
    ):
        """
        Initialize the Arize AX client.

        Args:
            api_key: Arize API key (defaults to env var ARIZE_API_KEY)
            space_id: Arize Space ID (defaults to env var ARIZE_SPACE_ID)
        """
        if httpx is None:
            raise ImportError("httpx not installed. Install with: pip install httpx")

        self.api_key = api_key or ARIZE_API_KEY
        self.space_id = space_id or os.getenv("ARIZE_SPACE_ID")
        self._client: Optional[httpx.AsyncClient] = None
        self._connected = False
        self._prompt_cache: Dict[str, str] = {}  # Cache prompt name -> ID mappings

        if not self.api_key:
            logger.warning("[WARNING] Arize API key not configured - AX client unavailable")
        if not self.space_id:
            logger.warning("[WARNING] Arize Space ID not configured - AX client may not work properly")

    async def connect(self) -> bool:
        """
        Establish connection to Arize AX.

        Returns:
            True if connection successful, False otherwise
        """
        if self._connected:
            return True

        if not self.api_key:
            logger.warning("[WARNING] Arize API key not configured - AX client unavailable")
            return False

        try:
            # Initialize HTTP client
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            self._client = httpx.AsyncClient(
                base_url=self.API_BASE_URL,
                headers=headers,
                timeout=30.0,
            )

            # Test connection
            self._connected = True
            logger.info(f"[OK] Arize AX client initialized (space: {self.space_id})")
            return True

        except Exception as e:
            logger.error(f"[ERROR] Failed to initialize Arize AX client: {e}")
            return False

    async def disconnect(self):
        """Close the Arize AX connection."""
        if self._client:
            await self._client.aclose()
            self._client = None
        self._connected = False
        logger.info("[OK] Arize AX client disconnected")

    async def _find_prompt_id_by_name(self, prompt_name: str) -> Optional[str]:
        """
        Find a prompt ID by searching for prompts with the given name.

        Args:
            prompt_name: Name of the prompt to find

        Returns:
            Prompt ID or None if not found
        """
        try:
            params = {"space_id": self.space_id, "limit": 100}

            response = await self._client.get("/prompts", params=params)

            if response.status_code == 200:
                data = response.json()
                prompts = data.get("prompts", [])

                for prompt in prompts:
                    if prompt.get("name") == prompt_name:
                        prompt_id = prompt.get("id")
                        logger.debug(f"[DEBUG] Found prompt '{prompt_name}' with ID: {prompt_id}")
                        return prompt_id

                logger.warning(f"[WARN] Prompt '{prompt_name}' not found in space")
                return None
            else:
                logger.warning(f"[WARN] Failed to list prompts: HTTP {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"[ERROR] Failed to find prompt ID: {e}")
            return None

    async def get_prompt(
        self,
        prompt_name: str,
        label: Optional[str] = None,
        fallback_to_file: bool = True,
    ) -> Optional[str]:
        """
        Fetch a prompt from Arize AX by name using the REST API.

        Args:
            prompt_name: Name/ID of the prompt to fetch (e.g., "senior_pr_reviewer_v1")
            label: Prompt label to fetch (e.g., "production", "staging")
                   Note: Labels are configured in Arize AX UI
            fallback_to_file: If True, falls back to local file if AX fetch fails

        Returns:
            Prompt content string or None if not found

        Example:
            # Get by name (fetches current version)
            prompt = await ax_client.get_prompt("senior_pr_reviewer_v1")
        """
        if not self._connected:
            await self.connect()

        if not self._connected:
            if fallback_to_file:
                return self._fallback_to_local_file(prompt_name)
            return None

        try:
            # Check cache first
            if prompt_name in self._prompt_cache:
                prompt_id = self._prompt_cache[prompt_name]
            else:
                # Find prompt ID by name
                prompt_id = await self._find_prompt_id_by_name(prompt_name)
                if not prompt_id:
                    if fallback_to_file:
                        return self._fallback_to_local_file(prompt_name)
                    return None
                # Cache the ID
                self._prompt_cache[prompt_name] = prompt_id

            logger.debug(f"[DEBUG] Fetching prompt '{prompt_name}' (ID: {prompt_id}) from Arize AX")

            # Fetch prompt with versions
            response = await self._client.get(f"/prompts/{prompt_id}")

            if response.status_code == 200:
                prompt_data = response.json()

                # Extract prompt content from version.messages
                # Response structure: {"version": {"messages": [{"role": "system", "content": "..."}]}}
                if "version" in prompt_data:
                    version = prompt_data["version"]

                    if "messages" in version and len(version["messages"]) > 0:
                        # Get the system message content
                        for msg in version["messages"]:
                            if msg.get("role") == "system":
                                content = msg.get("content")
                                if content:
                                    logger.info(f"[OK] Retrieved prompt '{prompt_name}' from Arize AX")
                                    return content

                        # If no system message, join all messages
                        messages = version["messages"]
                        content = self._format_messages_as_prompt(messages)
                        if content:
                            logger.info(f"[OK] Retrieved prompt '{prompt_name}' from Arize AX (no system message, using all)")
                            return content

                    logger.warning(f"[WARN] Prompt '{prompt_name}' found but no messages in version")
                else:
                    logger.warning(f"[WARN] Prompt '{prompt_name}' found but no version in response")

            elif response.status_code == 404:
                logger.warning(f"[WARN] Prompt '{prompt_name}' not found in Arize AX (404)")
            else:
                logger.warning(f"[WARN] Failed to fetch prompt: HTTP {response.status_code}")
                logger.debug(f"[DEBUG] Response: {response.text[:200]}")

        except Exception as e:
            logger.error(f"[ERROR] Failed to fetch prompt from Arize AX: {e}")
            logger.debug(f"[DEBUG] Error details: {type(e).__name__}: {str(e)}")

        # Fallback to local file if enabled
        if fallback_to_file:
            return self._fallback_to_local_file(prompt_name)

        return None

    def _format_messages_as_prompt(self, messages: List[Dict]) -> str:
        """
        Format a list of messages into a single prompt string.

        Args:
            messages: List of message dicts with 'role' and 'content'

        Returns:
            Formatted prompt string
        """
        if not messages:
            return ""

        formatted = []
        for msg in messages:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            formatted.append(f"{role.upper()}: {content}")

        return "\n\n".join(formatted)

    async def list_prompts(self, limit: int = 100) -> List[Dict]:
        """
        List available prompts in Arize AX.

        Args:
            limit: Maximum number of prompts to return

        Returns:
            List of prompt metadata dictionaries
        """
        if not self._connected:
            await self.connect()

        if not self._connected:
            return []

        try:
            params = {"space_id": self.space_id, "limit": limit}

            response = await self._client.get("/prompts", params=params)

            if response.status_code == 200:
                data = response.json()
                prompts = data.get("prompts", [])
                logger.info(f"[OK] Retrieved {len(prompts)} prompts from Arize AX")
                return prompts

        except Exception as e:
            logger.error(f"[ERROR] Failed to list prompts: {e}")

        return []

    def _fallback_to_local_file(self, prompt_name: str) -> Optional[str]:
        """
        Fallback to loading prompt from local file.

        Args:
            prompt_name: Name of the prompt (used to find .md file)

        Returns:
            Prompt content string or None if file not found
        """
        try:
            # Construct path to prompts directory
            prompts_dir = Path(__file__).parent.parent / "prompts"
            prompt_path = prompts_dir / f"{prompt_name}.md"

            if prompt_path.exists():
                content = prompt_path.read_text(encoding="utf-8")
                logger.info(f"[OK] Loaded prompt '{prompt_name}' from local file (fallback)")
                return content
            else:
                logger.warning(f"[WARN] Local prompt file not found: {prompt_path}")
                return None

        except Exception as e:
            logger.error(f"[ERROR] Failed to load local prompt file: {e}")
            return None

    def is_connected(self) -> bool:
        """Check if the client is connected."""
        return self._connected

    async def health_check(self) -> bool:
        """
        Test Arize AX connectivity.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            if not self._connected:
                await self.connect()

            # Simple test - try to list prompts with limit=1
            params = {"space_id": self.space_id, "limit": 1}
            response = await self._client.get("/prompts", params=params)

            is_healthy = response.status_code == 200

            if is_healthy:
                logger.info("[OK] Arize AX health check passed")
            else:
                logger.warning(f"[WARN] Arize AX health check failed: HTTP {response.status_code}")

            return is_healthy

        except Exception as e:
            logger.error(f"[ERROR] Arize AX health check failed: {e}")
            return False

    async def register_prompt(
        self,
        prompt_id: str,
        content: str,
        description: str = "",
        template_vars: List[str] = None,
        label: str = "development"
    ) -> Optional[str]:
        """
        Register a new prompt in Arize AX.

        Args:
            prompt_id: Unique identifier for the prompt
            content: Prompt content (can contain {variable} placeholders)
            description: Description of the prompt
            template_vars: List of template variable names used in content
            label: Environment label (development, staging, production)

        Returns:
            Prompt ID if successful, None otherwise
        """
        if not self._connected:
            await self.connect()

        if not self._connected:
            logger.error("[ERROR] Cannot register prompt - not connected to Arize AX")
            return None

        try:
            # Check if prompt already exists
            existing_id = await self._find_prompt_id_by_name(prompt_id)
            if existing_id:
                logger.info(f"[INFO] Prompt '{prompt_id}' already exists with ID: {existing_id}")
                logger.info(f"[INFO] Use update_prompt() to modify existing prompts")
                return existing_id

            # Create new prompt
            payload = {
                "space_id": self.space_id,
                "name": prompt_id,
                "description": description or f"Prompt: {prompt_id}",
                "versions": [
                    {
                        "label": label,
                        "messages": [
                            {
                                "role": "system",
                                "content": content
                            }
                        ],
                        "metadata": {
                            "template_vars": template_vars or []
                        }
                    }
                ]
            }

            logger.info(f"[INFO] Registering prompt '{prompt_id}' in Arize AX...")

            response = await self._client.post("/prompts", json=payload)

            if response.status_code in (200, 201):
                data = response.json()
                new_prompt_id = data.get("id") or data.get("prompt_id")
                logger.info(f"[OK] Successfully registered prompt '{prompt_id}' with ID: {new_prompt_id}")

                # Cache the new ID
                self._prompt_cache[prompt_id] = new_prompt_id

                return new_prompt_id
            else:
                logger.error(f"[ERROR] Failed to register prompt: HTTP {response.status_code}")
                logger.debug(f"[DEBUG] Response: {response.text[:500]}")
                return None

        except Exception as e:
            logger.error(f"[ERROR] Failed to register prompt '{prompt_id}': {e}")
            return None

    async def update_prompt(
        self,
        prompt_id: str,
        content: str,
        description: str = None,
        label: str = "development"
    ) -> bool:
        """
        Update an existing prompt in Arize AX.

        Args:
            prompt_id: ID of the prompt to update
            content: New prompt content
            description: New description (optional)
            label: Label for the new version

        Returns:
            True if successful, False otherwise
        """
        if not self._connected:
            await self.connect()

        if not self._connected:
            return False

        try:
            # Find the prompt ID
            actual_id = await self._find_prompt_id_by_name(prompt_id)
            if not actual_id:
                logger.error(f"[ERROR] Prompt '{prompt_id}' not found - cannot update")
                return False

            # Create a new version with updated content
            payload = {
                "label": label,
                "messages": [
                    {
                        "role": "system",
                        "content": content
                    }
                ]
            }

            if description:
                payload["description"] = description

            logger.info(f"[INFO] Updating prompt '{prompt_id}'...")

            response = await self._client.post(
                f"/prompts/{actual_id}/versions",
                json=payload
            )

            if response.status_code in (200, 201):
                logger.info(f"[OK] Successfully updated prompt '{prompt_id}'")
                return True
            else:
                logger.error(f"[ERROR] Failed to update prompt: HTTP {response.status_code}")
                logger.debug(f"[DEBUG] Response: {response.text[:500]}")
                return False

        except Exception as e:
            logger.error(f"[ERROR] Failed to update prompt '{prompt_id}': {e}")
            return False

    def validate_prompt_template(
        self,
        content: str,
        template_vars: List[str] = None
    ) -> tuple[bool, List[str]]:
        """
        Validate a prompt template by checking placeholder syntax.

        Args:
            content: Prompt content to validate
            template_vars: Expected template variables

        Returns:
            Tuple of (is_valid, list_of_found_variables)
        """
        import re

        # Find all {variable} placeholders
        pattern = r'\{([^}]+)\}'
        found_vars = re.findall(pattern, content)

        # Check if all expected vars are present
        if template_vars:
            missing = set(template_vars) - set(found_vars)
            if missing:
                logger.warning(f"[WARN] Missing expected template vars: {missing}")
                return False, found_vars

        logger.debug(f"[DEBUG] Validated prompt template with vars: {found_vars}")
        return True, found_vars

    async def get_prompt_with_fallback(
        self,
        prompt_name: str,
        label: str = "production",
        local_path: str = None,
        default: str = None
    ) -> Optional[str]:
        """
        Load prompt with multi-level fallback chain.

        Fallback order:
        1. Arize AX (primary)
        2. Local file (if local_path provided)
        3. Default prompt (if default provided)

        Args:
            prompt_name: Name/ID of the prompt
            label: Prompt label to fetch
            local_path: Local file path for fallback
            default: Default prompt string for fallback

        Returns:
            Prompt content string or None if all sources fail
        """
        # Try Arize AX first
        try:
            prompt = await self.get_prompt(prompt_name, label=label, fallback_to_file=False)
            if prompt:
                return prompt
        except Exception as e:
            logger.warning(f"[WARN] Failed to load '{prompt_name}' from Arize AX: {e}")

        # Try local file
        if local_path:
            local_file = Path(local_path)
            if local_file.exists():
                try:
                    content = local_file.read_text(encoding="utf-8")
                    logger.info(f"[OK] Loaded prompt '{prompt_name}' from local file: {local_path}")
                    return content
                except Exception as e:
                    logger.warning(f"[WARN] Failed to read local file {local_path}: {e}")

        # Try default
        if default:
            logger.info(f"[OK] Using default fallback for '{prompt_name}'")
            return default

        logger.error(f"[ERROR] All fallback sources failed for '{prompt_name}'")
        return None

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()


# Global Arize AX client instance
_ax_client: Optional[ArizeAXClient] = None


async def get_ax_client() -> ArizeAXClient:
    """
    Get the global Arize AX client instance.

    Returns:
        The ArizeAXClient instance (connected if not already)
    """
    global _ax_client

    if _ax_client is None:
        _ax_client = ArizeAXClient()

    if not _ax_client.is_connected():
        await _ax_client.connect()

    return _ax_client


async def close_ax_client():
    """Close the global Arize AX client."""
    global _ax_client

    if _ax_client:
        await _ax_client.disconnect()
        _ax_client = None
