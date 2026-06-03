"""
Arize/Phoenix Cloud Evaluation Export Module.

This module handles exporting evaluations to Arize Phoenix Cloud.
For Phoenix Cloud, evaluations need to be exported via Arize's API rather than
the local Phoenix log_evaluations function.
"""

import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)


class ArizeCloudEvalExporter:
    """
    Export evaluation records to Arize Phoenix Cloud.

    For Phoenix Cloud (app.phoenix.arize.com), evaluations must be exported
    via the Arize/Phoenix Cloud API rather than the local log_evaluations function.
    """

    def __init__(
        self,
        space_id: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: str = "https://app.phoenix.arize.com",
    ):
        """
        Initialize the Arize Cloud exporter.

        Args:
            space_id: Arize space ID (defaults to env var ARIZE_SPACE_ID)
            api_key: Arize API key (defaults to env var ARIZE_API_KEY)
            base_url: Phoenix Cloud base URL
        """
        self.space_id = space_id or os.getenv("ARIZE_SPACE_ID", "")
        self.api_key = api_key or os.getenv("ARIZE_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            headers = {
                "Content-Type": "application/json",
            }
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=30.0,
            )
        return self._client

    async def export_evaluations(
        self,
        evaluations: List[Dict[str, Any]],
        project_name: str = "gatekeeper",
    ) -> bool:
        """
        Export evaluation records to Arize Phoenix Cloud.

        Args:
            evaluations: List of evaluation dictionaries with:
                - span_id: The span ID being evaluated
                - eval_name: Name of the evaluation (e.g., 'security_coverage')
                - score: Numeric score (0-1 range)
                - label: Text label (e.g., 'critical', 'high', 'medium')
                - explanation: Text explanation
            project_name: Project name for grouping

        Returns:
            True if export was successful, False otherwise
        """
        if not evaluations:
            return True

        if not self.space_id or not self.api_key:
            logger.warning(
                "[⚠️] ARIZE_SPACE_ID or ARIZE_API_KEY not configured - "
                "cannot export evaluations to Phoenix Cloud"
            )
            logger.info(
                "[ℹ️] To export evaluations to Phoenix Cloud, set ARIZE_SPACE_ID and ARIZE_API_KEY in .env"
            )
            return False

        try:
            client = self._get_client()

            # Group evaluations by name
            eval_groups: Dict[str, List[Dict]] = {}
            for eval_data in evaluations:
                name = eval_data.get("eval_name", eval_data.get("criteria", "unknown"))
                if name not in eval_groups:
                    eval_groups[name] = []
                eval_groups[name].append(eval_data)

            # Export each group
            exported_count = 0
            for eval_name, evals in eval_groups.items():
                try:
                    # Prepare evaluation data for Arize
                    arize_evals = []
                    for eval_data in evals:
                        arize_evals.append({
                            "span_id": eval_data.get("span_id", ""),
                            "score": float(eval_data.get("score", 0)),
                            "label": eval_data.get("label", ""),
                            "explanation": eval_data.get("explanation", "")[:5000],
                        })

                    # Arize Phoenix Cloud API endpoint for evaluations
                    # Note: This is a simplified approach - actual API may differ
                    url = f"{self.base_url}/v1/spaces/{self.space_id}/evaluations"

                    response = await client.post(
                        url,
                        json={
                            "project_name": project_name,
                            "evaluations": arize_evals,
                        },
                    )

                    if response.status_code in (200, 201, 202):
                        exported_count += len(arize_evals)
                        logger.info(f"[✅] Exported {len(arize_evals)} '{eval_name}' evaluations to Phoenix Cloud")
                    else:
                        logger.warning(
                            f"[⚠️] Failed to export '{eval_name}' evaluations: "
                            f"Status {response.status_code}: {response.text[:200]}"
                        )

                except Exception as e:
                    logger.error(f"[x] Failed to export evaluation '{eval_name}': {e}")

            if exported_count > 0:
                logger.info(f"[✅] Total evaluations exported to Phoenix Cloud: {exported_count}")
                return True
            else:
                logger.warning("[⚠️] No evaluations were successfully exported")
                return False

        except Exception as e:
            logger.error(f"[x] Failed to export evaluations to Phoenix Cloud: {e}")
            return False

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Global exporter instance
_exporter: Optional[ArizeCloudEvalExporter] = None


def get_arize_cloud_exporter() -> ArizeCloudEvalExporter:
    """Get the global Arize Cloud exporter instance."""
    global _exporter
    if _exporter is None:
        _exporter = ArizeCloudEvalExporter()
    return _exporter
