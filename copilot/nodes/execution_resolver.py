"""Resolve and verify execution against repository scope."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException

from copilot.models.state import CopilotState
from peil.api.access import assert_repository_access, assert_repository_access_for_tests
from peil.store.execution_repository import ExecutionRepository


async def execution_resolver_node(
    state: CopilotState,
    *,
    db: Any = None,
) -> dict:
    if not state.execution_id:
        raise ValueError("execution_id is required")

    if db is not None:
        await assert_repository_access_for_tests(
            state.user_id, state.repository_id, db
        )
    else:
        await assert_repository_access(state.user_id, state.repository_id)

    repo = ExecutionRepository(db)
    execution = await repo.get_by_execution_id(state.execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found")

    if execution.repository_id != state.repository_id:
        raise HTTPException(
            status_code=403,
            detail="Execution does not belong to the requested repository",
        )

    return {
        "execution_id": execution.execution_id,
        "task_id": execution.task_id,
        "status": execution.status.value,
        "objective": execution.objective,
    }
