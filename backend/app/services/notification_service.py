"""Centralized in-app NotificationService (Step 11).

All notification creation goes through here — services never insert
Notification rows directly. Content is restricted to safe display text
(ticket numbers, short titles): never internal discussion, private files,
or workload data.

Transactional strategy: Step 11 core flows (submit/review/verify/close)
create notifications inside the SAME database transaction as the state
change, so a notification failure rolls everything back instead of
leaving e.g. RESOLVED status with released workloads but no audit trail.
Hooks into older flows (assignment, tasks) notify best-effort AFTER the
core commit so a notification hiccup can never break them.
"""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import NotificationType
from app.models.assignment import ProblemAssignment
from app.models.notification import Notification
from app.models.problem import Problem
from app.repositories.notification_repository import NotificationRepository

logger = logging.getLogger(__name__)

TITLE_MAX = 200
MESSAGE_MAX = 1000


class NotificationService:
    """The working in-app NotificationProvider."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = NotificationRepository(session)

    async def notify_user(
        self,
        recipient_user_id: UUID,
        type: NotificationType,
        title: str,
        message: str,
        *,
        problem_id: UUID | None = None,
        related_entity_type: str | None = None,
        related_entity_id: UUID | None = None,
    ) -> Notification:
        return await self.repo.create(
            recipient_user_id=recipient_user_id,
            type=type.value,
            title=title.strip()[:TITLE_MAX],
            message=message.strip()[:MESSAGE_MAX],
            problem_id=problem_id,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
        )

    async def notify_team(
        self,
        assignment: ProblemAssignment,
        type: NotificationType,
        title: str,
        message: str,
        *,
        problem_id: UUID,
        exclude_user_id: UUID | None = None,
        related_entity_type: str | None = None,
        related_entity_id: UUID | None = None,
    ) -> list[Notification]:
        created: list[Notification] = []
        for member in assignment.team.members:
            if not member.is_active:
                continue
            if exclude_user_id is not None and member.user_id == exclude_user_id:
                continue
            created.append(
                await self.notify_user(
                    member.user_id,
                    type,
                    title,
                    message,
                    problem_id=problem_id,
                    related_entity_type=related_entity_type,
                    related_entity_id=related_entity_id,
                )
            )
        return created

    async def notify_mentor(
        self,
        assignment: ProblemAssignment,
        type: NotificationType,
        title: str,
        message: str,
        *,
        problem_id: UUID,
        related_entity_type: str | None = None,
        related_entity_id: UUID | None = None,
    ) -> Notification:
        return await self.notify_user(
            assignment.mentor_user_id,
            type,
            title,
            message,
            problem_id=problem_id,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
        )

    async def notify_reporter(
        self,
        problem: Problem,
        type: NotificationType,
        title: str,
        message: str,
        *,
        related_entity_type: str | None = None,
        related_entity_id: UUID | None = None,
    ) -> Notification:
        return await self.notify_user(
            problem.reporter_id,
            type,
            title,
            message,
            problem_id=problem.id,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
        )

    # ---------- read helpers for APIs ----------

    async def list_for_user(
        self, user_id: UUID, *, unread_only: bool, limit: int, offset: int
    ) -> tuple[list[Notification], int]:
        return await self.repo.list_for_recipient(
            user_id, unread_only=unread_only, limit=limit, offset=offset
        )

    async def unread_count(self, user_id: UUID) -> int:
        return await self.repo.unread_count(user_id)
