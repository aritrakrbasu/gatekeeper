"""Integration tests for ARIL runtime wiring in WorkflowEngine."""

from __future__ import annotations

import uuid
from typing import Optional

import pytest

from agents.context import (
    AgentContext,
    BranchContext,
    RepositoryContext,
    SchemaContext,
    UserContext,
)
from peil.capture.bus import ExecutionCaptureBus, NullCaptureBus
from peil.config import get_aril_settings
from peil.models.enums import CaptureEventType, ExecutionSource, ExecutionStatus, ExecutionType
from peil.models.execution import PeilExecutionCreate
from peil.models.subject import PeilSubjectCreate, SubjectRef, build_subject_id
from peil.models.enums import SubjectType
from peil.store.capture_event_repository import CaptureEventRepository
from peil.store.evidence_repository import EvidenceRepository
from peil.store.execution_repository import ExecutionRepository
from peil.store.subject_repository import SubjectRepository


def _mr_context(task_id: str = "mr-review-test01") -> AgentContext:
    return AgentContext(
        task_id=task_id,
        objective="Review MR 42",
        repository=RepositoryContext(id="82576405", name="gatekeeper", git_url="https://gitlab.example/repo"),
        branch=BranchContext(source_branch="feature", target_branch="main"),
        user=UserContext(user_id="user-1", username="dev"),
        schema_ctx=SchemaContext(),
        metadata={"trigger_type": "gitlab_mr", "mr_iid": "42"},
    )


async def _build_fake_aril_session(fake_db, context: AgentContext):
    from agents.aril_bridge import ArilSession

    subject_ref = SubjectRef(type=SubjectType.MR, id="42", repository_id=context.repository_id)
    subject_id = build_subject_id(subject_ref)
    execution_id = str(uuid.uuid4())

    execution_repo = ExecutionRepository(fake_db)
    event_repo = CaptureEventRepository(fake_db)
    subject_repo = SubjectRepository(fake_db)
    evidence_repo = EvidenceRepository(fake_db)

    await subject_repo.upsert(
        PeilSubjectCreate(
            subject_id=subject_id,
            repository_id=context.repository_id,
            subject_ref=subject_ref,
        )
    )
    await execution_repo.create(
        PeilExecutionCreate(
            execution_id=execution_id,
            task_id=context.task_id,
            execution_type=ExecutionType.MR_REVIEW,
            execution_source=ExecutionSource.WORKFLOW_ENGINE,
            repository_id=context.repository_id,
            subject_ref=subject_ref,
            subject_id=subject_id,
            objective=context.objective,
        )
    )
    bus = ExecutionCaptureBus(
        execution_id=execution_id,
        task_id=context.task_id,
        repository_id=context.repository_id,
        event_repository=event_repo,
    )
    return ArilSession(
        execution_id=execution_id,
        task_id=context.task_id,
        subject_id=subject_id,
        bus=bus,
        execution_repo=execution_repo,
        event_repo=event_repo,
        subject_repo=subject_repo,
        evidence_repo=evidence_repo,
    )


@pytest.fixture
def enabled_aril(monkeypatch):
    monkeypatch.setenv("ARIL_CAPTURE_ENABLED", "true")
    monkeypatch.setenv("ARIL_CAPTURE_VIA_REGISTRY", "true")
    get_aril_settings.cache_clear()
    yield
    get_aril_settings.cache_clear()


@pytest.fixture
def disabled_aril(monkeypatch):
    monkeypatch.setenv("ARIL_CAPTURE_ENABLED", "false")
    get_aril_settings.cache_clear()
    yield
    get_aril_settings.cache_clear()


@pytest.mark.asyncio
async def test_bootstrap_new_execution_creates_session(fake_db, enabled_aril, monkeypatch):
    from agents import aril_bridge

    async def _fake_bootstrap(ctx):
        return await _build_fake_aril_session(fake_db, ctx)

    monkeypatch.setattr(aril_bridge, "bootstrap_new_execution", _fake_bootstrap)
    session = await aril_bridge.bootstrap_new_execution(_mr_context())
    assert session is not None
    assert session.execution_id
    assert isinstance(session.bus, ExecutionCaptureBus)


@pytest.mark.asyncio
async def test_bootstrap_returns_none_when_disabled(disabled_aril):
    from agents.aril_bridge import bootstrap_new_execution

    session = await bootstrap_new_execution(_mr_context())
    assert session is None


