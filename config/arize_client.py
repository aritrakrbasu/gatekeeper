"""
Arize Cloud Client for Trace Query.

This module enables The Gatekeeper to query its own traces from Arize Cloud
for billing and usage tracking purposes using the official Arize Python SDK.
"""

import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

# Import Arize SDK
try:
    from arize import ArizeClient
except ImportError:
    ArizeClient = None
    logging.warning("[WARNING] Arize SDK not installed. Install with: pip install arize")

from config.arize_config import API_KEY

logger = logging.getLogger(__name__)


class ArizeCloudClient:
    """
    Client for querying traces from Arize Cloud using the official SDK.

    This class provides methods to query spans and extract LLM usage data
    from Arize Cloud for billing calculations.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Arize Cloud client.

        Args:
            api_key: Arize API key (defaults to env var ARIZE_API_KEY)
        """
        if ArizeClient is None:
            raise ImportError("Arize SDK not installed. Install with: pip install arize")

        self.api_key = api_key or API_KEY
        self._client: Optional[ArizeClient] = None
        self._connected = False

        if not self.api_key:
            logger.warning("[WARNING] Arize API key not configured - client unavailable")

    async def connect(self) -> bool:
        """
        Establish connection to Arize Cloud.

        Returns:
            True if connection successful, False otherwise
        """
        if self._connected:
            return True

        if not self.api_key:
            logger.warning("[WARNING] Arize API key not configured - client unavailable")
            return False

        try:
            # Initialize Arize SDK client
            self._client = ArizeClient(api_key=self.api_key)

            # Test connection by listing projects
            projects_response = self._client.projects.list()
            if projects_response and hasattr(projects_response, 'projects'):
                self._connected = True
                logger.info("[OK] Arize Cloud client connected")
                return True
            else:
                logger.warning("[WARNING] Arize Cloud connection test failed")
                return False

        except Exception as e:
            logger.error(f"[ERROR] Failed to connect to Arize Cloud: {e}")
            return False

    async def disconnect(self):
        """Close the Arize Cloud connection."""
        self._client = None
        self._connected = False
        logger.info("[OK] Arize Cloud client disconnected")

    async def get_recent_traces(
        self,
        limit: int = 100,
        hours_ago: int = 24,
        project_name: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get recent LLM spans from Arize Cloud.

        Args:
            limit: Maximum number of spans to query from API
            hours_ago: Only get spans from the last N hours
            project_name: Optional project name to filter by (defaults to 'gatekeeper')
            user_id: Optional user ID to filter traces by (filtered during span processing loop)

        Returns:
            List of trace data dictionaries with LLM usage attributes, filtered by user_id if provided
        """
        if not self._connected:
            await self.connect()

        if not self._connected:
            return []

        try:
            # Get the target project
            project_id = await self._get_project_id(project_name or "gatekeeper")
            if not project_id:
                logger.warning("[WARNING] Could not find project")
                return []

            # Calculate time range (with timezone)
            now = datetime.now(timezone.utc)
            start_time = now - timedelta(hours=hours_ago)
            end_time = now

            # Log if filtering by user_id
            if user_id:
                logger.info(f"[INFO] Will filter spans for user_id: {user_id} during processing")

            # Query spans from Arize
            # Note: API-level filter syntax is complex, so we filter during processing
            spans_response = self._client.spans.list(
                project=project_id,
                start_time=start_time,
                end_time=end_time,
                limit=limit
            )

            # Extract spans list from response
            spans = []
            if hasattr(spans_response, 'spans'):
                spans = spans_response.spans
            elif hasattr(spans_response, 'data'):
                spans = spans_response.data
            else:
                # Try to convert to list
                try:
                    spans = list(spans_response)
                except:
                    pass

            # Convert spans to trace-like format for billing
            # We need to combine parent spans (with user context) and child spans (with LLM data)
            traces = []

            logger.info(f"[DEBUG] Retrieved {len(spans)} total spans from Arize")

            # First, collect all spans and index them
            parent_spans_by_id = {}  # Map span_id -> parent span with context
            llm_spans = []  # List of LLM spans

            for idx, span in enumerate(spans):
                # Get span context and attributes
                span_context = getattr(span, 'context', None)
                trace_id = getattr(span_context, 'trace_id', None) if span_context else None
                span_id = getattr(span_context, 'span_id', None) if span_context else None
                parent_id = getattr(span, 'parent_id', None)
                attrs = getattr(span, 'attributes', {})

                if not span_id:
                    logger.debug(f"[DEBUG] Span {idx} has no span_id, skipping")
                    continue

                # Log first few spans for debugging
                if idx < 3:
                    logger.info(f"[DEBUG] Span {idx} (trace_id: {trace_id[:16] if trace_id else 'N/A'}..., span_id: {span_id[:16] if span_id else 'N/A'}...): attribute keys = {list(attrs.keys())[:20]}")

                # Helper function to check for nested attributes
                def has_nested_attr(attrs, *keys):
                    """Check if nested attribute path exists"""
                    current = attrs
                    for key in keys:
                        if isinstance(current, dict) and key in current:
                            current = current[key]
                        else:
                            return False
                    return True

                # Check for LLM token data (handle both flat and nested formats)
                has_llm_data = (
                    'llm.token_count.total' in attrs or  # Flat format
                    has_nested_attr(attrs, 'llm', 'token_count', 'total') or  # Nested format
                    has_nested_attr(attrs, 'llm', 'token_count', 'completion') or  # Nested format (alternative)
                    'llm.token_count' in attrs  # Nested object at top level
                )

                # Check for parent span context (can be nested objects or flat keys)
                has_custom_attrs = (
                    any(key in attrs for key in ['user.id', 'mr.id', 'repository.id', 'user_id', 'mr_id', 'repository_id']) or
                    any(key in attrs for key in ['user', 'mr', 'repository', 'operation'])  # Nested object keys
                )

                if idx < 3:
                    logger.info(f"[DEBUG] Span {idx}: has_llm_data={has_llm_data}, has_custom_attrs={has_custom_attrs}, parent_id={parent_id}")

                # Classify spans
                if has_llm_data:
                    # This is an LLM span
                    llm_spans.append((span, parent_id, trace_id))
                elif has_custom_attrs:
                    # This is a parent span (has context but no LLM data)
                    parent_spans_by_id[span_id] = span

            logger.info(f"[DEBUG] Found {len(parent_spans_by_id)} parent spans and {len(llm_spans)} LLM spans")

            # Now match LLM spans with their parent spans
            for llm_span, parent_id, trace_id in llm_spans:
                # Find parent span by parent_id
                parent_span = parent_spans_by_id.get(parent_id)

                # Extract context from parent span
                context = {}
                if parent_span:
                    parent_attrs = getattr(parent_span, 'attributes', {})
                    logger.debug(f"[DEBUG] Matched LLM span with parent span: {parent_id[:16] if parent_id else 'N/A'}...")

                    # Extract user_id (handle both flat and nested formats)
                    if 'user.id' in parent_attrs:
                        context["user_id"] = parent_attrs['user.id']
                    elif 'user_id' in parent_attrs:
                        context["user_id"] = parent_attrs['user_id']
                    elif 'user' in parent_attrs and isinstance(parent_attrs['user'], dict):
                        context["user_id"] = parent_attrs['user'].get('id')

                    # Extract mr_id (handle both flat and nested formats)
                    if 'mr.id' in parent_attrs:
                        context["mr_id"] = parent_attrs['mr.id']
                    elif 'mr_id' in parent_attrs:
                        context["mr_id"] = parent_attrs['mr_id']
                    elif 'mr' in parent_attrs and isinstance(parent_attrs['mr'], dict):
                        context["mr_id"] = parent_attrs['mr'].get('id')

                    # Extract repository_id (handle both flat and nested formats)
                    if 'repository.id' in parent_attrs:
                        context["repository_id"] = parent_attrs['repository.id']
                    elif 'repository_id' in parent_attrs:
                        context["repository_id"] = parent_attrs['repository_id']
                    elif 'repository' in parent_attrs and isinstance(parent_attrs['repository'], dict):
                        context["repository_id"] = parent_attrs['repository'].get('id')

                    # Extract operation_type (handle both flat and nested formats)
                    if 'operation.type' in parent_attrs:
                        context["operation_type"] = parent_attrs['operation.type']
                    elif 'operation_type' in parent_attrs:
                        context["operation_type"] = parent_attrs['operation_type']
                    elif 'operation' in parent_attrs and isinstance(parent_attrs['operation'], dict):
                        context["operation_type"] = parent_attrs['operation'].get('type')
                else:
                    if parent_id:
                        logger.debug(f"[DEBUG] No parent span found for parent_id: {parent_id[:16]}...")

                # Filter by user_id if provided (early filtering during processing)
                if user_id:
                    trace_user_id = context.get("user_id")
                    if not trace_user_id or str(trace_user_id) != str(user_id):
                        logger.debug(f"[DEBUG] Skipping span - user_id filter: expected {user_id}, got {trace_user_id}")
                        continue

                # Create trace entry with parent context
                trace_data = self._convert_span_to_trace_format(llm_span, context)
                if trace_data:
                    traces.append(trace_data)
                else:
                    logger.debug(f"[DEBUG] Failed to convert LLM span to trace format")

            logger.info(f"[OK] Retrieved {len(traces)} LLM spans from Arize Cloud (combined with parent context)")
            logger.info(f"[DEBUG] Total traces created: {len(traces)}")
            return traces

        except Exception as e:
            logger.error(f"[ERROR] Failed to get spans: {e}")
            import traceback
            logger.debug(f"[DEBUG] Traceback: {traceback.format_exc()}")
            return []

    async def _get_project_id(self, project_name: str) -> Optional[str]:
        """
        Get the project ID for a given project name.

        Args:
            project_name: Name of the project to find

        Returns:
            Project ID or None if not found
        """
        try:
            projects_response = self._client.projects.list()

            projects = []
            if hasattr(projects_response, 'projects'):
                projects = projects_response.projects

            for project in projects:
                if getattr(project, 'name', '') == project_name:
                    return getattr(project, 'id', None)

            # If not found, return the first project's ID as fallback
            if projects:
                return getattr(projects[0], 'id', None)

            return None
        except Exception as e:
            logger.error(f"[ERROR] Failed to get project ID: {e}")
            return None

    def _convert_span_to_trace_format(self, span, context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Convert Arize span object to trace-like format for billing.

        Extracts LLM token usage and cost data from span attributes.

        Args:
            span: Arize span object
            context: Optional context from parent span (user_id, mr_id, repository_id)

        Returns:
            Dictionary with trace-like structure or None if no LLM data
        """
        try:
            if not hasattr(span, 'attributes'):
                return None

            attrs = span.attributes
            if not isinstance(attrs, dict):
                return None

            # Helper function to extract value from nested or flat attributes
            def get_attr_value(attrs, *keys):
                """Get attribute value from nested path like ('llm', 'token_count', 'total')"""
                current = attrs
                for key in keys:
                    if isinstance(current, dict) and key in current:
                        current = current[key]
                    else:
                        return None
                return current

            # Check if this is an LLM span with token usage (check both flat and nested formats)
            has_llm_data = (
                'llm.token_count.total' in attrs or  # Flat format
                (isinstance(attrs.get('llm'), dict) and isinstance(attrs['llm'].get('token_count'), dict))  # Nested format
            )

            if not has_llm_data:
                return None

            # Extract token usage (handle both flat and nested formats)
            # Try flat format first (llm.token_count.prompt)
            input_tokens = int(attrs.get('llm.token_count.prompt', 0) or 0)
            output_tokens = int(attrs.get('llm.token_count.completion', 0) or 0)
            total_tokens = int(attrs.get('llm.token_count.total', 0) or 0)

            # Extract cost from Arize (handle both flat and nested formats)
            # Try flat format first (llm.cost.total)
            total_cost = float(attrs.get('llm.cost.total', 0) or 0)
            if total_cost == 0:
                # Try nested format
                total_cost = float(get_attr_value(attrs, 'llm', 'cost', 'total') or 0)

            # Also extract individual costs for detail
            input_cost = float(attrs.get('llm.cost.prompt', 0) or 0)
            output_cost = float(attrs.get('llm.cost.completion', 0) or 0)

            # If flat format didn't work, try nested format (llm.token_count.input)
            if input_tokens == 0:
                input_tokens = int(get_attr_value(attrs, 'llm', 'token_count', 'input') or 0)
            if output_tokens == 0:
                output_tokens = int(get_attr_value(attrs, 'llm', 'token_count', 'completion') or 0)
            if total_tokens == 0:
                total_tokens = int(get_attr_value(attrs, 'llm', 'token_count', 'total') or 0)

            # Extract model name (handle both formats)
            model_name = attrs.get('llm.model_name') or get_attr_value(attrs, 'llm', 'model_name') or 'gemini-3.5-flash'

            # Get trace/span ID and timestamp from context
            span_context = getattr(span, 'context', None)
            span_start_time = getattr(span, 'start_time', None)

            if span_context:
                trace_id = getattr(span_context, 'trace_id', '') or ''
                span_id = getattr(span_context, 'span_id', '') or ''
            else:
                trace_id = ''
                span_id = ''

            # Convert span start_time to ISO format if available
            timestamp = None
            if span_start_time:
                if isinstance(span_start_time, datetime):
                    timestamp = span_start_time.isoformat()
                elif hasattr(span_start_time, 'isoformat'):
                    timestamp = span_start_time.isoformat()
                else:
                    timestamp = str(span_start_time)

            # Create trace-like object with LLM data
            trace = {
                "trace_id": trace_id,
                "span_id": span_id,  # Also store span_id for reference
                "attributes": {
                    "llm_input_tokens": input_tokens,
                    "llm_output_tokens": output_tokens,
                    "llm_total_tokens": total_tokens,
                    "llm_model_name": model_name,
                }
            }

            # Add cost if available from Arize
            if total_cost > 0:
                trace["attributes"]["llm_total_cost"] = total_cost
                trace["attributes"]["llm_input_cost"] = input_cost
                trace["attributes"]["llm_output_cost"] = output_cost

            # Add timestamp if available
            if timestamp:
                trace["attributes"]["timestamp"] = timestamp

            # Debug log the trace creation
            logger.debug(f"[DEBUG] Created trace {trace_id[:16]}...: input_tokens={input_tokens}, output_tokens={output_tokens}, context={context}")

            # First, add context from parent span if available
            if context:
                if "user_id" in context:
                    trace["attributes"]["user_id"] = context["user_id"]
                if "mr_id" in context:
                    trace["attributes"]["mr_id"] = context["mr_id"]
                if "repository_id" in context:
                    trace["attributes"]["repository_id"] = context["repository_id"]
                if "operation_type" in context:
                    trace["attributes"]["operation_type"] = context["operation_type"]

            # Also copy over any user_id directly from span attributes if present (check both naming conventions)
            # This is a fallback for spans that have context directly on them
            if 'user.id' in attrs and 'user_id' not in trace["attributes"]:
                trace["attributes"]["user_id"] = attrs['user.id']
            elif 'user_id' in attrs and 'user_id' not in trace["attributes"]:
                trace["attributes"]["user_id"] = attrs['user_id']

            # Copy over other useful attributes from span if not already in context (check both naming conventions)
            for key, alt_key in [('mr.id', 'mr_id'), ('repository.id', 'repository_id'), ('operation.type', 'operation_type')]:
                if key in attrs and alt_key not in trace["attributes"]:
                    trace["attributes"][alt_key] = attrs[key]
                elif alt_key in attrs and alt_key not in trace["attributes"]:
                    trace["attributes"][alt_key] = attrs[alt_key]

            return trace

        except Exception as e:
            logger.debug(f"[DEBUG] Failed to convert span: {e}")
            return None

    async def get_trace_details(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific trace.

        Note: This method is not fully implemented as Arize SDK
        doesn't provide a direct get_trace_by_id method.

        Args:
            trace_id: The trace ID to fetch

        Returns:
            Trace details dictionary or None if not found
        """
        logger.debug(f"[DEBUG] get_trace_details not implemented for Arize Cloud")
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


# Global Arize Cloud client instance
_arize_client: Optional[ArizeCloudClient] = None


async def get_arize_client() -> ArizeCloudClient:
    """
    Get the global Arize Cloud client instance.

    Returns:
        The ArizeCloudClient instance (connected if not already)
    """
    global _arize_client

    if _arize_client is None:
        _arize_client = ArizeCloudClient()

    if not _arize_client.is_connected():
        await _arize_client.connect()

    return _arize_client


async def close_arize_client():
    """Close the global Arize Cloud client."""
    global _arize_client

    if _arize_client:
        await _arize_client.disconnect()
        _arize_client = None
