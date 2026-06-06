"""Deterministic knowledge proposals from CopilotGraph replay state."""

from __future__ import annotations

from typing import List, Optional

from copilot.models.enums import QuestionType
from copilot.models.state import CopilotState
from knowledge.config import get_knowledge_settings
from knowledge.models.assertion import KnowledgeAssertionCreate
from knowledge.models.enums import AssertionType


def propose_from_copilot_state(state: CopilotState) -> List[KnowledgeAssertionCreate]:
    """
    Build proposed assertions from replay-backed copilot state.

    Proposals are suggestions only — callers must persist via AssertionRepository.propose().
    """
    bundle = state.replay_bundle
    if bundle is None or not state.execution_id:
        return []

    settings = get_knowledge_settings()
    proposals: List[KnowledgeAssertionCreate] = []
    evidence_refs = [item.ref for item in bundle.evidence_references if item.ref]

    if state.question_type == QuestionType.WHY_TOOL_CALLED:
        call = next(
            (c for c in bundle.tool_calls if c.step_id == state.focus_step_id),
            bundle.tool_calls[0] if bundle.tool_calls else None,
        )
        if call:
            step = next(
                (s for s in bundle.plan_steps if s.step_id == call.step_id),
                None,
            )
            proposals.append(
                KnowledgeAssertionCreate(
                    repository_id=state.repository_id,
                    source_execution_id=state.execution_id,
                    source_conversation_id=state.conversation_id,
                    type=AssertionType.REPOSITORY_PATTERN,
                    statement=(
                        f"Tool '{call.tool_name}' is invoked for step '{call.step_id}' "
                        f"because: {step.reason if step and step.reason else 'plan rationale captured in replay'}."
                    ),
                    evidence_refs=evidence_refs[:3],
                    confidence=settings.default_confidence,
                    graph_id=bundle.graph_id,
                    graph_hash=bundle.graph_hash,
                    replay_reference=f"replay:{state.execution_id}",
                    metadata={"source": "copilot_graph", "question_type": state.question_type.value},
                )
            )

    if state.question_type == QuestionType.IS_FINDING_CORRECT and state.assertion_conflicts:
        proposals.append(
            KnowledgeAssertionCreate(
                repository_id=state.repository_id,
                source_execution_id=state.execution_id,
                source_conversation_id=state.conversation_id,
                type=AssertionType.REVIEW_CORRECTION,
                statement=(
                    "Reviewer disputed a finding but replay evidence did not support the dispute. "
                    "Captured reflections and tool results should be checked before overriding."
                ),
                evidence_refs=evidence_refs[:5],
                confidence=max(0.3, settings.default_confidence - 0.1),
                graph_id=bundle.graph_id,
                graph_hash=bundle.graph_hash,
                replay_reference=f"replay:{state.execution_id}",
                metadata={
                    "source": "copilot_graph",
                    "conflicts": state.assertion_conflicts,
                },
            )
        )

    for step in bundle.plan_steps:
        if step.reason and "schema" in (step.reason or "").lower():
            proposals.append(
                KnowledgeAssertionCreate(
                    repository_id=state.repository_id,
                    source_execution_id=state.execution_id,
                    source_conversation_id=state.conversation_id,
                    type=AssertionType.ARCHITECTURE_RULE,
                    statement=f"Plan step '{step.step_id}' enforces architecture check: {step.reason}",
                    evidence_refs=evidence_refs[:2],
                    confidence=settings.default_confidence,
                    graph_id=bundle.graph_id,
                    graph_hash=bundle.graph_hash,
                    replay_reference=f"replay:{state.execution_id}",
                    metadata={"source": "copilot_graph", "step_id": step.step_id},
                )
            )
            break

    if state.question_type == QuestionType.WHAT_ALTERNATIVES and bundle.plan_steps:
        deps = {
            s.step_id: s.dependencies for s in bundle.plan_steps if s.dependencies
        }
        if deps:
            proposals.append(
                KnowledgeAssertionCreate(
                    repository_id=state.repository_id,
                    source_execution_id=state.execution_id,
                    source_conversation_id=state.conversation_id,
                    type=AssertionType.BUSINESS_RULE,
                    statement=(
                        "Executed review workflow follows deterministic plan dependencies; "
                        f"ordering constraints: {deps}."
                    ),
                    evidence_refs=evidence_refs[:2],
                    confidence=settings.default_confidence,
                    graph_id=bundle.graph_id,
                    graph_hash=bundle.graph_hash,
                    replay_reference=f"replay:{state.execution_id}",
                    metadata={"source": "copilot_graph"},
                )
            )

    return _dedupe_proposals(proposals)


def _dedupe_proposals(
    proposals: List[KnowledgeAssertionCreate],
) -> List[KnowledgeAssertionCreate]:
    seen: set[str] = set()
    unique: List[KnowledgeAssertionCreate] = []
    for proposal in proposals:
        key = f"{proposal.type.value}:{proposal.statement}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(proposal)
    return unique
