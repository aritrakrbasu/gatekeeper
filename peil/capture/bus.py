"""
ExecutionCaptureBus — in-process event buffer with optional persistence flush.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from peil.capture.sanitize import sanitize_event_payload
from peil.config import get_aril_settings, is_capture_enabled
from peil.logging import log_aril_event
from peil.models.enums import CaptureEventType
from peil.models.events import CaptureEvent, CaptureEventEnvelope


@runtime_checkable
class CaptureEventRepositoryProtocol(Protocol):
    async def append_events(self, events: List[CaptureEvent]) -> int: ...

    async def get_max_sequence(self, execution_id: str) -> int: ...


class CaptureEmitter(ABC):
    @abstractmethod
    def emit(self, envelope: CaptureEventEnvelope) -> None: ...

    @abstractmethod
    async def flush(self) -> int: ...

    @abstractmethod
    def get_buffer(self) -> List[CaptureEvent]: ...


class NullCaptureBus(CaptureEmitter):
    """No-op bus used when capture is disabled."""

    def emit(self, envelope: CaptureEventEnvelope) -> None:
        return None

    async def flush(self) -> int:
        return 0

    def get_buffer(self) -> List[CaptureEvent]:
        return []


class ExecutionCaptureBus(CaptureEmitter):
    """
    Buffers capture events for a single agent execution.

    execution_id is distinct from task_id per ARIL v4 adjustment.
    """

    def __init__(
        self,
        *,
        execution_id: str,
        task_id: str,
        repository_id: str,
        partition_key: Optional[str] = None,
        event_repository: Optional[CaptureEventRepositoryProtocol] = None,
        start_sequence: int = 0,
    ) -> None:
        self.execution_id = execution_id
        self.task_id = task_id
        self.repository_id = repository_id
        self.partition_key = partition_key or _default_partition_key()
        self._sequence = start_sequence
        self._buffer: List[CaptureEvent] = []
        self._event_repository = event_repository
        self._settings = get_aril_settings()

    @classmethod
    def create(
        cls,
        *,
        task_id: str,
        repository_id: str,
        execution_id: Optional[str] = None,
        event_repository: Optional[CaptureEventRepositoryProtocol] = None,
    ) -> CaptureEmitter:
        """Synchronous factory for brand-new executions (sequence starts at 0)."""
        if not is_capture_enabled():
            return NullCaptureBus()
        eid = execution_id or str(uuid.uuid4())
        return cls(
            execution_id=eid,
            task_id=task_id,
            repository_id=repository_id,
            event_repository=event_repository,
            start_sequence=0,
        )

    @classmethod
    async def open(
        cls,
        *,
        task_id: str,
        repository_id: str,
        execution_id: str,
        event_repository: Optional[CaptureEventRepositoryProtocol] = None,
    ) -> CaptureEmitter:
        """
        Async factory that restores sequence continuity for resumed executions.
        """
        if not is_capture_enabled():
            return NullCaptureBus()

        start_sequence = 0
        if event_repository is not None:
            start_sequence = await event_repository.get_max_sequence(execution_id)

        bus = cls(
            execution_id=execution_id,
            task_id=task_id,
            repository_id=repository_id,
            event_repository=event_repository,
            start_sequence=start_sequence,
        )
        log_aril_event(
            "capture_bus_opened",
            execution_id=execution_id,
            task_id=task_id,
            extra={"start_sequence": start_sequence},
        )
        return bus

    def emit(self, envelope: CaptureEventEnvelope) -> None:
        if not is_capture_enabled():
            return
        try:
            self._sequence += 1
            sanitized = sanitize_event_payload(envelope.payload)
            event = CaptureEvent(
                execution_id=self.execution_id,
                task_id=envelope.task_id or self.task_id,
                event_type=envelope.event_type,
                sequence=self._sequence,
                payload=sanitized,
                trace_id=envelope.trace_id,
                span_id=envelope.span_id,
                partition_key=self.partition_key,
            )
            self._buffer.append(event)
            log_aril_event(
                "capture_event_buffered",
                execution_id=self.execution_id,
                task_id=self.task_id,
                extra={
                    "event_type": envelope.event_type.value,
                    "sequence": self._sequence,
                },
            )
            if len(self._buffer) >= self._settings.event_flush_batch_size:
                # Fire-and-forget flush scheduling is caller responsibility.
                pass
        except Exception as exc:
            log_aril_event(
                "capture_emit_failed",
                level=40,
                execution_id=self.execution_id,
                task_id=self.task_id,
                extra={"error": str(exc), "event_type": envelope.event_type.value},
            )

    async def flush(self) -> int:
        if not self._buffer or self._event_repository is None:
            return 0
        try:
            batch = list(self._buffer)
            count = await self._event_repository.append_events(batch)
            self._buffer.clear()
            log_aril_event(
                "capture_events_flushed",
                execution_id=self.execution_id,
                task_id=self.task_id,
                extra={"count": count},
            )
            return count
        except Exception as exc:
            log_aril_event(
                "capture_flush_failed",
                level=40,
                execution_id=self.execution_id,
                task_id=self.task_id,
                extra={"error": str(exc), "buffered": len(self._buffer)},
            )
            return 0

    def get_buffer(self) -> List[CaptureEvent]:
        return list(self._buffer)

    def build_envelope(
        self,
        event_type: CaptureEventType,
        payload: Dict[str, Any],
        *,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
    ) -> CaptureEventEnvelope:
        return CaptureEventEnvelope(
            execution_id=self.execution_id,
            task_id=self.task_id,
            event_type=event_type,
            payload=payload,
            trace_id=trace_id,
            span_id=span_id,
        )


def _default_partition_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m")
