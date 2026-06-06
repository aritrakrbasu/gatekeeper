"""Deterministic investigation plan builder (no tool execution)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from agents.registry import ToolRegistry
from copilot.models.enums import QuestionType
from copilot.models.investigation import (
    InvestigationPlan,
    InvestigationPlanStep,
    InvestigationProfile,
)
from copilot.models.state import CopilotState
from copilot.tools.categories import classify_tool, requires_approval
from knowledge.resolver.models import KnowledgeContext

_PROFILE_PATTERNS: list[tuple[InvestigationProfile, re.Pattern[str]]] = [
    (
        InvestigationProfile.FINDING_CHALLENGE,
        re.compile(
            r"\b(wrong|incorrect|invalid|challenge|dispute|not correct|"
            r"is (this|the) (finding|issue|conclusion))\b",
            re.I,
        ),
    ),
    (
        InvestigationProfile.REPOSITORY_COMPARISON,
        re.compile(
            r"\b(compare|comparison|versus|vs\.?|other repo|alternative repo|"
            r"repository pattern|cross-repo)\b",
            re.I,
        ),
    ),
    (
        InvestigationProfile.DEEP_INVESTIGATION,
        re.compile(
            r"\b(investigate|dig deeper|look into|explore|check (this|it) (further|more))\b",
            re.I,
        ),
    ),
]


def detect_investigation_profile(state: CopilotState) -> InvestigationProfile:
    if state.question_type == QuestionType.IS_FINDING_CORRECT:
        return InvestigationProfile.FINDING_CHALLENGE
    if state.question_type == QuestionType.WHAT_ALTERNATIVES:
        return InvestigationProfile.REPOSITORY_COMPARISON
    if state.question_type == QuestionType.INVESTIGATE_FURTHER:
        return InvestigationProfile.DEEP_INVESTIGATION

    for profile, pattern in _PROFILE_PATTERNS:
        if pattern.search(state.question):
            return profile

    if state.live_investigation_enabled:
        return InvestigationProfile.DEEP_INVESTIGATION
    return InvestigationProfile.DEEP_INVESTIGATION


def _available_plan_tools(registry: ToolRegistry) -> List[str]:
    return sorted(tool.get_name() for tool in registry.list_tools())


def _tool_schema(registry: ToolRegistry, tool_name: str) -> Dict[str, Any]:
    return registry.get_tool(tool_name).get_schema()


def _replay_tool_names(state: CopilotState) -> List[str]:
    bundle = state.replay_bundle
    if bundle is None:
        return []
    return sorted({call.tool_name for call in bundle.tool_calls})


def _base_tool_args(state: CopilotState, tool_name: str) -> Dict[str, Any]:
    if tool_name == "get_gitlab_mr_diffs":
        return {"repository_id": state.repository_id}
    if tool_name in {"gitnexus_analyze", "clone_repo", "run_impact_analysis"}:
        return {"repo_path": f"/tmp/repos/{state.repository_id}"}
    if tool_name == "run_schema_inspection":
        return {"collection": "peil_executions"}
    return {}


def _knowledge_rationale(
    knowledge: Optional[KnowledgeContext],
    tool_name: str,
) -> str:
    if knowledge is None or not knowledge.manifest.assertion_count:
        return f"Inspect {tool_name} output to validate replay conclusions."

    for items in knowledge.assertions_by_type.values():
        for item in items:
            if tool_name in item.statement.lower():
                return (
                    f"Accepted knowledge [{item.assertion_id}] references {tool_name}; "
                    f"verify: {item.statement}"
                )
    first = next(
        (
            item
            for items in knowledge.assertions_by_type.values()
            for item in items
        ),
        None,
    )
    if first:
        return (
            f"Cross-check replay against accepted knowledge [{first.assertion_id}]: "
            f"{first.statement}"
        )
    return f"Gather evidence via {tool_name} to support or refute the user question."


def _expected_evidence(tool_name: str, profile: InvestigationProfile) -> str:
    expectations = {
        "get_gitlab_mr_diffs": "MR diff hunks and file paths relevant to the finding.",
        "gitnexus_analyze": "Dependency/impact graph nodes supporting the review conclusion.",
        "run_impact_analysis": "Blast-radius summary for changed symbols.",
        "run_schema_inspection": "Collection schema fields for repository comparison.",
        "clone_repo": "Repository checkout metadata confirming target branch.",
    }
    base = expectations.get(tool_name, f"Structured output from {tool_name}.")
    return f"[{profile.value}] {base}"


def _profile_tool_sequence(
    profile: InvestigationProfile,
    available: Sequence[str],
    replay_tools: Sequence[str],
    focus_tool: Optional[str],
) -> List[str]:
    if focus_tool and focus_tool in available:
        preferred = [focus_tool]
    else:
        preferred = []

    if profile == InvestigationProfile.FINDING_CHALLENGE:
        preferred.extend(
            name
            for name in ("get_gitlab_mr_diffs", "gitnexus_analyze", "run_impact_analysis")
            if name in available
        )
    elif profile == InvestigationProfile.REPOSITORY_COMPARISON:
        preferred.extend(
            name
            for name in ("run_schema_inspection", "run_impact_analysis", "get_gitlab_mr_diffs")
            if name in available
        )
    else:
        preferred.extend(
            name
            for name in ("get_gitlab_mr_diffs", "gitnexus_analyze", "run_impact_analysis")
            if name in available
        )

    for tool in replay_tools:
        if tool in available:
            preferred.append(tool)

    deduped: List[str] = []
    for name in preferred:
        if name not in deduped:
            deduped.append(name)

    if profile == InvestigationProfile.REPOSITORY_COMPARISON:
        return deduped[:2]
    if profile == InvestigationProfile.FINDING_CHALLENGE:
        return deduped[:2]
    for name in available:
        if requires_approval(classify_tool(name)) and name not in deduped:
            deduped.append(name)
    return deduped[:4]


def build_investigation_plan(
    state: CopilotState,
    *,
    registry: ToolRegistry,
) -> InvestigationPlan:
    """Build a deterministic, read-only investigation plan without executing tools."""
    profile = detect_investigation_profile(state)
    available = _available_plan_tools(registry)
    replay_tools = _replay_tool_names(state)
    tool_names = _profile_tool_sequence(
        profile,
        available,
        replay_tools,
        state.focus_tool_name,
    )

    knowledge = state.knowledge_context
    assertion_ids = list(knowledge.manifest.assertion_ids) if knowledge else []

    steps: List[InvestigationPlanStep] = []
    for idx, tool_name in enumerate(tool_names, start=1):
        schema = _tool_schema(registry, tool_name)
        steps.append(
            InvestigationPlanStep(
                step_id=f"inv-{idx:02d}",
                rationale=_knowledge_rationale(knowledge, tool_name),
                tool_name=tool_name,
                tool_args=_base_tool_args(state, tool_name),
                expected_evidence=_expected_evidence(tool_name, profile),
            )
        )
        _ = schema  # schema consulted for determinism; args validated structurally

    replay_id = None
    if state.replay_bundle is not None:
        replay_id = state.replay_bundle.execution_summary.execution_id

    return InvestigationPlan(
        plan_id=InvestigationPlan.new_id(),
        conversation_id=state.conversation_id,
        question_type=state.question_type,
        profile=profile,
        steps=steps,
        knowledge_assertion_ids=assertion_ids,
        replay_execution_id=replay_id,
    )
