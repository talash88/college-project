from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import ClassificationStatus, ProblemEventType, ProblemStatus
from app.models.problem import (
    Problem,
    ProblemActivity,
    ProblemAttachment,
    ProblemComment,
    TicketCounter,
)
from app.models.problem_classification import ProblemClassification
from app.models.user import User


class ProblemRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, problem_id: UUID) -> Problem | None:
        result = await self.session.execute(
            select(Problem)
            .options(
                selectinload(Problem.reporter),
                selectinload(Problem.attachments),
                selectinload(Problem.activities),
                selectinload(Problem.comments).selectinload(ProblemComment.author),
                selectinload(Problem.classifications),
            )
            .where(Problem.id == problem_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        ticket_number: str,
        title: str,
        description: str,
        reporter_id: UUID,
        location_text: str,
        building: str | None,
        area: str | None,
        affected_people_count: int | None,
    ) -> Problem:
        problem = Problem(
            ticket_number=ticket_number,
            title=title,
            description=description,
            reporter_id=reporter_id,
            location_text=location_text,
            building=building,
            area=area,
            affected_people_count=affected_people_count,
            status=ProblemStatus.SUBMITTED,
        )
        self.session.add(problem)
        await self.session.flush()
        return problem

    async def get_by_ticket(self, ticket_number: str) -> Problem | None:
        result = await self.session.execute(
            select(Problem).where(Problem.ticket_number == ticket_number)
        )
        return result.scalar_one_or_none()

    def _apply_common_filters(
        self,
        stmt: Select[Problem],
        *,
        status: ProblemStatus | None,
        search: str | None,
    ) -> Select[Problem]:
        if status is not None:
            stmt = stmt.where(Problem.status == status)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Problem.ticket_number.ilike(like),
                    Problem.title.ilike(like),
                    Problem.description.ilike(like),
                )
            )
        return stmt

    async def list_for_reporter(
        self,
        reporter_id: UUID,
        *,
        skip: int,
        limit: int,
        status: ProblemStatus | None,
        search: str | None,
        newest_first: bool,
    ) -> tuple[list[Problem], int]:
        stmt = select(Problem).where(Problem.reporter_id == reporter_id)
        stmt = self._apply_common_filters(stmt, status=status, search=search)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()
        order = Problem.created_at.desc() if newest_first else Problem.created_at.asc()
        result = await self.session.execute(stmt.order_by(order).offset(skip).limit(limit))
        return list(result.scalars().all()), total

    async def count_by_status(self, reporter_id: UUID) -> dict[str, int]:
        result = await self.session.execute(
            select(Problem.status, func.count())
            .where(Problem.reporter_id == reporter_id)
            .group_by(Problem.status)
        )
        return {str(status): count for status, count in result.all()}

    async def admin_list(
        self,
        *,
        skip: int,
        limit: int,
        status: ProblemStatus | None,
        reporter_id: UUID | None,
        search: str | None,
        date_from: datetime | None,
        date_to: datetime | None,
        min_affected: int | None,
        max_affected: int | None,
        newest_first: bool,
    ) -> tuple[list[Problem], int]:
        stmt = select(Problem).options(selectinload(Problem.reporter))
        stmt = self._apply_common_filters(stmt, status=status, search=search)
        if reporter_id is not None:
            stmt = stmt.where(Problem.reporter_id == reporter_id)
        if date_from is not None:
            stmt = stmt.where(Problem.created_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(Problem.created_at <= date_to)
        if min_affected is not None:
            stmt = stmt.where(Problem.affected_people_count >= min_affected)
        if max_affected is not None:
            stmt = stmt.where(Problem.affected_people_count <= max_affected)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()
        order = Problem.created_at.desc() if newest_first else Problem.created_at.asc()
        result = await self.session.execute(stmt.order_by(order).offset(skip).limit(limit))
        return list(result.scalars().all()), total


class TicketCounterRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def next_number(self, year: int) -> int:
        """Atomically increment and return the per-year counter (row-locked)."""
        result = await self.session.execute(
            select(TicketCounter).where(TicketCounter.year == year).with_for_update()
        )
        counter = result.scalar_one_or_none()
        if counter is None:
            counter = TicketCounter(year=year, last_number=0)
            self.session.add(counter)
            await self.session.flush()
        counter.last_number += 1
        await self.session.flush()
        return counter.last_number


class AttachmentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        problem_id: UUID,
        original_filename: str,
        stored_filename: str,
        mime_type: str,
        size_bytes: int,
        uploaded_by: UUID,
    ) -> ProblemAttachment:
        attachment = ProblemAttachment(
            problem_id=problem_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            uploaded_by=uploaded_by,
        )
        self.session.add(attachment)
        await self.session.flush()
        return attachment

    async def get(self, attachment_id: UUID) -> ProblemAttachment | None:
        result = await self.session.execute(
            select(ProblemAttachment).where(ProblemAttachment.id == attachment_id)
        )
        return result.scalar_one_or_none()

    async def list_for_problem(self, problem_id: UUID) -> list[ProblemAttachment]:
        result = await self.session.execute(
            select(ProblemAttachment)
            .where(ProblemAttachment.problem_id == problem_id)
            .order_by(ProblemAttachment.created_at.asc())
        )
        return list(result.scalars().all())

    async def count_for_problem(self, problem_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(ProblemAttachment)
            .where(ProblemAttachment.problem_id == problem_id)
        )
        return result.scalar_one()

    async def delete(self, attachment: ProblemAttachment) -> None:
        await self.session.delete(attachment)
        await self.session.flush()


class ActivityRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log(
        self,
        *,
        problem_id: UUID,
        event_type: ProblemEventType,
        actor_user_id: UUID | None,
        old_status: str | None = None,
        new_status: str | None = None,
        message: str | None = None,
    ) -> ProblemActivity:
        activity = ProblemActivity(
            problem_id=problem_id,
            event_type=event_type,
            actor_user_id=actor_user_id,
            old_status=old_status,
            new_status=new_status,
            message=message,
        )
        self.session.add(activity)
        await self.session.flush()
        return activity

    async def list_for_problem(self, problem_id: UUID) -> list[ProblemActivity]:
        result = await self.session.execute(
            select(ProblemActivity)
            .where(ProblemActivity.problem_id == problem_id)
            .order_by(ProblemActivity.created_at.asc())
        )
        return list(result.scalars().all())


class CommentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, *, problem_id: UUID, author_id: UUID, content: str, is_internal: bool
    ) -> ProblemComment:
        comment = ProblemComment(
            problem_id=problem_id, author_id=author_id, content=content, is_internal=is_internal
        )
        self.session.add(comment)
        await self.session.flush()
        return comment

    async def list_for_problem(
        self, problem_id: UUID, *, include_internal: bool
    ) -> list[ProblemComment]:
        stmt = (
            select(ProblemComment)
            .options(selectinload(ProblemComment.author))
            .where(ProblemComment.problem_id == problem_id)
        )
        if not include_internal:
            stmt = stmt.where(ProblemComment.is_internal.is_(False))
        result = await self.session.execute(stmt.order_by(ProblemComment.created_at.asc()))
        return list(result.scalars().all())


def reporter_summary(user: User | None) -> dict[str, object] | None:
    if user is None:
        return None
    return {"id": user.id, "full_name": user.full_name, "role": user.role}


class ClassificationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        problem_id: UUID,
        predicted_category: str | None,
        confidence: float | None,
        model_name: str,
        model_version: str,
        status: ClassificationStatus,
        requires_manual_review: bool,
        classified_at: datetime | None,
    ) -> ProblemClassification:
        row = ProblemClassification(
            problem_id=problem_id,
            predicted_category=predicted_category,
            confidence=confidence,
            model_name=model_name,
            model_version=model_version,
            status=status,
            requires_manual_review=requires_manual_review,
            classified_at=classified_at,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def latest_for_problem(self, problem_id: UUID) -> ProblemClassification | None:
        result = await self.session.execute(
            select(ProblemClassification)
            .where(ProblemClassification.problem_id == problem_id)
            .order_by(ProblemClassification.created_at.desc())
        )
        return result.scalars().first()

    async def history_for_problem(self, problem_id: UUID) -> list[ProblemClassification]:
        result = await self.session.execute(
            select(ProblemClassification)
            .where(ProblemClassification.problem_id == problem_id)
            .order_by(ProblemClassification.created_at.asc())
        )
        return list(result.scalars().all())
