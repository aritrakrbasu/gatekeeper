"""
ARIL runtime bridge — best-effort capture wiring for WorkflowEngine.

All operations swallow errors; workflow execution must never fail because of ARIL.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from peil.capture.bus import CaptureEmitter, ExecutionCaptureBus, NullCaptureBus
from peil.config import is_capture_enabled
from peil.logging import log_aril_event
from peil.models.enums import CaptureEventType, ExecutionSource, ExecutionStatus, ExecutionType, SubjectType
from peil.models.execution import PeilExecutionCreate
from peil.models.subject import PeilSubjectCreate, SubjectRef, build_subject_id
from peil.store.capture_event_repository import CaptureEventRepository
from peil.store.evidence_repository import EvidenceRepository
from peil.store.execution_repository import ExecutionRepository
from peil.store.subject_repository import SubjectRepository

from agents.context import AgentContext


@dataclass
class ArilSession:
    execution_id: str
    task_id: str
    subject_id: str
    bus: CaptureEmitter
    execution_repo: ExecutionRepository
    event_repo: CaptureEventRepository
    subject_repo: SubjectRepository
    evidence_repo: EvidenceRepository
    plan_revision: int = 0

    def emit(self, event_type: CaptureEventType, payload: Dict[str, Any]) -> None:
        if isinstance(self.bus, NullCaptureBus):
            return
        try:
            if isinstance(self.bus, ExecutionCaptureBus):
                envelope = self.bus.build_envelope(event_type, payload)
                self.bus.emit(envelope)
        except Exception as exc:
            log_aril_event(
                "aril_emit_failed",
                level=40,
                execution_id=self.execution_id,
                task_id=self.task_id,
                extra={"error": str(exc), "event_type": event_type.value},
            )

    async def flush(self) -> None:
        try:
            await self.bus.flush()
        except Exception as exc:
            log_aril_event(
                "aril_flush_failed",
                level=40,
                execution_id=self.execution_id,
                task_id=self.task_id,
                extra={"error": str(exc)},
            )

    async def update_status(self, status: ExecutionStatus, **fields: Any) -> None:
        try:
            update = {"status": status.value, **fields}
            await self.execution_repo.update_fields(self.execution_id, update)
        except Exception as exc:
            log_aril_event(
                "aril_status_update_failed",
                level=40,
                execution_id=self.execution_id,
                task_id=self.task_id,
                extra={"error": str(exc), "status": status.value},
            )


def _execution_type_for_context(context: AgentContext) -> ExecutionType:
    trigger = context.metadata.get("trigger_type", "")
    if trigger == "gitlab_mr":
        return ExecutionType.MR_REVIEW
    if trigger == "dynatrace_crash":
        if "remediation" in context.task_id:
            return ExecutionType.REMEDIATION
        return ExecutionType.INCIDENT
    if "remediation" in context.task_id:
        return ExecutionType.REMEDIATION
    if "incident" in context.task_id:
        return ExecutionType.INCIDENT
    if "mr-review" in context.task_id:
        return ExecutionType.MR_REVIEW
    return ExecutionType.MR_REVIEW


def _subject_ref_for_context(context: AgentContext) -> SubjectRef:
    mr_iid = context.metadata.get("mr_iid")
    if mr_iid:
        return SubjectRef(
            type=SubjectType.MR,
            id=str(mr_iid),
            repository_id=context.repository_id,
        )
    if context.incident and context.incident.problem_id:
        return SubjectRef(
            type=SubjectType.INCIDENT,
            id=str(context.incident.problem_id),
            repository_id=context.repository_id,
        )
    return SubjectRef(
        type=SubjectType.REPOSITORY,
        id=context.repository_id,
        repository_id=context.repository_id,
    )


def _trigger_type(context: AgentContext) -> str:
    return context.metadata.get("trigger_type") or "workflow_engine"


async def bootstrap_new_execution(context: AgentContext) -> Optional[ArilSession]:
    """Create execution_id, subject row, header, and capture bus for a new run."""
    if not is_capture_enabled():
        return None
    try:
        execution_id = str(uuid.uuid4())
        subject_ref = _subject_ref_for_context(context)
        subject_id = build_subject_id(subject_ref)
        execution_repo = ExecutionRepository()
        event_repo = CaptureEventRepository()
        subject_repo = SubjectRepository()
        evidence_repo = EvidenceRepository()

        await subject_repo.upsert(
            PeilSubjectCreate(
                subject_id=subject_id,
                repository_id=context.repository_id,
                subject_ref=subject_ref,
                display_name=context.objective[:120],
            )
        )
        await execution_repo.create(
            PeilExecutionCreate(
                execution_id=execution_id,
                task_id=context.task_id,
                execution_type=_execution_type_for_context(context),
                execution_source=ExecutionSource.WORKFLOW_ENGINE,
                repository_id=context.repository_id,
                subject_ref=subject_ref,
                subject_id=subject_id,
                objective=context.objective,
                context_snapshot=_context_snapshot(context),
            )
        )
        await subject_repo.register_execution(subject_id, execution_id)

        bus = ExecutionCaptureBus.create(
            task_id=context.task_id,
            repository_id=context.repository_id,
            execution_id=execution_id,
            event_repository=event_repo,
        )

        session = ArilSession(
            execution_id=execution_id,
            task_id=context.task_id,
            subject_id=subject_id,
            bus=bus,
            execution_repo=execution_repo,
            event_repo=event_repo,
            subject_repo=subject_repo,
            evidence_repo=evidence_repo,
        )
        session.emit(
            CaptureEventType.EXECUTION_STARTED,
            {
                "task_id": context.task_id,
                "objective": context.objective,
                "context_snapshot": _context_snapshot(context),
                "trigger_type": _trigger_type(context),
                "execution_type": _execution_type_for_context(context).value,
                "repository_id": context.repository_id,
                "subject_id": subject_id,
            },
        )
        await session.flush()
        return session
    except Exception as exc:
        log_aril_event(
            "aril_bootstrap_failed",
            level=40,
            task_id=context.task_id,
            extra={"error": str(exc)},
        )
        return None


async def bootstrap_resumed_execution(
    context: AgentContext,
    execution_id: str,
) -> Optional[ArilSession]:
    """Reopen capture bus with sequence continuity for a resumed execution."""
    if not is_capture_enabled():
        return None
    try:
        execution_repo = ExecutionRepository()
        event_repo = CaptureEventRepository()
        subject_repo = SubjectRepository()
        evidence_repo = EvidenceRepository()

        bus = await ExecutionCaptureBus.open(
            task_id=context.task_id,
            repository_id=context.repository_id,
            execution_id=execution_id,
            event_repository=event_repo,
        )

        subject_ref = _subject_ref_for_context(context)
        subject_id = build_subject_id(subject_ref)

        session = ArilSession(
            execution_id=execution_id,
            task_id=context.task_id,
            subject_id=subject_id,
            bus=bus,
            execution_repo=execution_repo,
            event_repo=event_repo,
            subject_repo=subject_repo,
            evidence_repo=evidence_repo,
        )
        await session.update_status(ExecutionStatus.CAPTURING)
        return session
    except Exception as exc:
        log_aril_event(
            "aril_resume_bootstrap_failed",
            level=40,
            task_id=context.task_id,
            execution_id=execution_id,
            extra={"error": str(exc)},
        )
        return None


async def _resume_copilot_execution(
    *,
    conversation_id: str,
    repository_id: str,
    execution_id: str,
    objective: str,
    linked_execution_id: Optional[str],
    subject_id: str,
    execution_repo: ExecutionRepository,
    event_repo: CaptureEventRepository,
    subject_repo: SubjectRepository,
    evidence_repo: EvidenceRepository,
) -> ArilSession:
    """Reopen ARIL capture for an existing Copilot conversation execution."""
    bus = await ExecutionCaptureBus.open(
        task_id=conversation_id,
        repository_id=repository_id,
        execution_id=execution_id,
        event_repository=event_repo,
    )

    session = ArilSession(
        execution_id=execution_id,
        task_id=conversation_id,
        subject_id=subject_id,
        bus=bus,
        execution_repo=execution_repo,
        event_repo=event_repo,
        subject_repo=subject_repo,
        evidence_repo=evidence_repo,
    )

    update_fields: Dict[str, Any] = {}
    if objective:
        update_fields["objective"] = objective
    if linked_execution_id is not None:
        update_fields["context_snapshot.linked_execution_id"] = linked_execution_id
    if update_fields:
        await execution_repo.update_fields(execution_id, update_fields)

    await subject_repo.register_execution(subject_id, execution_id)
    await session.update_status(ExecutionStatus.CAPTURING)
    return session


async def bootstrap_copilot_execution(
    *,
    conversation_id: str,
    user_id: str,
    repository_id: str,
    execution_id: Optional[str] = None,
    objective: str = "",
    linked_execution_id: Optional[str] = None,
    db: Any = None,
) -> Optional[ArilSession]:
    """Create or resume ARIL capture session for a LangGraph Copilot conversation."""
    if not is_capture_enabled():
        return None
    try:
        subject_ref = SubjectRef(
            type=SubjectType.CONVERSATION,
            id=conversation_id,
            repository_id=repository_id,
        )
        subject_id = build_subject_id(subject_ref)
        execution_repo = ExecutionRepository(db)
        event_repo = CaptureEventRepository(db)
        subject_repo = SubjectRepository(db)
        evidence_repo = EvidenceRepository(db)

        await subject_repo.upsert(
            PeilSubjectCreate(
                subject_id=subject_id,
                repository_id=repository_id,
                subject_ref=subject_ref,
                display_name=objective[:120] or f"Copilot {conversation_id}",
            )
        )

        existing = None
        if execution_id:
            existing = await execution_repo.get_by_execution_id(execution_id)
        if existing is None:
            existing = await execution_repo.get_by_task_id(conversation_id)

        if existing is not None:
            return await _resume_copilot_execution(
                conversation_id=conversation_id,
                repository_id=repository_id,
                execution_id=existing.execution_id,
                objective=objective,
                linked_execution_id=linked_execution_id,
                subject_id=subject_id,
                execution_repo=execution_repo,
                event_repo=event_repo,
                subject_repo=subject_repo,
                evidence_repo=evidence_repo,
            )

        resolved_execution_id = str(uuid.uuid4())
        snapshot: Dict[str, Any] = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "repository_id": repository_id,
            "linked_execution_id": linked_execution_id,
        }
        await execution_repo.create(
            PeilExecutionCreate(
                execution_id=resolved_execution_id,
                task_id=conversation_id,
                execution_type=ExecutionType.COPILOT_INVESTIGATE,
                execution_source=ExecutionSource.LANGGRAPH_COPILOT,
                repository_id=repository_id,
                subject_ref=subject_ref,
                subject_id=subject_id,
                objective=objective or f"Copilot conversation {conversation_id}",
                context_snapshot=snapshot,
            )
        )
        await subject_repo.register_execution(subject_id, resolved_execution_id)

        bus = ExecutionCaptureBus.create(
            task_id=conversation_id,
            repository_id=repository_id,
            execution_id=resolved_execution_id,
            event_repository=event_repo,
        )

        session = ArilSession(
            execution_id=resolved_execution_id,
            task_id=conversation_id,
            subject_id=subject_id,
            bus=bus,
            execution_repo=execution_repo,
            event_repo=event_repo,
            subject_repo=subject_repo,
            evidence_repo=evidence_repo,
        )
        session.emit(
            CaptureEventType.EXECUTION_STARTED,
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "repository_id": repository_id,
                "linked_execution_id": linked_execution_id,
                "execution_type": ExecutionType.COPILOT_INVESTIGATE.value,
                "execution_source": ExecutionSource.LANGGRAPH_COPILOT.value,
                "subject_id": subject_id,
            },
        )
        await session.flush()
        return session
    except Exception as exc:
        log_aril_event(
            "aril_copilot_bootstrap_failed",
            level=40,
            task_id=conversation_id,
            extra={"error": str(exc), "conversation_id": conversation_id},
        )
        return None


async def resolve_execution_id_for_task(task_id: str) -> Optional[str]:
    try:
        repo = ExecutionRepository()
        execution = await repo.get_by_task_id(task_id)
        if execution:
            return execution.execution_id
    except Exception:
        pass
    return None


def _context_snapshot(context: AgentContext) -> Dict[str, Any]:
    data = context.serialize()
    for key in ("repository", "branch", "user", "metadata"):
        if key in data and isinstance(data[key], dict):
            continue
    return {
        "task_id": context.task_id,
        "objective": context.objective,
        "repository_id": context.repository_id,
        "metadata": context.metadata,
        "trigger_type": _trigger_type(context),
    }


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def serialize_for_evidence(value: Any) -> bytes:
    try:
        return json.dumps(value, default=str).encode("utf-8")
    except Exception:
        return str(value).encode("utf-8")
