from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import SkillCategory
from app.models.skill import Skill
from app.schemas.skill import SkillCreate, SkillUpdate


def normalize_skill_name(name: str) -> str:
    """Normalize skill name to lowercase for case-insensitive uniqueness."""
    return name.strip().lower()


class SkillRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, skill_data: SkillCreate) -> Skill:
        normalized = normalize_skill_name(skill_data.name)
        skill = Skill(
            name=skill_data.name.strip(),
            normalized_name=normalized,
            category=skill_data.category,
            description=skill_data.description,
            is_active=skill_data.is_active,
        )
        self.session.add(skill)
        await self.session.flush()
        return skill

    async def get_by_id(self, skill_id: UUID) -> Skill | None:
        result = await self.session.execute(select(Skill).where(Skill.id == skill_id))
        return result.scalar_one_or_none()

    async def get_by_normalized_name(self, normalized_name: str) -> Skill | None:
        result = await self.session.execute(
            select(Skill).where(Skill.normalized_name == normalized_name)
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        category: SkillCategory | None = None,
        is_active: bool | None = None,
        search: str | None = None,
    ) -> list[Skill]:
        query = select(Skill).order_by(Skill.category, Skill.name)
        if category:
            query = query.where(Skill.category == category)
        if is_active is not None:
            query = query.where(Skill.is_active == is_active)
        if search:
            query = query.where(Skill.name.ilike(f"%{search}%"))
        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_all(
        self,
        category: SkillCategory | None = None,
        is_active: bool | None = None,
        search: str | None = None,
    ) -> int:
        query = select(func.count(Skill.id))
        if category:
            query = query.where(Skill.category == category)
        if is_active is not None:
            query = query.where(Skill.is_active == is_active)
        if search:
            query = query.where(Skill.name.ilike(f"%{search}%"))
        result = await self.session.execute(query)
        return result.scalar_one()

    async def update(self, skill_id: UUID, skill_data: SkillUpdate) -> Skill | None:
        skill = await self.get_by_id(skill_id)
        if not skill:
            return None
        for field, value in skill_data.model_dump(exclude_unset=True).items():
            if field == "name" and value:
                value = value.strip()
                skill.normalized_name = normalize_skill_name(value)
            setattr(skill, field, value)
        await self.session.flush()
        return skill

    async def delete(self, skill_id: UUID) -> bool:
        skill = await self.get_by_id(skill_id)
        if not skill:
            return False
        await self.session.delete(skill)
        await self.session.flush()
        return True

    async def get_or_create_by_name(self, name: str, category: SkillCategory, description: str | None = None) -> Skill:
        """Get existing skill by normalized name or create new one. Idempotent."""
        normalized = normalize_skill_name(name)
        existing = await self.get_by_normalized_name(normalized)
        if existing:
            return existing
        return await self.create(SkillCreate(name=name.strip(), category=category, description=description))
