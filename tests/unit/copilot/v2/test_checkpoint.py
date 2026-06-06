"""Unit tests for MongoLangGraphSaver."""

from __future__ import annotations

import pytest
from langgraph.checkpoint.base import Checkpoint, CheckpointMetadata

from copilot.checkpoint.langgraph_saver import (
    CHECKPOINTS_COLLECTION,
    MongoLangGraphSaver,
)


def _sample_checkpoint(checkpoint_id: str = "1") -> Checkpoint:
    return Checkpoint(
        v=1,
        id=checkpoint_id,
        ts="2026-06-06T00:00:00+00:00",
        channel_values={"copilot": {"conversation_id": "conv-1"}},
        channel_versions={"copilot": 1},
        versions_seen={},
        updated_channels=["copilot"],
    )


@pytest.mark.asyncio
async def test_checkpoint_round_trip(fake_db):
    saver = MongoLangGraphSaver(fake_db)
    config = {"configurable": {"thread_id": "conv-1", "checkpoint_ns": ""}}
    checkpoint = _sample_checkpoint("checkpoint-1")
    metadata: CheckpointMetadata = {"source": "loop", "step": 0}

    updated = await saver.aput(config, checkpoint, metadata, {"copilot": 1})
    assert updated["configurable"]["checkpoint_id"] == "checkpoint-1"

    loaded = await saver.aget_tuple(
        {"configurable": {"thread_id": "conv-1", "checkpoint_ns": ""}}
    )
    assert loaded is not None
    assert loaded.checkpoint["id"] == "checkpoint-1"
    assert loaded.checkpoint["channel_values"]["copilot"]["conversation_id"] == "conv-1"

    docs = fake_db[CHECKPOINTS_COLLECTION].docs
    assert len(docs) == 1
    assert docs[0]["thread_id"] == "conv-1"


@pytest.mark.asyncio
async def test_delete_thread_soft_marks_records(fake_db):
    saver = MongoLangGraphSaver(fake_db)
    config = {"configurable": {"thread_id": "conv-del", "checkpoint_ns": ""}}
    await saver.aput(config, _sample_checkpoint("cp-del"), {"source": "loop", "step": 0}, {"copilot": 1})

    await saver.adelete_thread("conv-del")

    loaded = await saver.aget_tuple(
        {"configurable": {"thread_id": "conv-del", "checkpoint_ns": ""}}
    )
    assert loaded is None
