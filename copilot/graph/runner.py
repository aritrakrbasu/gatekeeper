"""CopilotGraph v1 async runner with SSE event emission."""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, Optional

from agents.registry import ToolRegistry
from copilot.graph.builder import linear_node_order
from copilot.models.enums import CopilotNodeName, StreamEventType
from copilot.models.state import CopilotState
from copilot.nodes.base import run_node
from copilot.nodes.evidence_retrieval import evidence_retrieval_node
from copilot.nodes.execution_resolver import execution_resolver_node
from copilot.nodes.live_investigation import live_investigation_node
from copilot.nodes.question import question_node
from copilot.nodes.question_classifier import question_classifier_node
from copilot.nodes.replay_retrieval import replay_retrieval_node
from copilot.nodes.knowledge_proposal import knowledge_proposal_node
from copilot.nodes.response_generator import response_generator_node
from copilot.store.checkpoint_repository import CheckpointRepository


class CopilotGraphRunner:
    """Executes the v1 node pipeline deterministically."""

    def __init__(
        self,
        db: Any = None,
        *,
        registry: Optional[ToolRegistry] = None,
        checkpoints: Optional[CheckpointRepository] = None,
    ) -> None:
        self._db = db
        self._registry = registry
        self._checkpoints = checkpoints or CheckpointRepository(db)

    async def run(
        self,
        state: CopilotState,
        *,
        persist_checkpoints: bool = True,
    ) -> AsyncIterator[Dict[str, Any]]:
        handlers = {
            CopilotNodeName.QUESTION: lambda s: question_node(s),
            CopilotNodeName.EXECUTION_RESOLVER: lambda s: execution_resolver_node(
                s, db=self._db
            ),
            CopilotNodeName.REPLAY_RETRIEVAL: lambda s: replay_retrieval_node(
                s, db=self._db
            ),
            CopilotNodeName.EVIDENCE_RETRIEVAL: lambda s: evidence_retrieval_node(s),
            CopilotNodeName.QUESTION_CLASSIFIER: lambda s: question_classifier_node(s),
            CopilotNodeName.LIVE_INVESTIGATION: lambda s: live_investigation_node(
                s, registry=self._registry
            ),
            CopilotNodeName.RESPONSE_GENERATOR: lambda s: response_generator_node(s),
            CopilotNodeName.KNOWLEDGE_PROPOSAL: lambda s: knowledge_proposal_node(
                s, db=self._db
            ),
        }

        for node in linear_node_order():
            if node == CopilotNodeName.LIVE_INVESTIGATION:
                if not state.live_investigation_enabled:
                    continue

            async for event in run_node(state, node, handlers[node]):
                yield event
                if event.get("event") == StreamEventType.ERROR.value:
                    return

            if persist_checkpoints:
                await self._checkpoints.save(state)

        for chunk in state.response_chunks:
            yield {
                "event": StreamEventType.RESPONSE_CHUNK.value,
                "data": {"text": chunk},
            }

        if state.proposed_assertion_ids:
            yield {
                "event": StreamEventType.KNOWLEDGE_PROPOSED.value,
                "data": {
                    "assertion_ids": state.proposed_assertion_ids,
                    "count": len(state.proposed_assertion_ids),
                },
            }

        yield {
            "event": StreamEventType.DONE.value,
            "data": {
                "conversation_id": state.conversation_id,
                "question_type": state.question_type.value,
                "response_length": len(state.response_text),
            },
        }

        if persist_checkpoints:
            await self._checkpoints.save(state)
