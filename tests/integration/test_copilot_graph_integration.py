"""Integration tests for CopilotGraphRunner."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from agents.base_tool import BaseTool, ToolResult
from agents.context import AgentContext
from agents.registry import ToolRegistry
from copilot.graph.runner import CopilotGraphRunner
from copilot.models.enums import QuestionType, StreamEventType
from copilot.models.state import CopilotState
from copilot.store.checkpoint_repository import CheckpointRepository
from peil.graph.builder import GraphBuilder
from peil.graph.fixtures import mr_review_capture_events, mr_review_execution
from peil.models.enums import ExecutionSource, ExecutionType
from peil.models.execution import PeilExecutionCreate
from peil.store.capture_event_repository import CaptureEventRepository
from peil.store.evidence_repository import EvidenceRepository
from peil.store.execution_repository import ExecutionRepository

EXECUTION_ID = "exec-copilot-graph"
REPO_ID = "82576405"
USER_ID = "user-1"


class _StubTool(BaseTool):
    def __init__(self, name: str, content: Any = "ok") -> None:
        self._name = name
        self._content = content

    def get_name(self) -> str:
        return self._name

    def get_description(self) -> str:
        return f"Stub tool {self._name}"

    def get_schema(self) -> Dict[str, Any]:
        return {"name": self._name, "description": "stub", "parameters": {}}

    def validate(self, arguments: Dict[str, Any]) -> None:
        return None

    async def execute(
        self, arguments: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        return ToolResult(status="success", content=self._content)


def _stub_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register_tool(_StubTool("get_gitlab_mr_diffs", {"diffs": []}))
    registry.register_tool(_StubTool("gitnexus_analyze", {"graph": "ok"}))
    return registry


async def _seed_execution(fake_db) -> None:
    fake_db["connected_repositories"].docs.append(
        {"user_id": USER_ID, "id": REPO_ID, "name": "gatekeeper"}
    )
    execution = mr_review_execution(EXECUTION_ID)
    await ExecutionRepository(fake_db).create(
        PeilExecutionCreate(
            execution_id=execution.execution_id,
            task_id=execution.task_id,
            execution_type=ExecutionType.MR_REVIEW,
            execution_source=ExecutionSource.WORKFLOW_ENGINE,
            repository_id=execution.repository_id,
            subject_ref=execution.subject_ref,
            subject_id=execution.subject_id,
            objective=execution.objective,
        )
    )
    await CaptureEventRepository(fake_db).append_events(
        mr_review_capture_events(EXECUTION_ID)
    )
    evidence_repo = EvidenceRepository(fake_db)
    for suffix, payload in [
        ("abc123", b'{"cloned": true}'),
        ("def456", b'{"findings": 2}'),
        ("ghi789", b'{"comment_id": 99}'),
    ]:
        await evidence_repo._persist_inline_blob(
            content_hash=suffix,
            execution_id=EXECUTION_ID,
            payload=payload,
            content_type="application/json",
            metadata={"execution_id": EXECUTION_ID},
        )
    await GraphBuilder(fake_db).build_and_persist(EXECUTION_ID)


@pytest.mark.asyncio
async def test_copilot_graph_forensic_question(fake_db):
    await _seed_execution(fake_db)
    checkpoints = CheckpointRepository(fake_db)
    state = await checkpoints.create_conversation(
        user_id=USER_ID,
        repository_id=REPO_ID,
        execution_id=EXECUTION_ID,
    )
    state.question = "Why was gitnexus_analyze tool called?"
    state.question_type = QuestionType.WHY_TOOL_CALLED
    state.focus_step_id = "analyze"

    runner = CopilotGraphRunner(fake_db, registry=_stub_registry())
    events: List[dict] = []
    async for event in runner.run(state):
        events.append(event)

    assert any(e["event"] == StreamEventType.DONE.value for e in events)
    assert state.replay_bundle is not None
    assert "gitnexus_analyze" in state.response_text
    assert state.question_type == QuestionType.WHY_TOOL_CALLED
    assert state.checkpoint_version >= 7


@pytest.mark.asyncio
async def test_copilot_graph_investigate_runs_live_tools(fake_db):
    await _seed_execution(fake_db)
    checkpoints = CheckpointRepository(fake_db)
    state = await checkpoints.create_conversation(
        user_id=USER_ID,
        repository_id=REPO_ID,
        execution_id=EXECUTION_ID,
    )
    state.question = "Investigate this finding further"
    state.question_type = QuestionType.INVESTIGATE_FURTHER

    runner = CopilotGraphRunner(fake_db, registry=_stub_registry())
    async for _ in runner.run(state):
        pass

    assert len(state.investigation_results) >= 1
    assert "Live investigation" in state.response_text


@pytest.mark.asyncio
async def test_copilot_graph_assertion_conflict(fake_db):
    await _seed_execution(fake_db)
    state = CopilotState(
        conversation_id="conv-assert",
        user_id=USER_ID,
        repository_id=REPO_ID,
        execution_id=EXECUTION_ID,
        question="The finding is wrong without evidence",
    )

    runner = CopilotGraphRunner(fake_db, registry=_stub_registry(), checkpoints=CheckpointRepository(fake_db))
    async for _ in runner.run(state, persist_checkpoints=False):
        pass

    assert state.user_assertions_detected
    assert state.question_type in {
        QuestionType.IS_FINDING_CORRECT,
        QuestionType.UNKNOWN,
    }
    assert state.counter_evidence or state.assertion_conflicts
