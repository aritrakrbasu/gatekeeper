"""Integration tests for Copilot knowledge routing and investigation planning."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from agents.base_tool import BaseTool, ToolResult
from agents.context import AgentContext
from agents.registry import ToolRegistry
from copilot.graph.v2.routing import should_plan_investigation
from copilot.graph.v2.streaming import CopilotLangGraphRunner
from copilot.models.enums import QuestionType, StreamEventType
from copilot.store.checkpoint_repository import CheckpointRepository, COLLECTION
from knowledge.models.assertion import KnowledgeAssertionCreate
from knowledge.models.enums import AssertionType
from knowledge.store.assertion_repository import AssertionRepository
from peil.graph.builder import GraphBuilder
from peil.graph.fixtures import mr_review_capture_events, mr_review_execution
from peil.models.enums import ExecutionSource, ExecutionType
from peil.models.execution import PeilExecutionCreate
from peil.store.capture_event_repository import CaptureEventRepository
from peil.store.evidence_repository import EvidenceRepository
from peil.store.execution_repository import ExecutionRepository

EXECUTION_ID = "exec-copilot-knowledge"
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
    for name in (
        "get_gitlab_mr_diffs",
        "gitnexus_analyze",
        "run_impact_analysis",
        "run_schema_inspection",
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

    repo = AssertionRepository(fake_db)
    assertion = await repo.propose(
        KnowledgeAssertionCreate(
            repository_id=REPO_ID,
            source_execution_id=EXECUTION_ID,
            type=AssertionType.REPOSITORY_PATTERN,
            statement="gitnexus_analyze establishes impact surface before MR comments",
        ),
        proposed_by_user_id=USER_ID,
    )
    await repo.accept(assertion.assertion_id, actor_user_id="reviewer-1")


@pytest.mark.asyncio
async def test_knowledge_manifest_persisted_on_turn(fake_db):
    await _seed(fake_db)
    checkpoints = CheckpointRepository(fake_db)
    state = await checkpoints.create_conversation(
        user_id=USER_ID,
        repository_id=REPO_ID,
        execution_id=EXECUTION_ID,
    )
    state.question = "What evidence led to this conclusion?"
    state.question_type = QuestionType.WHAT_EVIDENCE

    runner = CopilotLangGraphRunner(fake_db, registry=_stub_registry())
    async for _ in runner.run(state):
        pass

    doc = await fake_db[COLLECTION].find_one({"conversation_id": state.conversation_id})
    assert doc["knowledge_manifest"]
    assert doc["knowledge_manifest"]["assertion_count"] >= 1
    assert "[knowledge:" in state.response_text
    execution = await ExecutionRepository(fake_db).get_by_execution_id(EXECUTION_ID)
    assert execution.knowledge_manifest


@pytest.mark.asyncio
async def test_investigation_plan_emitted_without_tool_execution(fake_db):
    await _seed(fake_db)
    checkpoints = CheckpointRepository(fake_db)
    state = await checkpoints.create_conversation(
        user_id=USER_ID,
        repository_id=REPO_ID,
        execution_id=EXECUTION_ID,
    )
    state.question = "Investigate this finding further"
    state.question_type = QuestionType.INVESTIGATE_FURTHER

    runner = CopilotLangGraphRunner(fake_db, registry=_stub_registry())
    events: List[dict] = []
    async for event in runner.run(state):
        events.append(event)

    assert any(e["event"] == StreamEventType.DONE.value for e in events)
    assert state.investigation_plan is not None
    assert len(state.investigation_plan.steps) >= 1
    assert len(state.investigation_results) >= 1
    assert state.pending_approval is not None or state.plan_step_cursor >= 1
