"""Integration tests for Copilot approval interrupt and resume."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from agents.base_tool import BaseTool, ToolResult
from agents.context import AgentContext
from agents.registry import ToolRegistry
from copilot.graph.v2.streaming import CopilotLangGraphRunner
from copilot.models.enums import QuestionType, StreamEventType
from copilot.store.checkpoint_repository import CheckpointRepository
from peil.graph.builder import GraphBuilder
from peil.graph.fixtures import mr_review_capture_events, mr_review_execution
from peil.models.enums import CaptureEventType, ExecutionSource, ExecutionType
from peil.models.execution import PeilExecutionCreate
from peil.store.capture_event_repository import CaptureEventRepository
from peil.store.evidence_repository import EvidenceRepository
from peil.store.execution_repository import ExecutionRepository

EXECUTION_ID = "exec-copilot-approval"
REPO_ID = "82576405"
USER_ID = "user-1"


class _StubTool(BaseTool):
    def __init__(self, name: str, content: Any = "ok") -> None:
        self._name = name
        self._content = content

    def get_name(self) -> str:
        return self._name

    def get_description(self) -> str:
        return f"Stub {self._name}"

    def get_schema(self) -> Dict[str, Any]:
        return {"name": self._name, "description": "stub", "parameters": {}}

    def validate(self, arguments: Dict[str, Any]) -> None:
        return None

    async def execute(
        self, arguments: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        return ToolResult(status="success", content=self._content)


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    for name in (
        "get_gitlab_mr_diffs",
        "gitnexus_analyze",
        "run_impact_analysis",
        "post_gitlab_mr_comment",
    ):
        registry.register_tool(_StubTool(name))
    return registry


async def _seed(fake_db) -> None:
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


@pytest.fixture
def enable_langgraph(monkeypatch):
    monkeypatch.setenv("COPILOT_LANGGRAPH_ENABLED", "true")
    monkeypatch.setenv("ARIL_CAPTURE_ENABLED", "true")
    from copilot.config import is_langgraph_enabled, is_v1_fallback_enabled
    from peil.config import get_aril_settings

    is_langgraph_enabled.cache_clear()
    is_v1_fallback_enabled.cache_clear()
    get_aril_settings.cache_clear()
    yield
    is_langgraph_enabled.cache_clear()
    is_v1_fallback_enabled.cache_clear()
    get_aril_settings.cache_clear()


@pytest.mark.asyncio
async def test_interrupt_and_resume_approve(fake_db, enable_langgraph, monkeypatch):
    await _seed(fake_db)
    checkpoints = CheckpointRepository(fake_db)
    state = await checkpoints.create_conversation(
        user_id=USER_ID,
        repository_id=REPO_ID,
        execution_id=EXECUTION_ID,
    )
    state.question = "Investigate this finding further"
    state.question_type = QuestionType.INVESTIGATE_FURTHER

    runner = CopilotLangGraphRunner(fake_db, registry=_registry())
    first_pass: List[dict] = []
    async for event in runner.run(state):
        first_pass.append(event)

    assert any(e["event"] == StreamEventType.APPROVAL_REQUIRED.value for e in first_pass)
    assert state.pending_approval is not None
    assert len(state.investigation_results) >= 1

    second_pass: List[dict] = []
    async for event in runner.resume(
        state,
        {"action": "approve", "actor_user_id": USER_ID},
    ):
        second_pass.append(event)

    assert any(e["event"] == StreamEventType.DONE.value for e in second_pass)
    assert state.pending_approval is None
    assert len(state.investigation_results) >= 2
    assert len(fake_db["copilot_approvals"].docs) == 1


@pytest.mark.asyncio
async def test_aril_records_approval_events(fake_db, enable_langgraph, monkeypatch):
    await _seed(fake_db)
    checkpoints = CheckpointRepository(fake_db)
    state = await checkpoints.create_conversation(
        user_id=USER_ID,
        repository_id=REPO_ID,
        execution_id=EXECUTION_ID,
    )
    state.question = "Investigate this finding further"
    state.question_type = QuestionType.INVESTIGATE_FURTHER

    runner = CopilotLangGraphRunner(fake_db, registry=_registry())
    async for event in runner.run(state):
        if event["event"] == StreamEventType.APPROVAL_REQUIRED.value:
            break

    assert state.copilot_execution_id
    copilot_exec_id = state.copilot_execution_id
    events = [
        doc
        for doc in fake_db["peil_capture_events"].docs
        if doc.get("execution_id") == copilot_exec_id
    ]
    event_types = {doc["event_type"] for doc in events}
    assert CaptureEventType.APPROVAL_REQUIRED.value in event_types

    async for _ in runner.resume(state, {"action": "reject", "actor_user_id": USER_ID}):
        pass

    event_types = {doc["event_type"] for doc in fake_db["peil_capture_events"].docs}
    assert CaptureEventType.APPROVAL_REJECTED.value in event_types
    assert CaptureEventType.APPROVAL_RESOLVED.value in event_types
