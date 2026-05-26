"""
Phoenix Evaluation Storage for Batch Evaluation.

This module stores evaluation results that can be used for batch evaluation
in the Phoenix UI. Phoenix doesn't support real-time individual evaluation
uploads, but does support batch evaluation of collected traces.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from opentelemetry import trace
from opentelemetry.trace import format_span_id

from .trace_utils import get_current_span_id

logger = logging.getLogger(__name__)


class EvaluationStore:
    """
    Stores evaluation results for later batch evaluation in Phoenix.

    Phoenix evaluations work best when run as batch evaluations on
    collected traces, not as individual real-time uploads.
    """

    def __init__(self, storage_dir: Optional[Path] = None):
        """
        Initialize the evaluation store.

        Args:
            storage_dir: Directory to store evaluation results (defaults to ./evaluations)
        """
        if storage_dir is None:
            storage_dir = Path(__file__).parent.parent / "evaluations"

        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)

        self._current_batch: List[Dict[str, Any]] = []

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
        Add an evaluation to the current batch.

        Args:
            span_id: The span ID this evaluation applies to
            eval_name: Name of the evaluation (e.g., 'security_coverage')
            score: Numeric score (0-1 for binary, 0-5 for ratings)
            label: Optional label (e.g., 'pass', 'fail')
            explanation: Optional explanation text
            metadata: Optional additional metadata
        """
        evaluation = {
            "span_id": span_id,
            "eval_name": eval_name,
            "score": score,
            "label": label,
            "explanation": explanation,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat(),
        }

        self._current_batch.append(evaluation)
        logger.debug(f"[DEBUG] Stored evaluation: {eval_name} = {score} for span {span_id[:12]}...")

    def save_batch(self, batch_name: Optional[str] = None) -> Path:
        """
        Save the current batch of evaluations to a file.

        Args:
            batch_name: Optional name for the batch file (defaults to timestamp)

        Returns:
            Path to the saved file
        """
        if not self._current_batch:
            logger.warning("[⚠️] No evaluations to save")
            return None

        if batch_name is None:
            batch_name = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        filename = f"evaluations_{batch_name}.jsonl"
        filepath = self.storage_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            for evaluation in self._current_batch:
                f.write(json.dumps(evaluation) + '\n')

        logger.info(f"[✅] Saved {len(self._current_batch)} evaluations to {filepath}")

        # Clear the batch after saving
        batch_size = len(self._current_batch)
        self._current_batch.clear()

        return filepath

    def get_batch_count(self) -> int:
        """Get the number of evaluations in the current batch."""
        return len(self._current_batch)

    def load_for_phoenix(self) -> Optional[str]:
        """
        Load evaluations in a format suitable for Phoenix batch evaluation.

        Returns:
            JSON string of evaluations for Phoenix, or None if no evaluations
        """
        if not self._current_batch:
            return None

        # Convert to format expected by Phoenix
        phoenix_evals = []
        for evaluation in self._current_batch:
            phoenix_evals.append({
                "span_id": evaluation["span_id"],
                "score": evaluation["score"],
                "label": evaluation.get("label"),
                "explanation": evaluation.get("explanation"),
            })

        return json.dumps(phoenix_evals, indent=2)


# Global evaluation store
_store: Optional[EvaluationStore] = None


def get_evaluation_store() -> EvaluationStore:
    """Get the global evaluation store instance."""
    global _store
    if _store is None:
        _store = EvaluationStore()
    return _store


def store_evaluation(
    span_id: str,
    eval_name: str,
    score: float,
    label: Optional[str] = None,
    explanation: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    Convenience function to store an evaluation.

    Args:
        span_id: The span ID this evaluation applies to
        eval_name: Name of the evaluation (e.g., 'security_coverage')
        score: Numeric score (0-1 for binary, 0-5 for ratings)
        label: Optional label (e.g., 'pass', 'fail')
        explanation: Optional explanation text
        metadata: Optional additional metadata
    """
    store = get_evaluation_store()
    store.add_evaluation(
        span_id=span_id,
        eval_name=eval_name,
        score=score,
        label=label,
        explanation=explanation,
        metadata=metadata,
    )
