from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import UserRole
from app.db.session import Base

if TYPE_CHECKING:
    from app.models.assignment import ProblemAssignment, ProblemTeam, ProblemTeamMember
    from app.models.faculty_profile import FacultyProfile
    from app.models.notification import Notification
    from app.models.problem import Problem, ProblemComment
    from app.models.problem_classification import ProblemClassification
    from app.models.problem_duplicate import ProblemDuplicateCandidate
    from app.models.recommendation import MentorRecommendation, TeamRecommendationMember
    from app.models.refresh_token import RefreshToken
    from app.models.solution import MentorSolutionReview, ProblemSolutionSubmission
    from app.models.student_profile import StudentProfile
    from app.models.user_skill import UserSkill
    from app.models.workspace import ProblemProgressUpdate, ProblemTask


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            create_constraint=False,
            native_enum=True,
            validate_strings=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    student_profile: Mapped[StudentProfile] = relationship(
        "StudentProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    faculty_profile: Mapped[FacultyProfile] = relationship(
        "FacultyProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    user_skills: Mapped[list[UserSkill]] = relationship(
        "UserSkill",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    reported_problems: Mapped[list[Problem]] = relationship(
        "Problem",
        back_populates="reporter",
        cascade="all, delete-orphan",
        foreign_keys="[Problem.reporter_id]",
    )
    problem_comments: Mapped[list[ProblemComment]] = relationship(
        "ProblemComment",
        back_populates="author",
        cascade="all, delete-orphan",
    )
    classification_reviews: Mapped[list[ProblemClassification]] = relationship(
        "ProblemClassification",
        back_populates="reviewer",
    )
    duplicate_reviews: Mapped[list[ProblemDuplicateCandidate]] = relationship(
        "ProblemDuplicateCandidate",
        back_populates="reviewer",
    )
    team_recommendation_memberships: Mapped[list[TeamRecommendationMember]] = relationship(
        "TeamRecommendationMember",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    mentor_recommendations: Mapped[list[MentorRecommendation]] = relationship(
        "MentorRecommendation",
        back_populates="mentor",
        cascade="all, delete-orphan",
    )
    created_teams: Mapped[list[ProblemTeam]] = relationship(
        "ProblemTeam",
        back_populates="creator",
    )
    team_memberships: Mapped[list[ProblemTeamMember]] = relationship(
        "ProblemTeamMember",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    mentor_assignments: Mapped[list[ProblemAssignment]] = relationship(
        "ProblemAssignment",
        back_populates="mentor",
        foreign_keys="[ProblemAssignment.mentor_user_id]",
        cascade="all, delete-orphan",
    )
    assigned_tasks: Mapped[list[ProblemTask]] = relationship(
        "ProblemTask",
        back_populates="assignee",
        foreign_keys="[ProblemTask.assigned_to_user_id]",
    )
    created_tasks: Mapped[list[ProblemTask]] = relationship(
        "ProblemTask",
        back_populates="creator",
        foreign_keys="[ProblemTask.created_by_user_id]",
    )
    progress_updates: Mapped[list[ProblemProgressUpdate]] = relationship(
        "ProblemProgressUpdate",
        back_populates="author",
    )
    solution_submissions: Mapped[list[ProblemSolutionSubmission]] = relationship(
        "ProblemSolutionSubmission",
        back_populates="submitter",
        foreign_keys="[ProblemSolutionSubmission.submitted_by_user_id]",
    )
    solution_reviews: Mapped[list[MentorSolutionReview]] = relationship(
        "MentorSolutionReview",
        back_populates="mentor",
        foreign_keys="[MentorSolutionReview.mentor_user_id]",
    )
    notifications: Mapped[list[Notification]] = relationship(
        "Notification",
        back_populates="recipient",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_users_email_lower", "email", postgresql_ops={"email": "text_pattern_ops"}),
        UniqueConstraint("email", name="uq_users_email"),
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"
