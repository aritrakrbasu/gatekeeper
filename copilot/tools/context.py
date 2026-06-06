"""AgentContext builder for Copilot tool execution."""

from __future__ import annotations

from agents.context import AgentContext, BranchContext, RepositoryContext, SchemaContext, UserContext
from copilot.models.state import CopilotState


def build_agent_context(state: CopilotState) -> AgentContext:
    bundle = state.replay_bundle
    repo_id = state.repository_id
    repo_name = repo_id
    if bundle is not None:
        repo_name = bundle.execution_summary.repository_id

    metadata = {
        "copilot_conversation_id": state.conversation_id,
        "source_execution_id": state.execution_id,
    }
    if state.copilot_execution_id:
        metadata["copilot_execution_id"] = state.copilot_execution_id

    return AgentContext(
        task_id=state.conversation_id,
        objective=state.question,
        repository=RepositoryContext(id=repo_id, name=repo_name),
        branch=BranchContext(source_branch="main", target_branch="main"),
        user=UserContext(user_id=state.user_id, username=state.user_id),
        schema_ctx=SchemaContext(),
        metadata=metadata,
    )
