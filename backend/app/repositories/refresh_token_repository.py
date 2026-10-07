from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user_id: UUID, token_hash: str, expires_at: datetime) -> RefreshToken:
        record = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self.session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def revoke(self, record: RefreshToken, revoked_at: datetime) -> None:
        record.revoked_at = revoked_at
        await self.session.flush()

    async def revoke_all_for_user(self, user_id: UUID, revoked_at: datetime) -> int:
        result = await self.session.execute(
            select(RefreshToken).where(RefreshToken.user_id == user_id)
        )
        records = list(result.scalars().all())
        count = 0
        for record in records:
            if record.revoked_at is None:
                record.revoked_at = revoked_at
                count += 1
        if count:
            await self.session.flush()
        return count
