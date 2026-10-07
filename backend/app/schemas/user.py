from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.email import CampusEmail


class UserBase(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    email: CampusEmail
    role: str


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128)


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=255)
    email: CampusEmail | None = None
    role: str | None = None
    is_active: bool | None = None
    is_verified: bool | None = None


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: str
    role: str
