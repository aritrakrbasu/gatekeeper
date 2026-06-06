"""Compile LangGraph Copilot v2 with Mongo checkpointing."""

from __future__ import annotations

from typing import Any, Optional

from langgraph.checkpoint.base import BaseCheckpointSaver

from agents.aril_bridge import ArilSession
from agents.registry import ToolRegistry
from copilot.checkpoint.langgraph_saver import MongoLangGraphSaver
from copilot.graph.v2.builder import build_copilot_state_graph
from copilot.store.checkpoint_repository import CheckpointRepository


def compile_copilot_graph(
    *,
    db: Any = None,
    registry: Optional[ToolRegistry] = None,
    checkpoints: Optional[CheckpointRepository] = None,
    aril: Optional[ArilSession] = None,
    checkpointer: Optional[BaseCheckpointSaver] = None,
    persist_checkpoints: bool = True,
):
    """Build and compile the Copilot v2 LangGraph runtime."""
    saver = checkpointer or MongoLangGraphSaver(db)
    graph = build_copilot_state_graph(
        db=db,
        registry=registry,
        checkpoints=checkpoints,
        aril=aril,
        persist_checkpoints=persist_checkpoints,
    )
    return graph.compile(checkpointer=saver), saver
