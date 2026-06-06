"""Conditional routing for LangGraph Copilot v2."""

from __future__ import annotations

from langgraph.constants import END

from copilot.graph.v2.state import CopilotGraphState, copilot_from_graph_state
from copilot.models.enums import CopilotNodeName, QuestionType


def should_plan_investigation(copilot) -> bool:
    if copilot.live_investigation_enabled:
        return True
    return copilot.question_type in {
        QuestionType.IS_FINDING_CORRECT,
        QuestionType.WHAT_ALTERNATIVES,
    }


def route_after_classifier(state: CopilotGraphState) -> str:
    if state.get("halted"):
        return END
    copilot = copilot_from_graph_state(state)
    if should_plan_investigation(copilot):
        return CopilotNodeName.PLAN_INVESTIGATION.value
    return CopilotNodeName.RESPONSE_GENERATOR.value


def route_if_halted(state: CopilotGraphState) -> str:
    if state.get("halted"):
        return END
    return "continue"


def route_after_execute(state: CopilotGraphState) -> str:
    if state.get("halted"):
        return END
    copilot = copilot_from_graph_state(state)
    if copilot.pending_approval:
        return CopilotNodeName.APPROVAL_GATE.value
    return CopilotNodeName.RESPONSE_GENERATOR.value


def route_after_resume(state: CopilotGraphState) -> str:
    if state.get("halted"):
        return END
    copilot = copilot_from_graph_state(state)
    if _plan_has_remaining_steps(copilot):
        return CopilotNodeName.EXECUTE_INVESTIGATION_PLAN.value
    return CopilotNodeName.RESPONSE_GENERATOR.value


def _plan_has_remaining_steps(copilot) -> bool:
    plan = copilot.investigation_plan
    if plan is None:
        return False
    return copilot.plan_step_cursor < len(plan.steps)
