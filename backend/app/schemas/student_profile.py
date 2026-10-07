from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import AvailabilityStatus, Department


class StudentProfileBase(BaseModel):
    student_identifier: str = Field(..., min_length=1, max_length=50)
    department: Department
    academic_year: int = Field(..., ge=1, le=5)
    semester: int | None = Field(None, ge=1, le=8)
    bio: str | None = Field(None, max_length=2000)
    availability_status: AvailabilityStatus = AvailabilityStatus.AVAILABLE
    current_workload: int = Field(default=0, ge=0)
    max_workload: int = Field(default=3, gt=0)


class StudentProfileCreate(StudentProfileBase):
    user_id: UUID


class StudentProfileUpdate(BaseModel):
    student_identifier: str | None = Field(None, min_length=1, max_length=50)
    department: Department | None = None
    academic_year: int | None = Field(None, ge=1, le=5)
    semester: int | None = Field(None, ge=1, le=8)
    bio: str | None = Field(None, max_length=2000)
    availability_status: AvailabilityStatus | None = None
    current_workload: int | None = Field(None, ge=0)
    max_workload: int | None = Field(None, gt=0)


class StudentProfileResponse(StudentProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
