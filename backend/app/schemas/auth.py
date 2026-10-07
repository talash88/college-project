from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.email import CampusEmail
from app.schemas.faculty_profile import FacultyProfileResponse
from app.schemas.student_profile import StudentProfileResponse


class RegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    email: CampusEmail
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(..., min_length=1, max_length=20)


class LoginRequest(BaseModel):
    email: CampusEmail
    password: str = Field(..., min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str | None = Field(None, min_length=1, max_length=512)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class AuthUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: str
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime


class MeResponse(AuthUserResponse):
    student_profile: StudentProfileResponse | None = None
    faculty_profile: FacultyProfileResponse | None = None


class RegisterResponse(BaseModel):
    user: AuthUserResponse
    access_token: str
    token_type: str = "bearer"
    expires_in: int
