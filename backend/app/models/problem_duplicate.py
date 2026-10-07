from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import DuplicateDecisionStatus
from app.db.session import Base

if TYPE_CHECKING:
    from app.models.problem import Problem
    from app.models.user import User

DECISION_STATUSES_SQL = ", ".join(f"'{s.value}'" for s in DuplicateDecisionStatus)


class ProblemEmbedding(Base):
    """Semantic embedding of one report (recomputed only when source text changes)."""

    __tablename__ = "problem_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problems.id", ondelete="CASCADE"), nullable=False
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(384), nullable=False)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
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

    problem: Mapped[Problem] = relationship("Problem", back_populates="embeddings")

    __table_args__ = (
        UniqueConstraint(
            "problem_id", "model_version", name="uq_problem_embeddings_problem_version"
        ),
        Index("ix_problem_embeddings_problem_id", "problem_id"),
    )


class ProblemDuplicateCandidate(Base):
    """One directed duplicate suggestion. Pair stored order-independent
    (source < candidate by UUID) plus the triggering report for audit."""

    __tablename__ = "problem_duplicate_candidates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problems.id", ondelete="CASCADE"), nullable=False
    )
    candidate_problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problems.id", ondelete="CASCADE"), nullable=False
    )
    triggered_by_problem_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problems.id", ondelete="SET NULL"), nullable=True
    )
    semantic_similarity: Mapped[float] = mapped_column(Float, nullable=False)
    location_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    category_support_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_match_score: Mapped[float] = mapped_column(Float, nullable=False)
    decision_status: Mapped[DuplicateDecisionStatus] = mapped_column(
        Enum(
            DuplicateDecisionStatus,
            name="duplicate_decision_status",
            create_constraint=False,
            native_enum=True,
            validate_strings=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=DuplicateDecisionStatus.PENDING,
        nullable=False,
    )
    embedding_version: Mapped[str] = mapped_column(String(100), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(100), nullable=False)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    source_problem: Mapped[Problem] = relationship(
        "Problem",
        back_populates="duplicate_candidates_out",
        foreign_keys="[ProblemDuplicateCandidate.source_problem_id]",
    )
    candidate_problem: Mapped[Problem] = relationship(
        "Problem",
        back_populates="duplicate_candidates_in",
        foreign_keys="[ProblemDuplicateCandidate.candidate_problem_id]",
    )
    reviewer: Mapped[User | None] = relationship("User", back_populates="duplicate_reviews")

    __table_args__ = (
        UniqueConstraint(
            "source_problem_id",
            "candidate_problem_id",
            name="uq_duplicate_candidates_pair",
        ),
        Index("ix_duplicate_candidates_source", "source_problem_id"),
        Index("ix_duplicate_candidates_candidate", "candidate_problem_id"),
        Index("ix_duplicate_candidates_status", "decision_status"),
        CheckConstraint(
            "source_problem_id != candidate_problem_id",
            name="ck_duplicate_candidates_no_self",
        ),
        CheckConstraint(
            "semantic_similarity >= 0 AND semantic_similarity <= 1",
            name="ck_duplicate_candidates_similarity_range",
        ),
        CheckConstraint(
            "final_match_score >= 0 AND final_match_score <= 1",
            name="ck_duplicate_candidates_match_range",
        ),
    )


class DuplicateCluster(Base):
    """A set of admin-confirmed duplicate reports. One canonical, N members."""

    __tablename__ = "duplicate_clusters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seq: Mapped[int] = mapped_column(
        Integer,
        server_default=text("nextval('duplicate_cluster_number_seq')"),
        nullable=False,
        unique=True,
    )
    cluster_number: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    canonical_problem_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problems.id", ondelete="SET NULL"), nullable=True
    )
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

    canonical_problem: Mapped[Problem | None] = relationship(
        "Problem",
        back_populates="canonical_for_clusters",
        foreign_keys="[DuplicateCluster.canonical_problem_id]",
    )
    members: Mapped[list[DuplicateClusterMember]] = relationship(
        "DuplicateClusterMember", back_populates="cluster", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("cluster_number", name="uq_duplicate_clusters_number"),
        Index("ix_duplicate_clusters_canonical", "canonical_problem_id"),
    )

    def __repr__(self) -> str:
        return f"<DuplicateCluster(id={self.id}, number={self.cluster_number})>"


class DuplicateClusterMember(Base):
    __tablename__ = "duplicate_cluster_members"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cluster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("duplicate_clusters.id", ondelete="CASCADE"), nullable=False
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_canonical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    cluster: Mapped[DuplicateCluster] = relationship("DuplicateCluster", back_populates="members")
    problem: Mapped[Problem] = relationship("Problem", back_populates="cluster_membership")

    __table_args__ = (
        UniqueConstraint("problem_id", name="uq_cluster_members_problem"),
        Index("ix_cluster_members_cluster_id", "cluster_id"),
    )
