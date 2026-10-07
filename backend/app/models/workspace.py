from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.problem import Problem
    from app.models.user import User

TASK_STATUSES_SQL = "'TODO', 'IN_PROGRESS', 'BLOCKED', 'DONE', 'CANCELLED'"
TASK_PRIORITIES_SQL = "'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'"
MILESTONE_STATUSES_SQL = "'PLANNED', 'IN_PROGRESS', 'COMPLETED', 'MISSED', 'CANCELLED'"


class ProblemTask(Base):
    """One unit of team work on an assigned problem (Step 10).

    History is preserved: rows are never hard-deleted while the problem
    lives (cancellation is a status change). Assignees must be ACTIVE
    members of the problem's active team — enforced in the service layer.
    """

    __tablename__ = "problem_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problems.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problem_teams.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="TODO")
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="MEDIUM")
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocker_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    problem: Mapped[Problem] = relationship("Problem", back_populates="tasks")
    assignee: Mapped[User | None] = relationship(
        "User", back_populates="assigned_tasks", foreign_keys="[ProblemTask.assigned_to_user_id]"
    )
    creator: Mapped[User | None] = relationship(
        "User", back_populates="created_tasks", foreign_keys="[ProblemTask.created_by_user_id]"
    )

    __table_args__ = (
        Index("ix_problem_tasks_problem_id", "problem_id"),
        Index("ix_problem_tasks_team_id", "team_id"),
        Index("ix_problem_tasks_assignee", "assigned_to_user_id"),
        Index("ix_problem_tasks_status", "status"),
        CheckConstraint(f"status IN ({TASK_STATUSES_SQL})", name="ck_problem_tasks_status"),
        CheckConstraint(f"priority IN ({TASK_PRIORITIES_SQL})", name="ck_problem_tasks_priority"),
        CheckConstraint("char_length(title) >= 3", name="ck_problem_tasks_title_min"),
    )


class ProblemMilestone(Base):
    """A mentor/admin-owned work phase on an assigned problem (Step 10)."""

    __tablename__ = "problem_milestones"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problems.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PLANNED")
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    problem: Mapped[Problem] = relationship("Problem", back_populates="milestones")

    __table_args__ = (
        Index("ix_problem_milestones_problem_id", "problem_id"),
        Index("ix_problem_milestones_status", "status"),
        CheckConstraint(f"status IN ({MILESTONE_STATUSES_SQL})", name="ck_milestones_status"),
        CheckConstraint("char_length(title) >= 3", name="ck_milestones_title_min"),
    )


class ProblemProgressUpdate(Base):
    """An author-signed progress note with a real computed snapshot (Step 10).

    progress_snapshot is always derived from live task/milestone state at
    write time — never supplied by the client.
    """

    __tablename__ = "problem_progress_updates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problems.id", ondelete="CASCADE"), nullable=False
    )
    author_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False
    )
    summary: Mapped[str] = mapped_column(String(1000), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    blockers: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_steps: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress_snapshot: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    problem: Mapped[Problem] = relationship("Problem", back_populates="progress_updates")
    author: Mapped[User | None] = relationship("User", back_populates="progress_updates")

    __table_args__ = (
        Index("ix_progress_updates_problem_id", "problem_id"),
        Index("ix_progress_updates_created_at", "created_at"),
        CheckConstraint("char_length(summary) >= 5", name="ck_progress_summary_min"),
        CheckConstraint(
            "progress_snapshot >= 0 AND progress_snapshot <= 100",
            name="ck_progress_snapshot_range",
        ),
    )


class ProblemWorkAttachment(Base):
    """Internal work/evidence file (Step 10). Reuses the Step 4 storage
    abstraction; visibility is workspace-only (never reporter-visible)."""

    __tablename__ = "problem_work_attachments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problems.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problem_tasks.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_reporter_visible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Explicit opt-in: only final-solution evidence flagged here may be
    # published to the Knowledge Repository. Default private.
    is_knowledge_shareable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    problem: Mapped[Problem] = relationship("Problem", back_populates="work_attachments")

    __table_args__ = (
        Index("ix_work_attachments_problem_id", "problem_id"),
        Index("ix_work_attachments_task_id", "task_id"),
        CheckConstraint("size_bytes > 0", name="ck_work_attachments_size_positive"),
    )
