"""Data access for Step 11 in-app notifications."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


class NotificationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        recipient_user_id: UUID,
        type: str,
        title: str,
        message: str,
        problem_id: UUID | None = None,
        related_entity_type: str | None = None,
        related_entity_id: UUID | None = None,
    ) -> Notification:
        row = Notification(
            recipient_user_id=recipient_user_id,
            type=type,
            title=title,
            message=message,
            problem_id=problem_id,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def list_for_recipient(
        self, user_id: UUID, *, unread_only: bool, limit: int, offset: int
    ) -> tuple[list[Notification], int]:
        base = select(Notification).where(Notification.recipient_user_id == user_id)
        if unread_only:
            base = base.where(Notification.read_at.is_(None))
        count_result = await self.session.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = int(count_result.scalar_one())
        result = await self.session.execute(
            base.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all()), total

    async def unread_count(self, user_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.recipient_user_id == user_id,
                Notification.read_at.is_(None),
            )
        )
        return int(result.scalar_one())

    async def get_for_recipient(self, notification_id: UUID, user_id: UUID) -> Notification | None:
        result = await self.session.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.recipient_user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def mark_all_read(self, user_id: UUID) -> int:
        result = await self.session.execute(
            select(Notification).where(
                Notification.recipient_user_id == user_id,
                Notification.read_at.is_(None),
            )
        )
        rows = list(result.scalars().all())
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        for row in rows:
            row.read_at = now
        await self.session.flush()
        return len(rows)
