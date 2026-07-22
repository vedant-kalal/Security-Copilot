"""
Security primitives: password hashing and JWT token issuance/verification.
"""
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return _pwd_context.verify(plain_password, hashed_password)


def create_token(subject: UUID, token_type: TokenType, extra_claims: Optional[Dict[str, Any]] = None) -> str:
    """Create a signed JWT for the given subject (user id)."""
    settings = get_settings()
    now = datetime.now(timezone.utc)

    if token_type is TokenType.ACCESS:
        expires_delta = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    else:
        expires_delta = timedelta(minutes=settings.JWT_REFRESH_TOKEN_EXPIRE_MINUTES)

    payload: Dict[str, Any] = {
        "sub": str(subject),
        "type": token_type.value,
        "iat": now,
        "exp": now + expires_delta,
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(subject: UUID, extra_claims: Optional[Dict[str, Any]] = None) -> str:
    return create_token(subject, TokenType.ACCESS, extra_claims)


def create_refresh_token(subject: UUID) -> str:
    return create_token(subject, TokenType.REFRESH)


def decode_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT. Raises `jose.JWTError` if invalid or expired."""
    settings = get_settings()
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise exc
