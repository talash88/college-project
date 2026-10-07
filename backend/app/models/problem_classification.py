from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ClassificationStatus
from app.db.session import Base

if TYPE_CHECKING:
    from app.models.problem import Problem
    from app.models.user import User


class ProblemClassification(Base):
    """Immutable audit row per classification run. History is never rewritten:
    admin review only fills the review fields on the latest row."""

    __tablename__ = "problem_classifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("problems.id", ondelete="CASCADE"), nullable=False
    )
    # Nullable: FAILED rows carry no prediction (never faked).
    predicted_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[ClassificationStatus] = mapped_column(
        Enum(
            ClassificationStatus,
            name="problem_classification_status",
            create_constraint=False,
            native_enum=True,
            validate_strings=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    requires_manual_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    classified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    final_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    review_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    problem: Mapped[Problem] = relationship("Problem", back_populates="classifications")
    reviewer: Mapped[User | None] = relationship("User", back_populates="classification_reviews")

    __table_args__ = (
        Index("ix_problem_classifications_problem_id", "problem_id"),
        Index("ix_problem_classifications_created_at", "created_at"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_classifications_confidence_range",
        ),
    )

    def __repr__(self) -> str:
        return f"<ProblemClassification(id={self.id}, predicted={self.predicted_category}, status={self.status})>"
