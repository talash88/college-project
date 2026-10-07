from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import SkillCategory


class SkillBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    category: SkillCategory
    description: str | None = Field(None, max_length=1000)
    is_active: bool = True


class SkillCreate(SkillBase):
    pass


class SkillUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    category: SkillCategory | None = None
    description: str | None = Field(None, max_length=1000)
    is_active: bool | None = None


class SkillResponse(SkillBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    normalized_name: str
    created_at: datetime
    updated_at: datetime
