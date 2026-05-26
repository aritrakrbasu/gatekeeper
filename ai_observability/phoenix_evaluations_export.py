"""
Phoenix Evaluation Export Module.

This module handles exporting evaluation results to Phoenix/Arize Evaluations tab.
It uses the proper Arize Cloud API for cloud deployments and Phoenix SDK for self-hosted.
"""

import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

import pandas as pd

logger = logging.getLogger(__name__)


class PhoenixEvalExporter:
    """
    Export evaluation results to Phoenix/Arize Evaluations tab.

    This class provides methods to export evaluation records so they
    appear in the Phoenix/Arize UI Evaluations tab (not just as span attributes).
    """

    def __init__(self, project_name: Optional[str] = None):
        """
        Initialize the Phoenix evaluation exporter.

        Args:
            project_name: Phoenix/Arize project name (defaults to env var or "gatekeeper")
        """
        self.project_name = project_name or os.getenv("PHOENIX_PROJECT_NAME", "gatekeeper")
        self._pending_evaluations: List[Dict[str, Any]] = []

    def add_evaluation(
        self,
        span_id: str,
        eval_name: str,
        score: float,
        label: Optional[str] = None,
        explanation: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Add an evaluation record for export.

        Args:
            span_id: The span ID this evaluation applies to
            eval_name: Name of the evaluation (e.g., 'security_coverage')
            score: Numeric score (0-1 for binary, 0-5 for ratings)
            label: Optional label (e.g., 'pass', 'fail', 'critical')
            explanation: Optional explanation text
            metadata: Optional additional metadata
        """
        self._pending_evaluations.append({
            "span_id": span_id,
            "eval_name": eval_name,
            "score": score,
            "label": label,
            "explanation": explanation,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat(),
        })

        logger.debug(f"[DEBUG] Added evaluation: {eval_name} = {score} for span {span_id[:12]}...")

    async def export_to_phoenix(self) -> bool:
        """
        Export all pending evaluations to Phoenix/Arize Evaluations tab.

        This uses the appropriate method based on Phoenix deployment mode:
        - Arize Cloud: Uses Arize SDK's evaluation export
        - Self-hosted Phoenix: Uses Phoenix SDK's log_evaluations

        Returns:
            True if export was successful, False otherwise
        """
        if not self._pending_evaluations:
            logger.debug("[DEBUG] No evaluations to export")
            return True

        try:
            from config.arize_config import (
                is_arize_initialized,
                is_phoenix_configured,
                get_phoenix_mode,
                get_phoenix_endpoint,
                get_phoenix_api_key,
                SPACE_ID,
                API_KEY,
            )

            phoenix_mode = get_phoenix_mode()

            # Get current span ID for linking
            from opentelemetry import trace
            current_span = trace.get_current_span()
            span_id = None
            if current_span and current_span.is_recording():
                from opentelemetry.trace import format_span_id
                span_context = current_span.get_span_context()
                if span_context.is_valid:
                    span_id = format_span_id(span_context.span_id)

            if not span_id:
                logger.warning("[⚠️] No active span found - evaluations may not link properly")

            # Group evaluations by name
            eval_groups: Dict[str, List[Dict]] = {}
            for eval_data in self._pending_evaluations:
                name = eval_data["eval_name"]
                if name not in eval_groups:
                    eval_groups[name] = []
                eval_groups[name].append(eval_data)

            # Export each group
            exported_count = 0
            for eval_name, evals in eval_groups.items():
                try:
                    # Create DataFrame for Phoenix
                    rows = []
                    for eval_data in evals:
                        row = {
                            "span_id": eval_data.get("span_id") or span_id or "unknown",
                            "score": eval_data["score"],
                        }
                        if eval_data.get("label"):
                            row["label"] = eval_data["label"]
                        if eval_data.get("explanation"):
                            row["explanation"] = eval_data["explanation"][:1000]

                        rows.append(row)

                    df = pd.DataFrame(rows)

                    if not df.empty:
                        # Choose export method based on mode
                        if phoenix_mode == "cloud" and SPACE_ID and API_KEY:
                            # Use Arize Cloud export
                            success = await self._export_via_arize_cloud(
                                eval_name, df, SPACE_ID, API_KEY
                            )
                        else:
                            # Use Phoenix SDK export
                            success = await self._export_via_phoenix_sdk(eval_name, df)

                        if success:
                            exported_count += len(df)
                            logger.info(f"[✅] Exported {len(df)} '{eval_name}' evaluations")
                        else:
                            logger.warning(f"[⚠️] Failed to export '{eval_name}' evaluations")

                except Exception as e:
                    logger.error(f"[x] Failed to export evaluation '{eval_name}': {e}")
                    import traceback
                    logger.debug(f"[DEBUG] Export error: {traceback.format_exc()[:500]}")

            if exported_count > 0:
                logger.info(f"[✅] Total evaluations exported: {exported_count}")
                self._pending_evaluations.clear()
                return True
            else:
                logger.warning("[⚠️] No evaluations were exported")
                return False

        except ImportError:
            logger.warning("[⚠️] Phoenix evaluation export not available - evaluations logged as span attributes only")
            return False
        except Exception as e:
            logger.error(f"[x] Failed to export evaluations to Phoenix: {e}")
            return False

    async def _export_via_phoenix_sdk(self, eval_name: str, dataframe: pd.DataFrame) -> bool:
        """
        Export using Phoenix SDK's log_evaluations (for self-hosted Phoenix).

        Args:
            eval_name: Name of the evaluation
            dataframe: DataFrame with evaluation data

        Returns:
            True if successful, False otherwise
        """
        try:
            from phoenix.trace.evaluations import log_evaluations

            log_evaluations(
                dataframe=dataframe,
                eval_name=eval_name,
            )
            return True
        except Exception as e:
            logger.warning(f"[⚠️] Phoenix SDK export failed: {e}")
            return False

    async def _export_via_arize_cloud(
        self,
        eval_name: str,
        dataframe: pd.DataFrame,
        space_id: str,
        api_key: str,
    ) -> bool:
        """
        Export evaluations to Arize Cloud.

        For Arize Cloud, we need to use the Arize SDK or direct API calls.
        This implementation uses the direct Arize evaluation API.

        Args:
            eval_name: Name of the evaluation
            dataframe: DataFrame with evaluation data
            space_id: Arize space ID
            api_key: Arize API key

        Returns:
            True if successful, False otherwise
        """
        try:
            import httpx

            # Arize Cloud API endpoint for evaluations
            base_url = os.getenv("PHOENIX_BASE_URL", "https://app.phoenix.arize.com").rstrip("/")

            # Try multiple possible endpoints for Arize Cloud
            endpoints = [
                f"{base_url}/v1/spaces/{space_id}/evaluations",
                f"{base_url}/api/v1/spaces/{space_id}/evaluations",
            ]

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }

            # Prepare evaluation data
            eval_records = []
            for _, row in dataframe.iterrows():
                record = {
                    "span_id": row.get("span_id", ""),
                    "score": float(row.get("score", 0)),
                }
                if "label" in row and pd.notna(row["label"]):
                    record["label"] = str(row["label"])
                if "explanation" in row and pd.notna(row["explanation"]):
                    record["explanation"] = str(row["explanation"])[:5000]
                eval_records.append(record)

            payload = {
                "eval_name": eval_name,
                "evaluations": eval_records,
            }

            # Try each endpoint
            for endpoint in endpoints:
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.post(
                            endpoint,
                            json=payload,
                            headers=headers,
                        )

                        if response.status_code in (200, 201, 202):
                            logger.info(f"[✅] Exported to Arize Cloud via {endpoint}")
                            return True
                        else:
                            logger.debug(
                                f"[DEBUG] Endpoint {endpoint} returned {response.status_code}: "
                                f"{response.text[:200]}"
                            )

                except httpx.ConnectError:
                    logger.debug(f"[DEBUG] Connection error to {endpoint}")
                    continue
                except Exception as e:
                    logger.debug(f"[DEBUG] Error calling {endpoint}: {e}")
                    continue

            # If API endpoints fail, try using the Phoenix SDK with environment config
            logger.info("[*] API endpoints failed, trying Phoenix SDK with Arize config...")
            return await self._export_via_phoenix_sdk(eval_name, dataframe)

        except Exception as e:
            logger.warning(f"[⚠️] Arize Cloud export failed: {e}")
            # Fallback to SDK
            return await self._export_via_phoenix_sdk(eval_name, dataframe)

    def flush(self) -> bool:
        """
        Synchronous flush of pending evaluations.

        Returns:
            True if export was successful, False otherwise
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.export_to_phoenix())
                    return future.result(timeout=60)
            else:
                return asyncio.run(self.export_to_phoenix())
        except Exception as e:
            logger.error(f"[x] Failed to flush evaluations: {e}")
            return False

    async def flush_async(self) -> bool:
        """
        Asynchronous flush of pending evaluations.

        Returns:
            True if export was successful, False otherwise
        """
        return await self.export_to_phoenix()

    def clear(self):
        """Clear all pending evaluations without exporting."""
        self._pending_evaluations.clear()


# Global exporter instance
_exporter: Optional[PhoenixEvalExporter] = None


def get_phoenix_exporter() -> PhoenixEvalExporter:
    """Get the global Phoenix evaluation exporter instance."""
    global _exporter
    if _exporter is None:
        _exporter = PhoenixEvalExporter()
    return _exporter


# Alias for compatibility with evaluators.py import
def get_evaluation_exporter() -> PhoenixEvalExporter:
    """Get the global evaluation exporter instance (alias for compatibility)."""
    return get_phoenix_exporter()
