"""Authentication service: registration, login, token issuance/refresh."""
from __future__ import annotations

from uuid import UUID

from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AlreadyExistsError, InvalidCredentialsError, UnauthorizedError, ValidationError
from app.core.logging import get_logger
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenResponse
from app.utils.validators import normalize_email

logger = get_logger(__name__)


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def register(self, email: str, password: str) -> User:
        email = normalize_email(email)

        if len(password) < 8:
            raise ValidationError("Password must be at least 8 characters long")
        if not any(c.isupper() for c in password):
            raise ValidationError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in password):
            raise ValidationError("Password must contain at least one digit")

        existing = await self.users.get_by_email(email)
        if existing:
            raise AlreadyExistsError(f"An account with email '{email}' already exists")

        user = User(email=email, password_hash=hash_password(password))
        await self.users.add(user)
        await self.users.commit()
        logger.info("New user registered: %s", email)
        return user

    async def authenticate(self, email: str, password: str) -> User:
        email = normalize_email(email)
        user = await self.users.get_by_email(email)
        if not user or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError("Invalid email or password")
        return user

    def issue_tokens(self, user: User) -> TokenResponse:
        from app.core.config import get_settings

        settings = get_settings()
        access_token = create_access_token(user.id, extra_claims={"email": user.email})
        refresh_token = create_refresh_token(user.id)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def refresh(self, refresh_token: str) -> TokenResponse:
        try:
            payload = decode_token(refresh_token)
        except JWTError as exc:
            raise UnauthorizedError("Invalid or expired refresh token") from exc

        if payload.get("type") != TokenType.REFRESH.value:
            raise UnauthorizedError("Provided token is not a refresh token")

        user = await self.users.get_by_id(UUID(payload["sub"]))
        if not user:
            raise UnauthorizedError("User no longer exists")

        return self.issue_tokens(user)
