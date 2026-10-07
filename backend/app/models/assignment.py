from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.problem import Problem
    from app.models.solution import ProblemSolutionSubmission
    from app.models.user import User


class ProblemTeam(Base):
    """A real, admin-created team for one problem (Step 9).

    Distinct from TeamRecommendation (advisory, immutable). One active
    primary team per problem, enforced by partial unique index.
    """

    __tablename__ = "problem_teams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problems.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    problem: Mapped[Problem] = relationship("Problem", back_populates="teams")
    members: Mapped[list[ProblemTeamMember]] = relationship(
        "ProblemTeamMember", back_populates="team", cascade="all, delete-orphan"
    )
    creator: Mapped[User | None] = relationship("User", back_populates="created_teams")

    __table_args__ = (Index("ix_problem_teams_problem_id", "problem_id"),)

    @property
    def display_label(self) -> str:
        return self.name or f"Team · {self.id.hex[:8]}"


class ProblemTeamMember(Base):
    """One solver membership in a real team. History preserved via
    is_active/removed_at (never hard-deleted while the team lives)."""

    __tablename__ = "problem_team_members"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problem_teams.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_in_team: Mapped[str | None] = mapped_column(String(50), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    team: Mapped[ProblemTeam] = relationship("ProblemTeam", back_populates="members")
    user: Mapped[User] = relationship("User", back_populates="team_memberships")

    __table_args__ = (
        Index("ix_team_members_team_id", "team_id"),
        Index("ix_team_members_user_id", "user_id"),
    )


class ProblemAssignment(Base):
    """The admin's final assignment decision (Step 9).

    Points at the real team + mentor actually assigned (which may differ from
    the AI recommendations cited via source_*_id). Exactly one ACTIVE row per
    problem, enforced by partial unique index. Workload increments happen in
    the same transaction that creates this row.
    """

    __tablename__ = "problem_assignments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problems.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problem_teams.id", ondelete="CASCADE"), nullable=False
    )
    mentor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source_team_recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("team_recommendations.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_mentor_recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mentor_recommendations.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    team_was_overridden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mentor_was_overridden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    team_override_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    mentor_override_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    unassigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unassigned_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    unassignment_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    problem: Mapped[Problem] = relationship("Problem", back_populates="assignments")
    team: Mapped[ProblemTeam] = relationship("ProblemTeam")
    mentor: Mapped[User] = relationship(
        "User",
        back_populates="mentor_assignments",
        foreign_keys="[ProblemAssignment.mentor_user_id]",
    )
    # Submissions belong to an assignment. The ORM cascade keeps flush order
    # (reviews -> submissions -> assignment) ahead of the DB-level
    # ON DELETE CASCADE, so bulk deletes never hit already-removed rows.
    # App code never deletes assignment rows (reassign/cancel only retires
    # status), so this edge only orders full-graph deletes (e.g. tests).
    solution_submissions: Mapped[list[ProblemSolutionSubmission]] = relationship(
        "ProblemSolutionSubmission",
        back_populates="assignment",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_assignments_problem_id", "problem_id"),
        Index("ix_assignments_team_id", "team_id"),
        Index("ix_assignments_mentor_user_id", "mentor_user_id"),
        CheckConstraint(
            "status IN ('ACTIVE', 'COMPLETED', 'CANCELLED', 'REASSIGNED')",
            name="ck_assignments_status",
        ),
    )
