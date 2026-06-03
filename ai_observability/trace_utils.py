"""
Trace utilities for linking evaluations to traces in Arize/Phoenix.

This module provides helper functions to extract trace IDs from the
OpenTelemetry context and properly link evaluations to traces.
"""

import logging
from typing import Optional
from opentelemetry import trace
from opentelemetry.trace import format_trace_id, get_current_span

logger = logging.getLogger(__name__)


def get_current_trace_id() -> Optional[str]:
    """
    Get the current trace ID from the OpenTelemetry context.

    This returns the trace ID in hexadecimal format, which can be used
    to link evaluations to traces in Arize/Phoenix.

    Returns:
        The current trace ID as a hex string, or None if no trace is active
    """
    try:
        current_span = get_current_span()

        if current_span and current_span.is_recording():
            span_context = current_span.get_span_context()

            if span_context and span_context.is_valid:
                # Format trace ID as 32-character hex string
                trace_id = format_trace_id(span_context.trace_id)
                return trace_id

        return None

    except Exception as e:
        return None


def get_current_span_id() -> Optional[str]:
    """
    Get the current span ID from the OpenTelemetry context.

    Returns:
        The current span ID as a hex string, or None if no span is active
    """
    try:
        current_span = get_current_span()

        if current_span and current_span.is_recording():
            span_context = current_span.get_span_context()

            if span_context and span_context.is_valid:
                # Format span ID as 16-character hex string
                from opentelemetry.trace import format_span_id
                span_id = format_span_id(span_context.span_id)
                return span_id

        return None

    except Exception as e:
        return None


def get_trace_context() -> dict:
    """
    Get the full trace context (trace_id and span_id) from OpenTelemetry.

    Returns:
        Dictionary with 'trace_id' and 'span_id' keys (values may be None)
    """
    return {
        "trace_id": get_current_trace_id(),
        "span_id": get_current_span_id(),
    }


def link_evaluation_to_trace(
    evaluation_data: dict,
    trace_id: Optional[str] = None,
) -> dict:
    """
    Add trace linkage information to evaluation data.

    This ensures the evaluation can be associated with the trace
    in the Arize/Phoenix dashboard.

    Args:
        evaluation_data: The evaluation data dictionary
        trace_id: Optional trace ID (will be auto-detected if not provided)

    Returns:
        The evaluation data with trace linkage added
    """
    if trace_id is None:
        trace_id = get_current_trace_id()

    if trace_id:
        evaluation_data["linked_trace_id"] = trace_id
        evaluation_data["trace_id"] = trace_id  # For compatibility

    return evaluation_data
