"""Data access for Step 8 recommendations (team + mentor)."""

import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import AvailabilityStatus, UserRole
from app.models.faculty_profile import FacultyProfile
from app.models.recommendation import (
    MentorRecommendation,
    TeamRecommendation,
    TeamRecommendationMember,
)
from app.models.student_profile import StudentProfile
from app.models.user import User
from app.models.user_skill import UserSkill

# Role/availability columns are VARCHAR with check constraints in this project
# (see migration 002) while the models map them as native enums — so any
# Enum-typed bind renders a failing ::enum cast under asyncpg. Comparing the
# String-cast column against plain values avoids the cast entirely (the same
# reason the existing status.in_(...) queries only work on the real
# problem_status enum column).
ELIGIBLE_AVAILABILITY = [AvailabilityStatus.AVAILABLE.value, AvailabilityStatus.LIMITED.value]


class CandidateRepository:
    """Eligible solvers/mentors with profiles and skills, in one query each."""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _workload_ok(profile: StudentProfile | FacultyProfile) -> bool:
        return (
            profile.max_workload > 0
            and profile.current_workload >= 0
            and profile.current_workload < profile.max_workload
        )

    async def eligible_solvers(self) -> list[User]:
        """SOLVERs that may be recommended: active, profiled, reachable, spare capacity.

        Role/availability columns are VARCHAR with check constraints in this
        project (see migration 002), and the mapped Enum type renders a
        failing ::enum cast for == comparisons under asyncpg — so membership
        is expressed with IN (...), the same pattern as the existing
        status.in_(...) queries.
        """
        result = await self.session.execute(
            select(User)
            .join(StudentProfile, StudentProfile.user_id == User.id)
            .options(
                selectinload(User.student_profile),
                selectinload(User.user_skills).selectinload(UserSkill.skill),
            )
            .where(
                cast(User.role, String).in_([UserRole.SOLVER.value]),
                User.is_active.is_(True),
                cast(StudentProfile.availability_status, String).in_(ELIGIBLE_AVAILABILITY),
                StudentProfile.current_workload >= 0,
                StudentProfile.max_workload > 0,
                StudentProfile.current_workload < StudentProfile.max_workload,
            )
            .order_by(User.created_at.asc(), User.id.asc())
        )
        users = list(result.scalars().all())
        # Belt-and-braces: drop rows whose joined data is inconsistent.
        return [u for u in users if u.student_profile is not None and self._workload_ok(u.student_profile)]

    async def eligible_mentors(self) -> list[User]:
        """MENTORs that may be recommended: active, profiled, reachable, spare capacity."""
        result = await self.session.execute(
            select(User)
            .join(FacultyProfile, FacultyProfile.user_id == User.id)
            .options(
                selectinload(User.faculty_profile),
                selectinload(User.user_skills).selectinload(UserSkill.skill),
            )
            .where(
                cast(User.role, String).in_([UserRole.MENTOR.value]),
                User.is_active.is_(True),
                cast(FacultyProfile.availability_status, String).in_(ELIGIBLE_AVAILABILITY),
                FacultyProfile.current_workload >= 0,
                FacultyProfile.max_workload > 0,
                FacultyProfile.current_workload < FacultyProfile.max_workload,
            )
            .order_by(User.created_at.asc(), User.id.asc())
        )
        users = list(result.scalars().all())
        return [u for u in users if u.faculty_profile is not None and self._workload_ok(u.faculty_profile)]


class TeamRecommendationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_option(
        self,
        *,
        problem_id: UUID,
        run_id: uuid.UUID,
        algorithm_version: str,
        score: float,
        skill_coverage_score: float,
        proficiency_score: float,
        availability_score: float,
        workload_score: float,
        verified_skill_score: float,
        domain_score: float,
        coverage_percent: float,
        team_size: int,
        missing_skills: list[str],
    ) -> TeamRecommendation:
        row = TeamRecommendation(
            problem_id=problem_id,
            run_id=run_id,
            algorithm_version=algorithm_version,
            score=score,
            skill_coverage_score=skill_coverage_score,
            proficiency_score=proficiency_score,
            availability_score=availability_score,
            workload_score=workload_score,
            verified_skill_score=verified_skill_score,
            domain_score=domain_score,
            coverage_percent=coverage_percent,
            team_size=team_size,
            status="COMPLETED",
            missing_skills=missing_skills,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def add_member(
        self,
        *,
        recommendation_id: UUID,
        user_id: UUID,
        individual_score: float,
        covered_skills: list[dict[str, Any]],
        reason_data: dict[str, Any],
    ) -> TeamRecommendationMember:
        member = TeamRecommendationMember(
            recommendation_id=recommendation_id,
            user_id=user_id,
            individual_score=individual_score,
            covered_skills=covered_skills,
            reason_data=reason_data,
        )
        self.session.add(member)
        await self.session.flush()
        return member

    async def latest_run_id(self, problem_id: UUID) -> uuid.UUID | None:
        result = await self.session.execute(
            select(TeamRecommendation.run_id)
            .where(TeamRecommendation.problem_id == problem_id)
            .order_by(TeamRecommendation.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_option(self, option_id: UUID) -> TeamRecommendation | None:
        result = await self.session.execute(
            select(TeamRecommendation)
            .options(
                selectinload(TeamRecommendation.members).selectinload(
                    TeamRecommendationMember.user
                ),
            )
            .where(TeamRecommendation.id == option_id)
        )
        return result.scalar_one_or_none()

    async def options_for_run(self, run_id: uuid.UUID) -> list[TeamRecommendation]:
        result = await self.session.execute(
            select(TeamRecommendation)
            .options(
                selectinload(TeamRecommendation.members).selectinload(
                    TeamRecommendationMember.user
                ),
            )
            .where(TeamRecommendation.run_id == run_id)
            .order_by(TeamRecommendation.score.desc(), TeamRecommendation.created_at.asc())
        )
        return list(result.scalars().all())

    async def history_run_ids(self, problem_id: UUID) -> list[dict[str, Any]]:
        """One entry per analysis run, newest first (history is append-only)."""
        result = await self.session.execute(
            select(
                TeamRecommendation.run_id,
                func.min(TeamRecommendation.created_at).label("created_at"),
                func.count().label("options"),
            )
            .where(TeamRecommendation.problem_id == problem_id)
            .group_by(TeamRecommendation.run_id)
            .order_by(func.min(TeamRecommendation.created_at).desc())
        )
        return [
            {"run_id": row[0], "created_at": row[1], "options": row[2]} for row in result.all()
        ]


class MentorRecommendationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        problem_id: UUID,
        run_id: uuid.UUID,
        mentor_user_id: UUID,
        score: float,
        specialization_score: float,
        skill_match_score: float,
        category_score: float,
        availability_score: float,
        workload_score: float,
        semantic_similarity: float,
        algorithm_version: str,
        reason_data: dict[str, Any],
    ) -> MentorRecommendation:
        row = MentorRecommendation(
            problem_id=problem_id,
            run_id=run_id,
            mentor_user_id=mentor_user_id,
            score=score,
            specialization_score=specialization_score,
            skill_match_score=skill_match_score,
            category_score=category_score,
            availability_score=availability_score,
            workload_score=workload_score,
            semantic_similarity=semantic_similarity,
            algorithm_version=algorithm_version,
            reason_data=reason_data,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def latest_run_id(self, problem_id: UUID) -> uuid.UUID | None:
        result = await self.session.execute(
            select(MentorRecommendation.run_id)
            .where(MentorRecommendation.problem_id == problem_id)
            .order_by(MentorRecommendation.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_row(self, row_id: UUID) -> MentorRecommendation | None:
        result = await self.session.execute(
            select(MentorRecommendation)
            .options(selectinload(MentorRecommendation.mentor))
            .where(MentorRecommendation.id == row_id)
        )
        return result.scalar_one_or_none()

    async def for_run(self, run_id: uuid.UUID) -> list[MentorRecommendation]:
        result = await self.session.execute(
            select(MentorRecommendation)
            .options(selectinload(MentorRecommendation.mentor))
            .where(MentorRecommendation.run_id == run_id)
            .order_by(MentorRecommendation.score.desc(), MentorRecommendation.created_at.asc())
        )
        return list(result.scalars().all())

    async def history_run_ids(self, problem_id: UUID) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(
                MentorRecommendation.run_id,
                func.min(MentorRecommendation.created_at).label("created_at"),
                func.count().label("candidates"),
            )
            .where(MentorRecommendation.problem_id == problem_id)
            .group_by(MentorRecommendation.run_id)
            .order_by(func.min(MentorRecommendation.created_at).desc())
        )
        return [
            {"run_id": row[0], "created_at": row[1], "candidates": row[2]} for row in result.all()
        ]
