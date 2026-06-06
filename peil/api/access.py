"""Repository-scoped access control for ARIL read APIs."""

from __future__ import annotations

from fastapi import HTTPException

from services import mongo_client

REPOS_COLLECTION = "connected_repositories"


async def assert_repository_access(user_id: str, repository_id: str) -> None:
    """Ensure the JWT user has a connected_repositories row for repository_id."""
    doc = await mongo_client.find_one(
        REPOS_COLLECTION,
        {"user_id": str(user_id), "id": str(repository_id)},
    )
    if not doc:
        raise HTTPException(
            status_code=403,
            detail=f"Access denied for repository {repository_id}",
        )


async def assert_repository_access_for_tests(
    user_id: str, repository_id: str, db: object
) -> None:
    """Test helper using injected fake database."""
    doc = await db[REPOS_COLLECTION].find_one(  # type: ignore[index]
        {"user_id": str(user_id), "id": str(repository_id)}
    )
    if not doc:
        raise HTTPException(
            status_code=403,
            detail=f"Access denied for repository {repository_id}",
        )
