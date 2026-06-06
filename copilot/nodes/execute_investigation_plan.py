"""Execute investigation plan steps via shared ToolRegistry."""

from __future__ import annotations

from typing import Any, Optional

from agents.aril_bridge import ArilSession
from agents.registry import ToolRegistry
from copilot.models.state import CopilotState
from copilot.tools.execution import run_immediate_plan_steps


async def execute_investigation_plan_node(
    state: CopilotState,
    *,
    registry: Optional[ToolRegistry] = None,
    aril: Optional[ArilSession] = None,
    db: Any = None,
) -> dict:
    if state.investigation_plan is None:
        return {"skipped": True, "reason": "no_plan"}

    if registry is None:
        from agents.registry import build_default_registry

        registry = await build_default_registry(aril=aril)

    return await run_immediate_plan_steps(
        state,
        registry=registry,
        aril=aril,
    )