@pytest.mark.asyncio
async def test_workflow_emits_lifecycle_events(fake_db, enabled_aril, monkeypatch):
    from agents.engine import WorkflowEngine
    from agents.planner import StepSchema
    from agents.registry import ToolRegistry
    import agents.engine as engine_module

    context = _mr_context("mr-review-integ01")
    session_holder: dict = {}

    async def _fake_bootstrap(ctx):
        session = await _build_fake_aril_session(fake_db, ctx)
        session_holder["session"] = session
        session.emit(
            CaptureEventType.EXECUTION_STARTED,
            {
                "task_id": ctx.task_id,
                "objective": ctx.objective,
                "context_snapshot": {},
                "trigger_type": "gitlab_mr",
                "execution_type": ExecutionType.MR_REVIEW.value,
                "repository_id": ctx.repository_id,
                "subject_id": session.subject_id,
            },
        )
        await session.flush()
        return session

    monkeypatch.setattr(engine_module, "bootstrap_new_execution", _fake_bootstrap)

    plan_steps = [
        StepSchema(
            step_id="clone",
            tool_name="clone_repo",
            arguments_json="{}",
            action="Clone repo",
            reason="Need workspace",
        ),
        StepSchema(
            step_id="analyze",
            tool_name="gitnexus_analyze",
            arguments_json="{}",
            dependencies=["clone"],
            action="Analyze",
            reason="Call graph",
        ),
    ]

    async def fake_generate_plan(*args, **kwargs):
        aril = kwargs.get("aril")
        if aril is not None:
            aril.emit(
                CaptureEventType.PLAN_EMITTED,
                {"explanation": "test plan", "steps": [], "plan_revision": 0},
            )
            aril.emit(
                CaptureEventType.MODEL_TURN,
                {"source": "planner", "prompt_hash": "abc", "response_hash": "def"},
            )
            await aril.flush()
        return plan_steps

    monkeypatch.setattr("agents.planner.PlannerAgent.generate_plan", fake_generate_plan)
    async def _noop_persist(self):
        return None

    async def _empty_memories(self, *a, **k):
        return []

    monkeypatch.setattr("agents.memory.MemoryStore.persist_to_mongodb", _noop_persist)
    monkeypatch.setattr("agents.memory.MemoryStore.find_similar_fixes", _empty_memories)
    monkeypatch.setattr("agents.memory.MemoryStore.find_similar_incidents", _empty_memories)
    monkeypatch.setattr("agents.memory.MemoryStore.add_step", lambda self, *a, **k: None)

    registry = ToolRegistry()

    async def fake_execute_tool(name, arguments, context=None, step_id=None):
        return {"tool": name, "step_id": step_id}

    registry.execute_tool = fake_execute_tool  # type: ignore[method-assign]

    engine = WorkflowEngine(registry)
    result = await engine.run_task(context)

    assert result["status"] == "completed"
    assert "execution_id" in result

    session = session_holder["session"]
    events = await session.event_repo.list_by_execution_id(result["execution_id"])
    event_types = [e.event_type for e in events]
    assert CaptureEventType.EXECUTION_STARTED in event_types
    assert CaptureEventType.PLAN_EMITTED in event_types
    assert CaptureEventType.MODEL_TURN in event_types
    assert CaptureEventType.STEP_STARTED in event_types
    assert CaptureEventType.STEP_COMPLETED in event_types
    assert CaptureEventType.REFLECTION_EVALUATED in event_types
    assert CaptureEventType.EXECUTION_COMPLETED in event_types


@pytest.mark.asyncio
async def test_resume_uses_open_for_sequence_continuity(fake_db, enabled_aril):
    context = _mr_context("mr-review-resume01")
    session = await _build_fake_aril_session(fake_db, context)
    event_repo = session.event_repo

    session.emit(CaptureEventType.EXECUTION_STARTED, {"objective": "x"})
    session.emit(CaptureEventType.PLAN_EMITTED, {"explanation": "p", "steps": [], "plan_revision": 0})
    await session.flush()

    bus = await ExecutionCaptureBus.open(
        task_id=context.task_id,
        repository_id=context.repository_id,
        execution_id=session.execution_id,
        event_repository=event_repo,
    )
    bus.emit(bus.build_envelope(CaptureEventType.STEP_STARTED, {"step_id": "s1"}))
    await bus.flush()

    events = await event_repo.list_by_execution_id(session.execution_id)
    sequences = [e.sequence for e in events]
    assert sequences == [1, 2, 3]


@pytest.mark.asyncio
async def test_null_capture_bus_when_disabled(disabled_aril):
    bus = ExecutionCaptureBus.create(task_id="t1", repository_id="repo")
    assert isinstance(bus, NullCaptureBus)
