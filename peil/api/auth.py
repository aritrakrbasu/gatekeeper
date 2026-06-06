"""JWT authentication dependencies for ARIL APIs."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import Header, HTTPException

from services import auth_service


async def require_jwt_user(authorization: str = Header(None)) -> Dict[str, Any]:
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization required")
    token = (
        authorization.replace("Bearer ", "")
        if authorization.startswith("Bearer ")
        else authorization
    )
    try:
        user_info = auth_service.verify_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    user_id = user_info.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user_info
