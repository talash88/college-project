"""Campus problem reporting APIs (Steps 4-7: reports, classification, priority, skills, duplicates)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.config import settings
from app.core.enums import ProblemStatus, UserRole
from app.db.session import get_db
from app.models.problem import Problem, ProblemComment
from app.models.user import User
from app.repositories.problem_repository import reporter_summary
from app.schemas.assignment import (
    AssignedProblemSummary,
    AssignmentHistoryEntry,
    AssignmentMemberResponse,
    AssignmentMentorResponse,
    AssignmentResponse,
    AssignmentTeamResponse,
)
from app.schemas.duplicates import (
    CandidateProblemSummary,
    CanonicalSummary,
    DuplicateCandidateResponse,
    DuplicateClusterResponse,
    OwnerDuplicatesResponse,
)
from app.schemas.knowledge import RelatedKnowledgeItem, RelatedSolutionsResponse
from app.schemas.problem import ActivityResponse as ActivitySchema
from app.schemas.problem import (
    AttachmentResponse,
    ClassificationResponse,
    CommentCreate,
    CommentResponse,
    PriorityAnalysisResponse,
    ProblemCreate,
    ProblemListResponse,
    ProblemResponse,
    ProblemStatsResponse,
    ProblemSummary,
    ProblemUpdate,
    ReporterSummary,
    RequiredSkillResponse,
    SkillAnalysisResponse,
)
from app.schemas.recommendations import (
    CoveredSkillSummary,
    MentorHistoryEntry,
    MentorMatchedSkill,
    MentorRecommendationResponse,
    MentorRecommendationsResponse,
    TeamHistoryEntry,
    TeamMemberResponse,
    TeamOptionResponse,
    TeamRecommendationsResponse,
)
from app.services.assignment_service import AssignmentService
from app.services.attachment_service import AttachmentService
from app.services.auth_service import AuthError
from app.services.classification_service import ProblemClassificationService
from app.services.duplicate_service import DuplicateService
from app.services.mentor_recommendation_service import MentorRecommendationService
from app.services.priority_service import PriorityService
from app.services.problem_service import ProblemService
from app.services.skill_extraction_service import RequiredSkillService
from app.services.team_recommendation_service import TeamRecommendationService

router = APIRouter(prefix="/problems", tags=["Problems"])


def _to_http(exc: AuthError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def _comment_response(comment: ProblemComment) -> CommentResponse:
    author = comment.author
    return CommentResponse(
        id=comment.id,
        problem_id=comment.problem_id,
        author_id=comment.author_id,
        author_name=author.full_name if author is not None else None,
        content=comment.content,
        is_internal=comment.is_internal,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )


def _priority_response(row: object) -> PriorityAnalysisResponse | None:
    if row is None:
        return None
    base = PriorityAnalysisResponse.model_validate(row)
    details = getattr(row, "component_details", None)
    reasons = details.get("reasons", []) if isinstance(details, dict) else []
    base.reasons = [str(r) for r in reasons]
    return base


def _required_skill_response(row: object) -> RequiredSkillResponse:
    base = RequiredSkillResponse.model_validate(row)
    skill = getattr(row, "skill", None)
    if skill is not None:
        base.skill_name = skill.name
        category = skill.category
        base.skill_category = category.value if hasattr(category, "value") else str(category)
    return base


def _assignment_response(
    row: object, problem: Problem, *, include_private: bool
) -> AssignmentResponse:
    """Assignment view. Reporters/solvers/mentors get the safe summary
    (names, roles, flags); admins additionally get identifiers, source
    recommendation links, override reasons, and unassignment audit."""
    from app.models.assignment import ProblemAssignment

    assert isinstance(row, ProblemAssignment)
    members: list[AssignmentMemberResponse] = []
    for member in sorted(row.team.members, key=lambda m: m.joined_at):
        user = member.user
        members.append(
            AssignmentMemberResponse(
                user_id=member.user_id if include_private else None,
                name=user.full_name if user is not None else None,
                role_in_team=member.role_in_team or "Member",
                joined_at=member.joined_at,
                is_active=member.is_active,
            )
        )
    mentor = row.mentor
    mentor_profile = mentor.faculty_profile if mentor is not None else None
    team_label = row.team.name or f"Team · {problem.ticket_number}"
    response = AssignmentResponse(
        id=row.id,
        problem_id=row.problem_id,
        ticket_number=problem.ticket_number,
        team=AssignmentTeamResponse(
            id=row.team.id,
            name=row.team.name,
            display_label=team_label,
            is_active=row.team.is_active,
            members=members,
            created_at=row.team.created_at,
        ),
        mentor=AssignmentMentorResponse(
            user_id=row.mentor_user_id if include_private else None,
            name=mentor.full_name if mentor is not None else None,
            designation=mentor_profile.designation if mentor_profile is not None else None,
            specialization=mentor_profile.specialization if mentor_profile is not None else None,
        ),
        assigned_at=row.assigned_at,
        team_was_overridden=row.team_was_overridden,
        mentor_was_overridden=row.mentor_was_overridden,
        status=row.status,
        unassigned_at=row.unassigned_at,
        created_at=row.created_at,
    )
    if include_private:
        response.source_team_recommendation_id = row.source_team_recommendation_id
        response.source_mentor_recommendation_id = row.source_mentor_recommendation_id
        response.assigned_by = row.assigned_by
        response.team_override_reason = row.team_override_reason
        response.mentor_override_reason = row.mentor_override_reason
        response.unassigned_by = row.unassigned_by
        response.unassignment_reason = row.unassignment_reason
    return response


def _assignment_history_entry(row: object) -> AssignmentHistoryEntry:
    from app.models.assignment import ProblemAssignment

    assert isinstance(row, ProblemAssignment)
    mentor = row.mentor
    return AssignmentHistoryEntry(
        id=row.id,
        status=row.status,
        team_name=row.team.name,
        member_count=sum(1 for m in row.team.members if m.is_active),
        mentor_name=mentor.full_name if mentor is not None else None,
        team_was_overridden=row.team_was_overridden,
        mentor_was_overridden=row.mentor_was_overridden,
        assigned_by=row.assigned_by,
        assigned_at=row.assigned_at,
        unassigned_at=row.unassigned_at,
        unassignment_reason=row.unassignment_reason,
    )


async def build_detail_response(
    problem: Problem, db: AsyncSession, *, include_internal: bool
) -> ProblemResponse:
    comments = [
        _comment_response(c)
        for c in sorted(problem.comments, key=lambda c: c.created_at)
        if include_internal or not c.is_internal
    ]
    summary = reporter_summary(problem.reporter)
    latest = (
        max(problem.classifications, key=lambda c: c.created_at)
        if problem.classifications
        else None
    )
    priority_row = await PriorityService(db).latest_for(problem.id)
    _, required_rows = await RequiredSkillService(db).latest_with_skills(problem.id)
    dup_service = DuplicateService(db)
    canonical_summary: CanonicalSummary | None = None
    if problem.canonical_problem_id is not None:
        summary_dict = await dup_service.safe_canonical_summary(problem.canonical_problem_id)
        if summary_dict is not None:
            canonical_summary = CanonicalSummary(
                id=UUID(str(summary_dict["id"])),
                ticket_number=str(summary_dict["ticket_number"]),
                title=str(summary_dict["title"]),
                status=str(summary_dict["status"]),
                location_text=str(summary_dict["location_text"]),
                created_at=datetime.fromisoformat(str(summary_dict["created_at"])),
            )
    active_assignment = await AssignmentService(db).active_for_problem(problem.id)
    assignment_view = (
        _assignment_response(active_assignment, problem, include_private=include_internal)
        if active_assignment is not None
        else None
    )
    return ProblemResponse(
        id=problem.id,
        ticket_number=problem.ticket_number,
        title=problem.title,
        description=problem.description,
        reporter_id=problem.reporter_id,
        reporter=ReporterSummary.model_validate(summary) if summary is not None else None,
        location_text=problem.location_text,
        building=problem.building,
        area=problem.area,
        affected_people_count=problem.affected_people_count,
        status=problem.status,
        classification_status=problem.classification_status,
        predicted_category=problem.predicted_category,
        classification_confidence=problem.classification_confidence,
        priority_score=problem.priority_score,
        priority_level=problem.priority_level,
        progress_percent=problem.progress_percent,
        priority_status=problem.priority_status,        required_skills_status=problem.required_skills_status,
        duplicate_status=problem.duplicate_status,
        team_recommendation_status=problem.team_recommendation_status,
        mentor_recommendation_status=problem.mentor_recommendation_status,
        reviewed_by=problem.reviewed_by,
        reviewed_at=problem.reviewed_at,
        approved_by=problem.approved_by,
        approved_at=problem.approved_at,
        rejection_reason=problem.rejection_reason,
        canonical=canonical_summary,
        submitted_at=problem.submitted_at,
        resolved_at=problem.resolved_at,
        closed_at=problem.closed_at,
        created_at=problem.created_at,
        updated_at=problem.updated_at,
        classification=ClassificationResponse.model_validate(latest)
        if latest is not None
        else None,
        priority=_priority_response(priority_row),
        required_skills=[_required_skill_response(r) for r in required_rows],
        attachments=[
            AttachmentResponse.model_validate(a)
            for a in sorted(problem.attachments, key=lambda a: a.created_at)
        ],
        activity=[
            ActivitySchema.model_validate(a)
            for a in sorted(problem.activities, key=lambda a: a.created_at)
        ],
        comments=comments,
        assignment=assignment_view,
    )


def _to_summary(problem: Problem) -> ProblemSummary:
    return ProblemSummary.model_validate(problem)


@router.post("", response_model=ProblemResponse, status_code=status.HTTP_201_CREATED)
async def create_problem(
    payload: ProblemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProblemResponse:
    """Report a campus problem. The reporter is always the authenticated user."""
    service = ProblemService(db)
    try:
        problem = await service.create_problem(current_user, payload)
    except AuthError as exc:
        raise _to_http(exc) from None
    return await build_detail_response(problem, db, include_internal=False)


@router.get("/me", response_model=ProblemListResponse)
async def list_my_problems(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: ProblemStatus | None = Query(None),
    q: str | None = Query(None, max_length=200),
    sort: Literal["newest", "oldest"] = Query("newest"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProblemListResponse:
    service = ProblemService(db)
    items, total = await service.list_mine(
        current_user,
        skip=skip,
        limit=limit,
        status=status,
        search=q,
        newest_first=sort == "newest",
    )
    return ProblemListResponse(
        items=[_to_summary(p) for p in items], total=total, skip=skip, limit=limit
    )


@router.get("/me/stats", response_model=ProblemStatsResponse)
async def my_problem_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProblemStatsResponse:
    service = ProblemService(db)
    total, by_status = await service.stats_mine(current_user)
    return ProblemStatsResponse(total=total, by_status=by_status)


def _assigned_problem_summary(
    problem: Problem, assignment: object
) -> AssignedProblemSummary:
    """Safe worklist entry: ticket/title/status/priority plus team + mentor names."""
    from app.models.assignment import ProblemAssignment

    assert isinstance(assignment, ProblemAssignment)
    member_names = [
        m.user.full_name
        for m in sorted(assignment.team.members, key=lambda m: m.joined_at)
        if m.is_active and m.user is not None
    ]
    mentor = assignment.mentor
    return AssignedProblemSummary(
        id=problem.id,
        ticket_number=problem.ticket_number,
        title=problem.title,
        status=problem.status.value,
        priority_level=problem.priority_level,
        priority_score=problem.priority_score,
        location_text=problem.location_text,
        team_name=assignment.team.name or f"Team · {problem.ticket_number}",
        team_member_names=member_names,
        mentor_name=mentor.full_name if mentor is not None else None,
        assigned_at=assignment.assigned_at,
        submitted_at=problem.submitted_at,
    )


@router.get("/assigned/me", response_model=list[AssignedProblemSummary])
async def my_assigned_problems(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AssignedProblemSummary]:
    """Problems where the caller holds an active team membership (Step 9)."""
    service = AssignmentService(db)
    problems = ProblemService(db)
    summaries: list[AssignedProblemSummary] = []
    for problem_id in await service.assignments.active_assignment_member_problem_ids(
        current_user.id
    ):
        try:
            problem = await problems.get_visible_problem(current_user, problem_id)
        except AuthError:
            continue
        active = await service.active_for_problem(problem_id)
        if active is not None:
            summaries.append(_assigned_problem_summary(problem, active))
    return sorted(summaries, key=lambda s: s.assigned_at or s.submitted_at, reverse=True)


@router.get("/mentored/me", response_model=list[AssignedProblemSummary])
async def my_mentored_problems(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AssignedProblemSummary]:
    """Problems where the caller is the assigned mentor (Step 9)."""
    service = AssignmentService(db)
    problems = ProblemService(db)
    summaries: list[AssignedProblemSummary] = []
    for problem_id in await service.assignments.active_assignment_mentor_problem_ids(
        current_user.id
    ):
        try:
            problem = await problems.get_visible_problem(current_user, problem_id)
        except AuthError:
            continue
        active = await service.active_for_problem(problem_id)
        if active is not None:
            summaries.append(_assigned_problem_summary(problem, active))
    return sorted(summaries, key=lambda s: s.assigned_at or s.submitted_at, reverse=True)


@router.get("/{problem_id}", response_model=ProblemResponse)
async def get_problem(
    problem_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProblemResponse:
    service = ProblemService(db)
    try:
        problem = await service.get_visible_problem(current_user, problem_id)
    except AuthError as exc:
        raise _to_http(exc) from None
    return await build_detail_response(
        problem, db, include_internal=current_user.role == UserRole.ADMIN
    )


@router.patch("/{problem_id}", response_model=ProblemResponse)
async def update_problem(
    problem_id: UUID,
    payload: ProblemUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProblemResponse:
    service = ProblemService(db)
    try:
        problem = await service.update_problem(current_user, problem_id, payload)
    except AuthError as exc:
        raise _to_http(exc) from None
    return await build_detail_response(
        problem, db, include_internal=current_user.role == UserRole.ADMIN
    )


@router.delete("/{problem_id}", response_model=ProblemResponse)
async def withdraw_problem(
    problem_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProblemResponse:
    """Withdraw a report (soft: status → WITHDRAWN, history preserved)."""
    service = ProblemService(db)
    try:
        problem = await service.withdraw_problem(current_user, problem_id)
    except AuthError as exc:
        raise _to_http(exc) from None
    return await build_detail_response(
        problem, db, include_internal=current_user.role == UserRole.ADMIN
    )


@router.post(
    "/{problem_id}/attachments",
    response_model=AttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_attachment(
    problem_id: UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AttachmentResponse:
    service = AttachmentService(db, ProblemService(db))
    try:
        attachment = await service.add(current_user, problem_id, file)
    except AuthError as exc:
        raise _to_http(exc) from None
    return AttachmentResponse.model_validate(attachment)


@router.get("/{problem_id}/attachments", response_model=list[AttachmentResponse])
async def list_attachments(
    problem_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AttachmentResponse]:
    service = ProblemService(db)
    try:
        problem = await service.get_visible_problem(current_user, problem_id)
    except AuthError as exc:
        raise _to_http(exc) from None
    return [
        AttachmentResponse.model_validate(a)
        for a in sorted(problem.attachments, key=lambda a: a.created_at)
    ]


@router.delete("/{problem_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(
    problem_id: UUID,
    attachment_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = AttachmentService(db, ProblemService(db))
    try:
        await service.remove(current_user, problem_id, attachment_id)
    except AuthError as exc:
        raise _to_http(exc) from None
    return None


@router.get("/{problem_id}/activity", response_model=list[ActivitySchema])
async def list_activity(
    problem_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ActivitySchema]:
    service = ProblemService(db)
    try:
        problem = await service.get_visible_problem(current_user, problem_id)
    except AuthError as exc:
        raise _to_http(exc) from None
    return [
        ActivitySchema.model_validate(a)
        for a in sorted(problem.activities, key=lambda a: a.created_at)
    ]


@router.get("/{problem_id}/comments", response_model=list[CommentResponse])
async def list_comments(
    problem_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CommentResponse]:
    service = ProblemService(db)
    try:
        problem = await service.get_visible_problem(current_user, problem_id)
    except AuthError as exc:
        raise _to_http(exc) from None
    include_internal = current_user.role == UserRole.ADMIN
    return [
        _comment_response(c)
        for c in sorted(problem.comments, key=lambda c: c.created_at)
        if include_internal or not c.is_internal
    ]


@router.post(
    "/{problem_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_comment(
    problem_id: UUID,
    payload: CommentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommentResponse:
    service = ProblemService(db)
    try:
        comment = await service.add_comment(current_user, problem_id, payload)
    except AuthError as exc:
        raise _to_http(exc) from None
    return _comment_response(comment)


@router.get("/{problem_id}/classification", response_model=ClassificationResponse)
async def get_classification(
    problem_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ClassificationResponse:
    """Latest AI classification for a visible report (owner or admin)."""
    problems = ProblemService(db)
    try:
        await problems.get_visible_problem(current_user, problem_id)
    except AuthError as exc:
        raise _to_http(exc) from None
    classifier = ProblemClassificationService(db)
    latest = await classifier.latest_for(problem_id)
    if latest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not classified yet")
    return ClassificationResponse.model_validate(latest)


@router.get("/{problem_id}/classifications", response_model=list[ClassificationResponse])
async def list_classifications(
    problem_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ClassificationResponse]:
    """Full classification history for a visible report (owner or admin)."""
    problems = ProblemService(db)
    try:
        await problems.get_visible_problem(current_user, problem_id)
    except AuthError as exc:
        raise _to_http(exc) from None
    classifier = ProblemClassificationService(db)
    history = await classifier.history_for(problem_id)
    return [ClassificationResponse.model_validate(row) for row in history]


@router.get("/{problem_id}/priority", response_model=PriorityAnalysisResponse)
async def get_priority(
    problem_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PriorityAnalysisResponse:
    """Latest priority analysis for a visible report (owner or admin)."""
    problems = ProblemService(db)
    try:
        await problems.get_visible_problem(current_user, problem_id)
    except AuthError as exc:
        raise _to_http(exc) from None
    latest = await PriorityService(db).latest_for(problem_id)
    if latest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No priority analysis yet"
        )
    response = _priority_response(latest)
    assert response is not None
    return response


@router.get("/{problem_id}/required-skills", response_model=SkillAnalysisResponse)
async def get_required_skills(
    problem_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SkillAnalysisResponse:
    """Latest required-skill analysis for a visible report (owner or admin)."""
    problems = ProblemService(db)
    try:
        await problems.get_visible_problem(current_user, problem_id)
    except AuthError as exc:
        raise _to_http(exc) from None
    service = RequiredSkillService(db)
    latest, required_rows = await service.latest_with_skills(problem_id)
    if latest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No skill analysis yet")
    return SkillAnalysisResponse(
        id=latest.id,
        problem_id=latest.problem_id,
        model_name=latest.model_name,
        model_version=latest.model_version,
        status=latest.status,
        recalculation_reason=latest.recalculation_reason,
        created_at=latest.created_at,
        required_skills=[_required_skill_response(r) for r in required_rows],
    )


def _candidate_response(row: object, focus_id: UUID) -> DuplicateCandidateResponse:
    """Candidate with only the counterpart's ticket/title/status exposed."""
    from app.models.problem_duplicate import ProblemDuplicateCandidate

    assert isinstance(row, ProblemDuplicateCandidate)
    base = DuplicateCandidateResponse.model_validate(row)
    base.match_strength = (
        "STRONG"
        if float(row.final_match_score) >= settings.DUPLICATE_STRONG_THRESHOLD
        else "POSSIBLE"
    )
    counterpart = row.candidate_problem if row.source_problem_id == focus_id else row.source_problem
    if counterpart is not None:
        base.candidate = CandidateProblemSummary(
            id=counterpart.id,
            ticket_number=counterpart.ticket_number,
            title=counterpart.title,
            status=counterpart.status.value,
        )
    return base


