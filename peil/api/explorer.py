"""
ARIL Execution Explorer query service (read-only).
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from fastapi import HTTPException

from peil.api.access import assert_repository_access, assert_repository_access_for_tests
from peil.api.models import (
    CaptureEventListResponse,
    CaptureEventResponse,
    DecisionGraphResponse,
    EvidenceRefResponse,
    ExecutionDetailResponse,
    GraphEdgeResponse,
    GraphMetadataResponse,
    GraphNodeResponse,
    GraphSummaryResponse,
    PaginationMeta,
    SubjectRefResponse,
    SubjectResponse,
    SubjectTimelineResponse,
    TimelineEntryResponse,
)
from peil.models.execution import PeilExecution
from peil.models.graph import DecisionGraph
from peil.models.subject import PeilSubject
from peil.store.capture_event_repository import CaptureEventRepository
from peil.store.evidence_repository import EvidenceRepository
from peil.store.execution_repository import ExecutionRepository
from peil.store.graph_repository import GraphRepository
from peil.store.subject_repository import SubjectRepository

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500


class ExecutionExplorerService:
    def __init__(self, db: Any = None) -> None:
        self._db = db
        self._executions = ExecutionRepository(db)
        self._events = CaptureEventRepository(db)
        self._graphs = GraphRepository(db)
        self._subjects = SubjectRepository(db)
        self._evidence = EvidenceRepository(db)

    async def _check_repo(self, user_id: str, repository_id: str) -> None:
        if self._db is not None:
            await assert_repository_access_for_tests(user_id, repository_id, self._db)
        else:
            await assert_repository_access(user_id, repository_id)

    @staticmethod
    def _pagination(page: int, page_size: int, total: int) -> PaginationMeta:
        page = max(1, page)
        page_size = max(1, min(page_size, MAX_PAGE_SIZE))
        offset = (page - 1) * page_size
        has_more = offset + page_size < total
        return PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            has_more=has_more,
        )

    async def get_execution(
        self,
        execution_id: str,
        user_id: str,
    ) -> ExecutionDetailResponse:
        execution = await self._executions.get_by_execution_id(execution_id)
        if execution is None:
            raise HTTPException(status_code=404, detail="Execution not found")
        await self._check_repo(user_id, execution.repository_id)

        graph_summary = None
        graph = await self._graphs.get_by_execution_id(execution_id)
        if graph is not None:
            graph_summary = self._graph_summary(graph)

        return self._execution_detail(execution, graph_summary)

    async def list_events(
        self,
        execution_id: str,
        user_id: str,
        *,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> CaptureEventListResponse:
        execution = await self._executions.get_by_execution_id(execution_id)
        if execution is None:
            raise HTTPException(status_code=404, detail="Execution not found")
        await self._check_repo(user_id, execution.repository_id)

        page_size = max(1, min(page_size, MAX_PAGE_SIZE))
        page = max(1, page)
        offset = (page - 1) * page_size

        items, total = await self._events.list_paginated(
            execution_id, offset=offset, limit=page_size
        )
        return CaptureEventListResponse(
            execution_id=execution_id,
            items=[
                CaptureEventResponse(
                    event_id=e.event_id,
                    execution_id=e.execution_id,
                    task_id=e.task_id,
                    event_type=e.event_type.value,
                    sequence=e.sequence,
                    timestamp=e.timestamp,
                    payload=e.payload,
                    trace_id=e.trace_id,
                    span_id=e.span_id,
                    partition_key=e.partition_key,
                )
                for e in items
            ],
            pagination=self._pagination(page, page_size, total),
        )

    async def get_graph(
        self,
        execution_id: str,
        user_id: str,
        *,
        graph_revision: Optional[int] = None,
        include_evidence: bool = True,
        evidence_max_chars: int = 512,
    ) -> DecisionGraphResponse:
        execution = await self._executions.get_by_execution_id(execution_id)
        if execution is None:
            raise HTTPException(status_code=404, detail="Execution not found")
        await self._check_repo(user_id, execution.repository_id)

        graph = await self._graphs.get_by_execution_id(
            execution_id, graph_revision=graph_revision
        )
        if graph is None:
            raise HTTPException(status_code=404, detail="Decision graph not found")

        return await self._graph_response(
            graph,
            include_evidence=include_evidence,
            evidence_max_chars=evidence_max_chars,
        )

    async def get_subject(self, subject_id: str, user_id: str) -> SubjectResponse:
        subject = await self._subjects.get(subject_id)
        if subject is None:
            raise HTTPException(status_code=404, detail="Subject not found")
        await self._check_repo(user_id, subject.repository_id)
        return self._subject_response(subject)

    async def get_subject_timeline(
        self,
        subject_id: str,
        user_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> SubjectTimelineResponse:
        subject = await self._subjects.get(subject_id)
        if subject is None:
            raise HTTPException(status_code=404, detail="Subject not found")
        await self._check_repo(user_id, subject.repository_id)

        page_size = max(1, min(page_size, MAX_PAGE_SIZE))
        page = max(1, page)
        offset = (page - 1) * page_size

        executions, total = await self._executions.list_by_subject_id_paginated(
            subject_id,
            subject.repository_id,
            offset=offset,
            limit=page_size,
        )
        return SubjectTimelineResponse(
            subject_id=subject_id,
            repository_id=subject.repository_id,
            items=[self._timeline_entry(e) for e in executions],
            pagination=self._pagination(page, page_size, total),
        )

    async def _graph_response(
        self,
        graph: DecisionGraph,
        *,
        include_evidence: bool,
        evidence_max_chars: int,
    ) -> DecisionGraphResponse:
        nodes: List[GraphNodeResponse] = []
        for node in graph.nodes:
            evidence_items: List[EvidenceRefResponse] = []
            if include_evidence and node.evidence_refs:
                for ref in node.evidence_refs:
                    excerpt = await self._evidence.resolve(
                        ref, max_chars=evidence_max_chars
                    )
                    evidence_items.append(
                        EvidenceRefResponse(
                            ref=ref,
                            excerpt=excerpt or None,
                            byte_length=len(excerpt.encode("utf-8")) if excerpt else 0,
                        )
                    )
            nodes.append(
                GraphNodeResponse(
                    node_id=node.node_id,
                    type=node.type.value,
                    content=node.content,
                    evidence_refs=node.evidence_refs,
                    evidence=evidence_items,
                    created_at=node.created_at,
                )
            )

        return DecisionGraphResponse(
            graph_id=graph.graph_id,
            execution_id=graph.execution_id,
            task_id=graph.task_id,
            repository_id=graph.repository_id,
            graph_version=graph.graph_version,
            builder_version=graph.builder_version,
            schema_version=graph.schema_version,
            graph_revision=graph.graph_revision,
            graph_hash=graph.graph_hash,
            status=graph.status,
            metadata=GraphMetadataResponse(
                root_node_ids=graph.metadata.root_node_ids,
                terminal_node_ids=graph.metadata.terminal_node_ids,
                outcome_node_ids=graph.metadata.outcome_node_ids,
                node_count=graph.metadata.node_count,
                edge_count=graph.metadata.edge_count,
                graph_revision=graph.metadata.graph_revision,
            ),
            nodes=nodes,
            edges=[
                GraphEdgeResponse(
                    edge_id=e.edge_id,
                    from_node_id=e.from_node_id,
                    to_node_id=e.to_node_id,
                    relation=e.relation.value,
                    weight=e.weight,
                )
                for e in graph.edges
            ],
            created_at=graph.created_at,
        )

    @staticmethod
    def _graph_summary(graph: DecisionGraph) -> GraphSummaryResponse:
        return GraphSummaryResponse(
            graph_id=graph.graph_id,
            graph_revision=graph.graph_revision,
            graph_version=graph.graph_version,
            builder_version=graph.builder_version,
            graph_hash=graph.graph_hash,
            status=graph.status,
            root_node_ids=graph.metadata.root_node_ids,
            terminal_node_ids=graph.metadata.terminal_node_ids,
            outcome_node_ids=graph.metadata.outcome_node_ids,
            node_count=graph.metadata.node_count,
            edge_count=graph.metadata.edge_count,
        )

    @staticmethod
    def _execution_detail(
        execution: PeilExecution,
        graph_summary: Optional[GraphSummaryResponse],
    ) -> ExecutionDetailResponse:
        return ExecutionDetailResponse(
            execution_id=execution.execution_id,
            task_id=execution.task_id,
            execution_type=execution.execution_type.value,
            execution_source=execution.execution_source.value,
            repository_id=execution.repository_id,
            subject_id=execution.subject_id,
            subject_ref=SubjectRefResponse(
                type=execution.subject_ref.type.value,
                id=execution.subject_ref.id,
                sub_id=execution.subject_ref.sub_id,
                repository_id=execution.subject_ref.repository_id,
            ),
            objective=execution.objective,
            status=execution.status.value,
            graph_id=execution.graph_id,
            outcome_profile=execution.outcome_profile.value,
            terminal_outcome_ids=execution.terminal_outcome_ids,
            partition_key=execution.partition_key,
            schema_version=execution.schema_version,
            trace_id=execution.trace_id,
            span_id=execution.span_id,
            created_at=execution.created_at,
            updated_at=execution.updated_at,
            completed_at=execution.completed_at,
            graph_summary=graph_summary,
        )

    @staticmethod
    def _subject_response(subject: PeilSubject) -> SubjectResponse:
        return SubjectResponse(
            subject_id=subject.subject_id,
            repository_id=subject.repository_id,
            subject_ref=SubjectRefResponse(
                type=subject.subject_ref.type.value,
                id=subject.subject_ref.id,
                sub_id=subject.subject_ref.sub_id,
                repository_id=subject.subject_ref.repository_id,
            ),
            display_name=subject.display_name,
            execution_ids=subject.execution_ids,
            latest_execution_id=subject.latest_execution_id,
            execution_count=subject.execution_count,
            metadata=subject.metadata,
            created_at=subject.created_at,
            updated_at=subject.updated_at,
        )

    @staticmethod
    def _timeline_entry(execution: PeilExecution) -> TimelineEntryResponse:
        return TimelineEntryResponse(
            execution_id=execution.execution_id,
            task_id=execution.task_id,
            execution_type=execution.execution_type.value,
            status=execution.status.value,
            objective=execution.objective,
            graph_id=execution.graph_id,
            created_at=execution.created_at,
            updated_at=execution.updated_at,
        )
