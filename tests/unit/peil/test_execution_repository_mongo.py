"""Tests for Peil execution repository Mongo deserialization."""

from __future__ import annotations

from datetime import datetime, timezone

from peil.models.enums import ExecutionSource, ExecutionStatus, ExecutionType, OutcomeProfile
from peil.models.subject import SubjectRef
from peil.store.execution_repository import _execution_from_mongo


def test_execution_from_mongo_coerces_datetime_completed_at():
    doc = {
        "execution_id": "exec-1",
        "task_id": "task-1",
        "execution_type": ExecutionType.MR_REVIEW.value,
        "execution_source": ExecutionSource.WORKFLOW_ENGINE.value,
        "repository_id": "82677447",
        "subject_ref": {
            "type": "mr",
            "id": "3",
            "repository_id": "82677447",
        },
        "subject_id": "mr:3:82677447",
        "objective": "Review MR",
        "status": ExecutionStatus.FAILED.value,
        "outcome_profile": OutcomeProfile.NONE.value,
        "partition_key": "82677447",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "completed_at": datetime(2026, 6, 6, 18, 21, 15, 783000, tzinfo=timezone.utc),
    }

    execution = _execution_from_mongo(doc)

    assert isinstance(execution.completed_at, str)
    assert execution.completed_at.startswith("2026-06-06")
