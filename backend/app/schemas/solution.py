"""Step 11 schemas: solution submission, mentor review, verification, closure."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SolutionSubmit(BaseModel):
    solution_summary: str = Field(..., min_length=10, max_length=2000)
    root_cause: str = Field(..., min_length=10, max_length=2000)
    work_performed: str = Field(..., min_length=20, max_length=20000)
    testing_performed: str | None = Field(None, max_length=20000)
    deployment_notes: str | None = Field(None, max_length=20000)
    limitations: str | None = Field(None, max_length=20000)
    evidence_attachment_ids: list[UUID] = Field(default_factory=list, max_length=20)
    share_evidence_with_reporter: bool = False
    override_reason: str | None = Field(None, max_length=1000)


class SolutionReviewCreate(BaseModel):
    decision: str = Field(..., pattern="^(APPROVED|CHANGES_REQUESTED)$")
    review_comment: str | None = Field(None, max_length=2000)


class VerificationCreate(BaseModel):
    decision: str = Field(..., pattern="^(RESOLVED|NOT_RESOLVED)$")
    reason: str | None = Field(None, max_length=2000)


class CloseRequest(BaseModel):
    reason: str | None = Field(None, max_length=1000)


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    solution_submission_id: UUID
    mentor_user_id: UUID | None
    mentor_name: str | None = None
    decision: str
    review_comment: str | None = None
    is_admin_override: bool = False
    created_at: datetime


class SolutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    problem_id: UUID
    assignment_id: UUID
    submitted_by_user_id: UUID | None
    submitter_name: str | None = None
    revision_number: int
    solution_summary: str
    root_cause: str
    work_performed: str
    testing_performed: str | None = None
    deployment_notes: str | None = None
    limitations: str | None = None
    evidence_attachment_ids: list[str] = Field(default_factory=list)
    readiness_override_reason: str | None = None
    status: str
    submitted_at: datetime
    updated_at: datetime
    reviews: list[ReviewResponse] = Field(default_factory=list)


class VerificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    problem_id: UUID
    solution_submission_id: UUID | None = None
    reporter_user_id: UUID | None
    decision: str
    reason: str | None = None
    created_at: datetime


class ReadinessResponse(BaseModel):
    ready: bool
    reasons: list[str] = Field(default_factory=list)
    progress_percent: float
    done_tasks: int
    total_tasks: int
    done_milestones: int
    total_milestones: int
    blocked_tasks: int


class SafeSolutionView(BaseModel):
    revision_number: int
    solution_summary: str
    work_performed: str
    testing_performed: str | None = None
    limitations: str | None = None
    status: str
    submitted_at: str
    evidence: list[dict[str, object]] = Field(default_factory=list)


class SharedEvidenceFile(BaseModel):
    id: UUID
    original_filename: str
    mime_type: str
    size_bytes: int
    description: str | None = None
