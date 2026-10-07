"""Data access for Step 10 workspace (tasks, milestones, progress, work files)."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.problem import Problem
from app.models.workspace import (
    ProblemMilestone,
    ProblemProgressUpdate,
    ProblemTask,
    ProblemWorkAttachment,
)

_TASK_OPTIONS = (
    selectinload(ProblemTask.assignee),
    selectinload(ProblemTask.creator),
)


class TaskRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_for_problem(self, problem_id: UUID) -> list[ProblemTask]:
        result = await self.session.execute(
            select(ProblemTask)
            .options(*_TASK_OPTIONS)
            .where(ProblemTask.problem_id == problem_id)
            .order_by(ProblemTask.order_index.asc(), ProblemTask.created_at.asc())
        )
        return list(result.scalars().all())

    async def get(self, task_id: UUID) -> ProblemTask | None:
        result = await self.session.execute(
            select(ProblemTask).options(*_TASK_OPTIONS).where(ProblemTask.id == task_id)
        )
        return result.scalar_one_or_none()

    async def next_order_index(self, problem_id: UUID) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.max(ProblemTask.order_index), -1)).where(
                ProblemTask.problem_id == problem_id
            )
        )
        return int(result.scalar_one()) + 1

    async def create(self, **fields: object) -> ProblemTask:
        task = ProblemTask(**fields)
        self.session.add(task)
        await self.session.flush()
        return task

    async def active_for_assignee(self, problem_id: UUID, user_id: UUID) -> list[ProblemTask]:
        """Non-terminal tasks still pointing at a (possibly removed) member."""
        result = await self.session.execute(
            select(ProblemTask).where(
                ProblemTask.problem_id == problem_id,
                ProblemTask.assigned_to_user_id == user_id,
                ProblemTask.status.notin_(["DONE", "CANCELLED"]),
            )
        )
        return list(result.scalars().all())


class MilestoneRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_for_problem(self, problem_id: UUID) -> list[ProblemMilestone]:
        result = await self.session.execute(
            select(ProblemMilestone)
            .where(ProblemMilestone.problem_id == problem_id)
            .order_by(ProblemMilestone.order_index.asc(), ProblemMilestone.created_at.asc())
        )
        return list(result.scalars().all())

    async def get(self, milestone_id: UUID) -> ProblemMilestone | None:
        result = await self.session.execute(
            select(ProblemMilestone).where(ProblemMilestone.id == milestone_id)
        )
        return result.scalar_one_or_none()

    async def next_order_index(self, problem_id: UUID) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.max(ProblemMilestone.order_index), -1)).where(
                ProblemMilestone.problem_id == problem_id
            )
        )
        return int(result.scalar_one()) + 1

    async def create(self, **fields: object) -> ProblemMilestone:
        row = ProblemMilestone(**fields)
        self.session.add(row)
        await self.session.flush()
        return row


class ProgressRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_for_problem(self, problem_id: UUID, *, limit: int = 50) -> list[ProblemProgressUpdate]:
        result = await self.session.execute(
            select(ProblemProgressUpdate)
            .options(selectinload(ProblemProgressUpdate.author))
            .where(ProblemProgressUpdate.problem_id == problem_id)
            .order_by(ProblemProgressUpdate.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create(self, **fields: object) -> ProblemProgressUpdate:
        row = ProblemProgressUpdate(**fields)
        self.session.add(row)
        await self.session.flush()
        return row

    async def latest_for_problem(self, problem_id: UUID) -> ProblemProgressUpdate | None:
        result = await self.session.execute(
            select(ProblemProgressUpdate)
            .where(ProblemProgressUpdate.problem_id == problem_id)
            .order_by(ProblemProgressUpdate.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


class WorkAttachmentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_for_problem(self, problem_id: UUID) -> list[ProblemWorkAttachment]:
        result = await self.session.execute(
            select(ProblemWorkAttachment)
            .where(ProblemWorkAttachment.problem_id == problem_id)
            .order_by(ProblemWorkAttachment.created_at.asc())
        )
        return list(result.scalars().all())

    async def get(self, attachment_id: UUID) -> ProblemWorkAttachment | None:
        result = await self.session.execute(
            select(ProblemWorkAttachment).where(ProblemWorkAttachment.id == attachment_id)
        )
        return result.scalar_one_or_none()

    async def create(self, **fields: object) -> ProblemWorkAttachment:
        row = ProblemWorkAttachment(**fields)
        self.session.add(row)
        await self.session.flush()
        return row

    async def delete(self, row: ProblemWorkAttachment) -> None:
        await self.session.delete(row)
        await self.session.flush()


def compute_progress(
    tasks: list[ProblemTask], milestones: list[ProblemMilestone]
) -> tuple[float, int, int, int, int]:
    """Real progress from live task/milestone state.

    Tasks weigh 70%, milestones 30%. Cancelled items are excluded. When
    only one kind exists it carries 100%. Returns
    (overall, done_tasks, total_tasks, done_milestones, total_milestones).
    """
    active_tasks = [t for t in tasks if t.status != "CANCELLED"]
    active_milestones = [m for m in milestones if m.status != "CANCELLED"]
    done_tasks = sum(1 for t in active_tasks if t.status == "DONE")
    done_milestones = sum(1 for m in active_milestones if m.status == "COMPLETED")
    total_tasks = len(active_tasks)
    total_milestones = len(active_milestones)

    task_ratio = (done_tasks / total_tasks) if total_tasks else None
    milestone_ratio = (done_milestones / total_milestones) if total_milestones else None

    if task_ratio is None and milestone_ratio is None:
        overall = 0.0
    elif milestone_ratio is None:
        overall = 100.0 * task_ratio  # type: ignore[operator]
    elif task_ratio is None:
        overall = 100.0 * milestone_ratio
    else:
        overall = 100.0 * (0.70 * task_ratio + 0.30 * milestone_ratio)
    return max(0.0, min(100.0, round(overall, 2))), done_tasks, total_tasks, done_milestones, total_milestones


async def has_work_started(session: AsyncSession, problem_id: UUID) -> bool:
    """True if a WORK_STARTED activity already exists (idempotency guard)."""
    from app.core.enums import ProblemEventType
    from app.models.problem import ProblemActivity

    result = await session.execute(
        select(func.count())
        .select_from(ProblemActivity)
        .where(
            ProblemActivity.problem_id == problem_id,
            ProblemActivity.event_type == ProblemEventType.WORK_STARTED,
        )
    )
    return bool(result.scalar_one())


def utcnow() -> datetime:
    return datetime.now(UTC)


async def get_problem_locked(session: AsyncSession, problem_id: UUID) -> Problem | None:
    result = await session.execute(
        select(Problem).where(Problem.id == problem_id).with_for_update()
    )
    return result.scalar_one_or_none()
