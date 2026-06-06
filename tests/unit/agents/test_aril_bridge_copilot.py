"""Unit tests for bootstrap_copilot_execution."""

from __future__ import annotations

import pytest

from agents.aril_bridge import bootstrap_copilot_execution
from peil.models.enums import ExecutionSource, ExecutionType, SubjectType
from peil.store.execution_repository import ExecutionRepository


@pytest.mark.asyncio
async def test_bootstrap_copilot_execution_creates_langgraph_header(fake_db, monkeypatch):
    monkeypatch.setenv("ARIL_CAPTURE_ENABLED", "true")
    from peil.config import get_aril_settings

    get_aril_settings.cache_clear()

    session = await bootstrap_copilot_execution(
        conversation_id="conv-bootstrap",
        user_id="user-1",
        repository_id="repo-1",
        linked_execution_id="exec-linked",
        objective="Explain MR review",
        db=fake_db,
    )
    assert session is not None
    assert session.task_id == "conv-bootstrap"

    repo = ExecutionRepository(fake_db)
    header = await repo.get_by_execution_id(session.execution_id)
    assert header is not None
    assert header.execution_type == ExecutionType.COPILOT_INVESTIGATE
    assert header.execution_source == ExecutionSource.LANGGRAPH_COPILOT
    assert header.subject_ref.type == SubjectType.CONVERSATION
    assert header.subject_ref.id == "conv-bootstrap"
    assert header.context_snapshot["linked_execution_id"] == "exec-linked"

    get_aril_settings.cache_clear()
