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

from app.core.enums import SkillCategory
from app.db.session import Base

if TYPE_CHECKING:
    from app.models.problem_analysis import SkillEmbedding
    from app.models.user_skill import UserSkill


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )
    category: Mapped[SkillCategory] = mapped_column(
        Enum(
            SkillCategory,
            name="skill_category",
            create_constraint=False,
            native_enum=True,
            validate_strings=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
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
    user_skills: Mapped[list[UserSkill]] = relationship(
        "UserSkill",
        back_populates="skill",
        cascade="all, delete-orphan",
    )
    embeddings: Mapped[list[SkillEmbedding]] = relationship(
        "SkillEmbedding",
        back_populates="skill",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("normalized_name", name="uq_skills_normalized_name"),
        Index("ix_skills_category", "category"),
        Index("ix_skills_is_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Skill(id={self.id}, name={self.name}, category={self.category})>"
