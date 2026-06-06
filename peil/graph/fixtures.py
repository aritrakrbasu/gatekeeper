"""Deterministic capture-event fixtures for GraphBuilder tests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from peil.models.enums import (
    CaptureEventType,
    ExecutionSource,
    ExecutionType,
    SubjectType,
)
from peil.models.events import CaptureEvent
from peil.models.execution import PeilExecution
from peil.models.subject import SubjectRef


def mr_review_execution(execution_id: str = "exec-mr-42-sample") -> PeilExecution:
    now = datetime.now(timezone.utc)
    subject_ref = SubjectRef(type=SubjectType.MR, id="42", repository_id="82576405")
    return PeilExecution(
        execution_id=execution_id,
        task_id="mr-review-sample01",
        execution_type=ExecutionType.MR_REVIEW,
        execution_source=ExecutionSource.WORKFLOW_ENGINE,
        repository_id="82576405",
        subject_ref=subject_ref,
        subject_id="mr:42:82576405",
        objective="Perform GitLab Merge Request Review for MR 42",
        partition_key="202606",
        created_at=now,
        updated_at=now,
    )


def mr_review_capture_events(execution_id: str = "exec-mr-42-sample") -> List[CaptureEvent]:
    """Realistic MR review capture sequence aligned with runtime integration."""
    base = datetime(2026, 6, 6, 10, 0, 0, tzinfo=timezone.utc)
    task_id = "mr-review-sample01"

    def ev(seq: int, event_type: CaptureEventType, payload: dict) -> CaptureEvent:
        return CaptureEvent(
            execution_id=execution_id,
            task_id=task_id,
            event_type=event_type,
            sequence=seq,
            timestamp=base.replace(second=seq),
            payload=payload,
        )

    return [
        ev(
            1,
            CaptureEventType.EXECUTION_STARTED,
            {
                "task_id": task_id,
                "objective": "Perform GitLab Merge Request Review for MR 42",
                "trigger_type": "gitlab_mr",
                "execution_type": ExecutionType.MR_REVIEW.value,
                "repository_id": "82576405",
                "subject_id": "mr:42:82576405",
            },
        ),
        ev(
            2,
            CaptureEventType.MODEL_TURN,
            {
                "source": "planner",
                "prompt_hash": "a" * 64,
                "response_hash": "b" * 64,
                "token_count": 1200,
            },
        ),
        ev(
            3,
            CaptureEventType.PLAN_EMITTED,
            {
                "explanation": "Clone, analyze, diff, inspect schema, post MR comment.",
                "plan_revision": 0,
                "steps": [
                    {
                        "step_id": "clone",
                        "tool_name": "clone_repo",
                        "action": "Clone repository",
                        "reason": "Workspace required",
                        "arguments_json": "{}",
                        "dependencies": [],
                    },
                    {
                        "step_id": "analyze",
                        "tool_name": "gitnexus_analyze",
                        "action": "Run call-graph analysis",
                        "reason": "Impact surface",
                        "arguments_json": "{}",
                        "dependencies": ["clone"],
                    },
                    {
                        "step_id": "comment",
                        "tool_name": "post_gitlab_mr_comment",
                        "action": "Post review comment",
                        "reason": "Deliver findings",
                        "arguments_json": "{}",
                        "dependencies": ["analyze"],
                    },
                ],
            },
        ),
        ev(
            4,
            CaptureEventType.TOOL_INVOKED,
            {
                "tool_name": "clone_repo",
                "masked_arguments": {"repo_path": "workspace/gatekeeper"},
                "step_id": "clone",
            },
        ),
        ev(
            5,
            CaptureEventType.TOOL_COMPLETED,
            {
                "tool_name": "clone_repo",
                "result_ref": "inline:abc123",
                "duration_ms": 2100.0,
                "status": "success",
                "step_id": "clone",
            },
        ),
        ev(
            6,
            CaptureEventType.REFLECTION_EVALUATED,
            {"step_id": "clone", "passed": True},
        ),
        ev(
            7,
            CaptureEventType.TOOL_INVOKED,
            {
                "tool_name": "gitnexus_analyze",
                "masked_arguments": {"repo_path": "workspace/gatekeeper"},
                "step_id": "analyze",
            },
        ),
        ev(
            8,
            CaptureEventType.TOOL_COMPLETED,
            {
                "tool_name": "gitnexus_analyze",
                "result_ref": "inline:def456",
                "duration_ms": 5400.0,
                "status": "success",
                "step_id": "analyze",
            },
        ),
        ev(
            9,
            CaptureEventType.REFLECTION_EVALUATED,
            {"step_id": "analyze", "passed": True},
        ),
        ev(
            10,
            CaptureEventType.TOOL_INVOKED,
            {
                "tool_name": "post_gitlab_mr_comment",
                "masked_arguments": {"mr_iid": "42"},
                "step_id": "comment",
            },
        ),
        ev(
            11,
            CaptureEventType.TOOL_COMPLETED,
            {
                "tool_name": "post_gitlab_mr_comment",
                "result_ref": "inline:ghi789",
                "duration_ms": 800.0,
                "status": "success",
                "step_id": "comment",
            },
        ),
        ev(
            12,
            CaptureEventType.REFLECTION_EVALUATED,
            {"step_id": "comment", "passed": True},
        ),
        ev(
            13,
            CaptureEventType.EXECUTION_COMPLETED,
            {"status": "completed", "step_count": 3, "duration_ms": 12000.0},
        ),
    ]
