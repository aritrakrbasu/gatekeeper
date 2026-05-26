"""
AI Observability Module for The Gatekeeper.

This module provides LLM-as-a-Judge evaluation and self-improvement capabilities.

The module now supports two evaluation backends:
- Phoenix SDK Evaluator (default): Uses Phoenix SDK's ClassificationEvaluator with
  function calling for reliable structured output, built-in rate limiting, and
  automatic OpenTelemetry tracing.
- Legacy Evaluator (fallback): Original Gemini-based evaluator with regex parsing.
"""

# Try to import Phoenix SDK evaluator first (recommended)
try:
    from .phoenix_sdk_evaluator import (
        PhoenixSDKEvaluator,
        EvaluationCriteria,
        get_phoenix_sdk_evaluator,
    )
    PHOENIX_SDK_AVAILABLE = True
except ImportError:
    PHOENIX_SDK_AVAILABLE = False
    # Re-export from legacy module as fallback
    from .evaluators_legacy import EvaluationCriteria

# Legacy evaluator (kept for backward compatibility and fallback)
from .evaluators_legacy import (
    ReviewQualityEvaluator,
    BatchEvaluator,
    get_evaluator as get_legacy_evaluator,
)

from .self_improvement import (
    SelfImprovingPromptManager,
    PromptVersion,
    PromptExperiment,
    get_prompt_manager,
    analyze_and_improve,
)

from .trace_utils import (
    get_current_trace_id,
    get_current_span_id,
    get_trace_context,
    link_evaluation_to_trace,
)

from .phoenix_evaluations import (
    PhoenixEvaluationExporter,
    get_evaluation_exporter,
    export_evaluation_to_phoenix,
    flush_evaluations,
)

__all__ = [
    # Phoenix SDK Evaluator (recommended)
    "PhoenixSDKEvaluator",
    "EvaluationCriteria",
    "get_phoenix_sdk_evaluator",
    "PHOENIX_SDK_AVAILABLE",
    # Legacy Evaluator (backward compatibility)
    "ReviewQualityEvaluator",
    "BatchEvaluator",
    "get_legacy_evaluator",
    # Self-improvement
    "SelfImprovingPromptManager",
    "PromptVersion",
    "PromptExperiment",
    "get_prompt_manager",
    "analyze_and_improve",
    # Trace utilities
    "get_current_trace_id",
    "get_current_span_id",
    "get_trace_context",
    "link_evaluation_to_trace",
    # Phoenix evaluations
    "PhoenixEvaluationExporter",
    "get_evaluation_exporter",
    "export_evaluation_to_phoenix",
    "flush_evaluations",
]
