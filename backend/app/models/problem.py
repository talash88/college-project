from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ClassificationStatus, ProblemEventType, ProblemStatus
from app.db.session import Base

if TYPE_CHECKING:
    from app.models.assignment import ProblemAssignment, ProblemTeam
    from app.models.knowledge import KnowledgeEntry
    from app.models.notification import Notification
    from app.models.problem_analysis import ProblemPriorityAnalysis, ProblemSkillAnalysis
    from app.models.problem_classification import ProblemClassification
    from app.models.problem_duplicate import (
        DuplicateCluster,
        DuplicateClusterMember,
        ProblemDuplicateCandidate,
        ProblemEmbedding,
    )
    from app.models.recommendation import MentorRecommendation, TeamRecommendation
    from app.models.solution import ProblemResolutionVerification, ProblemSolutionSubmission
    from app.models.user import User
    from app.models.workspace import (
        ProblemMilestone,
        ProblemProgressUpdate,
        ProblemTask,
        ProblemWorkAttachment,
    )

PROBLEM_STATUSES_SQL = ", ".join(f"'{s.value}'" for s in ProblemStatus)
PROBLEM_EVENTS_SQL = ", ".join(f"'{e.value}'" for e in ProblemEventType)


class Problem(Base):
    """A campus problem report. AI fields are nullable placeholders for later steps."""

    __tablename__ = "problems"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reporter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    location_text: Mapped[str] = mapped_column(String(300), nullable=False)
    building: Mapped[str | None] = mapped_column(String(150), nullable=True)
    area: Mapped[str | None] = mapped_column(String(150), nullable=True)
    affected_people_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[ProblemStatus] = mapped_column(
        Enum(
            ProblemStatus,
            name="problem_status",
            create_constraint=False,
            native_enum=True,
            validate_strings=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=ProblemStatus.SUBMITTED,
        nullable=False,
    )
    # AI placeholders (Step 5+). Never populated in Step 4.
    predicted_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    classification_confidence: Mapped[float | None] = mapped_column(nullable=True)
    classification_status: Mapped[ClassificationStatus] = mapped_column(
        Enum(
            ClassificationStatus,
            name="problem_classification_status",
            create_constraint=False,
            native_enum=True,
            validate_strings=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=ClassificationStatus.NOT_RUN,
        nullable=False,
    )
    priority_score: Mapped[float | None] = mapped_column(nullable=True)
    priority_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    progress_percent: Mapped[float] = mapped_column(nullable=False, default=0.0)
    priority_status: Mapped[str] = mapped_column(String(20), default="NOT_RUN", nullable=False)
    required_skills_status: Mapped[str] = mapped_column(String(20), default="NOT_RUN", nullable=False)
    duplicate_status: Mapped[str] = mapped_column(String(20), default="NOT_RUN", nullable=False)
    team_recommendation_status: Mapped[str] = mapped_column(
        String(30), default="NOT_RUN", nullable=False
    )
    mentor_recommendation_status: Mapped[str] = mapped_column(
        String(30), default="NOT_RUN", nullable=False
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    canonical_problem_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problems.id", ondelete="SET NULL"), nullable=True
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    reporter: Mapped[User] = relationship(
        "User", back_populates="reported_problems", foreign_keys="[Problem.reporter_id]"
    )
    attachments: Mapped[list[ProblemAttachment]] = relationship(
        "ProblemAttachment", back_populates="problem", cascade="all, delete-orphan"
    )
    activities: Mapped[list[ProblemActivity]] = relationship(
        "ProblemActivity", back_populates="problem", cascade="all, delete-orphan"
    )
    comments: Mapped[list[ProblemComment]] = relationship(
        "ProblemComment", back_populates="problem", cascade="all, delete-orphan"
    )
    classifications: Mapped[list[ProblemClassification]] = relationship(
        "ProblemClassification", back_populates="problem", cascade="all, delete-orphan"
    )
    priority_analyses: Mapped[list[ProblemPriorityAnalysis]] = relationship(
        "ProblemPriorityAnalysis", back_populates="problem", cascade="all, delete-orphan"
    )
    skill_analyses: Mapped[list[ProblemSkillAnalysis]] = relationship(
        "ProblemSkillAnalysis", back_populates="problem", cascade="all, delete-orphan"
    )
    embeddings: Mapped[list[ProblemEmbedding]] = relationship(
        "ProblemEmbedding", back_populates="problem", cascade="all, delete-orphan"
    )
    duplicate_candidates_out: Mapped[list[ProblemDuplicateCandidate]] = relationship(
        "ProblemDuplicateCandidate",
        back_populates="source_problem",
        foreign_keys="[ProblemDuplicateCandidate.source_problem_id]",
        cascade="all, delete-orphan",
    )
    duplicate_candidates_in: Mapped[list[ProblemDuplicateCandidate]] = relationship(
        "ProblemDuplicateCandidate",
        back_populates="candidate_problem",
        foreign_keys="[ProblemDuplicateCandidate.candidate_problem_id]",
        cascade="all, delete-orphan",
    )
    cluster_membership: Mapped[DuplicateClusterMember | None] = relationship(
        "DuplicateClusterMember", back_populates="problem", uselist=False, cascade="all, delete-orphan"
    )
    canonical_for_clusters: Mapped[list[DuplicateCluster]] = relationship(
        "DuplicateCluster",
        back_populates="canonical_problem",
        foreign_keys="[DuplicateCluster.canonical_problem_id]",
    )
    canonical_problem: Mapped[Problem | None] = relationship(
        "Problem", remote_side="Problem.id", foreign_keys="[Problem.canonical_problem_id]"
    )
    team_recommendations: Mapped[list[TeamRecommendation]] = relationship(
        "TeamRecommendation", back_populates="problem", cascade="all, delete-orphan"
    )
    mentor_recommendations: Mapped[list[MentorRecommendation]] = relationship(
        "MentorRecommendation", back_populates="problem", cascade="all, delete-orphan"
    )
    teams: Mapped[list[ProblemTeam]] = relationship(
        "ProblemTeam", back_populates="problem", cascade="all, delete-orphan"
    )
    assignments: Mapped[list[ProblemAssignment]] = relationship(
        "ProblemAssignment", back_populates="problem", cascade="all, delete-orphan"
    )
    tasks: Mapped[list[ProblemTask]] = relationship(
        "ProblemTask", back_populates="problem", cascade="all, delete-orphan"
    )
    milestones: Mapped[list[ProblemMilestone]] = relationship(
        "ProblemMilestone", back_populates="problem", cascade="all, delete-orphan"
    )
    progress_updates: Mapped[list[ProblemProgressUpdate]] = relationship(
        "ProblemProgressUpdate", back_populates="problem", cascade="all, delete-orphan"
    )
    solution_submissions: Mapped[list[ProblemSolutionSubmission]] = relationship(
        "ProblemSolutionSubmission", back_populates="problem", cascade="all, delete-orphan"
    )
    resolution_verifications: Mapped[list[ProblemResolutionVerification]] = relationship(
        "ProblemResolutionVerification", back_populates="problem", cascade="all, delete-orphan"
    )
    notifications: Mapped[list[Notification]] = relationship(
        "Notification", back_populates="problem", cascade="all, delete-orphan"
    )
    work_attachments: Mapped[list[ProblemWorkAttachment]] = relationship(
        "ProblemWorkAttachment", back_populates="problem", cascade="all, delete-orphan"
    )
    knowledge_entry: Mapped[KnowledgeEntry | None] = relationship(
        "KnowledgeEntry", back_populates="problem", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("ticket_number", name="uq_problems_ticket_number"),
        Index("ix_problems_reporter_id", "reporter_id"),
        Index("ix_problems_status", "status"),
        Index("ix_problems_created_at", "created_at"),
        CheckConstraint("char_length(title) >= 5", name="ck_problems_title_min"),
        CheckConstraint("char_length(description) >= 20", name="ck_problems_description_min"),
        CheckConstraint(
            "affected_people_count IS NULL OR affected_people_count >= 1",
            name="ck_problems_affected_positive",
        ),
    )

    def __repr__(self) -> str:
        return f"<Problem(id={self.id}, ticket={self.ticket_number}, status={self.status})>"


class ProblemAttachment(Base):
    __tablename__ = "problem_attachments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problems.id", ondelete="CASCADE"), nullable=False
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    problem: Mapped[Problem] = relationship("Problem", back_populates="attachments")

    __table_args__ = (
        Index("ix_problem_attachments_problem_id", "problem_id"),
        CheckConstraint("size_bytes > 0", name="ck_problem_attachments_size_positive"),
    )


class ProblemActivity(Base):
    __tablename__ = "problem_activities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problems.id", ondelete="CASCADE"), nullable=False
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[ProblemEventType] = mapped_column(
        Enum(
            ProblemEventType,
            name="problem_event_type",
            create_constraint=False,
            native_enum=True,
            validate_strings=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    old_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    problem: Mapped[Problem] = relationship("Problem", back_populates="activities")

    __table_args__ = (
        Index("ix_problem_activities_problem_id", "problem_id"),
        Index("ix_problem_activities_created_at", "created_at"),
    )


class ProblemComment(Base):
    __tablename__ = "problem_comments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problems.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(String(2000), nullable=False)
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    problem: Mapped[Problem] = relationship("Problem", back_populates="comments")
    author: Mapped[User] = relationship("User", back_populates="problem_comments")

    __table_args__ = (
        Index("ix_problem_comments_problem_id", "problem_id"),
        CheckConstraint("char_length(content) >= 1", name="ck_problem_comments_content_nonempty"),
    )


class TicketCounter(Base):
    """Per-year counter row for concurrency-safe ticket numbers (locked with FOR UPDATE)."""

    __tablename__ = "ticket_counters"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
