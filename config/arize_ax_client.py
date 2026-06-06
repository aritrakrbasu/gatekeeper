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
