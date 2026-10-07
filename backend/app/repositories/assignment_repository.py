"""Data access for Step 9 assignments (teams, members, assignment rows)."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.assignment import ProblemAssignment, ProblemTeam, ProblemTeamMember
from app.models.faculty_profile import FacultyProfile
from app.models.problem import Problem
from app.models.student_profile import StudentProfile
from app.models.user import User

_ASSIGNMENT_OPTIONS = (
    selectinload(ProblemAssignment.team).selectinload(ProblemTeam.members).selectinload(
        ProblemTeamMember.user
    ),
    selectinload(ProblemAssignment.mentor).selectinload(User.faculty_profile),
)


class AssignmentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ---------- locking reads ----------

    async def get_problem_for_update(self, problem_id: UUID) -> Problem | None:
        """Reload the problem with a row lock: concurrent assignments serialize here."""
        result = await self.session.execute(
            select(Problem).where(Problem.id == problem_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def lock_student_profile(self, profile_id: UUID) -> StudentProfile | None:
        result = await self.session.execute(
            select(StudentProfile).where(StudentProfile.id == profile_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def lock_faculty_profile(self, profile_id: UUID) -> FacultyProfile | None:
        result = await self.session.execute(
            select(FacultyProfile).where(FacultyProfile.id == profile_id).with_for_update()
        )
        return result.scalar_one_or_none()

    # ---------- people ----------

    async def get_solver(self, user_id: UUID) -> User | None:
        result = await self.session.execute(
            select(User)
            .options(selectinload(User.student_profile))
            .where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_mentor(self, user_id: UUID) -> User | None:
        result = await self.session.execute(
            select(User)
            .options(selectinload(User.faculty_profile))
            .where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    # ---------- teams ----------

    async def create_team(
        self, *, problem_id: UUID, name: str | None, created_by: UUID | None
    ) -> ProblemTeam:
        team = ProblemTeam(problem_id=problem_id, name=name, created_by=created_by, is_active=True)
        self.session.add(team)
        await self.session.flush()
        return team

    async def add_member(
        self, *, team_id: UUID, user_id: UUID, role_in_team: str | None
    ) -> ProblemTeamMember:
        member = ProblemTeamMember(
            team_id=team_id, user_id=user_id, role_in_team=role_in_team, is_active=True
        )
        self.session.add(member)
        await self.session.flush()
        return member

    async def deactivate_team(self, team: ProblemTeam, *, now: datetime) -> None:
        team.is_active = False
        for member in team.members:
            if member.is_active:
                member.is_active = False
                member.removed_at = now
        await self.session.flush()

    # ---------- assignments ----------

    async def active_for_problem(
        self, problem_id: UUID, *, for_update: bool = False
    ) -> ProblemAssignment | None:
        stmt = (
            select(ProblemAssignment)
            .options(*_ASSIGNMENT_OPTIONS)
            .where(
                ProblemAssignment.problem_id == problem_id,
                ProblemAssignment.status == "ACTIVE",
            )
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def history_for_problem(self, problem_id: UUID) -> list[ProblemAssignment]:
        result = await self.session.execute(
            select(ProblemAssignment)
            .options(*_ASSIGNMENT_OPTIONS)
            .where(ProblemAssignment.problem_id == problem_id)
            .order_by(ProblemAssignment.created_at.desc())
        )
        return list(result.scalars().all())

    async def create_assignment(
        self,
        *,
        problem_id: UUID,
        team_id: UUID,
        mentor_user_id: UUID,
        source_team_recommendation_id: UUID | None,
        source_mentor_recommendation_id: UUID | None,
        assigned_by: UUID | None,
        team_was_overridden: bool,
        mentor_was_overridden: bool,
        team_override_reason: str | None,
        mentor_override_reason: str | None,
    ) -> ProblemAssignment:
        row = ProblemAssignment(
            problem_id=problem_id,
            team_id=team_id,
            mentor_user_id=mentor_user_id,
            source_team_recommendation_id=source_team_recommendation_id,
            source_mentor_recommendation_id=source_mentor_recommendation_id,
            assigned_by=assigned_by,
            assigned_at=datetime.now(UTC),
            team_was_overridden=team_was_overridden,
            mentor_was_overridden=mentor_was_overridden,
            team_override_reason=team_override_reason,
            mentor_override_reason=mentor_override_reason,
            status="ACTIVE",
        )
        self.session.add(row)
        await self.session.flush()
        return row

    # ---------- solver / mentor problem lists ----------

    async def _assigned_problem_ids(self, stmt: object) -> list[UUID]:
        from sqlalchemy.sql import Select

        assert isinstance(stmt, Select)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def active_assignment_member_problem_ids(self, user_id: UUID) -> list[UUID]:
        """Problems where the user holds an active membership in the active team."""
        return await self._assigned_problem_ids(
            select(ProblemAssignment.problem_id)
            .join(ProblemTeam, ProblemTeam.id == ProblemAssignment.team_id)
            .join(
                ProblemTeamMember,
                (ProblemTeamMember.team_id == ProblemTeam.id)
                & (ProblemTeamMember.user_id == user_id)
                & (ProblemTeamMember.is_active.is_(True)),
            )
            .where(
                ProblemAssignment.status == "ACTIVE",
                ProblemTeam.is_active.is_(True),
            )
        )

    async def active_assignment_mentor_problem_ids(self, user_id: UUID) -> list[UUID]:
        return await self._assigned_problem_ids(
            select(ProblemAssignment.problem_id).where(
                ProblemAssignment.mentor_user_id == user_id,
                ProblemAssignment.status == "ACTIVE",
            )
        )

    async def count_assignments_for_problem(self, problem_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(ProblemAssignment)
            .where(ProblemAssignment.problem_id == problem_id)
        )
        return result.scalar_one()
