"""Extract evidence and counter-evidence from replay bundle."""

from __future__ import annotations

from copilot.models.state import CopilotState, CounterEvidenceItem


async def evidence_retrieval_node(state: CopilotState) -> dict:
    bundle = state.replay_bundle
    if bundle is None:
        raise ValueError("Replay bundle required before evidence retrieval")

    excerpts: list[dict] = []
    for item in bundle.evidence_references:
        excerpts.append(
            {
                "ref": item.ref,
                "node_id": item.node_id,
                "excerpt": item.excerpt,
                "byte_length": item.byte_length,
            }
        )
    state.evidence_excerpts = excerpts

    counter: list[CounterEvidenceItem] = []

    for reflection in bundle.reflections:
        if reflection.passed is False:
            counter.append(
                CounterEvidenceItem(
                    source="reflection",
                    node_id=reflection.node_id,
                    description=(
                        f"Reflection failed for step '{reflection.step_id}'"
                        + (f": {reflection.reason}" if reflection.reason else "")
                    ),
                )
            )

    for result in bundle.tool_results:
        if result.status and result.status != "success":
            counter.append(
                CounterEvidenceItem(
                    source="tool_result",
                    node_id=result.node_id,
                    description=(
                        f"Tool '{result.tool_name}' returned status '{result.status}'"
                        + (
                            f": {result.error_message}"
                            if result.error_message
                            else ""
                        )
                    ),
                )
            )

    if state.user_assertions_detected:
        replay_status = bundle.outcome.status or bundle.execution_summary.status
        if "wrong" in state.question.lower() or "incorrect" in state.question.lower():
            if replay_status in {"completed", "complete"} and bundle.reflections:
                failed = [r for r in bundle.reflections if r.passed is False]
                if not failed:
                    counter.append(
                        CounterEvidenceItem(
                            source="assertion_check",
                            description=(
                                "Replay shows all reflections passed; user claim of "
                                "incorrectness is not supported by captured evidence."
                            ),
                        )
                    )
                    state.assertion_conflicts.append(
                        "User asserted incorrectness but replay reflections passed."
                    )

    state.counter_evidence = counter
    return {
        "evidence_count": len(excerpts),
        "counter_evidence_count": len(counter),
        "assertion_conflicts": len(state.assertion_conflicts),
    }
