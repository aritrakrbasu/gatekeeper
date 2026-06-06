"""Knowledge API service layer."""

from __future__ import annotations

from typing import Any, List, Optional

from fastapi import HTTPException

from knowledge.models.api_models import (
    AssertionListResponse,
    AssertionResponse,
    CreateAssertionRequest,
    ReviewAssertionRequest,
)
from knowledge.models.assertion import KnowledgeAssertion, KnowledgeAssertionCreate
from knowledge.models.enums import AssertionStatus
from knowledge.store.assertion_repository import AssertionRepository
from peil.api.access import assert_repository_access, assert_repository_access_for_tests
from peil.store.execution_repository import ExecutionRepository

MAX_PAGE_SIZE = 100


class KnowledgeService:
    def __init__(self, db: Any = None) -> None:
        self._db = db
        self._assertions = AssertionRepository(db)
        self._executions = ExecutionRepository(db)

    async def _check_repo(self, user_id: str, repository_id: str) -> None:
        if self._db is not None:
            await assert_repository_access_for_tests(user_id, repository_id, self._db)
        else:
            await assert_repository_access(user_id, repository_id)

    async def _verify_execution_scope(
        self, repository_id: str, execution_id: str
    ) -> None:
        execution = await self._executions.get_by_execution_id(execution_id)
        if execution is None:
            raise HTTPException(status_code=404, detail="Source execution not found")
        if execution.repository_id != repository_id:
            raise HTTPException(
                status_code=400,
                detail="source_execution_id does not belong to repository_id",
            )

    @staticmethod
    def _to_response(assertion: KnowledgeAssertion) -> AssertionResponse:
        return AssertionResponse(
            assertion_id=assertion.assertion_id,
            repository_id=assertion.repository_id,
            source_execution_id=assertion.source_execution_id,
            source_conversation_id=assertion.source_conversation_id,
            type=assertion.type.value,
            statement=assertion.statement,
            evidence_refs=assertion.evidence_refs,
            confidence=assertion.confidence,
            status=assertion.status.value,
            graph_id=assertion.graph_id,
            graph_hash=assertion.graph_hash,
            replay_reference=assertion.replay_reference,
            provenance=assertion.provenance,
            proposed_by_user_id=assertion.proposed_by_user_id,
            reviewed_by_user_id=assertion.reviewed_by_user_id,
            reviewed_at=assertion.reviewed_at,
            audit_trail=assertion.audit_trail,
            metadata=assertion.metadata,
            created_at=assertion.created_at,
            updated_at=assertion.updated_at,
        )

    async def propose_assertion(
        self,
        user_id: str,
        request: CreateAssertionRequest,
    ) -> AssertionResponse:
        await self._check_repo(user_id, request.repository_id)
        await self._verify_execution_scope(
            request.repository_id, request.source_execution_id
        )

        data = KnowledgeAssertionCreate(
            repository_id=request.repository_id,
            source_execution_id=request.source_execution_id,
            source_conversation_id=request.source_conversation_id,
            type=request.type,
            statement=request.statement,
            evidence_refs=request.evidence_refs,
            confidence=request.confidence,
            graph_id=request.graph_id,
            graph_hash=request.graph_hash,
            replay_reference=request.replay_reference,
            metadata=request.metadata,
        )
        assertion = await self._assertions.propose(
            data, proposed_by_user_id=user_id
        )
        assert assertion.status == AssertionStatus.PROPOSED
        return self._to_response(assertion)

    async def list_assertions(
        self,
        user_id: str,
        repository_id: str,
        *,
        status: Optional[AssertionStatus] = None,
        assertion_type: Optional[str] = None,
        source_execution_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> AssertionListResponse:
        await self._check_repo(user_id, repository_id)
        page = max(1, page)
        page_size = max(1, min(page_size, MAX_PAGE_SIZE))
        offset = (page - 1) * page_size

        items, total = await self._assertions.list_paginated(
            repository_id,
            status=status,
            assertion_type=assertion_type,
            source_execution_id=source_execution_id,
            offset=offset,
            limit=page_size,
        )
        return AssertionListResponse(
            items=[self._to_response(a) for a in items],
            total=total,
            page=page,
            page_size=page_size,
            has_more=offset + page_size < total,
        )

    async def accept_assertion(
        self,
        user_id: str,
        assertion_id: str,
        request: ReviewAssertionRequest,
    ) -> AssertionResponse:
        assertion = await self._get_scoped(assertion_id, user_id)
        updated = await self._assertions.accept(
            assertion.assertion_id,
            actor_user_id=user_id,
            reason=request.reason,
        )
        return self._to_response(updated)

    async def reject_assertion(
        self,
        user_id: str,
        assertion_id: str,
        request: ReviewAssertionRequest,
    ) -> AssertionResponse:
        assertion = await self._get_scoped(assertion_id, user_id)
        updated = await self._assertions.reject(
            assertion.assertion_id,
            actor_user_id=user_id,
            reason=request.reason,
        )
        return self._to_response(updated)

    async def _get_scoped(self, assertion_id: str, user_id: str) -> KnowledgeAssertion:
        assertion = await self._assertions.get_by_id(assertion_id)
        if assertion is None:
            raise HTTPException(status_code=404, detail="Assertion not found")
        await self._check_repo(user_id, assertion.repository_id)
        return assertion

    async def propose_from_copilot(
        self,
        user_id: str,
        proposals: List[KnowledgeAssertionCreate],
    ) -> List[AssertionResponse]:
        results: List[AssertionResponse] = []
        for proposal in proposals:
            assertion = await self._assertions.propose(
                proposal, proposed_by_user_id=user_id
            )
            assert assertion.status == AssertionStatus.PROPOSED
            results.append(self._to_response(assertion))
        return results
