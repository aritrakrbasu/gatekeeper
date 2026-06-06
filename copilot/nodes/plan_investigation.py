"""Deterministic investigation planning node (no tool execution)."""

from __future__ import annotations

from typing import Any, Optional

from agents.registry import ToolRegistry
from copilot.models.state import CopilotState
from copilot.planning.planner import build_investigation_plan


async def plan_investigation_node(
    state: CopilotState,
    *,
    registry: Optional[ToolRegistry] = None,
) -> dict:
    if not state.live_investigation_enabled:
        return {"skipped": True, "reason": "investigation_not_required"}

    if registry is None:
        from agents.registry import build_default_registry

        registry = await build_default_registry()

    plan = build_investigation_plan(state, registry=registry)
    state.investigation_plan = plan
    state.plan_step_cursor = 0
    state.pending_approval = None
    state.approval_resume = None
    state.investigation_results = []

    return {
        "plan_id": plan.plan_id,
        "profile": plan.profile.value,
        "step_count": len(plan.steps),
        "tools_planned": [step.tool_name for step in plan.steps],
        "knowledge_assertion_ids": plan.knowledge_assertion_ids,
    }
