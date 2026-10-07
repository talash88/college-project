from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.assignment import ProblemAssignment
    from app.models.problem import Problem
    from app.models.user import User

SOLUTION_STATUSES_SQL = (
    "'SUBMITTED', 'CHANGES_REQUESTED', 'MENTOR_APPROVED', 'REPORTER_REJECTED', 'VERIFIED'"
)
REVIEW_DECISIONS_SQL = "'APPROVED', 'CHANGES_REQUESTED'"
VERIFICATION_DECISIONS_SQL = "'RESOLVED', 'NOT_RESOLVED'"


class ProblemSolutionSubmission(Base):
    """One submitted solution revision for an assigned problem (Step 11).

    Revisions are append-only rows: a resubmission creates a new row with an
    incremented revision_number. History (including mentor reviews) is never
    overwritten or deleted while the problem lives.
    """

    __tablename__ = "problem_solution_submissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problems.id", ondelete="CASCADE"), nullable=False
    )
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problem_assignments.id", ondelete="CASCADE"), nullable=False
    )
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    revision_number: Mapped[int] = mapped_column(nullable=False, default=1)
    solution_summary: Mapped[str] = mapped_column(String(2000), nullable=False)
    root_cause: Mapped[str] = mapped_column(String(2000), nullable=False)
    work_performed: Mapped[str] = mapped_column(Text, nullable=False)
    testing_performed: Mapped[str | None] = mapped_column(Text, nullable=True)
    deployment_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_attachment_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    readiness_override_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="SUBMITTED")
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    problem: Mapped[Problem] = relationship("Problem", back_populates="solution_submissions")
    assignment: Mapped[ProblemAssignment] = relationship(
        "ProblemAssignment", back_populates="solution_submissions"
    )
    submitter: Mapped[User | None] = relationship("User", back_populates="solution_submissions")
    reviews: Mapped[list[MentorSolutionReview]] = relationship(
        "MentorSolutionReview", back_populates="submission", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_solution_submissions_problem_id", "problem_id"),
        Index("ix_solution_submissions_assignment_id", "assignment_id"),
        CheckConstraint(f"status IN ({SOLUTION_STATUSES_SQL})", name="ck_solution_status"),
        CheckConstraint("revision_number >= 1", name="ck_solution_revision_positive"),
        CheckConstraint("char_length(solution_summary) >= 10", name="ck_solution_summary_min"),
        CheckConstraint("char_length(root_cause) >= 10", name="ck_solution_root_cause_min"),
        CheckConstraint("char_length(work_performed) >= 20", name="ck_solution_work_min"),
    )


class MentorSolutionReview(Base):
    """One mentor decision on one solution revision (Step 11, append-only)."""

    __tablename__ = "mentor_solution_reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    solution_submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("problem_solution_submissions.id", ondelete="CASCADE"),
        nullable=False,
    )
    mentor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    review_comment: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    is_admin_override: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    submission: Mapped[ProblemSolutionSubmission] = relationship(
        "ProblemSolutionSubmission", back_populates="reviews"
    )
    mentor: Mapped[User | None] = relationship("User", back_populates="solution_reviews")

    __table_args__ = (
        Index("ix_solution_reviews_submission_id", "solution_submission_id"),
        CheckConstraint(f"decision IN ({REVIEW_DECISIONS_SQL})", name="ck_review_decision"),
    )


class ProblemResolutionVerification(Base):
    """One reporter verdict on a mentor-approved solution (Step 11, append-only)."""

    __tablename__ = "problem_resolution_verifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problems.id", ondelete="CASCADE"), nullable=False
    )
    solution_submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("problem_solution_submissions.id", ondelete="SET NULL"),
        nullable=True,
    )
    reporter_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    problem: Mapped[Problem] = relationship("Problem", back_populates="resolution_verifications")

    __table_args__ = (
        Index("ix_verifications_problem_id", "problem_id"),
        CheckConstraint(f"decision IN ({VERIFICATION_DECISIONS_SQL})", name="ck_verification_decision"),
    )
