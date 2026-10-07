from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import ClassificationStatus, ProblemEventType, ProblemStatus
from app.schemas.assignment import AssignmentResponse
from app.schemas.duplicates import CanonicalSummary

TITLE_MIN = 5
TITLE_MAX = 200
DESCRIPTION_MIN = 20
DESCRIPTION_MAX = 10000
LOCATION_MIN = 3
LOCATION_MAX = 300
COMMENT_MAX = 2000


class ProblemCreate(BaseModel):
    title: str = Field(..., min_length=TITLE_MIN, max_length=TITLE_MAX)
    description: str = Field(..., min_length=DESCRIPTION_MIN, max_length=DESCRIPTION_MAX)
    location_text: str = Field(..., min_length=LOCATION_MIN, max_length=LOCATION_MAX)
    building: str | None = Field(None, max_length=150)
    area: str | None = Field(None, max_length=150)
    affected_people_count: int | None = Field(None, ge=1, le=1000000)


class ProblemUpdate(BaseModel):
    """Owner/admin editable fields only. Extra fields (status, ticket, AI…) → 422."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(None, min_length=TITLE_MIN, max_length=TITLE_MAX)
    description: str | None = Field(None, min_length=DESCRIPTION_MIN, max_length=DESCRIPTION_MAX)
    location_text: str | None = Field(None, min_length=LOCATION_MIN, max_length=LOCATION_MAX)
    building: str | None = Field(None, max_length=150)
    area: str | None = Field(None, max_length=150)
    affected_people_count: int | None = Field(None, ge=1, le=1000000)


class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=COMMENT_MAX)
    is_internal: bool = False


class ClassificationReviewRequest(BaseModel):
    accept: bool = True
    final_category: str | None = Field(None, min_length=1, max_length=50)
    review_note: str | None = Field(None, max_length=1000)


class RecalculateRequest(BaseModel):
    reason: str | None = Field(None, max_length=500)


class ClassificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    problem_id: UUID
    predicted_category: str | None
    confidence: float | None
    model_name: str
    model_version: str
    status: ClassificationStatus
    requires_manual_review: bool
    classified_at: datetime | None
    created_at: datetime
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None
    final_category: str | None = None
    review_note: str | None = None


class ReporterSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    role: str


class AttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    problem_id: UUID
    original_filename: str
    mime_type: str
    size_bytes: int
    uploaded_by: UUID
    created_at: datetime


class ActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    problem_id: UUID
    actor_user_id: UUID | None
    event_type: ProblemEventType
    old_status: str | None
    new_status: str | None
    message: str | None
    created_at: datetime


class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    problem_id: UUID
    author_id: UUID
    author_name: str | None = None
    content: str
    is_internal: bool
    created_at: datetime
    updated_at: datetime


class ProblemSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ticket_number: str
    title: str
    status: ProblemStatus
    location_text: str
    affected_people_count: int | None
    classification_status: ClassificationStatus
    created_at: datetime
    submitted_at: datetime


class PriorityComponentResponse(BaseModel):
    component: str
    raw_value: Any | None = None
    contribution: float
    max_contribution: float
    reason: str


class PriorityAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    problem_id: UUID
    score: float | None
    priority_level: str | None
    severity_component: float
    affected_people_component: float
    age_component: float
    category_component: float
    duplicate_component: float
    reasons: list[str] = []
    component_details: dict[str, Any] = {}
    algorithm_version: str
    status: str
    recalculation_reason: str | None = None
    calculated_at: datetime | None = None
    created_at: datetime


class RequiredSkillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    problem_id: UUID
    skill_id: UUID
    skill_name: str | None = None
    skill_category: str | None = None
    score: float
    match_type: str
    reason: str | None = None
    model_name: str
    model_version: str
    created_at: datetime


class SkillAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    problem_id: UUID
    model_name: str
    model_version: str
    status: str
    recalculation_reason: str | None = None
    created_at: datetime
    required_skills: list[RequiredSkillResponse] = []


class ProblemResponse(ProblemSummary):
    description: str
    reporter_id: UUID
    reporter: ReporterSummary | None = None
    building: str | None
    area: str | None
    predicted_category: str | None = None
    classification_confidence: float | None = None
    priority_score: float | None = None
    priority_level: str | None = None
    progress_percent: float = 0.0
    priority_status: str = "NOT_RUN"
    required_skills_status: str = "NOT_RUN"
    duplicate_status: str = "NOT_RUN"
    team_recommendation_status: str = "NOT_RUN"
    mentor_recommendation_status: str = "NOT_RUN"
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    rejection_reason: str | None = None
    canonical: CanonicalSummary | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    updated_at: datetime
    classification: ClassificationResponse | None = None
    priority: PriorityAnalysisResponse | None = None
    required_skills: list[RequiredSkillResponse] = []
    attachments: list[AttachmentResponse] = []
    activity: list[ActivityResponse] = []
    comments: list[CommentResponse] = []
    assignment: AssignmentResponse | None = None


class ProblemListResponse(BaseModel):
    items: list[ProblemSummary]
    total: int
    skip: int
    limit: int


class AdminProblemSummary(ProblemSummary):
    reporter_name: str | None = None
    reporter_email: str | None = None


class AdminProblemListResponse(BaseModel):
    items: list[AdminProblemSummary]
    total: int
    skip: int
    limit: int


class ProblemStatsResponse(BaseModel):
    total: int
    by_status: dict[str, int]
