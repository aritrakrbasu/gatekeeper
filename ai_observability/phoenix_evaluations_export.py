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

        This uses Phoenix Client's log_span_annotations API, which works for
        both Arize Cloud and self-hosted Phoenix deployments. Evaluations are
        sent as "annotations" which appear in the Evaluations tab.

        Returns:
            True if export was successful, False otherwise
        """
        if not self._pending_evaluations:
            logger.debug("[DEBUG] No evaluations to export")
            return True

        try:
            from config.arize_config import (
                is_phoenix_configured,
            )

            if not is_phoenix_configured():
                logger.warning("[⚠️] Phoenix not configured - evaluations will only be in span attributes")

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
                        # Use unified Phoenix Client approach for both cloud and self-hosted
                        # Phoenix Client handles both modes via log_span_annotations
                        success = await self._export_via_phoenix_client_annotations(eval_name, df)

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

    async def _export_via_phoenix_client_annotations(
        self,
        eval_name: str,
        dataframe: pd.DataFrame,
    ) -> bool:
        """
        Export evaluations using Phoenix Client's log_span_annotations.

        This creates formal evaluation records (called "annotations" in Phoenix/Arize)
        that appear in the Evaluations tab of the Arize Cloud UI.

        Args:
            eval_name: Name of the evaluation
            dataframe: DataFrame with evaluation data

        Returns:
            True if successful, False otherwise
        """
        try:
            from phoenix.client import Client

            # Get Phoenix configuration
            base_url = os.getenv("PHOENIX_BASE_URL", "https://app.phoenix.arize.com")
            api_key = os.getenv("PHOENIX_API_KEY")

            # Create Phoenix Client
            client = Client(base_url=base_url, api_key=api_key)

            # Build annotation data for Phoenix/Arize
            annotations = []
            for _, row in dataframe.iterrows():
                span_id = row.get("span_id", "")
                score = float(row.get("score", 0))

                annotation_data = {
                    "span_id": span_id,
                    "name": eval_name,
                    "annotator_kind": "CODE",  # Programmatic LLM-as-a-Judge evaluations
                    "result": {
                        "score": score,
                    }
                }

                # Add optional fields
                if "label" in row and pd.notna(row["label"]):
                    annotation_data["result"]["label"] = str(row["label"])

                if "explanation" in row and pd.notna(row["explanation"]):
                    annotation_data["result"]["explanation"] = str(row["explanation"])[:5000]

                annotations.append(annotation_data)

            # Use Phoenix Client's log_span_annotations method
            # This works for both Arize Cloud and self-hosted Phoenix
            client.spans.log_span_annotations(
                span_annotations=annotations,
                sync=False  # Async processing is fine for evaluations
            )

            logger.info(f"[✅] Exported {len(annotations)} '{eval_name}' annotations to Phoenix/Arize")
            return True

        except ImportError:
            logger.warning("[⚠️] Phoenix Client not available - falling back to SDK")
            return await self._export_via_phoenix_sdk(eval_name, dataframe)
        except Exception as e:
            logger.warning(f"[⚠️] Phoenix Client export failed: {e}")
            import traceback
            logger.debug(f"[DEBUG] Annotation export error: {traceback.format_exc()[:500]}")
            # Fallback to SDK method
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
