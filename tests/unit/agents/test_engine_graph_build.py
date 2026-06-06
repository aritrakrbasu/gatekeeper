"""Unit tests for WorkflowEngine terminal graph build hook."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.aril_bridge import ArilSession
from agents.engine import WorkflowEngine
from peil.capture.bus import NullCaptureBus
from peil.store.capture_event_repository import CaptureEventRepository
from peil.store.evidence_repository import EvidenceRepository
from peil.store.execution_repository import ExecutionRepository
from peil.store.subject_repository import SubjectRepository


@pytest.mark.asyncio
async def test_emit_terminal_triggers_graph_build_on_completed(fake_db, monkeypatch):
    monkeypatch.setenv("ARIL_GRAPH_BUILD_ON_PAUSE", "true")
    from peil.config import get_aril_settings

    get_aril_settings.cache_clear()

    engine = WorkflowEngine(MagicMock())
    aril = ArilSession(
        execution_id="exec-terminal",
        task_id="task-1",
        subject_id="subj-1",
        bus=NullCaptureBus(),
        execution_repo=ExecutionRepository(fake_db),
        event_repo=CaptureEventRepository(fake_db),
        subject_repo=SubjectRepository(fake_db),
        evidence_repo=EvidenceRepository(fake_db),
    )

    with patch.object(
        WorkflowEngine,
        "_maybe_build_decision_graph",
        new_callable=AsyncMock,
    ) as mock_build:
        await engine._emit_terminal(aril, "completed", step_count=3, duration_ms=100.0)
        mock_build.assert_awaited_once_with(aril, "completed")

    get_aril_settings.cache_clear()
