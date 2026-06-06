"""Unit tests for Copilot Mongo indexes."""

from __future__ import annotations

import pytest

from copilot.store.indexes import ensure_copilot_indexes, get_copilot_index_specs


def test_copilot_index_specs_include_frontend_collections():
    collections = {spec[0] for spec in get_copilot_index_specs()}
    assert "copilot_conversation_checkpoints" in collections
    assert "copilot_approvals" in collections
    assert "copilot_sse_events" in collections
    assert "copilot_langgraph_checkpoints" in collections


@pytest.mark.asyncio
async def test_ensure_copilot_indexes_on_fake_db(fake_db):
    summary = await ensure_copilot_indexes(fake_db)
    assert summary["indexes_ensured"] >= 10
