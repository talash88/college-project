from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import ProficiencyLevel
from app.schemas.skill import SkillResponse


class UserSkillBase(BaseModel):
    skill_id: UUID
    proficiency_level: ProficiencyLevel
    years_experience: int | None = Field(None, ge=0)
    is_verified: bool = False


class UserSkillCreate(UserSkillBase):
    user_id: UUID


class UserSkillUpdate(BaseModel):
    proficiency_level: ProficiencyLevel | None = None
    years_experience: int | None = Field(None, ge=0)
    is_verified: bool | None = None


class UserSkillResponse(UserSkillBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime


class UserSkillWithSkill(UserSkillResponse):
    skill: SkillResponse | None = None


UserSkillWithSkill.model_rebuild()
