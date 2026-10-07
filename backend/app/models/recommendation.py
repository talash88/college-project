from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.problem import Problem
    from app.models.user import User


class TeamRecommendation(Base):
    """One recommended team option for a problem (advisory only, Step 8).

    History is append-only: recalculation adds rows, never rewrites.
    Scores are 0-100 recommendation scores, NOT probabilities.
    """

    __tablename__ = "team_recommendations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problems.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, default=uuid.uuid4
    )
    algorithm_version: Mapped[str] = mapped_column(String(100), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    skill_coverage_score: Mapped[float] = mapped_column(Float, nullable=False)
    proficiency_score: Mapped[float] = mapped_column(Float, nullable=False)
    availability_score: Mapped[float] = mapped_column(Float, nullable=False)
    workload_score: Mapped[float] = mapped_column(Float, nullable=False)
    verified_skill_score: Mapped[float] = mapped_column(Float, nullable=False)
    domain_score: Mapped[float] = mapped_column(Float, nullable=False)
    coverage_percent: Mapped[float] = mapped_column(Float, nullable=False)
    team_size: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="COMPLETED")
    missing_skills: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    problem: Mapped[Problem] = relationship("Problem", back_populates="team_recommendations")
    members: Mapped[list[TeamRecommendationMember]] = relationship(
        "TeamRecommendationMember", back_populates="recommendation", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_team_recommendations_problem_id", "problem_id"),
        Index("ix_team_recommendations_run_id", "run_id"),
        Index("ix_team_recommendations_created_at", "created_at"),
        CheckConstraint("score >= 0 AND score <= 100", name="ck_team_recommendations_score_range"),
        CheckConstraint(
            "coverage_percent >= 0 AND coverage_percent <= 100",
            name="ck_team_recommendations_coverage_range",
        ),
    )


class TeamRecommendationMember(Base):
    """One solver inside a recommended team option, with per-member reasons."""

    __tablename__ = "team_recommendation_members"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("team_recommendations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    individual_score: Mapped[float] = mapped_column(Float, nullable=False)
    covered_skills: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    reason_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    recommendation: Mapped[TeamRecommendation] = relationship(
        "TeamRecommendation", back_populates="members"
    )
    user: Mapped[User] = relationship("User", back_populates="team_recommendation_memberships")

    __table_args__ = (
        Index("ix_team_rec_members_recommendation_id", "recommendation_id"),
        Index("ix_team_rec_members_user_id", "user_id"),
        CheckConstraint(
            "individual_score >= 0 AND individual_score <= 100",
            name="ck_team_rec_members_score_range",
        ),
    )


class MentorRecommendation(Base):
    """One evaluated faculty mentor for a problem (advisory only, Step 8).

    One row per eligible mentor per analysis run; history is append-only.
    Score is a 0-100 recommendation score, NOT a probability.
    """

    __tablename__ = "mentor_recommendations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problems.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, default=uuid.uuid4
    )
    mentor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    specialization_score: Mapped[float] = mapped_column(Float, nullable=False)
    skill_match_score: Mapped[float] = mapped_column(Float, nullable=False)
    category_score: Mapped[float] = mapped_column(Float, nullable=False)
    availability_score: Mapped[float] = mapped_column(Float, nullable=False)
    workload_score: Mapped[float] = mapped_column(Float, nullable=False)
    semantic_similarity: Mapped[float] = mapped_column(Float, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(100), nullable=False)
    reason_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    problem: Mapped[Problem] = relationship("Problem", back_populates="mentor_recommendations")
    mentor: Mapped[User] = relationship("User", back_populates="mentor_recommendations")

    __table_args__ = (
        Index("ix_mentor_recommendations_problem_id", "problem_id"),
        Index("ix_mentor_recommendations_run_id", "run_id"),
        Index("ix_mentor_recommendations_created_at", "created_at"),
        Index("ix_mentor_recommendations_mentor_user_id", "mentor_user_id"),
        CheckConstraint(
            "score >= 0 AND score <= 100", name="ck_mentor_recommendations_score_range"
        ),
        CheckConstraint(
            "semantic_similarity >= 0 AND semantic_similarity <= 1",
            name="ck_mentor_recommendations_semantic_range",
        ),
    )