async def _cluster_response(
    cluster: object, db: AsyncSession, *, include_reporter: bool
) -> DuplicateClusterResponse:
    """Cluster view. Reporter names only when include_reporter (admin)."""
    from app.models.problem_duplicate import DuplicateCluster
    from app.schemas.duplicates import ClusterMemberResponse, DuplicateClusterResponse

    assert isinstance(cluster, DuplicateCluster)
    service = DuplicateService(db)
    members = await service.clusters.members_of(cluster.id)
    member_views: list[ClusterMemberResponse] = []
    for member in members:
        detail = await service.problems.get_by_id(member.problem_id)
        if detail is None:
            continue
        reporter_name = None
        if include_reporter and detail.reporter is not None:
            reporter_name = detail.reporter.full_name
        member_views.append(
            ClusterMemberResponse(
                problem_id=detail.id,
                ticket_number=detail.ticket_number,
                title=detail.title,
                status=detail.status.value,
                reporter_name=reporter_name,
                is_canonical=member.is_canonical,
                joined_at=member.joined_at,
            )
        )
    canonical_view = None
    if cluster.canonical_problem_id is not None:
        summary_dict = await service.safe_canonical_summary(cluster.canonical_problem_id)
        if summary_dict is not None:
            canonical_view = CanonicalSummary(
                id=UUID(str(summary_dict["id"])),
                ticket_number=str(summary_dict["ticket_number"]),
                title=str(summary_dict["title"]),
                status=str(summary_dict["status"]),
                location_text=str(summary_dict["location_text"]),
                created_at=datetime.fromisoformat(str(summary_dict["created_at"])),
            )
    return DuplicateClusterResponse(
        id=cluster.id,
        cluster_number=cluster.cluster_number or f"DC-{cluster.seq:04d}",
        canonical_problem_id=cluster.canonical_problem_id,
        canonical=canonical_view,
        members=member_views,
        created_at=cluster.created_at,
    )


