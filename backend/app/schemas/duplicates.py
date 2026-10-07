from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CandidateProblemSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ticket_number: str
    title: str
    status: str


class DuplicateCandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_problem_id: UUID
    candidate_problem_id: UUID
    # Counterpart only (relative to the focused report): ticket/title/status.
    candidate: CandidateProblemSummary | None = None
    semantic_similarity: float
    location_score: float | None = None
    category_support_score: float | None = None
    final_match_score: float
    # Diagnostic label only: STRONG when final_match_score >=
    # DUPLICATE_STRONG_THRESHOLD, else POSSIBLE. Admin confirmation of every
    # suggestion remains mandatory; this never auto-confirms anything.
    match_strength: str = "POSSIBLE"
    decision_status: str
    embedding_version: str
    algorithm_version: str
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    created_at: datetime


class CanonicalSummary(BaseModel):
    id: UUID
    ticket_number: str
    title: str
    status: str
    location_text: str
    created_at: datetime


class ClusterMemberResponse(BaseModel):
    problem_id: UUID
    ticket_number: str
    title: str
    status: str
    reporter_name: str | None = None
    is_canonical: bool
    joined_at: datetime


class DuplicateClusterResponse(BaseModel):
    id: UUID
    cluster_number: str
    canonical_problem_id: UUID | None
    canonical: CanonicalSummary | None = None
    members: list[ClusterMemberResponse] = []
    created_at: datetime


class OwnerDuplicatesResponse(BaseModel):
    analysis_status: str
    candidates: list[DuplicateCandidateResponse] = []
    cluster: DuplicateClusterResponse | None = None
    canonical: CanonicalSummary | None = None


class DuplicateReviewRequest(BaseModel):
    review_note: str | None = Field(None, max_length=1000)


class RecalculateDuplicatesRequest(BaseModel):
    reason: str | None = Field(None, max_length=500)
