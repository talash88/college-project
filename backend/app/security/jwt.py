"""JWT access tokens and opaque refresh tokens.

Security notes:
- Access tokens are short-lived signed JWTs (HS256, actively-maintained
  PyJWT with the algorithm explicitly pinned — never accept attacker-chosen
  algorithms or asymmetric keys as HMAC secrets).
- Refresh tokens are opaque random values; only their SHA-256 hash is
  stored in the database. Raw token values are never logged.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from jwt import InvalidTokenError

from app.core.config import settings
from app.core.enums import UserRole

ACCESS_TOKEN_TYPE = "access"
REFRESH_COOKIE_NAME = "cx_refresh"


def create_access_token(user_id: UUID, role: UserRole, expires_minutes: int | None = None) -> str:
    expire_delta = timedelta(
        minutes=expires_minutes
        if expires_minutes is not None
        else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role.value,
        "typ": ACCESS_TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int((now + expire_delta).timestamp()),
        "jti": str(uuid4()),
    }
    encoded: str = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded


def decode_access_token(token: str) -> dict[str, str]:
    """Decode and validate an access token.

    Raises:
        ValueError: if the token is invalid, expired, or of the wrong type.
    """
    try:
        payload: dict[str, str] = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except InvalidTokenError as exc:
        raise ValueError("Invalid or expired token") from exc
    if payload.get("typ") != ACCESS_TOKEN_TYPE:
        raise ValueError("Invalid token type")
    if not payload.get("sub"):
        raise ValueError("Invalid token subject")
    return payload


def generate_refresh_token() -> str:
    """Generate a new opaque refresh token value (returned to the client once)."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """SHA-256 hash of a refresh token for database storage/lookup."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def refresh_token_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
