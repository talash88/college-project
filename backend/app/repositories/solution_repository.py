"""Data access for Step 11 solution submission, mentor review, verification."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.solution import (
    MentorSolutionReview,
    ProblemResolutionVerification,
    ProblemSolutionSubmission,
)


class SolutionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_for_problem(self, problem_id: UUID) -> list[ProblemSolutionSubmission]:
        result = await self.session.execute(
            select(ProblemSolutionSubmission)
            .options(
                selectinload(ProblemSolutionSubmission.submitter),
                selectinload(ProblemSolutionSubmission.reviews).selectinload(
                    MentorSolutionReview.mentor
                ),
            )
            .where(ProblemSolutionSubmission.problem_id == problem_id)
            .order_by(ProblemSolutionSubmission.revision_number.asc())
        )
        return list(result.scalars().all())

    async def get(self, submission_id: UUID) -> ProblemSolutionSubmission | None:
        result = await self.session.execute(
            select(ProblemSolutionSubmission)
            .options(
                selectinload(ProblemSolutionSubmission.submitter),
                selectinload(ProblemSolutionSubmission.reviews).selectinload(
                    MentorSolutionReview.mentor
                ),
            )
            .where(ProblemSolutionSubmission.id == submission_id)
        )
        return result.scalar_one_or_none()

    async def latest_for_problem(self, problem_id: UUID) -> ProblemSolutionSubmission | None:
        result = await self.session.execute(
            select(ProblemSolutionSubmission)
            .options(
                selectinload(ProblemSolutionSubmission.submitter),
                selectinload(ProblemSolutionSubmission.reviews).selectinload(
                    MentorSolutionReview.mentor
                ),
            )
            .where(ProblemSolutionSubmission.problem_id == problem_id)
            .order_by(ProblemSolutionSubmission.revision_number.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def max_revision(self, problem_id: UUID) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.max(ProblemSolutionSubmission.revision_number), 0)).where(
                ProblemSolutionSubmission.problem_id == problem_id
            )
        )
        return int(result.scalar_one())

    async def create(self, **fields: object) -> ProblemSolutionSubmission:
        row = ProblemSolutionSubmission(**fields)
        self.session.add(row)
        await self.session.flush()
        return row


class ReviewRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_for_submission(self, submission_id: UUID) -> list[MentorSolutionReview]:
        result = await self.session.execute(
            select(MentorSolutionReview)
            .options(selectinload(MentorSolutionReview.mentor))
            .where(MentorSolutionReview.solution_submission_id == submission_id)
            .order_by(MentorSolutionReview.created_at.asc())
        )
        return list(result.scalars().all())

    async def create(self, **fields: object) -> MentorSolutionReview:
        row = MentorSolutionReview(**fields)
        self.session.add(row)
        await self.session.flush()
        return row


class VerificationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_for_problem(self, problem_id: UUID) -> list[ProblemResolutionVerification]:
        result = await self.session.execute(
            select(ProblemResolutionVerification)
            .where(ProblemResolutionVerification.problem_id == problem_id)
            .order_by(ProblemResolutionVerification.created_at.asc())
        )
        return list(result.scalars().all())

    async def create(self, **fields: object) -> ProblemResolutionVerification:
        row = ProblemResolutionVerification(**fields)
        self.session.add(row)
        await self.session.flush()
        return row
