"""
AI Observability Module for The Gatekeeper.

This module provides LLM-as-a-Judge evaluation and self-improvement capabilities.
"""

from .evaluators import (
    ReviewQualityEvaluator,
    BatchEvaluator,
    EvaluationCriteria,
    get_evaluator,
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
    "ReviewQualityEvaluator",
    "BatchEvaluator",
    "EvaluationCriteria",
    "get_evaluator",
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
]
