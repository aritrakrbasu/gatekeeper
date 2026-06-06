"""Optional live investigation via read-only ToolRegistry tools."""

from __future__ import annotations

import json
from typing import Any, Optional

from agents.context import AgentContext, BranchContext, RepositoryContext, SchemaContext, UserContext
from agents.registry import ToolRegistry
from copilot.models.enums import QuestionType
from copilot.models.state import CopilotState, InvestigationResult

READ_ONLY_TOOLS = frozenset(
    {
        "get_gitlab_mr_diffs",
        "gitnexus_analyze",
        "run_schema_inspection",
        "run_impact_analysis",
        "clone_repo",
    }
)


def _preview(value: Any, max_chars: int = 512) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    if len(text) > max_chars:
        return text[:max_chars] + "…"
    return text


def _build_context(state: CopilotState) -> AgentContext:
    bundle = state.replay_bundle
    repo_id = state.repository_id
    repo_name = repo_id
    if bundle is not None:
        repo_name = bundle.execution_summary.repository_id

    return AgentContext(
        task_id=f"copilot-{state.conversation_id}",
        objective=state.question,
        repository=RepositoryContext(id=repo_id, name=repo_name),
        branch=BranchContext(source_branch="main", target_branch="main"),
        user=UserContext(user_id=state.user_id, username=state.user_id),
        schema_ctx=SchemaContext(),
        metadata={
            "copilot_conversation_id": state.conversation_id,
            "source_execution_id": state.execution_id,
        },
    )


def _select_tools(state: CopilotState, registry: ToolRegistry) -> list[str]:
    available = {t.get_name() for t in registry.list_tools()}
    candidates: list[str] = []

    if state.focus_tool_name and state.focus_tool_name in READ_ONLY_TOOLS:
        candidates.append(state.focus_tool_name)

    if state.question_type == QuestionType.INVESTIGATE_FURTHER:
        for name in ("get_gitlab_mr_diffs", "gitnexus_analyze", "run_impact_analysis"):
            if name in available and name in READ_ONLY_TOOLS:
                candidates.append(name)

    if state.question_type == QuestionType.WHAT_EVIDENCE:
        if "get_gitlab_mr_diffs" in available:
            candidates.append("get_gitlab_mr_diffs")

    deduped: list[str] = []
    for name in candidates:
        if name not in deduped and name in available:
            deduped.append(name)
    return deduped[:2]


async def live_investigation_node(
    state: CopilotState,
    *,
    registry: Optional[ToolRegistry] = None,
) -> dict:
    if not state.live_investigation_enabled:
        return {"skipped": True, "reason": "not_required_for_question_type"}

    if registry is None:
        from agents.registry import build_default_registry

        registry = await build_default_registry()

    tools = _select_tools(state, registry)
    if not tools:
        return {"skipped": True, "reason": "no_read_only_tools_available"}

    context = _build_context(state)
    results: list[InvestigationResult] = []

    for tool_name in tools:
        args: dict[str, Any] = {}
        if tool_name == "get_gitlab_mr_diffs":
            args = {"repository_id": state.repository_id}
        elif tool_name in {"gitnexus_analyze", "clone_repo", "run_impact_analysis"}:
            args = {"repo_path": context.repository_path}

        try:
            output = await registry.execute_tool(
                tool_name,
                args,
                context=context,
                step_id=f"copilot-{tool_name}",
            )
            results.append(
                InvestigationResult(
                    tool_name=tool_name,
                    status="success",
                    summary=f"Live investigation via {tool_name} completed.",
                    raw_preview=_preview(output),
                )
            )
        except Exception as exc:
            results.append(
                InvestigationResult(
                    tool_name=tool_name,
                    status="error",
                    summary=str(exc),
                )
            )

    state.investigation_results = results
    return {
        "tools_invoked": [r.tool_name for r in results],
        "success_count": sum(1 for r in results if r.status == "success"),
    }
