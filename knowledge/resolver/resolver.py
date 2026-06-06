"""Deterministic repository knowledge resolver (no vector search / LLM)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from knowledge.config import get_knowledge_settings
from knowledge.models.assertion import KnowledgeAssertion
from knowledge.models.enums import AssertionStatus, AssertionType
from knowledge.resolver.models import (
    ConfidenceSummary,
    KnowledgeContext,
    KnowledgeManifest,
    ResolvedAssertion,
)
from knowledge.store.assertion_repository import AssertionRepository
from peil.models.enums import ExecutionType
from peil.models.subject import SubjectRef

# Group ordering priority per execution type (deterministic).
_TYPE_PRIORITY: Dict[str, List[AssertionType]] = {
    ExecutionType.MR_REVIEW.value: [
        AssertionType.REVIEW_CORRECTION,
        AssertionType.REPOSITORY_PATTERN,
        AssertionType.BUSINESS_RULE,
        AssertionType.ARCHITECTURE_RULE,
    ],
    ExecutionType.INCIDENT.value: [
        AssertionType.ARCHITECTURE_RULE,
        AssertionType.BUSINESS_RULE,
        AssertionType.REPOSITORY_PATTERN,
        AssertionType.REVIEW_CORRECTION,
    ],
    ExecutionType.REMEDIATION.value: [
        AssertionType.ARCHITECTURE_RULE,
        AssertionType.REPOSITORY_PATTERN,
        AssertionType.BUSINESS_RULE,
        AssertionType.REVIEW_CORRECTION,
    ],
    ExecutionType.COPILOT_INVESTIGATE.value: [
        AssertionType.REPOSITORY_PATTERN,
        AssertionType.BUSINESS_RULE,
        AssertionType.ARCHITECTURE_RULE,
        AssertionType.REVIEW_CORRECTION,
    ],
}

_DEFAULT_PRIORITY = list(AssertionType)


class KnowledgeResolver:
    """Retrieve accepted, repository-scoped knowledge for active executions."""

    def __init__(self, db: Any = None, *, limit: Optional[int] = None) -> None:
        self._db = db
        self._settings = get_knowledge_settings()
        self._assertions = AssertionRepository(db)
        self._limit = limit or self._settings.resolver_limit

    async def resolve(
        self,
        *,
        repository_id: str,
        execution_type: str,
        subject_ref: Optional[SubjectRef] = None,
        question: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> KnowledgeContext:
        effective_limit = max(1, limit or self._limit)

        items, total = await self._assertions.list_paginated(
            repository_id,
            status=AssertionStatus.ACCEPTED,
            offset=0,
            limit=max(effective_limit * 3, effective_limit),
        )

        filtered = _filter_by_question(items, question)
        ordered = _deterministic_order(filtered, execution_type)
        selected = ordered[:effective_limit]

        grouped = _group_by_type(selected, execution_type)
        confidence_by_type = {
            key: _confidence_summary(values)
            for key, values in grouped.items()
        }

        manifest = KnowledgeManifest(
            repository_id=repository_id,
            execution_type=execution_type,
            assertion_count=len(selected),
            assertion_ids=[a.assertion_id for a in selected],
            groups={k: [a.assertion_id for a in v] for k, v in grouped.items()},
            limit=effective_limit,
            total_available=total,
            resolved_at=datetime.now(timezone.utc),
            subject_id=_subject_id(subject_ref),
            question=question.strip() if question else None,
        )

        return KnowledgeContext(
            repository_id=repository_id,
            execution_type=execution_type,
            subject_ref=subject_ref,
            question=question,
            limit=effective_limit,
            total_available=total,
            assertions_by_type={
                k: [_to_resolved(a) for a in v] for k, v in grouped.items()
            },
            confidence_by_type=confidence_by_type,
            manifest=manifest,
        )

    async def resolve_for_context(
        self,
        context: Any,
        *,
        question: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> KnowledgeContext:
        from agents.aril_bridge import _execution_type_for_context, _subject_ref_for_context

        execution_type = _execution_type_for_context(context).value
        subject_ref = _subject_ref_for_context(context)
        return await self.resolve(
            repository_id=context.repository_id,
            execution_type=execution_type,
            subject_ref=subject_ref,
            question=question,
            limit=limit,
        )


def _subject_id(subject_ref: Optional[SubjectRef]) -> Optional[str]:
    if subject_ref is None:
        return None
    from peil.models.subject import build_subject_id

    return build_subject_id(subject_ref)


def _to_resolved(assertion: KnowledgeAssertion) -> ResolvedAssertion:
    return ResolvedAssertion(
        assertion_id=assertion.assertion_id,
        type=assertion.type,
        statement=assertion.statement,
        confidence=assertion.confidence,
        evidence_refs=list(assertion.evidence_refs),
        provenance=assertion.provenance,
        source_execution_id=assertion.source_execution_id,
        reviewed_at=assertion.reviewed_at,
        created_at=assertion.created_at,
    )


def _tokenize_question(question: Optional[str]) -> List[str]:
    if not question:
        return []
    tokens = re.findall(r"[a-z0-9]{4,}", question.lower())
    return sorted(set(tokens))


def _filter_by_question(
    items: Sequence[KnowledgeAssertion],
    question: Optional[str],
) -> List[KnowledgeAssertion]:
    tokens = _tokenize_question(question)
    if not tokens:
        return list(items)

    matched: List[KnowledgeAssertion] = []
    for item in items:
        statement = item.statement.lower()
        if any(token in statement for token in tokens):
            matched.append(item)
    return matched if matched else list(items)


def _deterministic_order(
    items: Sequence[KnowledgeAssertion],
    execution_type: str,
) -> List[KnowledgeAssertion]:
    """Most recent first; tie-break by assertion_id for stable ordering."""
    del execution_type
    return sorted(
        items,
        key=lambda item: (
            item.created_at.isoformat() if item.created_at else "",
            item.assertion_id,
        ),
        reverse=True,
    )


def _group_by_type(
    items: Sequence[KnowledgeAssertion],
    execution_type: str,
) -> Dict[str, List[KnowledgeAssertion]]:
    priority = _TYPE_PRIORITY.get(execution_type, _DEFAULT_PRIORITY)
    grouped: Dict[str, List[KnowledgeAssertion]] = {
        t.value: [] for t in priority
    }
    for item in items:
        grouped.setdefault(item.type.value, []).append(item)

    return {k: v for k, v in grouped.items() if v}


def _confidence_summary(items: Sequence[KnowledgeAssertion]) -> ConfidenceSummary:
    if not items:
        return ConfidenceSummary()
    values = [item.confidence for item in items]
    return ConfidenceSummary(
        count=len(values),
        min_confidence=min(values),
        max_confidence=max(values),
        avg_confidence=sum(values) / len(values),
    )
