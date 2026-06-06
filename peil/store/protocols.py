"""Repository protocol interfaces for test doubles."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol

from peil.models.events import CaptureEvent
from peil.models.execution import PeilExecution, PeilExecutionCreate
from peil.models.graph import DecisionGraph, DecisionGraphCreate
from peil.models.subject import PeilSubject, PeilSubjectCreate, SubjectRef


class CaptureEventRepositoryProtocol(Protocol):
    async def append_events(self, events: List[CaptureEvent]) -> int: ...

    async def get_max_sequence(self, execution_id: str) -> int: ...

    async def list_by_execution_id(
        self, execution_id: str, *, limit: Optional[int] = None
    ) -> List[CaptureEvent]: ...


class EvidenceRepositoryProtocol(Protocol):
    async def store(
        self,
        *,
        execution_id: str,
        payload: bytes,
        content_type: str = "application/octet-stream",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str: ...

    async def resolve(self, ref: str, *, max_chars: Optional[int] = None) -> str: ...


class ExecutionRepositoryProtocol(Protocol):
    async def create(self, data: PeilExecutionCreate) -> PeilExecution: ...

    async def upsert(self, execution: PeilExecution) -> PeilExecution: ...

    async def get_by_execution_id(self, execution_id: str) -> Optional[PeilExecution]: ...

    async def get_by_task_id(self, task_id: str) -> Optional[PeilExecution]: ...

    async def find_by_subject(
        self,
        repository_id: str,
        subject_ref: SubjectRef,
        *,
        limit: int = 50,
    ) -> List[PeilExecution]: ...

    async def update_fields(
        self, execution_id: str, fields: Dict[str, Any]
    ) -> bool: ...


class GraphRepositoryProtocol(Protocol):
    async def insert(self, data: DecisionGraphCreate) -> DecisionGraph: ...

    async def get_by_graph_id(self, graph_id: str) -> Optional[DecisionGraph]: ...

    async def get_by_execution_id(
        self, execution_id: str, *, graph_revision: Optional[int] = None
    ) -> Optional[DecisionGraph]: ...


class SubjectRepositoryProtocol(Protocol):
    async def upsert(self, data: PeilSubjectCreate) -> PeilSubject: ...

    async def get(self, subject_id: str) -> Optional[PeilSubject]: ...

    async def register_execution(
        self, subject_id: str, execution_id: str
    ) -> Optional[PeilSubject]: ...

    async def find_by_ref(
        self, repository_id: str, subject_ref: SubjectRef
    ) -> Optional[PeilSubject]: ...
