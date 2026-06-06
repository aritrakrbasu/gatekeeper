"""Deterministic response synthesis from replay and investigation data."""

from __future__ import annotations

from typing import List, Optional

from copilot.knowledge.citations import format_citations_section
from copilot.models.enums import QuestionType
from copilot.models.state import CopilotState
from peil.replay.models import ReplayPlanStep, ReplayToolCall


def _find_tool_call(
    state: CopilotState,
) -> Optional[ReplayToolCall]:
    bundle = state.replay_bundle
    if bundle is None:
        return None

    if state.focus_node_id:
        for call in bundle.tool_calls:
            if call.node_id == state.focus_node_id:
                return call

    if state.focus_tool_name:
        for call in bundle.tool_calls:
            if call.tool_name == state.focus_tool_name:
                return call

    if state.focus_step_id:
        for call in bundle.tool_calls:
            if call.step_id == state.focus_step_id:
                return call

    return bundle.tool_calls[0] if bundle.tool_calls else None


def _find_plan_step(state: CopilotState, step_id: Optional[str]) -> Optional[ReplayPlanStep]:
    bundle = state.replay_bundle
    if bundle is None or not step_id:
        return None
    for step in bundle.plan_steps:
        if step.step_id == step_id:
            return step
    return None


def _format_evidence(state: CopilotState) -> List[str]:
    lines: List[str] = []
    for item in state.evidence_excerpts:
        excerpt = item.get("excerpt") or "(no excerpt)"
        lines.append(f"- {item.get('ref')}: {excerpt}")
    return lines


def _format_counter_evidence(state: CopilotState) -> List[str]:
    return [f"- [{c.source}] {c.description}" for c in state.counter_evidence]


def _format_investigation_plan(state: CopilotState) -> List[str]:
    plan = state.investigation_plan
    if plan is None or not plan.steps:
        return []
    remaining = plan.steps[state.plan_step_cursor :]
    if not remaining and state.investigation_results:
        return []
    status = "pending approval" if state.pending_approval else "remaining steps"
    lines = [
        f"Investigation plan ({plan.profile.value}, plan_id={plan.plan_id}) — {status}:"
    ]
    for step in remaining:
        lines.append(f"- {step.step_id}: {step.tool_name} — {step.rationale}")
        lines.append(f"  Expected evidence: {step.expected_evidence}")
    return lines


def generate_response(state: CopilotState) -> str:
    bundle = state.replay_bundle
    if bundle is None:
        return "No replay data available for this execution."

    summary = bundle.execution_summary
    parts: List[str] = [
        f"Execution {summary.execution_id} ({summary.execution_type}): {summary.objective}",
        f"Replay source: graph {bundle.graph_id} with {len(bundle.graph_path)} nodes.",
    ]

    qtype = state.question_type

    if qtype == QuestionType.WHY_ISSUE_RAISED:
        comment_step = _find_plan_step(state, "comment") or (
            bundle.plan_steps[-1] if bundle.plan_steps else None
        )
        if comment_step:
            parts.append(
                f"The review comment step '{comment_step.step_id}' was planned because: "
                f"{comment_step.reason or 'no reason captured in replay'}."
            )
        analyze = _find_plan_step(state, "analyze")
        if analyze:
            parts.append(
                f"Prior analysis step '{analyze.step_id}' ({analyze.tool_name}) "
                f"ran for: {analyze.reason or 'impact assessment'}."
            )

    elif qtype == QuestionType.WHY_TOOL_CALLED:
        call = _find_tool_call(state)
        if call:
            step = _find_plan_step(state, call.step_id)
            parts.append(
                f"Tool '{call.tool_name}' was invoked for step '{call.step_id}'."
            )
            if step:
                parts.append(f"Plan rationale: {step.reason or step.action or 'not recorded'}.")
        else:
            parts.append("No matching tool call found in replay.")

    elif qtype == QuestionType.WHAT_EVIDENCE:
        evidence_lines = _format_evidence(state)
        if evidence_lines:
            parts.append("Captured evidence from replay:")
            parts.extend(evidence_lines)
        else:
            parts.append("Replay contains no resolved evidence excerpts.")

    elif qtype == QuestionType.WHAT_ALTERNATIVES:
        parts.append(
            "Replay captures the executed plan only; alternative branches were not materialized "
            "in the decision graph."
        )
        if bundle.plan_steps:
            parts.append("Executed plan steps:")
            for step in bundle.plan_steps:
                deps = ", ".join(step.dependencies) if step.dependencies else "none"
                parts.append(
                    f"- {step.step_id}: {step.action or step.tool_name} (deps: {deps})"
                )

    elif qtype == QuestionType.IS_FINDING_CORRECT:
        passed = [r for r in bundle.reflections if r.passed is True]
        failed = [r for r in bundle.reflections if r.passed is False]
        parts.append(
            f"Replay shows {len(passed)} passing and {len(failed)} failing reflections."
        )
        if state.assertion_conflicts:
            parts.append(
                "User assertion conflicts with replay: "
                + "; ".join(state.assertion_conflicts)
            )
        counter = _format_counter_evidence(state)
        if counter:
            parts.append("Counter-evidence:")
            parts.extend(counter)
        else:
            parts.append(
                "No counter-evidence in replay; conclusion aligns with captured validations."
            )

    elif qtype == QuestionType.INVESTIGATE_FURTHER:
        if state.investigation_results:
            parts.append("Investigation execution results (supplement replay):")
            for inv in state.investigation_results:
                parts.append(f"- {inv.tool_name} [{inv.status}]: {inv.summary}")
                if inv.raw_preview:
                    parts.append(f"  Preview: {inv.raw_preview}")
        plan_lines = _format_investigation_plan(state)
        if plan_lines:
            parts.extend(plan_lines)
        if not state.investigation_results and not plan_lines:
            parts.append(
                "No investigation plan or execution results are available for this turn."
            )
        evidence_lines = _format_evidence(state)
        if evidence_lines:
            parts.append("Replay evidence remains authoritative:")
            parts.extend(evidence_lines)

    else:
        if bundle.narrative:
            parts.append(bundle.narrative.summary)
        else:
            parts.append(
                f"Outcome: {bundle.outcome.status}; "
                f"{len(bundle.tool_calls)} tool calls recorded."
            )

    if state.counter_evidence and qtype != QuestionType.IS_FINDING_CORRECT:
        parts.append("Counter-evidence noted:")
        parts.extend(_format_counter_evidence(state))

    citation_section = format_citations_section(state.knowledge_citations)
    if citation_section:
        parts.append(citation_section)

    plan_lines = _format_investigation_plan(state)
    if plan_lines and qtype != QuestionType.INVESTIGATE_FURTHER:
        parts.extend(plan_lines)

    parts.append(
        "Note: This answer is derived from ReasoningReplayService graph replay; "
        "user assertions are verified against captured evidence."
    )
    return "\n".join(parts)


def chunk_response(text: str, chunk_size: int = 120) -> List[str]:
    if not text:
        return []
    words = text.split()
    chunks: List[str] = []
    current: List[str] = []
    length = 0
    for word in words:
        word_len = len(word) + (1 if current else 0)
        if length + word_len > chunk_size and current:
            chunks.append(" ".join(current))
            current = [word]
            length = len(word)
        else:
            current.append(word)
            length += word_len
    if current:
        chunks.append(" ".join(current))
    return chunks


async def response_generator_node(state: CopilotState) -> dict:
    text = generate_response(state)
    state.response_text = text
    state.response_chunks = chunk_response(text)
    return {
        "response_length": len(text),
        "chunk_count": len(state.response_chunks),
    }
