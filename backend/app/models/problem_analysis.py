from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.problem import Problem
    from app.models.skill import Skill

ANALYSIS_STATUSES_SQL = "'NOT_RUN', 'PROCESSING', 'COMPLETED', 'LOW_CONFIDENCE', 'FAILED'"
PRIORITY_LEVELS_SQL = "'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'"
MATCH_TYPES_SQL = "'EXACT', 'SEMANTIC', 'HYBRID'"


class ProblemPriorityAnalysis(Base):
    """Immutable audit row per priority scoring run. History is never rewritten."""

    __tablename__ = "problem_priority_analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problems.id", ondelete="CASCADE"), nullable=False
    )
    # Nullable: FAILED rows carry no score (never faked).
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    priority_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    severity_component: Mapped[float] = mapped_column(Float, nullable=False)
    affected_people_component: Mapped[float] = mapped_column(Float, nullable=False)
    age_component: Mapped[float] = mapped_column(Float, nullable=False)
    category_component: Mapped[float] = mapped_column(Float, nullable=False)
    duplicate_component: Mapped[float] = mapped_column(Float, nullable=False)
    component_details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    recalculation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    problem: Mapped[Problem] = relationship("Problem", back_populates="priority_analyses")

    __table_args__ = (
        Index("ix_priority_analyses_problem_id", "problem_id"),
        Index("ix_priority_analyses_created_at", "created_at"),
        CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 100)",
            name="ck_priority_score_range",
        ),
    )

    def __repr__(self) -> str:
        return f"<ProblemPriorityAnalysis(id={self.id}, score={self.score}, level={self.priority_level})>"


class SkillEmbedding(Base):
    """One embedding row per (skill, embedding-model version). Built by script, not per request."""

    __tablename__ = "skill_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(384), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    skill: Mapped[Skill] = relationship("Skill", back_populates="embeddings")

    __table_args__ = (
        UniqueConstraint("skill_id", "model_version", name="uq_skill_embeddings_skill_version"),
        Index("ix_skill_embeddings_skill_id", "skill_id"),
    )


class ProblemSkillAnalysis(Base):
    """Run-level metadata for one required-skill extraction over a problem."""

    __tablename__ = "problem_skill_analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problems.id", ondelete="CASCADE"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    recalculation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    problem: Mapped[Problem] = relationship("Problem", back_populates="skill_analyses")
    required_skills: Mapped[list[ProblemRequiredSkill]] = relationship(
        "ProblemRequiredSkill", back_populates="analysis", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_skill_analyses_problem_id", "problem_id"),
        Index("ix_skill_analyses_created_at", "created_at"),
    )


class ProblemRequiredSkill(Base):
    """One matched skill within an analysis run. Never faked: rows exist only above threshold."""

    __tablename__ = "problem_required_skills"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("problem_skill_analyses.id", ondelete="CASCADE"),
        nullable=False,
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problems.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    match_type: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    analysis: Mapped[ProblemSkillAnalysis] = relationship(
        "ProblemSkillAnalysis", back_populates="required_skills"
    )
    skill: Mapped[Skill] = relationship("Skill")

    __table_args__ = (
        UniqueConstraint("analysis_id", "skill_id", name="uq_required_skills_analysis_skill"),
        Index("ix_required_skills_problem_id", "problem_id"),
        CheckConstraint("score >= 0 AND score <= 1", name="ck_required_skills_score_range"),
    )
