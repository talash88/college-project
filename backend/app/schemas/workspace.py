"""Step 10 workspace schemas (tasks, milestones, progress, work files)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: str | None = Field(None, max_length=10000)
    assigned_to_user_id: UUID | None = None
    priority: str = Field("MEDIUM", pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$")
    due_date: datetime | None = None
    order_index: int | None = Field(None, ge=0, le=10000)


class TaskUpdate(BaseModel):
    """Partial edit. Assignee/blocker/status validated against transitions."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(None, min_length=3, max_length=200)
    description: str | None = Field(None, max_length=10000)
    assigned_to_user_id: UUID | None = None
    priority: str | None = Field(None, pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$")
    due_date: datetime | None = None
    order_index: int | None = Field(None, ge=0, le=10000)
    status: str | None = Field(None, pattern="^(TODO|IN_PROGRESS|BLOCKED|DONE|CANCELLED)$")
    blocker_reason: str | None = Field(None, max_length=1000)


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    problem_id: UUID
    team_id: UUID
    title: str
    description: str | None = None
    assigned_to_user_id: UUID | None = None
    assignee_name: str | None = None
    created_by_user_id: UUID
    creator_name: str | None = None
    status: str
    priority: str
    due_date: datetime | None = None
    order_index: int
    blocker_reason: str | None = None
    is_overdue: bool = False
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class MilestoneCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: str | None = Field(None, max_length=10000)
    target_date: datetime | None = None
    order_index: int | None = Field(None, ge=0, le=10000)


class MilestoneUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(None, min_length=3, max_length=200)
    description: str | None = Field(None, max_length=10000)
    target_date: datetime | None = None
    order_index: int | None = Field(None, ge=0, le=10000)
    status: str | None = Field(None, pattern="^(PLANNED|IN_PROGRESS|COMPLETED|MISSED|CANCELLED)$")


class MilestoneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    problem_id: UUID
    title: str
    description: str | None = None
    target_date: datetime | None = None
    status: str
    order_index: int
    created_by: UUID | None = None
    is_overdue: bool = False
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class ProgressCreate(BaseModel):
    summary: str = Field(..., min_length=5, max_length=1000)
    details: str | None = Field(None, max_length=10000)
    blockers: str | None = Field(None, max_length=5000)
    next_steps: str | None = Field(None, max_length=5000)


class ProgressResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    problem_id: UUID
    author_user_id: UUID
    author_name: str | None = None
    author_role: str | None = None
    summary: str
    details: str | None = None
    blockers: str | None = None
    next_steps: str | None = None
    progress_snapshot: float
    created_at: datetime


class WorkFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    problem_id: UUID
    task_id: UUID | None = None
    uploaded_by: UUID
    uploader_name: str | None = None
    original_filename: str
    mime_type: str
    size_bytes: int
    description: str | None = None
    is_knowledge_shareable: bool = False
    created_at: datetime


class WorkspaceMemberView(BaseModel):
    user_id: UUID | None = None
    name: str | None = None
    role_in_team: str | None = None
    joined_at: datetime | None = None


class WorkspaceTeamView(BaseModel):
    id: UUID
    name: str | None = None
    display_label: str | None = None
    members: list[WorkspaceMemberView] = Field(default_factory=list)


class WorkspaceMentorView(BaseModel):
    name: str | None = None
    designation: str | None = None
    specialization: str | None = None


class WorkspaceProgressView(BaseModel):
    percent: float
    done_tasks: int
    total_tasks: int
    done_milestones: int
    total_milestones: int


class WorkspaceOverviewResponse(BaseModel):
    problem_id: UUID
    ticket_number: str
    title: str
    status: str
    priority_level: str | None = None
    priority_score: float | None = None
    predicted_category: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    team: WorkspaceTeamView | None = None
    mentor: WorkspaceMentorView | None = None
    assigned_at: datetime | None = None
    progress: WorkspaceProgressView


class PublicProgressUpdateView(BaseModel):
    summary: str
    progress_snapshot: float
    author_role: str | None = None
    created_at: datetime


class PublicSolutionView(BaseModel):
    revision_number: int
    solution_summary: str
    work_performed: str
    testing_performed: str | None = None
    limitations: str | None = None
    status: str
    submitted_at: str
    evidence: list[dict[str, object]] = Field(default_factory=list)


class PublicProgressResponse(BaseModel):
    problem_id: UUID
    ticket_number: str
    title: str
    status: str
    progress_percent: float
    completed_tasks: int
    total_tasks: int
    completed_milestones: int
    total_milestones: int
    team_name: str | None = None
    team_member_names: list[str] = Field(default_factory=list)
    mentor_name: str | None = None
    assignment_active: bool
    recent_updates: list[PublicProgressUpdateView] = Field(default_factory=list)
    solution: PublicSolutionView | None = None


class DiscussionCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
