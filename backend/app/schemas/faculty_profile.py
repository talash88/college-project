from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import AvailabilityStatus, Department


class FacultyProfileBase(BaseModel):
    employee_identifier: str = Field(..., min_length=1, max_length=50)
    department: Department
    designation: str = Field(..., min_length=1, max_length=100)
    specialization: str = Field(..., min_length=1, max_length=500)
    bio: str | None = Field(None, max_length=2000)
    availability_status: AvailabilityStatus = AvailabilityStatus.AVAILABLE
    current_workload: int = Field(default=0, ge=0)
    max_workload: int = Field(default=5, gt=0)


class FacultyProfileCreate(FacultyProfileBase):
    user_id: UUID


class FacultyProfileUpdate(BaseModel):
    employee_identifier: str | None = Field(None, min_length=1, max_length=50)
    department: Department | None = None
    designation: str | None = Field(None, min_length=1, max_length=100)
    specialization: str | None = Field(None, min_length=1, max_length=500)
    bio: str | None = Field(None, max_length=2000)
    availability_status: AvailabilityStatus | None = None
    current_workload: int | None = Field(None, ge=0)
    max_workload: int | None = Field(None, gt=0)


class FacultyProfileResponse(FacultyProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
