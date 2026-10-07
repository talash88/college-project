from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApproveRequest(BaseModel):
    note: str | None = Field(None, max_length=1000)


class RejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class ReviewActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ticket_number: str
    status: str
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    rejection_reason: str | None = None
    already_in_state: bool = False


class AssignRequest(BaseModel):
    solver_user_ids: list[UUID] = Field(min_length=1, max_length=8)
    mentor_user_id: UUID
    team_recommendation_id: UUID | None = None
    mentor_recommendation_id: UUID | None = None
    team_name: str | None = Field(None, max_length=100)
    team_override_reason: str | None = Field(None, max_length=1000)
    mentor_override_reason: str | None = Field(None, max_length=1000)
    member_roles: dict[str, str] | None = None


class ReassignRequest(BaseModel):
    solver_user_ids: list[UUID] = Field(min_length=1, max_length=8)
    mentor_user_id: UUID
    reason: str = Field(min_length=1, max_length=1000)
    team_name: str | None = Field(None, max_length=100)
    member_roles: dict[str, str] | None = None


class CancelAssignmentRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)
    return_to: str = Field("APPROVED", pattern="^(APPROVED|UNDER_REVIEW)$")


class CloseRequest(BaseModel):
    reason: str | None = Field(None, max_length=1000)


class AssignmentMemberResponse(BaseModel):
    user_id: UUID | None = None
    name: str | None = None
    role_in_team: str | None = None
    joined_at: datetime | None = None
    is_active: bool = True


class AssignmentTeamResponse(BaseModel):
    id: UUID
    name: str | None = None
    display_label: str
    is_active: bool
    members: list[AssignmentMemberResponse] = Field(default_factory=list)
    created_at: datetime


class AssignmentMentorResponse(BaseModel):
    user_id: UUID | None = None
    name: str | None = None
    designation: str | None = None
    specialization: str | None = None


class AssignmentResponse(BaseModel):
    id: UUID
    problem_id: UUID
    ticket_number: str | None = None
    team: AssignmentTeamResponse
    mentor: AssignmentMentorResponse
    source_team_recommendation_id: UUID | None = None
    source_mentor_recommendation_id: UUID | None = None
    assigned_by: UUID | None = None
    assigned_at: datetime
    team_was_overridden: bool
    mentor_was_overridden: bool
    team_override_reason: str | None = None
    mentor_override_reason: str | None = None
    status: str
    unassigned_at: datetime | None = None
    unassigned_by: UUID | None = None
    unassignment_reason: str | None = None
    created_at: datetime
    idempotent_replay: bool = False


class AssignmentHistoryEntry(BaseModel):
    id: UUID
    status: str
    team_name: str | None = None
    member_count: int
    mentor_name: str | None = None
    team_was_overridden: bool
    mentor_was_overridden: bool
    assigned_by: UUID | None = None
    assigned_at: datetime
    unassigned_at: datetime | None = None
    unassignment_reason: str | None = None


class AssignmentDetailResponse(BaseModel):
    active: AssignmentResponse | None = None
    history: list[AssignmentHistoryEntry] = Field(default_factory=list)


class AssignedProblemSummary(BaseModel):
    """Safe problem summary for solver/mentor worklists."""

    id: UUID
    ticket_number: str
    title: str
    status: str
    priority_level: str | None = None
    priority_score: float | None = None
    location_text: str
    team_name: str | None = None
    team_member_names: list[str] = Field(default_factory=list)
    mentor_name: str | None = None
    assigned_at: datetime | None = None
    submitted_at: datetime


class EligibleSolverSummary(BaseModel):
    user_id: UUID
    name: str
    availability: str
    current_workload: int
    max_workload: int
    department: str | None = None
    academic_year: int | None = None
    skills: list[dict[str, object]] = Field(default_factory=list)
