from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CoveredSkillSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    skill_id: UUID | None = None
    name: str
    relevance: float | None = None
    match_kind: str | None = None
    proficiency: int | None = None
    proficiency_label: str | None = None
    verified: bool | None = None


class TeamMemberResponse(BaseModel):
    """One solver in a recommended option. Private fields are only filled
    for admins; reporters receive the safe subset."""

    user_id: UUID | None = None
    name: str
    individual_score: float | None = None
    availability: str | None = None
    current_workload: int | None = None
    max_workload: int | None = None
    department: str | None = None
    academic_year: int | None = None
    covered_skills: list[CoveredSkillSummary] = Field(default_factory=list)
    high_relevance_covered: list[str] = Field(default_factory=list)


class TeamOptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    score: float
    skill_coverage_score: float
    proficiency_score: float
    availability_score: float
    workload_score: float
    verified_skill_score: float
    domain_score: float
    coverage_percent: float
    team_size: int
    missing_skills: list[str] = Field(default_factory=list)
    members: list[TeamMemberResponse] = Field(default_factory=list)
    algorithm_version: str
    created_at: datetime


class TeamRecommendationsResponse(BaseModel):
    status: str
    options: list[TeamOptionResponse] = Field(default_factory=list)
    canonical: dict[str, Any] | None = None
    message: str | None = None


class TeamHistoryEntry(BaseModel):
    run_id: UUID
    created_at: datetime
    options: int


class MentorMatchedSkill(BaseModel):
    skill_id: UUID | None = None
    name: str
    relevance: float | None = None
    match_kind: str | None = None
    proficiency: int | None = None
    proficiency_label: str | None = None


class MentorRecommendationResponse(BaseModel):
    """One ranked mentor. Private fields are only filled for admins."""

    id: UUID
    run_id: UUID
    mentor_user_id: UUID | None = None
    name: str | None = None
    designation: str | None = None
    specialization: str | None = None
    department: str | None = None
    score: float
    specialization_score: float
    skill_match_score: float
    category_score: float
    availability_score: float
    workload_score: float
    semantic_similarity: float
    availability: str | None = None
    current_workload: int | None = None
    max_workload: int | None = None
    matched_skills: list[MentorMatchedSkill] = Field(default_factory=list)
    algorithm_version: str
    created_at: datetime


class MentorRecommendationsResponse(BaseModel):
    status: str
    mentors: list[MentorRecommendationResponse] = Field(default_factory=list)
    canonical: dict[str, Any] | None = None
    message: str | None = None


class MentorHistoryEntry(BaseModel):
    run_id: UUID
    created_at: datetime
    candidates: int
