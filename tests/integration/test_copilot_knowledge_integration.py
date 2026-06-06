"""Integration test: CopilotGraph proposes knowledge assertions."""

import pytest

from agents.base_tool import BaseTool, ToolResult
from agents.context import AgentContext
from agents.registry import ToolRegistry
from copilot.graph.runner import CopilotGraphRunner
from copilot.models.enums import QuestionType, StreamEventType
from copilot.store.checkpoint_repository import CheckpointRepository
from knowledge.models.enums import AssertionStatus
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
    def __init__(self, name: str) -> None:
        self._name = name

    def get_name(self) -> str:
        return self._name

    def get_description(self) -> str:
        return "stub"

    def get_schema(self):
        return {"name": self._name, "parameters": {}}

    def validate(self, arguments):
        return None

    async def execute(self, arguments, context: AgentContext) -> ToolResult:
        return ToolResult(status="success", content={"ok": True})


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
    for suffix, payload in [("abc123", b'{"cloned": true}')]:
        await evidence_repo._persist_inline_blob(
            content_hash=suffix,
            execution_id=EXECUTION_ID,
            payload=payload,
            content_type="application/json",
            metadata={"execution_id": EXECUTION_ID},
        )
    await GraphBuilder(fake_db).build_and_persist(EXECUTION_ID)


@pytest.mark.asyncio
async def test_copilot_proposes_knowledge_assertions(fake_db):
    await _seed(fake_db)
    checkpoints = CheckpointRepository(fake_db)
    state = await checkpoints.create_conversation(
        user_id=USER_ID,
        repository_id=REPO_ID,
        execution_id=EXECUTION_ID,
    )
    state.question = "Why was gitnexus_analyze tool called?"
    state.question_type = QuestionType.WHY_TOOL_CALLED
    state.focus_step_id = "analyze"

    registry = ToolRegistry()
    registry.register_tool(_StubTool("get_gitlab_mr_diffs"))

    runner = CopilotGraphRunner(fake_db, registry=registry)
    events = []
    async for event in runner.run(state):
        events.append(event)

    assert state.proposed_assertion_ids
    assert any(e["event"] == StreamEventType.KNOWLEDGE_PROPOSED.value for e in events)

    assertion_repo = AssertionRepository(fake_db)
    stored = await assertion_repo.get_by_id(state.proposed_assertion_ids[0])
    assert stored is not None
    assert stored.status == AssertionStatus.PROPOSED
    assert stored.graph_id is not None
    assert stored.replay_reference == f"replay:{EXECUTION_ID}"
