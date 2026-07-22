"""Shared FastAPI dependencies: DB session injection and JWT authentication."""
from __future__ import annotations

from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import UnauthorizedError
from app.core.security import TokenType, decode_token
from app.models.user import User
from app.repositories.user_repository import UserRepository

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the authenticated user from the `Authorization: Bearer <token>` header."""
    if credentials is None:
        raise UnauthorizedError("Missing authentication token")

    try:
        payload = decode_token(credentials.credentials)
    except JWTError as exc:
        raise UnauthorizedError("Invalid or expired access token") from exc

    if payload.get("type") != TokenType.ACCESS.value:
        raise UnauthorizedError("Provided token is not an access token")

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(UUID(payload["sub"]))
    if user is None:
        raise UnauthorizedError("User no longer exists")

    return user


CurrentUser = Depends(get_current_user)
DbSession = Depends(get_db)
