"""Authentication business logic: registration, login, refresh rotation, logout."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import UserRole
from app.models.user import User
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate
from app.security.jwt import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    refresh_token_expiry,
)
from app.services.security import hash_password, verify_password

PUBLIC_REGISTRATION_ROLES = frozenset({UserRole.REPORTER, UserRole.SOLVER})
KNOWN_ROLES = frozenset({UserRole.REPORTER, UserRole.SOLVER, UserRole.MENTOR, UserRole.ADMIN})


class AuthError(Exception):
    """Domain error carrying an HTTP status code and safe client message."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.refresh_repo = RefreshTokenRepository(session)

    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().lower()

    async def register(
        self, full_name: str, email: str, password: str, role: str
    ) -> tuple[User, TokenPair]:
        name = full_name.strip()
        if not name:
            raise AuthError(422, "Full name is required")
        normalized = self.normalize_email(email)

        try:
            requested_role = UserRole(role)
        except ValueError:
            raise AuthError(422, "Invalid role") from None
        if requested_role not in KNOWN_ROLES:
            raise AuthError(422, "Invalid role")
        if requested_role not in PUBLIC_REGISTRATION_ROLES:
            raise AuthError(403, f"{requested_role.value} registration is not allowed publicly")

        existing = await self.user_repo.get_by_email(normalized)
        if existing is not None:
            raise AuthError(409, "Email already registered")

        user_data = UserCreate(
            full_name=name, email=normalized, password=password, role=requested_role.value
        )
        try:
            user = await self.user_repo.create(user_data, hash_password(password))
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AuthError(409, "Email already registered") from exc

        pair = await self._issue_pair(user)
        await self.session.commit()
        return user, pair

    async def authenticate(self, email: str, password: str) -> tuple[User, TokenPair]:
        normalized = self.normalize_email(email)
        user = await self.user_repo.get_by_email(normalized)
        if user is None or not verify_password(password, user.password_hash):
            raise AuthError(401, "Invalid email or password")
        if not user.is_active:
            raise AuthError(403, "Account is inactive")
        pair = await self._issue_pair(user)
        await self.session.commit()
        return user, pair

    async def refresh(self, raw_refresh_token: str) -> tuple[User, TokenPair]:
        record = await self.refresh_repo.get_by_hash(hash_refresh_token(raw_refresh_token))
        now = datetime.now(UTC)
        if record is None or record.revoked_at is not None or record.expires_at <= now:
            raise AuthError(401, "Invalid or expired refresh token")
        user = await self.user_repo.get_by_id(record.user_id)
        if user is None or not user.is_active:
            raise AuthError(401, "Invalid or expired refresh token")
        # Rotation: revoke the presented token, then issue a fresh pair.
        await self.refresh_repo.revoke(record, now)
        pair = await self._issue_pair(user)
        await self.session.commit()
        return user, pair

    async def logout(self, raw_refresh_token: str | None) -> None:
        if raw_refresh_token:
            record = await self.refresh_repo.get_by_hash(hash_refresh_token(raw_refresh_token))
            if record is not None and record.revoked_at is None:
                await self.refresh_repo.revoke(record, datetime.now(UTC))
                await self.session.commit()

    async def logout_all(self, user_id: UUID) -> int:
        count = await self.refresh_repo.revoke_all_for_user(user_id, datetime.now(UTC))
        await self.session.commit()
        return count

    async def _issue_pair(self, user: User) -> TokenPair:
        raw = generate_refresh_token()
        await self.refresh_repo.create(user.id, hash_refresh_token(raw), refresh_token_expiry())
        await self.session.flush()
        return TokenPair(
            access_token=create_access_token(user.id, UserRole(user.role)),
            refresh_token=raw,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
