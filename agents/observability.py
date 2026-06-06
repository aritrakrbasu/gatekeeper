import datetime
import json
import os
from typing import Dict, Any, Optional

from opentelemetry import trace
from pydantic import BaseModel, Field

tracer = trace.get_tracer("gatekeeper-agent-runtime")


class ToolExecutionEvent(BaseModel):
    """Execution event data model for agent tool runs."""
    tool_name: str
    arguments: Dict[str, Any]
    status: str
    duration_ms: float
    retry_count: int
    error_message: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.datetime.utcnow().isoformat())


def mask_sensitive_arguments(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively replaces keys matching sensitive patterns with a [MASKED] label."""
    masked = {}
    sensitive_keys = {"token", "password", "key", "secret", "auth", "jwt", "credential"}
    for k, v in arguments.items():
        if any(sk in str(k).lower() for sk in sensitive_keys):
            masked[k] = "[MASKED]"
        elif isinstance(v, dict):
            masked[k] = mask_sensitive_arguments(v)
        elif isinstance(v, list):
            masked[k] = [mask_sensitive_arguments(item) if isinstance(item, dict) else item for item in v]
        else:
            masked[k] = v
    return masked


def _capture_via_registry_enabled() -> bool:
    if os.getenv("ARIL_CAPTURE_VIA_REGISTRY", "true").strip().lower() in {"0", "false", "no", "off"}:
        return False
    return os.getenv("ARIL_CAPTURE_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


async def record_tool_event(event: ToolExecutionEvent):
    """
    Logs structured JSON telemetry to stdout/stderr and injects
    OpenTelemetry trace attributes on the current span.

    Skipped when ARIL captures tool lifecycle via ToolRegistry to avoid duplicates.
    """
    if _capture_via_registry_enabled():
        return

    masked_args = mask_sensitive_arguments(event.arguments)

    log_payload = {
        "event": "tool_execution",
        "tool_name": event.tool_name,
        "arguments": masked_args,
        "status": event.status,
        "duration_ms": event.duration_ms,
        "retry_count": event.retry_count,
        "error_message": event.error_message,
        "timestamp": event.timestamp,
    }
    print(f"[TELEMETRY] {json.dumps(log_payload)}", flush=True)

    current_span = trace.get_current_span()
    if current_span and current_span.is_recording():
        current_span.set_attribute("gatekeeper.tool.name", event.tool_name)
        current_span.set_attribute("gatekeeper.tool.status", event.status)
        current_span.set_attribute("gatekeeper.tool.duration_ms", event.duration_ms)
        current_span.set_attribute("gatekeeper.tool.retry_count", event.retry_count)

        try:
            current_span.set_attribute("gatekeeper.tool.arguments", json.dumps(masked_args))
        except Exception:
            current_span.set_attribute("gatekeeper.tool.arguments", str(masked_args))

        if event.error_message:
            current_span.set_attribute("gatekeeper.tool.error", event.error_message)

        current_span.add_event(
            name="tool_execution",
            attributes={
                "tool_name": event.tool_name,
                "status": event.status,
                "duration_ms": event.duration_ms,
            },
        )
