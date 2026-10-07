"""Institutional Knowledge Repository models (Step 12).

Knowledge entries are publication snapshots built ONLY from real verified
solved problems (CLOSED + mentor-approved final solution + reporter-confirmed
RESOLVED). Snapshots are audit-friendly: published content never silently
changes when source objects are edited later.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.problem import Problem
    from app.models.skill import Skill
    from app.models.solution import ProblemSolutionSubmission

KNOWLEDGE_EMBEDDING_DIM = 384

PUBLICATION_STATUSES_SQL = "'PENDING', 'PUBLISHED', 'FAILED', 'ARCHIVED'"


class KnowledgeEntry(Base):
    """One published knowledge article for one closed problem.

    One official active entry per source problem (unique problem_id).
    """

    __tablename__ = "knowledge_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problems.id", ondelete="CASCADE"), nullable=False
    )
    entry_number: Mapped[int] = mapped_column(Integer(), nullable=False)
    public_id: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    problem_summary: Mapped[str] = mapped_column(Text(), nullable=False)
    final_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    location_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    root_cause: Mapped[str | None] = mapped_column(Text(), nullable=True)
    solution_summary: Mapped[str] = mapped_column(Text(), nullable=False)
    work_performed: Mapped[str] = mapped_column(Text(), nullable=False)
    testing_performed: Mapped[str | None] = mapped_column(Text(), nullable=True)
    deployment_notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    known_limitations: Mapped[str | None] = mapped_column(Text(), nullable=True)
    resolution_duration_minutes: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    # Snapshot of safe display names only (never emails/IDs/workloads).
    team_names: Mapped[list[Any]] = mapped_column(JSONB(), nullable=False, default=list)
    mentor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    mentor_designation: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Snapshot of explicitly shareable evidence files at publish time.
    evidence_files: Mapped[list[Any]] = mapped_column(JSONB(), nullable=False, default=list)
    publication_status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    is_published: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_solution_submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("problem_solution_submissions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_text_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    problem: Mapped[Problem] = relationship("Problem", back_populates="knowledge_entry")
    source_submission: Mapped[ProblemSolutionSubmission] = relationship(
        "ProblemSolutionSubmission"
    )
    skills: Mapped[list[KnowledgeEntrySkill]] = relationship(
        "KnowledgeEntrySkill", back_populates="entry", cascade="all, delete-orphan"
    )
    embedding: Mapped[KnowledgeEmbedding | None] = relationship(
        "KnowledgeEmbedding",
        back_populates="entry",
        uselist=False,
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_knowledge_entries_problem_id", "problem_id"),
        Index("ix_knowledge_entries_status", "publication_status"),
        Index("ix_knowledge_entries_published_at", "published_at"),
        Index("ix_knowledge_entries_category", "final_category"),
        CheckConstraint(
            f"publication_status IN ({PUBLICATION_STATUSES_SQL})",
            name="ck_knowledge_entries_status",
        ),
        CheckConstraint("char_length(title) >= 5", name="ck_knowledge_entries_title_min"),
    )

    def __repr__(self) -> str:
        return f"<KnowledgeEntry(id={self.id}, public={self.public_id}, status={self.publication_status})>"


class KnowledgeEntrySkill(Base):
    """Skill taxonomy rows referenced by a knowledge entry (never invented)."""

    __tablename__ = "knowledge_entry_skills"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    knowledge_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    relevance_score: Mapped[float | None] = mapped_column(Float(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    entry: Mapped[KnowledgeEntry] = relationship("KnowledgeEntry", back_populates="skills")
    skill: Mapped[Skill] = relationship("Skill")

    __table_args__ = (
        Index("ix_knowledge_entry_skills_entry_id", "knowledge_entry_id"),
        Index("ix_knowledge_entry_skills_skill_id", "skill_id"),
    )


class KnowledgeEmbedding(Base):
    """384-dim pgvector embedding of one knowledge entry's semantic text."""

    __tablename__ = "knowledge_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    knowledge_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    embedding: Mapped[Any] = mapped_column(Vector(KNOWLEDGE_EMBEDDING_DIM), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(200), nullable=False)
    embedding_version: Mapped[str] = mapped_column(String(100), nullable=False)
    source_text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    entry: Mapped[KnowledgeEntry] = relationship("KnowledgeEntry", back_populates="embedding")

    __table_args__ = (
        Index("ix_knowledge_embeddings_entry_id", "knowledge_entry_id"),
    )
