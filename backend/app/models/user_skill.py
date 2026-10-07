from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ProficiencyLevel
from app.db.session import Base

if TYPE_CHECKING:
    from app.models.skill import Skill
    from app.models.user import User


class UserSkill(Base):
    __tablename__ = "user_skills"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
    )
    proficiency_level: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_verified: Mapped[bool] = mapped_column(default=False, nullable=False)
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
    user: Mapped[User] = relationship("User", back_populates="user_skills")
    skill: Mapped[Skill] = relationship("Skill", back_populates="user_skills")

    # Hybrid property for enum conversion
    @property
    def proficiency(self) -> ProficiencyLevel:
        return ProficiencyLevel(self.proficiency_level)

    @proficiency.setter
    def proficiency(self, value: ProficiencyLevel) -> None:
        self.proficiency_level = value.value

    __table_args__ = (
        CheckConstraint("proficiency_level BETWEEN 1 AND 5", name="ck_user_skills_proficiency_range"),
        CheckConstraint("years_experience >= 0", name="ck_user_skills_years_exp_nonneg"),
        UniqueConstraint("user_id", "skill_id", name="uq_user_skills_user_skill"),
        Index("ix_user_skills_user_id", "user_id"),
        Index("ix_user_skills_skill_id", "skill_id"),
        Index("ix_user_skills_proficiency", "proficiency_level"),
    )

    def __repr__(self) -> str:
        return f"<UserSkill(user_id={self.user_id}, skill_id={self.skill_id}, proficiency={self.proficiency_level})>"
