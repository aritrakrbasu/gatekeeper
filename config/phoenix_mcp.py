"""
Phoenix MCP Bridge for Self-Introspection.

This module enables The Gatekeeper to query its own traces, evaluations,
and experiments at runtime via the Phoenix MCP server.

This allows the agent to self-reflect and improve based on its observability data.
"""

import os
import json
import logging
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

import httpx

from config.arize_config import (
    get_phoenix_endpoint,
    is_phoenix_configured,
    get_phoenix_mode,
    PHOENIX_API_KEY,
)

logger = logging.getLogger(__name__)


class PhoenixMCPBridge:
    """
    Bridge to Phoenix MCP server for self-introspection capabilities.

    This class provides methods to query traces, evaluations, and experiments
    from Phoenix, enabling the agent to reflect on its own performance.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
    ):
        """
        Initialize the Phoenix MCP bridge.

        Args:
            base_url: Phoenix base URL (defaults to env var or standard cloud URL)
            api_key: Phoenix API key for cloud mode (defaults to env var)
            timeout: HTTP request timeout in seconds
        """
        self.base_url = (base_url or get_phoenix_endpoint()).rstrip("/")
        self.api_key = api_key or PHOENIX_API_KEY
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._connected = False

        # Build API endpoints
        if get_phoenix_mode() == "cloud":
            self.api_base = f"{self.base_url}/v1"
        else:
            # Self-hosted Phoenix uses different endpoint structure
            self.api_base = f"{self.base_url}/api"

    async def connect(self) -> bool:
        """
        Establish connection to Phoenix.

        Returns:
            True if connection successful, False otherwise
        """
        if self._connected:
            return True

        if not is_phoenix_configured():
            logger.warning("[WARN] Phoenix not configured - MCP bridge unavailable")
            return False

        try:
            # Initialize HTTP client
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            self._client = httpx.AsyncClient(
                base_url=self.api_base,
                headers=headers,
                timeout=self.timeout,
            )

            # Test connection
            await self._test_connection()
            self._connected = True
            logger.info(f"[OK] Phoenix MCP bridge connected to {self.base_url}")
            return True

        except Exception as e:
            logger.error(f"[ERROR] Failed to connect to Phoenix: {e}")
            return False

    async def _test_connection(self):
        """Test the Phoenix connection."""
        try:
            # Try to get project info or health check
            response = await self._client.get("/health")
            if response.status_code == 200:
                logger.debug("[DEBUG] Phoenix health check passed")
        except Exception:
            # Health endpoint might not exist, try getting traces instead
            response = await self._client.get("/traces", params={"limit": 1})
            if response.status_code in (200, 404):  # 404 is OK if no traces yet
                logger.debug("[DEBUG] Phoenix API accessible")

    async def disconnect(self):
        """Close the Phoenix connection."""
        if self._client:
            await self._client.aclose()
            self._client = None
            self._connected = False
            logger.info("[OK] Phoenix MCP bridge disconnected")

    async def get_recent_traces(
        self,
        limit: int = 10,
        span_name: Optional[str] = None,
        hours_ago: int = 24,
    ) -> List[Dict[str, Any]]:
        """
        Get recent traces from Phoenix.

        Args:
            limit: Maximum number of traces to return
            span_name: Filter by span name (e.g., "generate_content")
            hours_ago: Only get traces from the last N hours

        Returns:
            List of trace data dictionaries
        """
        if not self._connected:
            await self.connect()

        if not self._connected:
            return []

        try:
            # Build query parameters
            params = {"limit": limit}
            if span_name:
                params["span_name"] = span_name

            # Calculate time range
            start_time = datetime.utcnow() - timedelta(hours=hours_ago)
            params["start_time"] = start_time.isoformat()

            # Make request
            response = await self._client.get("/traces", params=params)
            response.raise_for_status()

            data = response.json()
            traces = data.get("data", [])

            logger.info(f"[OK] Retrieved {len(traces)} traces from Phoenix")
            return traces

        except httpx.HTTPStatusError as e:
            logger.warning(f"[WARN] Phoenix API error: {e.response.status_code}")
            return []
        except Exception as e:
            logger.error(f"[ERROR] Failed to get traces: {e}")
            return []

    async def get_trace_details(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific trace.

        Args:
            trace_id: The trace ID to fetch

        Returns:
            Trace details dictionary or None if not found
        """
        if not self._connected:
            await self.connect()

        if not self._connected:
            return None

        try:
            response = await self._client.get(f"/traces/{trace_id}")
            response.raise_for_status()

            data = response.json()
            logger.debug(f"[DEBUG] Retrieved trace details for {trace_id}")
            return data.get("data")

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.debug(f"[DEBUG] Trace {trace_id} not found")
            else:
                logger.warning(f"[WARN] Phoenix API error: {e.response.status_code}")
            return None
        except Exception as e:
            logger.error(f"[ERROR] Failed to get trace details: {e}")
            return None

    async def get_evaluations(
        self,
        limit: int = 50,
        evaluator_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get evaluation results from Phoenix.

        Args:
            limit: Maximum number of evaluations to return
            evaluator_name: Filter by evaluator name

        Returns:
            List of evaluation data dictionaries
        """
        if not self._connected:
            await self.connect()

        if not self._connected:
            return []

        try:
            params = {"limit": limit}
            if evaluator_name:
                params["evaluator_name"] = evaluator_name

            response = await self._client.get("/evaluations", params=params)
            response.raise_for_status()

            data = response.json()
            evaluations = data.get("data", [])

            logger.info(f"[OK] Retrieved {len(evaluations)} evaluations from Phoenix")
            return evaluations

        except httpx.HTTPStatusError as e:
            logger.warning(f"[WARN] Phoenix API error: {e.response.status_code}")
            return []
        except Exception as e:
            logger.error(f"[ERROR] Failed to get evaluations: {e}")
            return []

    async def get_evaluation_summary(self, hours_ago: int = 24) -> Dict[str, Any]:
        """
        Get a summary of evaluation results.

        Args:
            hours_ago: Only include evaluations from the last N hours

        Returns:
            Summary dictionary with aggregate metrics
        """
        evaluations = await self.get_evaluations(limit=1000)

        # Filter by time
        cutoff = datetime.utcnow() - timedelta(hours=hours_ago)
        recent_evals = [
            e for e in evaluations
            if datetime.fromisoformat(e.get("timestamp", "").replace("Z", "+00:00")) > cutoff
        ]

        if not recent_evals:
            return {
                "total_evaluations": 0,
                "average_score": 0,
                "by_criteria": {},
            }

        # Calculate summary stats
        total = len(recent_evals)
        scores = [e.get("score", 0) for e in recent_evals if e.get("score") is not None]
        avg_score = sum(scores) / len(scores) if scores else 0

        # Group by criteria
        by_criteria = {}
        for eval_data in recent_evals:
            criteria = eval_data.get("criteria", "unknown")
            score = eval_data.get("score", 0)
            if criteria not in by_criteria:
                by_criteria[criteria] = {"count": 0, "total_score": 0}
            by_criteria[criteria]["count"] += 1
            by_criteria[criteria]["total_score"] += score

        # Calculate averages per criteria
        for criteria in by_criteria:
            by_criteria[criteria]["average"] = (
                by_criteria[criteria]["total_score"] / by_criteria[criteria]["count"]
            )

        return {
            "total_evaluations": total,
            "average_score": avg_score,
            "by_criteria": by_criteria,
        }

    async def get_experiments(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get A/B experiment results from Phoenix.

        Args:
            limit: Maximum number of experiments to return

        Returns:
            List of experiment data dictionaries
        """
        if not self._connected:
            await self.connect()

        if not self._connected:
            return []

        try:
            response = await self._client.get("/experiments", params={"limit": limit})
            response.raise_for_status()

            data = response.json()
            experiments = data.get("data", [])

            logger.info(f"[OK] Retrieved {len(experiments)} experiments from Phoenix")
            return experiments

        except httpx.HTTPStatusError as e:
            logger.warning(f"[WARN] Phoenix API error: {e.response.status_code}")
            return []
        except Exception as e:
            logger.error(f"[ERROR] Failed to get experiments: {e}")
            return []

    async def query_traces_by_metadata(
        self,
        metadata_filters: Dict[str, Any],
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Query traces by metadata attributes.

        Args:
            metadata_filters: Key-value pairs to filter traces by
            limit: Maximum number of traces to return

        Returns:
            List of matching trace dictionaries

        Example:
            await bridge.query_traces_by_metadata(
                {"mr_id": "123", "project_id": "myproject"}
            )
        """
        if not self._connected:
            await self.connect()

        if not self._connected:
            return []

        try:
            # Build query with metadata filters
            # Note: Phoenix API syntax for metadata filtering may vary
            params = {"limit": limit}

            # Add metadata as JSON filter
            if metadata_filters:
                params["filter"] = json.dumps(metadata_filters)

            response = await self._client.get("/traces", params=params)

            if response.status_code == 200:
                data = response.json()
                traces = data.get("data", [])
                logger.info(f"[OK] Found {len(traces)} traces matching filters")
                return traces
            else:
                logger.warning(f"[WARN] Query returned status {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"[ERROR] Failed to query traces by metadata: {e}")
            return []

    async def get_performance_metrics(self, hours_ago: int = 24) -> Dict[str, Any]:
        """
        Get performance metrics from traced operations.

        Args:
            hours_ago: Only include data from the last N hours

        Returns:
            Dictionary with performance metrics
        """
        traces = await self.get_recent_traces(limit=1000, hours_ago=hours_ago)

        if not traces:
            return {
                "total_traces": 0,
                "average_latency_ms": 0,
                "success_rate": 0,
                "error_count": 0,
            }

        # Calculate metrics
        total = len(traces)
        latencies = []
        error_count = 0

        for trace in traces:
            # Extract latency (in milliseconds)
            latency_ms = trace.get("latency_ms", 0)
            if latency_ms:
                latencies.append(latency_ms)

            # Check for errors
            if trace.get("error"):
                error_count += 1

        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        success_rate = ((total - error_count) / total * 100) if total > 0 else 0

        return {
            "total_traces": total,
            "average_latency_ms": round(avg_latency, 2),
            "success_rate": round(success_rate, 2),
            "error_count": error_count,
        }

    def is_connected(self) -> bool:
        """Check if the bridge is connected."""
        return self._connected

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()


# Global Phoenix MCP bridge instance
_phoenix_bridge: Optional[PhoenixMCPBridge] = None


async def get_phoenix_bridge() -> PhoenixMCPBridge:
    """
    Get the global Phoenix MCP bridge instance.

    Returns:
        The PhoenixMCPBridge instance (connected if not already)
    """
    global _phoenix_bridge

    if _phoenix_bridge is None:
        _phoenix_bridge = PhoenixMCPBridge()

    if not _phoenix_bridge.is_connected():
        await _phoenix_bridge.connect()

    return _phoenix_bridge


async def close_phoenix_bridge():
    """Close the global Phoenix MCP bridge."""
    global _phoenix_bridge

    if _phoenix_bridge:
        await _phoenix_bridge.disconnect()
        _phoenix_bridge = None