@router.get("/{problem_id}/duplicates", response_model=OwnerDuplicatesResponse)
async def get_duplicates(
    problem_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OwnerDuplicatesResponse:
    """Duplicate suggestions + cluster link for a visible report (owner or admin).

    Only ticket/title/status of other reports are exposed — never reporter
    identity, attachments or internal notes.
    """
    problems = ProblemService(db)
    try:
        problem = await problems.get_visible_problem(current_user, problem_id)
    except AuthError as exc:
        raise _to_http(exc) from None
    service = DuplicateService(db)
    include_decided = current_user.role == UserRole.ADMIN
    rows = await service.candidates.visible_for_problem(problem_id, include_decided=include_decided)
    cluster_view = None
    canonical_view = None
    membership = await service.membership_for(problem_id)
    if membership is not None:
        full = await service.cluster_with_members(membership.cluster_id)
        if full is not None:
            cluster_view = await _cluster_response(full, db, include_reporter=False)
    if problem.canonical_problem_id is not None:
        summary_dict = await service.safe_canonical_summary(problem.canonical_problem_id)
        if summary_dict is not None:
            canonical_view = CanonicalSummary(
                id=UUID(str(summary_dict["id"])),
                ticket_number=str(summary_dict["ticket_number"]),
                title=str(summary_dict["title"]),
                status=str(summary_dict["status"]),
                location_text=str(summary_dict["location_text"]),
                created_at=datetime.fromisoformat(str(summary_dict["created_at"])),
            )
    return OwnerDuplicatesResponse(
        analysis_status=problem.duplicate_status,
        candidates=[_candidate_response(r, problem_id) for r in rows],
        cluster=cluster_view,
        canonical=canonical_view,
    )


@router.get("/{problem_id}/related-solutions", response_model=RelatedSolutionsResponse)
async def get_related_solutions(
    problem_id: UUID,
    limit: int = Query(5, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RelatedSolutionsResponse:
    """Previously solved similar issues (informational only).

    Follows existing problem visibility rules first: unrelated users cannot
    reach private reports through this endpoint. Never marks duplicates,
    never changes state.
    """
    from app.api.v1.knowledge import _summary as _knowledge_summary
    from app.services.knowledge_service import KnowledgeService

    service = KnowledgeService(db)
    try:
        result = await service.related_for_problem(problem_id, current_user, limit=limit)
    except AuthError as exc:
        raise _to_http(exc) from None
    items = result["items"]
    assert isinstance(items, list)
    summaries: list[RelatedKnowledgeItem] = []
    for row in items:
        assert isinstance(row, dict)
        raw_entry = row["entry"]
        from app.models.knowledge import KnowledgeEntry

        assert isinstance(raw_entry, KnowledgeEntry)
        raw_sim = row["semantic_similarity"]
        assert isinstance(raw_sim, (int, float))
        summaries.append(
            RelatedKnowledgeItem(
                entry=_knowledge_summary(raw_entry),
                semantic_similarity=float(raw_sim),
            )
        )
    return RelatedSolutionsResponse(
        items=summaries,
        semantic_available=bool(result.get("semantic_available", True)),
    )


def _covered_skill_summary(entry: dict[str, object]) -> CoveredSkillSummary:
    skill_id = entry.get("skill_id")
    return CoveredSkillSummary(
        skill_id=UUID(str(skill_id)) if skill_id else None,
        name=_as_str(entry.get("name")) or "",
        relevance=_optional_float(entry.get("relevance")),
        match_kind=_as_str(entry.get("match_kind")),
        proficiency=_as_int(entry.get("proficiency")),
        proficiency_label=_as_str(entry.get("proficiency_label")),
        verified=_as_bool(entry.get("verified")),
    )


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _as_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _as_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _as_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return None


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _as_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return {str(k): v for k, v in value.items()}
    return {}


def _team_member_response(member: object, *, include_private: bool) -> TeamMemberResponse:
    """Member view. Reporters get names + covered skills only; admins get
    identifiers, scores, availability, and workload details."""
    from app.models.recommendation import TeamRecommendationMember

    assert isinstance(member, TeamRecommendationMember)
    user = member.user
    reasons = _as_dict(member.reason_data)
    covered = [
        _covered_skill_summary(_as_dict(e)) for e in _as_list(member.covered_skills)
    ]
    high_relevance = [_as_str(n) or "" for n in _as_list(reasons.get("high_relevance_covered"))]
    high_relevance = [n for n in high_relevance if n]
    name = _as_str(reasons.get("name")) or (user.full_name if user is not None else "Solver")
    if not include_private:
        return TeamMemberResponse(
            name=name,
            availability=_as_str(reasons.get("availability")),
            covered_skills=covered,
            high_relevance_covered=high_relevance,
        )
    return TeamMemberResponse(
        user_id=member.user_id,
        name=name,
        individual_score=member.individual_score,
        availability=_as_str(reasons.get("availability")),
        current_workload=_as_int(reasons.get("current_workload")),
        max_workload=_as_int(reasons.get("max_workload")),
        department=_as_str(reasons.get("department")),
        academic_year=_as_int(reasons.get("academic_year")),
        covered_skills=covered,
        high_relevance_covered=high_relevance,
    )


def _team_option_response(row: object, *, include_private: bool) -> TeamOptionResponse:
    from app.models.recommendation import TeamRecommendation

    assert isinstance(row, TeamRecommendation)
    missing = [str(n) for n in (row.missing_skills or []) if n]
    return TeamOptionResponse(
        id=row.id,
        run_id=row.run_id,
        score=row.score,
        skill_coverage_score=row.skill_coverage_score,
        proficiency_score=row.proficiency_score,
        availability_score=row.availability_score,
        workload_score=row.workload_score,
        verified_skill_score=row.verified_skill_score,
        domain_score=row.domain_score,
        coverage_percent=row.coverage_percent,
        team_size=row.team_size,
        missing_skills=missing,
        members=[
            _team_member_response(m, include_private=include_private)
            for m in sorted(row.members, key=lambda m: m.created_at)
        ],
        algorithm_version=row.algorithm_version,
        created_at=row.created_at,
    )


def _mentor_response(row: object, *, include_private: bool) -> MentorRecommendationResponse:
    """Mentor view. Reporters get professional details + scores; admins also
    get identifiers and exact workload numbers."""
    from app.models.recommendation import MentorRecommendation

    assert isinstance(row, MentorRecommendation)
    reasons = _as_dict(row.reason_data)
    matched: list[MentorMatchedSkill] = []
    for raw in _as_list(reasons.get("matched_skills")):
        entry = _as_dict(raw)
        skill_id = entry.get("skill_id")
        matched.append(
            MentorMatchedSkill(
                skill_id=UUID(str(skill_id)) if skill_id else None,
                name=_as_str(entry.get("name")) or "",
                relevance=_optional_float(entry.get("relevance")),
                match_kind=_as_str(entry.get("match_kind")),
                proficiency=_as_int(entry.get("proficiency")),
                proficiency_label=_as_str(entry.get("proficiency_label")),
            )
        )
    mentor = row.mentor
    name = _as_str(reasons.get("name")) or (mentor.full_name if mentor is not None else "Mentor")
    base = MentorRecommendationResponse(
        id=row.id,
        run_id=row.run_id,
        score=row.score,
        specialization_score=row.specialization_score,
        skill_match_score=row.skill_match_score,
        category_score=row.category_score,
        availability_score=row.availability_score,
        workload_score=row.workload_score,
        semantic_similarity=row.semantic_similarity,
        name=name,
        designation=_as_str(reasons.get("designation")),
        specialization=_as_str(reasons.get("specialization")),
        department=_as_str(reasons.get("department")),
        availability=_as_str(reasons.get("availability")),
        matched_skills=matched,
        algorithm_version=row.algorithm_version,
        created_at=row.created_at,
    )
    if include_private:
        base.mentor_user_id = row.mentor_user_id
        base.current_workload = _as_int(reasons.get("current_workload"))
        base.max_workload = _as_int(reasons.get("max_workload"))
    return base


_TEAM_STATUS_MESSAGES = {
    "NOT_RUN": "Team recommendation has not run yet.",
    "PROCESSING": "Team recommendation is running.",
    "COMPLETED": None,
    "NO_ELIGIBLE_CANDIDATES": "No eligible solvers found for a confident recommendation.",
    "INSUFFICIENT_DATA": "Insufficient skill requirements for confident recommendation.",
    "FAILED": "Team recommendation analysis failed. The report itself is unaffected.",
}

_MENTOR_STATUS_MESSAGES = {
    "NOT_RUN": "Mentor recommendation has not run yet.",
    "PROCESSING": "Mentor recommendation is running.",
    "COMPLETED": None,
    "NO_ELIGIBLE_CANDIDATES": "No eligible mentors found for a confident recommendation.",
    "INSUFFICIENT_DATA": "Insufficient skill requirements for confident recommendation.",
    "FAILED": "Mentor recommendation analysis failed. The report itself is unaffected.",
}


async def _canonical_pointer(
    problem: Problem, db: AsyncSession
) -> dict[str, object] | None:
    """Safe canonical reference for confirmed-duplicate members."""
    if problem.canonical_problem_id is None:
        return None
    summary = await DuplicateService(db).safe_canonical_summary(problem.canonical_problem_id)
    if summary is None:
        return None
    return {
        "id": summary["id"],
        "ticket_number": summary["ticket_number"],
        "title": summary["title"],
        "status": summary["status"],
    }


@router.get("/{problem_id}/team-recommendations", response_model=TeamRecommendationsResponse)
async def get_team_recommendations(
    problem_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TeamRecommendationsResponse:
    """Latest team options for a visible report (owner-safe, admin-full)."""
    problems = ProblemService(db)
    try:
        problem = await problems.get_visible_problem(current_user, problem_id)
    except AuthError as exc:
        raise _to_http(exc) from None
    include_private = current_user.role == UserRole.ADMIN
    if problem.status == ProblemStatus.DUPLICATE and problem.canonical_problem_id is not None:
        canonical = await _canonical_pointer(problem, db)
        ticket = canonical.get("ticket_number") if canonical else None
        return TeamRecommendationsResponse(
            status=problem.team_recommendation_status,
            options=[],
            canonical=canonical,
            message=f"Recommendation handled through canonical issue {ticket}."
            if ticket
            else "Recommendation handled through the canonical issue.",
        )
    service = TeamRecommendationService(db)
    rows = await service.latest_options(problem_id)
    status = problem.team_recommendation_status
    message = _TEAM_STATUS_MESSAGES.get(status)
    if status == "COMPLETED" and not rows:
        message = "No team options were produced for this report."
    return TeamRecommendationsResponse(
        status=status,
        options=[_team_option_response(r, include_private=include_private) for r in rows],
        canonical=None,
        message=message,
    )


@router.get(
    "/{problem_id}/team-recommendations/history", response_model=list[TeamHistoryEntry]
)
async def get_team_recommendation_history(
    problem_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TeamHistoryEntry]:
    """Append-only team recommendation run history for a visible report."""
    problems = ProblemService(db)
    try:
        await problems.get_visible_problem(current_user, problem_id)
    except AuthError as exc:
        raise _to_http(exc) from None
    return [
        TeamHistoryEntry.model_validate(entry)
        for entry in await TeamRecommendationService(db).history(problem_id)
    ]


@router.get("/{problem_id}/mentor-recommendations", response_model=MentorRecommendationsResponse)
async def get_mentor_recommendations(
    problem_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MentorRecommendationsResponse:
    """Latest mentor ranking for a visible report (owner-safe, admin-full)."""
    problems = ProblemService(db)
    try:
        problem = await problems.get_visible_problem(current_user, problem_id)
    except AuthError as exc:
        raise _to_http(exc) from None
    include_private = current_user.role == UserRole.ADMIN
    if problem.status == ProblemStatus.DUPLICATE and problem.canonical_problem_id is not None:
        canonical = await _canonical_pointer(problem, db)
        ticket = canonical.get("ticket_number") if canonical else None
        return MentorRecommendationsResponse(
            status=problem.mentor_recommendation_status,
            mentors=[],
            canonical=canonical,
            message=f"Recommendation handled through canonical issue {ticket}."
            if ticket
            else "Recommendation handled through the canonical issue.",
        )
    rows = await MentorRecommendationService(db).latest_ranking(problem_id)
    status = problem.mentor_recommendation_status
    message = _MENTOR_STATUS_MESSAGES.get(status)
    if status == "COMPLETED" and not rows:
        message = "No mentor candidates were produced for this report."
    return MentorRecommendationsResponse(
        status=status,
        mentors=[_mentor_response(r, include_private=include_private) for r in rows],
        canonical=None,
        message=message,
    )


@router.get(
    "/{problem_id}/mentor-recommendations/history", response_model=list[MentorHistoryEntry]
)
async def get_mentor_recommendation_history(
    problem_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MentorHistoryEntry]:
    """Append-only mentor recommendation run history for a visible report."""
    problems = ProblemService(db)
    try:
        await problems.get_visible_problem(current_user, problem_id)
    except AuthError as exc:
        raise _to_http(exc) from None
    return [
        MentorHistoryEntry.model_validate(entry)
        for entry in await MentorRecommendationService(db).history(problem_id)
    ]
