"""Self-service profile schemas.

`current_workload` is deliberately absent: workload is controlled by future
assignment workflows, never edited directly by users (extra fields are
forbidden so attempts fail with 422).
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import AvailabilityStatus, Department
from app.schemas.faculty_profile import FacultyProfileResponse
from app.schemas.student_profile import StudentProfileResponse
from app.schemas.user_skill import UserSkillWithSkill


class StudentSelfUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_identifier: str | None = Field(None, min_length=1, max_length=50)
    department: Department | None = None
    academic_year: int | None = Field(None, ge=1, le=5)
    semester: int | None = Field(None, ge=1, le=8)
    bio: str | None = Field(None, max_length=2000)
    availability_status: AvailabilityStatus | None = None
    max_workload: int | None = Field(None, gt=0)


class FacultySelfUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_identifier: str | None = Field(None, min_length=1, max_length=50)
    department: Department | None = None
    designation: str | None = Field(None, min_length=1, max_length=100)
    specialization: str | None = Field(None, min_length=1, max_length=500)
    bio: str | None = Field(None, max_length=2000)
    availability_status: AvailabilityStatus | None = None
    max_workload: int | None = Field(None, gt=0)


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(None, min_length=1, max_length=255)
    student_profile: StudentSelfUpdate | None = None
    faculty_profile: FacultySelfUpdate | None = None


class ProfileMeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: str
    role: str
    is_active: bool
    is_verified: bool
    student_profile: StudentProfileResponse | None = None
    faculty_profile: FacultyProfileResponse | None = None


class UserSkillAdd(BaseModel):
    skill_id: UUID
    proficiency_level: int = Field(..., ge=1, le=5)
    years_experience: int | None = Field(None, ge=0)


class UserSkillPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proficiency_level: int | None = Field(None, ge=1, le=5)
    years_experience: int | None = Field(None, ge=0)


class MySkillsResponse(BaseModel):
    skills: list[UserSkillWithSkill]
