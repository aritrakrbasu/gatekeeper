"""Resolve MR review executions for Copilot conversation creation."""

from __future__ import annotations

from typing import Any, List, Optional

from fastapi import HTTPException

from copilot.models.resolution import ExecutionLink, MrExecutionResponse
from peil.api.access import assert_repository_access, assert_repository_access_for_tests
from peil.models.enums import SubjectType
from peil.models.subject import SubjectRef, build_subject_id
from peil.store.execution_repository import ExecutionRepository
from peil.store.graph_repository import GraphRepository
from peil.store.subject_repository import SubjectRepository


def _mr_subject_ref(repository_id: str, mr_iid: int) -> SubjectRef:
    return SubjectRef(
        type=SubjectType.MR,
        id=str(mr_iid),
        repository_id=repository_id,
    )


def _mr_subject_id(repository_id: str, mr_iid: int) -> str:
    return build_subject_id(_mr_subject_ref(repository_id, mr_iid))


async def _assert_repo_access(
    user_id: str,
    repository_id: str,
    *,
    db: Any = None,
) -> None:
    if db is not None:
        await assert_repository_access_for_tests(user_id, repository_id, db)
    else:
        await assert_repository_access(user_id, repository_id)


async def _candidate_execution_ids(
    *,
    db: Any,
    repository_id: str,
    mr_iid: int,
) -> List[str]:
    subject_id = _mr_subject_id(repository_id, mr_iid)
    subject_repo = SubjectRepository(db)
    execution_repo = ExecutionRepository(db)

    ordered: List[str] = []
    seen: set[str] = set()

    def _add(execution_id: Optional[str]) -> None:
        if execution_id and execution_id not in seen:
            seen.add(execution_id)
            ordered.append(execution_id)

    subject = await subject_repo.get(subject_id)
    if subject is not None:
        _add(subject.latest_execution_id)
        for execution_id in reversed(subject.execution_ids):
            _add(execution_id)

    subject_ref = _mr_subject_ref(repository_id, mr_iid)
    for execution in await execution_repo.find_by_subject(
        repository_id,
        subject_ref,
        limit=50,
    ):
        _add(execution.execution_id)

    return ordered


async def resolve_mr_execution(
    repository_id: str,
    mr_iid: int,
    user_id: str,
    *,
    db: Any = None,
) -> ExecutionLink:
    """
    Resolve a graph-backed ARIL execution for an MR.

    Raises:
        HTTPException 403: repository access denied
        HTTPException 404: no_captured_review (missing execution or graph)
    """
    await _assert_repo_access(user_id, repository_id, db=db)

    subject_id = _mr_subject_id(repository_id, mr_iid)
    execution_repo = ExecutionRepository(db)
    graph_repo = GraphRepository(db)

    candidates = await _candidate_execution_ids(
        db=db,
        repository_id=repository_id,
        mr_iid=mr_iid,
    )
    if not candidates:
        raise HTTPException(status_code=404, detail="no_captured_review")

    for execution_id in candidates:
        execution = await execution_repo.get_by_execution_id(execution_id)
        if execution is None:
            continue
        if execution.repository_id != repository_id:
            continue

        graph = await graph_repo.get_by_execution_id(execution_id)
        if graph is None:
            continue

        status = (
            execution.status.value
            if hasattr(execution.status, "value")
            else str(execution.status)
        )
        return ExecutionLink(
            execution_id=execution.execution_id,
            graph_id=graph.graph_id,
            subject_id=subject_id,
            status=status,
            copilot_ready=True,
        )

    raise HTTPException(status_code=404, detail="no_captured_review")


async def resolve_mr_execution_response(
    repository_id: str,
    mr_iid: int,
    user_id: str,
    *,
    db: Any = None,
) -> MrExecutionResponse:
    link = await resolve_mr_execution(
        repository_id,
        mr_iid,
        user_id,
        db=db,
    )
    return MrExecutionResponse(
        repository_id=repository_id,
        mr_iid=mr_iid,
        subject_id=link.subject_id,
        execution_id=link.execution_id,
        graph_id=link.graph_id,
        status=link.status,
        copilot_ready=link.copilot_ready,
    )
