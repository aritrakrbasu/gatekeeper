import pytest

from peil.capture.bus import ExecutionCaptureBus, NullCaptureBus
from peil.config import get_aril_settings
from peil.models.enums import CaptureEventType


class InMemoryEventRepo:
    def __init__(self) -> None:
        self.events = []

    async def append_events(self, events):
        self.events.extend(events)
        return len(events)


@pytest.fixture
def enabled_capture(monkeypatch):
    monkeypatch.setenv("ARIL_CAPTURE_ENABLED", "true")
    get_aril_settings.cache_clear()


def test_null_bus_when_disabled(monkeypatch):
    monkeypatch.setenv("ARIL_CAPTURE_ENABLED", "false")
    get_aril_settings.cache_clear()
    bus = ExecutionCaptureBus.create(task_id="t1", repository_id="repo")
    assert isinstance(bus, NullCaptureBus)


def test_execution_id_distinct_from_task_id(enabled_capture):
    bus = ExecutionCaptureBus(
        execution_id="exec-99",
        task_id="task-11",
        repository_id="82576405",
    )
    assert bus.execution_id == "exec-99"
    assert bus.task_id == "task-11"
    assert bus.execution_id != bus.task_id


def test_emit_increments_sequence_and_sanitizes(enabled_capture):
    bus = ExecutionCaptureBus(
        execution_id="exec-1",
        task_id="task-1",
        repository_id="82576405",
    )
    envelope = bus.build_envelope(
        CaptureEventType.EXECUTION_STARTED,
        {"api_key": "secret", "objective": "review"},
    )
    bus.emit(envelope)
    buffer = bus.get_buffer()
    assert len(buffer) == 1
    assert buffer[0].sequence == 1
    assert buffer[0].execution_id == "exec-1"
    assert buffer[0].task_id == "task-1"
    assert buffer[0].payload["api_key"] == "[MASKED]"


@pytest.mark.asyncio
async def test_flush_persists_to_repository(enabled_capture):
    repo = InMemoryEventRepo()
    bus = ExecutionCaptureBus(
        execution_id="exec-1",
        task_id="task-1",
        repository_id="82576405",
        event_repository=repo,
    )
    bus.emit(
        bus.build_envelope(CaptureEventType.PLAN_EMITTED, {"explanation": "plan"})
    )
    count = await bus.flush()
    assert count == 1
    assert len(bus.get_buffer()) == 0
    assert len(repo.events) == 1
