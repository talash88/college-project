from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import AvailabilityStatus, Department
from app.db.session import Base

if TYPE_CHECKING:
    from app.models.user import User


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    student_identifier: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )
    department: Mapped[Department] = mapped_column(
        Enum(
            Department,
            name="department",
            create_constraint=False,
            native_enum=True,
            validate_strings=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    academic_year: Mapped[int] = mapped_column(Integer, nullable=False)
    semester: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bio: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    availability_status: Mapped[AvailabilityStatus] = mapped_column(
        Enum(
            AvailabilityStatus,
            name="availability_status",
            create_constraint=False,
            native_enum=True,
            validate_strings=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=AvailabilityStatus.AVAILABLE,
        nullable=False,
    )
    current_workload: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_workload: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
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
    user: Mapped[User] = relationship("User", back_populates="student_profile")

    __table_args__ = (
        CheckConstraint("current_workload >= 0", name="ck_student_profiles_current_workload_nonneg"),
        CheckConstraint("max_workload > 0", name="ck_student_profiles_max_workload_pos"),
        CheckConstraint("current_workload <= max_workload", name="ck_student_profiles_workload_valid"),
        UniqueConstraint("student_identifier", name="uq_student_profiles_student_identifier"),
        Index("ix_student_profiles_department", "department"),
        Index("ix_student_profiles_availability", "availability_status"),
    )

    def __repr__(self) -> str:
        return f"<StudentProfile(id={self.id}, student_identifier={self.student_identifier}, department={self.department})>"
