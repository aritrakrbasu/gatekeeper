"""
Phoenix Evaluation Export Module.

This module handles the creation and export of formal evaluation records
to Phoenix/Arize that appear in the Evaluations tab.
"""

import pandas as pd
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path
import json
import os
import httpx

logger = logging.getLogger(__name__)


class PhoenixEvaluationExporter:
    """
    Exports evaluations to Phoenix/Arize in the format expected by the Evaluations tab.

    This creates formal evaluation records that can be viewed in the
    Phoenix Evaluations tab, not just span attributes.
    """

    def __init__(self, project_name: str = "gatekeeper", storage_path: Optional[str] = None):
        """
        Initialize the Phoenix evaluation exporter.

        Args:
            project_name: Project name for grouping evaluations
            storage_path: Optional path to store evaluation parquet files locally
        """
        self.project_name = project_name
        self._evaluations: List[Dict[str, Any]] = []
        self.storage_path = storage_path or Path(__file__).parent.parent / "evaluations_store"
        self.storage_path = Path(self.storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

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
        Add an evaluation record to be exported.

        Args:
            span_id: The span ID this evaluation applies to
            eval_name: Name of the evaluation (e.g., 'security_coverage')
            score: Numeric score (0-1 for binary, 0-5 for ratings)
            label: Optional label (e.g., 'pass', 'fail', 'toxic')
            explanation: Optional explanation text
            metadata: Optional additional metadata
        """
        self._evaluations.append({
            "span_id": span_id,
            "eval_name": eval_name,
            "score": score,
            "label": label,
            "explanation": explanation,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def _export_via_phoenix_api(
        self,
        eval_name: str,
        dataframe: pd.DataFrame,
    ) -> bool:
        """
        Export evaluations via Phoenix Cloud REST API.

        This uses the Phoenix Cloud API to send evaluations that will appear
        in the Evaluations tab. For Arize Cloud, we use the project-scoped
        span_annotations endpoint.

        Args:
            eval_name: Name of the evaluation
            dataframe: DataFrame with evaluation data

        Returns:
            True if successful, False otherwise
        """
        from config.arize_config import (
            PHOENIX_API_KEY,
            get_phoenix_endpoint,
            get_phoenix_mode,
            get_phoenix_project_name,
        )

        phoenix_mode = get_phoenix_mode()
        project_name = get_phoenix_project_name()

        # For Phoenix Cloud, use the correct API endpoint
        base_url = get_phoenix_endpoint().rstrip("/")

        # Prepare the evaluation data in the format expected by Phoenix/Arize
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

        headers = {
            "Content-Type": "application/json",
        }

        # Add authentication for Phoenix Cloud
        if PHOENIX_API_KEY:
            headers["Authorization"] = f"Bearer {PHOENIX_API_KEY}"

        # Phoenix Cloud API endpoints
        if phoenix_mode == "cloud":
            # For Arize Cloud, use the project-scoped span_annotations endpoint
            # This is the key fix - evaluations must be sent to the specific project
            endpoints = [
                f"{base_url}/v1/projects/{project_name}/span_annotations",
                f"{base_url}/v1/span_annotations",  # Fallback to global endpoint
            ]
        else:
            # Self-hosted Phoenix
            endpoints = [
                f"{base_url}/v1/span_annotations",
            ]

        # Prepare the evaluation data
        eval_data = {
            "data": annotations,  # Phoenix expects the data array at the root
        }

        # Try each endpoint
        for endpoint in endpoints:
            try:
                logger.info(f"[*] Trying endpoint: {endpoint}")

                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        endpoint,
                        json=eval_data,
                        headers=headers,
                    )

                    if response.status_code in (200, 201, 202):
                        logger.info(f"[✅] Successfully exported {len(annotations)} '{eval_name}' evaluations to Arize Cloud project '{project_name}'")
                        return True

            except httpx.ConnectError as e:
                continue
            except Exception as e:
                continue

        logger.warning(f"[⚠️] All Phoenix API endpoints failed for '{eval_name}'")
        return False

    async def flush_async(self) -> bool:
        """
        Flush all pending evaluations to Phoenix (async version).

        Returns:
            True if evaluations were sent successfully, False otherwise
        """
        if not self._evaluations:
            return True

        from config.arize_config import is_phoenix_configured, get_phoenix_mode

        if not is_phoenix_configured():
            logger.warning("[⚠️] Phoenix not configured - cannot flush evaluations")
            self._save_locally()
            return False

        phoenix_mode = get_phoenix_mode()
        logger.info(f"[*] Phoenix mode: {phoenix_mode}")
        logger.info(f"[*] Exporting {len(self._evaluations)} evaluations to Evaluations tab...")

        # Group evaluations by eval_name for export
        eval_groups: Dict[str, List[Dict]] = {}
        for eval_data in self._evaluations:
            eval_name = eval_data["eval_name"]
            if eval_name not in eval_groups:
                eval_groups[eval_name] = []
            eval_groups[eval_name].append(eval_data)

        # Export each evaluation type
        exported_count = 0
        for eval_name, evals in eval_groups.items():
            try:
                # Create DataFrame for this evaluation type
                rows = []
                for eval_data in evals:
                    row = {
                        "span_id": eval_data["span_id"],
                        "score": eval_data["score"],
                    }
                    if eval_data.get("label"):
                        row["label"] = eval_data["label"]
                    if eval_data.get("explanation"):
                        row["explanation"] = eval_data["explanation"][:1000]

                    # Add metadata as columns
                    for key, value in eval_data.get("metadata", {}).items():
                        if key not in ["span_id", "score", "label", "explanation"]:
                            row[f"metadata.{key}"] = str(value)[:500]

                    rows.append(row)

                df = pd.DataFrame(rows)
                logger.info(f"[*] Exporting {len(df)} '{eval_name}' evaluations via Phoenix API...")

                # Try to export via Phoenix API
                if phoenix_mode == "cloud":
                    success = await self._export_via_phoenix_api(eval_name, df)
                else:
                    # For self-hosted, try SDK methods
                    success = await self._export_via_sdk(eval_name, df)

                if success:
                    exported_count += len(df)
                else:
                    # Save failed export locally
                    self._save_group_locally(eval_name, evals)

            except Exception as e:
                logger.error(f"[x] Failed to export evaluation '{eval_name}': {e}")
                self._save_group_locally(eval_name, evals)

        if exported_count > 0:
            logger.info(f"[✅] Successfully exported {exported_count} evaluations to Phoenix Evaluations tab")
            self._evaluations.clear()
            return True

        logger.warning("[⚠️] No evaluations were successfully exported")
        return False

    async def _export_via_sdk(self, eval_name: str, dataframe: pd.DataFrame) -> bool:
        """Export via Phoenix SDK (for self-hosted)."""
        try:
            from phoenix.trace.evaluations import log_evaluations

            logger.info(f"[*] Using Phoenix SDK log_evaluations...")
            log_evaluations(eval_name=eval_name, dataframe=dataframe)
            return True
        except Exception as e:
            logger.warning(f"[⚠️] SDK export failed: {e}")
            return False

    def flush(self) -> bool:
        """
        Flush all pending evaluations to Phoenix (sync wrapper).

        Returns:
            True if evaluations were sent successfully, False otherwise
        """
        import asyncio

        try:
            # Try to get the running event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context, create a task
                import concurrent.futures

                # Run in a thread pool to avoid blocking
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.flush_async())
                    return future.result(timeout=60)
            else:
                # No loop running, just run
                return asyncio.run(self.flush_async())
        except Exception as e:
            logger.error(f"[x] Failed to flush evaluations: {e}")
            self._save_locally()
            return False

    def _save_group_locally(self, eval_name: str, evals: List[Dict]):
        """Save a group of evaluations locally as fallback."""
        try:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"{eval_name}_{timestamp}.jsonl"
            filepath = self.storage_path / filename

            with open(filepath, 'w') as f:
                for eval_data in evals:
                    f.write(json.dumps(eval_data) + '\n')

            logger.info(f"[💾] Saved {len(evals)} '{eval_name}' evaluations locally to {filepath}")
        except Exception as e:
            logger.error(f"[x] Failed to save evaluations locally: {e}")

    def _save_locally(self):
        """Save all pending evaluations locally as fallback."""
        if not self._evaluations:
            return

        try:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"evaluations_{timestamp}.jsonl"
            filepath = self.storage_path / filename

            with open(filepath, 'w') as f:
                for eval_data in self._evaluations:
                    f.write(json.dumps(eval_data) + '\n')

            logger.info(f"[💾] Saved {len(self._evaluations)} evaluations locally to {filepath}")
            self._evaluations.clear()
        except Exception as e:
            logger.error(f"[x] Failed to save evaluations locally: {e}")

    def export_as_dataframe(self) -> Optional[pd.DataFrame]:
        """
        Export evaluations as a pandas DataFrame.

        Returns:
            DataFrame with evaluation records
        """
        if not self._evaluations:
            return None

        rows = []
        for eval_data in self._evaluations:
            row = {
                "span_id": eval_data["span_id"],
                "eval_name": eval_data["eval_name"],
                "score": eval_data["score"],
                "timestamp": eval_data["timestamp"],
            }
            if eval_data.get("label"):
                row["label"] = eval_data["label"]
            if eval_data.get("explanation"):
                row["explanation"] = eval_data["explanation"]

            # Add metadata
            for key, value in eval_data.get("metadata", {}).items():
                row[f"metadata.{key}"] = str(value)

            rows.append(row)

        return pd.DataFrame(rows)

    def clear(self):
        """Clear all stored evaluations."""
        self._evaluations.clear()


# Global exporter instance
_exporter: Optional[PhoenixEvaluationExporter] = None


def get_evaluation_exporter() -> PhoenixEvaluationExporter:
    """Get the global evaluation exporter instance."""
    global _exporter
    if _exporter is None:
        _exporter = PhoenixEvaluationExporter()
    return _exporter


def export_evaluation_to_phoenix(
    span_id: str,
    eval_name: str,
    score: float,
    label: Optional[str] = None,
    explanation: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    Convenience function to export a single evaluation to Phoenix.

    Args:
        span_id: The span ID this evaluation applies to
        eval_name: Name of the evaluation (e.g., 'security_coverage')
        score: Numeric score (0-1 for binary, 0-5 for ratings)
        label: Optional label (e.g., 'pass', 'fail', 'toxic')
        explanation: Optional explanation text
        metadata: Optional additional metadata
    """
    exporter = get_evaluation_exporter()
    exporter.add_evaluation(
        span_id=span_id,
        eval_name=eval_name,
        score=score,
        label=label,
        explanation=explanation,
        metadata=metadata,
    )


async def flush_evaluations_async() -> bool:
    """
    Async flush all pending evaluations to Phoenix.

    Returns:
        True if evaluations were sent successfully, False otherwise
    """
    exporter = get_evaluation_exporter()
    return await exporter.flush_async()


def flush_evaluations() -> bool:
    """
    Flush all pending evaluations to Phoenix.

    Returns:
        True if evaluations were sent successfully, False otherwise
    """
    exporter = get_evaluation_exporter()
    return exporter.flush()
