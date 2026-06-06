"""Resolve accepted repository knowledge for the current copilot turn."""

from __future__ import annotations

from typing import Any, Optional

from copilot.knowledge.citations import build_knowledge_citations
from copilot.models.state import CopilotState
from knowledge.resolver.resolver import KnowledgeResolver
from peil.models.enums import ExecutionType, SubjectType
from peil.models.subject import SubjectRef
from peil.store.execution_repository import ExecutionRepository


async def _execution_type_for_copilot(
    state: CopilotState,
    db: Any,
) -> str:
    if not state.execution_id:
        return ExecutionType.COPILOT_INVESTIGATE.value

    execution = await ExecutionRepository(db).get_by_execution_id(state.execution_id)
    if execution is None:
        return ExecutionType.COPILOT_INVESTIGATE.value
    return execution.execution_type.value


def _subject_ref_from_subject_id(
    subject_id: str,
    *,
    repository_id: str,
    conversation_id: str,
) -> SubjectRef:
    parts = subject_id.split(":")
    if len(parts) >= 2:
        try:
            subject_type = SubjectType(parts[0])
            return SubjectRef(
                type=subject_type,
                id=parts[1],
                repository_id=parts[2] if len(parts) > 2 else repository_id,
            )
        except ValueError:
            pass
    return SubjectRef(
        type=SubjectType.CONVERSATION,
        id=conversation_id,
        repository_id=repository_id,
    )


def _subject_ref_for_copilot(state: CopilotState) -> SubjectRef:
    bundle = state.replay_bundle
    if bundle is not None and bundle.execution_summary.subject_id:
        return _subject_ref_from_subject_id(
            bundle.execution_summary.subject_id,
            repository_id=state.repository_id,
            conversation_id=state.conversation_id,
        )
    return SubjectRef(
        type=SubjectType.CONVERSATION,
        id=state.conversation_id,
        repository_id=state.repository_id,
    )


async def _persist_knowledge_manifest(state: CopilotState, db: Any) -> None:
    if not state.knowledge_manifest:
        return
    if state.execution_id:
        try:
            await ExecutionRepository(db).update_fields(
                state.execution_id,
                {"knowledge_manifest": state.knowledge_manifest},
            )
        except Exception:
            pass


async def resolve_knowledge_node(
    state: CopilotState,
    *,
    db: Any = None,
    limit: Optional[int] = None,
) -> dict:
    execution_type = await _execution_type_for_copilot(state, db)
    subject_ref = _subject_ref_for_copilot(state)

    resolver = KnowledgeResolver(db)
    context = await resolver.resolve(
        repository_id=state.repository_id,
        execution_type=execution_type,
        subject_ref=subject_ref,
        question=state.question,
        limit=limit,
    )

    state.knowledge_context = context
    state.knowledge_manifest = context.to_manifest_dict()
    state.knowledge_citations = build_knowledge_citations(context)

    await _persist_knowledge_manifest(state, db)

    return {
        "assertion_count": context.manifest.assertion_count,
        "assertion_ids": context.manifest.assertion_ids,
        "citation_count": len(state.knowledge_citations),
        "execution_type": execution_type,
    }
