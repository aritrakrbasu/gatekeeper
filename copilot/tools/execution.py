"""Execute investigation plan steps via the shared ToolRegistry."""

from __future__ import annotations

import json
from typing import Any, Optional

from agents.aril_bridge import ArilSession
from agents.registry import ToolRegistry
from copilot.models.investigation import InvestigationPlanStep
from copilot.models.state import CopilotState, InvestigationResult
from copilot.tools.categories import ToolRiskCategory, classify_tool, executes_immediately
from copilot.tools.context import build_agent_context


def _preview(value: Any, max_chars: int = 512) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    if len(text) > max_chars:
        return text[:max_chars] + "…"
    return text


def estimate_scope(step: InvestigationPlanStep, category: ToolRiskCategory) -> str:
    if category == ToolRiskCategory.DESTRUCTIVE:
        return "repository-wide branch and merge-request changes"
    if category == ToolRiskCategory.MUTATING:
        return f"scoped write via {step.tool_name}"
    if category == ToolRiskCategory.SAFE_READ:
        return "read-only repository inspection"
    return f"investigation via {step.tool_name}"


def build_interrupt_payload(
    step: InvestigationPlanStep,
    *,
    reason: str,
    category: ToolRiskCategory,
) -> dict[str, Any]:
    return {
        "reason": reason,
        "tool_name": step.tool_name,
        "tool_args": step.tool_args,
        "risk_level": category.value,
        "estimated_scope": estimate_scope(step, category),
        "step_id": step.step_id,
        "requires_admin": category == ToolRiskCategory.DESTRUCTIVE,
    }


async def execute_plan_step(
    state: CopilotState,
    step: InvestigationPlanStep,
    *,
    registry: ToolRegistry,
    aril: Optional[ArilSession] = None,
    tool_args: Optional[dict[str, Any]] = None,
) -> InvestigationResult:
    args = tool_args if tool_args is not None else step.tool_args
    context = build_agent_context(state)
    if aril is not None:
        registry.attach_aril(aril)

    try:
        output = await registry.execute_tool(
            step.tool_name,
            args,
            context=context,
            step_id=step.step_id,
        )
        return InvestigationResult(
            tool_name=step.tool_name,
            status="success",
            summary=f"Executed {step.tool_name} for plan step {step.step_id}.",
            raw_preview=_preview(output),
        )
    except Exception as exc:
        return InvestigationResult(
            tool_name=step.tool_name,
            status="error",
            summary=str(exc),
        )


async def run_immediate_plan_steps(
    state: CopilotState,
    *,
    registry: ToolRegistry,
    aril: Optional[ArilSession] = None,
) -> dict[str, Any]:
    """Execute SAFE_READ and INVESTIGATE steps until approval is required or plan ends."""
    plan = state.investigation_plan
    if plan is None or not plan.steps:
        return {"skipped": True, "reason": "no_plan"}

    executed: list[str] = []
    while state.plan_step_cursor < len(plan.steps):
        step = plan.steps[state.plan_step_cursor]
        category = classify_tool(step.tool_name)

        if not executes_immediately(category):
            state.pending_approval = build_interrupt_payload(
                step,
                reason=step.rationale,
                category=category,
            )
            break

        result = await execute_plan_step(
            state,
            step,
            registry=registry,
            aril=aril,
        )
        state.investigation_results.append(result)
        executed.append(step.tool_name)
        state.plan_step_cursor += 1

    return {
        "executed_tools": executed,
        "plan_step_cursor": state.plan_step_cursor,
        "pending_approval": state.pending_approval is not None,
    }
