"""Integration tests for LangGraph Copilot v2 parity with v1."""

from __future__ import annotations

import os
from typing import Any, Dict, List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agents.base_tool import BaseTool, ToolResult
from agents.context import AgentContext
from agents.registry import ToolRegistry
from copilot.api.router import _copilot_service, copilot_router
from copilot.api.service import CopilotService
from copilot.graph.v2.streaming import CopilotLangGraphRunner
from copilot.models.enums import QuestionType, StreamEventType
from copilot.store.checkpoint_repository import CheckpointRepository
from peil.api.auth import require_jwt_user
from peil.graph.builder import GraphBuilder
from peil.graph.fixtures import mr_review_capture_events, mr_review_execution
from peil.models.enums import ExecutionSource, ExecutionType
from peil.models.execution import PeilExecutionCreate
from peil.store.capture_event_repository import CaptureEventRepository
from peil.store.evidence_repository import EvidenceRepository
from peil.store.execution_repository import ExecutionRepository

EXECUTION_ID = "exec-copilot-v2"
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


@pytest.fixture
def enable_langgraph(monkeypatch):
    monkeypatch.setenv("COPILOT_LANGGRAPH_ENABLED", "true")
    monkeypatch.setenv("COPILOT_V1_FALLBACK", "true")
    from copilot.config import is_langgraph_enabled, is_v1_fallback_enabled

    is_langgraph_enabled.cache_clear()
    is_v1_fallback_enabled.cache_clear()
    yield
    is_langgraph_enabled.cache_clear()
    is_v1_fallback_enabled.cache_clear()


@pytest.mark.asyncio
async def test_langgraph_runner_forensic_question(fake_db):
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

    runner = CopilotLangGraphRunner(fake_db, registry=_stub_registry())
    events: List[dict] = []
    async for event in runner.run(state):
        events.append(event)

    assert any(e["event"] == StreamEventType.DONE.value for e in events)
    assert state.replay_bundle is not None
    assert "gitnexus_analyze" in state.response_text
    assert state.checkpoint_version >= 7


@pytest.mark.asyncio
async def test_langgraph_runner_investigate_builds_plan_without_execution(fake_db):
    await _seed_execution(fake_db)
    checkpoints = CheckpointRepository(fake_db)
    state = await checkpoints.create_conversation(
        user_id=USER_ID,
        repository_id=REPO_ID,
        execution_id=EXECUTION_ID,
    )
    state.question = "Investigate this finding further"
    state.question_type = QuestionType.INVESTIGATE_FURTHER

    runner = CopilotLangGraphRunner(fake_db, registry=_stub_registry())
    async for _ in runner.run(state):
        pass

    assert state.investigation_plan is not None
    assert len(state.investigation_plan.steps) >= 1
    assert len(state.investigation_results) >= 1


@pytest.fixture
async def copilot_v2_client(fake_db, enable_langgraph):
    await _seed_execution(fake_db)

    app = FastAPI()
    app.include_router(copilot_router)

    def _fake_user():
        return {"id": USER_ID, "username": "dev"}

    def _fake_service():
        return CopilotService(fake_db)

    app.dependency_overrides[require_jwt_user] = _fake_user
    app.dependency_overrides[_copilot_service] = _fake_service

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


def test_v2_api_create_and_ask_sse_stream(copilot_v2_client):
    create_resp = copilot_v2_client.post(
        "/api/copilot/conversations",
        json={"execution_id": EXECUTION_ID, "repository_id": REPO_ID},
        headers={"Authorization": "Bearer test-token"},
    )
    assert create_resp.status_code == 200
    conversation_id = create_resp.json()["conversation_id"]

    with copilot_v2_client.stream(
        "POST",
        f"/api/copilot/conversations/{conversation_id}/ask",
        json={
            "question": "What evidence led to this conclusion?",
            "question_type": "what_evidence",
        },
        headers={"Authorization": "Bearer test-token"},
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "event: node_started" in body
    assert "event: done" in body
    assert "event: response_chunk" in body

    checkpoint = copilot_v2_client.get(
        f"/api/copilot/conversations/{conversation_id}",
        headers={"Authorization": "Bearer test-token"},
    )
    assert checkpoint.status_code == 200
    data = checkpoint.json()
    assert data["question_type"] == "what_evidence"
    assert data["response_text"]
    assert data["checkpoint_version"] >= 1
