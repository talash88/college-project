"""Knowledge Repository schemas (Step 12). All views are privacy-safe."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeSkillSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    skill_id: UUID
    name: str
    relevance_score: float | None = None


class KnowledgeEvidenceFile(BaseModel):
    file_id: UUID
    original_filename: str
    mime_type: str
    size_bytes: int


class KnowledgeEntrySummary(BaseModel):
    """Safe card view: no names, no internals."""

    id: UUID
    public_id: str
    title: str
    problem_preview: str
    final_category: str | None = None
    location_summary: str | None = None
    skills: list[KnowledgeSkillSummary] = Field(default_factory=list)
    resolution_duration_minutes: int | None = None
    published_at: datetime | None = None
    relevance: float | None = None
    semantic_similarity: float | None = None
    keyword_score: float | None = None


class RelatedKnowledgeItem(BaseModel):
    entry: KnowledgeEntrySummary
    semantic_similarity: float


class KnowledgeEntryDetail(BaseModel):
    """Safe full article: display names + explicitly shareable evidence only."""

    id: UUID
    public_id: str
    title: str
    problem_summary: str
    final_category: str | None = None
    location_summary: str | None = None
    root_cause: str | None = None
    solution_summary: str
    work_performed: str
    testing_performed: str | None = None
    deployment_notes: str | None = None
    known_limitations: str | None = None
    skills: list[KnowledgeSkillSummary] = Field(default_factory=list)
    resolution_duration_minutes: int | None = None
    team_names: list[str] = Field(default_factory=list)
    mentor_name: str | None = None
    mentor_designation: str | None = None
    evidence_files: list[KnowledgeEvidenceFile] = Field(default_factory=list)
    published_at: datetime | None = None
    related: list[RelatedKnowledgeItem] = Field(default_factory=list)


class KnowledgeSearchResponse(BaseModel):
    items: list[KnowledgeEntrySummary]
    total: int
    page: int
    page_size: int
    search_mode: str
    semantic_available: bool = True
    error: str | None = None


class RelatedSolutionsResponse(BaseModel):
    items: list[RelatedKnowledgeItem]
    semantic_available: bool = True


class AdminKnowledgeEntryResponse(BaseModel):
    id: UUID
    public_id: str
    problem_id: UUID
    problem_ticket: str | None = None
    title: str
    publication_status: str
    is_published: bool
    published_at: datetime | None = None
    archived_at: datetime | None = None
    failure_reason: str | None = None
    created_at: datetime


class PublicationActionResponse(BaseModel):
    entry_id: UUID
    public_id: str
    publication_status: str
