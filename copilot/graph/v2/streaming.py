"""SSE streaming adapter for LangGraph Copilot v2."""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, Optional

from langgraph.errors import GraphInterrupt
from langgraph.types import Command

from agents.aril_bridge import ArilSession, bootstrap_copilot_execution
from agents.registry import ToolRegistry
from copilot.aril.capture import finalize_copilot_execution
from copilot.graph.v2.compile import compile_copilot_graph
from copilot.graph.v2.state import copilot_from_graph_state, graph_input_from_copilot
from copilot.models.enums import StreamEventType
from copilot.models.state import CopilotState
from copilot.store.checkpoint_repository import CheckpointRepository


class CopilotLangGraphRunner:
    """Checkpointed LangGraph runtime with interrupt/resume support."""

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
        self._compiled = None
        self._checkpointer = None
        self._aril: Optional[ArilSession] = None

    def _ensure_compiled(self, aril: Optional[ArilSession] = None):
        if self._compiled is None or aril is not self._aril:
            self._aril = aril
            self._compiled, self._checkpointer = compile_copilot_graph(
                db=self._db,
                registry=self._registry,
                checkpoints=self._checkpoints,
                aril=aril,
            )

    async def _ensure_aril(self, state: CopilotState) -> Optional[ArilSession]:
        if state.copilot_execution_id and self._aril is not None:
            return self._aril
        session = await bootstrap_copilot_execution(
            conversation_id=state.conversation_id,
            user_id=state.user_id,
            repository_id=state.repository_id,
            linked_execution_id=state.execution_id,
            objective=state.question,
            db=self._db,
        )
        if session is not None:
            state.copilot_execution_id = session.execution_id
            self._aril = session
            if self._registry is not None:
                self._registry.attach_aril(session)
        return session

    async def run(
        self,
        state: CopilotState,
        *,
        persist_checkpoints: bool = True,
        fresh_thread: bool = True,
    ) -> AsyncIterator[Dict[str, Any]]:
        aril = await self._ensure_aril(state)
        self._ensure_compiled(aril)

        if fresh_thread:
            await self._checkpointer.adelete_thread(state.conversation_id)
            state.plan_step_cursor = 0
            state.pending_approval = None
            state.approval_resume = None
            state.interrupted = False
            state.interrupt_payload = None

        graph_input = graph_input_from_copilot(state)
        config = {
            "configurable": {
                "thread_id": state.conversation_id,
                "execution_id": state.copilot_execution_id or state.execution_id,
            }
        }

        async for event in self._stream_graph(
            graph_input,
            config,
            state=state,
            persist_checkpoints=persist_checkpoints,
            aril=aril,
            paused_ok=False,
        ):
            yield event

    async def resume(
        self,
        state: CopilotState,
        resume_payload: Dict[str, Any],
        *,
        persist_checkpoints: bool = True,
    ) -> AsyncIterator[Dict[str, Any]]:
        aril = await self._ensure_aril(state)
        self._ensure_compiled(aril)

        config = {
            "configurable": {
                "thread_id": state.conversation_id,
                "execution_id": state.copilot_execution_id or state.execution_id,
            }
        }
        resume_value = {
            **resume_payload,
            "actor_user_id": resume_payload.get("actor_user_id", state.user_id),
        }

        async for event in self._stream_graph(
            Command(resume=resume_value),
            config,
            state=state,
            persist_checkpoints=persist_checkpoints,
            aril=aril,
            paused_ok=True,
        ):
            yield event

    async def _stream_graph(
        self,
        graph_input: Any,
        config: dict,
        *,
        state: CopilotState,
        persist_checkpoints: bool,
        aril: Optional[ArilSession],
        paused_ok: bool,
    ) -> AsyncIterator[Dict[str, Any]]:
        final_copilot: Optional[CopilotState] = None
        interrupted = False

        try:
            async for chunk in self._compiled.astream(
                graph_input,
                config,
                stream_mode="updates",
            ):
                if not isinstance(chunk, dict):
                    continue
                for _node_name, update in chunk.items():
                    if not isinstance(update, dict):
                        continue
                    for event in update.get("sse_events", []):
                        yield event
                        if event.get("event") == StreamEventType.ERROR.value:
                            return
                    if "copilot" in update:
                        final_copilot = CopilotState.model_validate(update["copilot"])
                    if update.get("halted"):
                        return
        except GraphInterrupt:
            interrupted = True

        if final_copilot is None:
            final_copilot = await self._load_copilot_from_checkpoint(config, state)

        snapshot = await self._compiled.aget_state(config)
        interrupt_values = list(getattr(snapshot, "interrupts", None) or [])
        if not interrupt_values and interrupted and final_copilot.interrupt_payload:
            interrupt_values = [final_copilot.interrupt_payload]
        if not interrupt_values and final_copilot.pending_approval:
            interrupt_values = [final_copilot.pending_approval]
            interrupted = True
        if interrupt_values:
            for intr in interrupt_values:
                payload = intr.value if hasattr(intr, "value") else intr
                yield {
                    "event": StreamEventType.APPROVAL_REQUIRED.value,
                    "data": payload if isinstance(payload, dict) else {"value": payload},
                }
                yield {
                    "event": StreamEventType.INTERRUPTED.value,
                    "data": {
                        "conversation_id": state.conversation_id,
                        "thread_id": state.conversation_id,
                        "execution_id": state.copilot_execution_id,
                    },
                }
            if aril is not None:
                await finalize_copilot_execution(aril, status="paused", db=self._db)
            if final_copilot is not None:
                self._sync_state(state, final_copilot)
            if persist_checkpoints:
                await self._checkpoints.save(state)
            return

        if final_copilot is None:
            final_copilot = await self._load_copilot_from_checkpoint(config, state)

        for chunk in final_copilot.response_chunks:
            yield {
                "event": StreamEventType.RESPONSE_CHUNK.value,
                "data": {"text": chunk},
            }

        if final_copilot.proposed_assertion_ids:
            yield {
                "event": StreamEventType.KNOWLEDGE_PROPOSED.value,
                "data": {
                    "assertion_ids": final_copilot.proposed_assertion_ids,
                    "count": len(final_copilot.proposed_assertion_ids),
                },
            }

        yield {
            "event": StreamEventType.DONE.value,
            "data": {
                "conversation_id": final_copilot.conversation_id,
                "question_type": final_copilot.question_type.value,
                "response_length": len(final_copilot.response_text),
                "interrupted": interrupted,
            },
        }

        self._sync_state(state, final_copilot)
        if persist_checkpoints:
            await self._checkpoints.save(final_copilot)

        if aril is not None and not interrupted:
            await finalize_copilot_execution(aril, status="completed", db=self._db)

    async def _load_copilot_from_checkpoint(
        self,
        config: dict,
        fallback: CopilotState,
    ) -> CopilotState:
        checkpoint = await self._checkpointer.aget_tuple(config)
        if checkpoint is not None:
            channel_values = checkpoint.checkpoint.get("channel_values", {})
            if "copilot" in channel_values:
                return copilot_from_graph_state(
                    {
                        "copilot": channel_values["copilot"],
                        "sse_events": [],
                        "halted": channel_values.get("halted", False),
                    }
                )
        return fallback

    @staticmethod
    def _sync_state(target: CopilotState, source: CopilotState) -> None:
        for field_name in CopilotState.model_fields:
            setattr(target, field_name, getattr(source, field_name))
