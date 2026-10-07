"""Admin-only problem intake visibility (Step 4: read-only, no assignment/AI)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_admin
from app.api.v1.problems import (
    _assignment_history_entry,
    _cluster_response,
    build_detail_response,
)
from app.core.enums import ProblemStatus
from app.db.session import get_db
from app.models.user import User
from app.repositories.recommendation_repository import CandidateRepository
from app.schemas.assignment import (
    ApproveRequest,
    AssignmentDetailResponse,
    AssignmentResponse,
    AssignRequest,
    CancelAssignmentRequest,
    CloseRequest,
    EligibleSolverSummary,
    ReassignRequest,
    RejectRequest,
    ReviewActionResponse,
)
from app.schemas.duplicates import (
    DuplicateCandidateResponse,
    DuplicateClusterResponse,
    DuplicateReviewRequest,
    OwnerDuplicatesResponse,
)
from app.schemas.problem import (
    AdminProblemListResponse,
    AdminProblemSummary,
    ClassificationResponse,
    ClassificationReviewRequest,
    PriorityAnalysisResponse,
    ProblemResponse,
    RecalculateRequest,
    SkillAnalysisResponse,
)
from app.schemas.recommendations import (
    MentorRecommendationsResponse,
    TeamRecommendationsResponse,
)
from app.services.assignment_service import AssignmentService
from app.services.auth_service import AuthError
from app.services.classification_service import ProblemClassificationService
from app.services.duplicate_service import DuplicateService
from app.services.mentor_recommendation_service import MentorRecommendationService
from app.services.priority_service import PriorityService
from app.services.problem_service import ProblemService
from app.services.review_service import ReviewService
from app.services.skill_extraction_service import RequiredSkillService
from app.services.team_recommendation_service import TeamRecommendationService

router = APIRouter(prefix="/admin/problems", tags=["Admin Problems"])


@router.get("", response_model=AdminProblemListResponse)
async def admin_list_problems(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: ProblemStatus | None = Query(None),
    reporter_id: UUID | None = Query(None),
    q: str | None = Query(None, max_length=200),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    min_affected: int | None = Query(None, ge=1),
    max_affected: int | None = Query(None, ge=1),
    sort: Literal["newest", "oldest"] = Query("newest"),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminProblemListResponse:
    """List all reports with filters. Admin only; no assignment or AI actions."""
    service = ProblemService(db)
    items, total = await service.admin_list(
        skip=skip,
        limit=limit,
        status=status,
        reporter_id=reporter_id,
        search=q,
        date_from=date_from,
        date_to=date_to,
        min_affected=min_affected,
        max_affected=max_affected,
        newest_first=sort == "newest",
    )
    summaries: list[AdminProblemSummary] = []
    for problem in items:
        base = AdminProblemSummary.model_validate(problem)
        reporter = problem.reporter
        base.reporter_name = reporter.full_name if reporter is not None else None
        base.reporter_email = reporter.email if reporter is not None else None
        summaries.append(base)
    return AdminProblemListResponse(items=summaries, total=total, skip=skip, limit=limit)


@router.get("/{problem_id}", response_model=ProblemResponse)
async def admin_get_problem(
    problem_id: UUID,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ProblemResponse:
    """Full report detail including internal comments. Admin only."""
    service = ProblemService(db)
    problem = await service.problems.get_by_id(problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    return await build_detail_response(problem, db, include_internal=True)


@router.post("/{problem_id}/classification/run", response_model=ClassificationResponse)
async def admin_rerun_classification(
    problem_id: UUID,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ClassificationResponse:
    """Re-run AI classification (appends a new audit row). Admin only."""
    service = ProblemClassificationService(db)
    try:
        row = await service.rerun(problem_id)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    return ClassificationResponse.model_validate(row)


@router.post("/{problem_id}/classification/review", response_model=ClassificationResponse)
async def admin_review_classification(
    problem_id: UUID,
    payload: ClassificationReviewRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ClassificationResponse:
    """Accept the AI prediction or set the final category. Admin only.

    The original prediction is preserved; review fills final_category,
    reviewed_by/at and an optional note.
    """
    service = ProblemClassificationService(db)
    latest = await service.latest_for(problem_id)
    if latest is None:
        raise HTTPException(status_code=404, detail="Not classified yet")
    try:
        reviewed = await service.review(
            latest,
            admin,
            accept=payload.accept,
            final_category=payload.final_category,
            review_note=payload.review_note,
        )
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    return ClassificationResponse.model_validate(reviewed)


@router.post("/{problem_id}/priority/recalculate", response_model=PriorityAnalysisResponse)
async def admin_recalculate_priority(
    problem_id: UUID,
    payload: RecalculateRequest | None = None,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> PriorityAnalysisResponse:
    """Re-run priority scoring (appends history). Uses current age/text. Admin only."""
    from app.api.v1.problems import _priority_response

    service = PriorityService(db)
    try:
        row = await service.analyze_problem_id(
            problem_id, payload.reason if payload and payload.reason else None
        )
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    response = _priority_response(row)
    assert response is not None
    return response


@router.post("/{problem_id}/skills/reanalyze", response_model=SkillAnalysisResponse)
async def admin_reanalyze_skills(
    problem_id: UUID,
    payload: RecalculateRequest | None = None,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> SkillAnalysisResponse:
    """Re-run required-skill extraction (appends history). Admin only."""
    from app.api.v1.problems import _required_skill_response

    service = RequiredSkillService(db)
    try:
        analysis = await service.analyze_problem_id(
            problem_id, payload.reason if payload and payload.reason else None
        )
        required_rows = await service.analyses.required_skills_for_analysis(analysis.id)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    return SkillAnalysisResponse(
        id=analysis.id,
        problem_id=analysis.problem_id,
        model_name=analysis.model_name,
        model_version=analysis.model_version,
        status=analysis.status,
        recalculation_reason=analysis.recalculation_reason,
        created_at=analysis.created_at,
        required_skills=[_required_skill_response(r) for r in required_rows],
    )


@router.post("/{problem_id}/duplicates/reanalyze", response_model=OwnerDuplicatesResponse)
async def admin_reanalyze_duplicates(
    problem_id: UUID,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> OwnerDuplicatesResponse:
    """Re-run duplicate candidate search (old PENDING suggestions go STALE). Admin only."""
    from app.api.v1.problems import _candidate_response

    service = DuplicateService(db)
    problem = await service.problems.get_by_id(problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    await service.analyze(problem)
    refreshed = await service.problems.get_by_id(problem_id)
    assert refreshed is not None
    membership = await service.membership_for(problem_id)
    cluster_view = None
    if membership is not None:
        full = await service.cluster_with_members(membership.cluster_id)
        if full is not None:
            cluster_view = await _cluster_response(full, db, include_reporter=True)
    rows = await service.candidates.visible_for_problem(problem_id, include_decided=True)
    return OwnerDuplicatesResponse(
        analysis_status=refreshed.duplicate_status,
        candidates=[_candidate_response(r, problem_id) for r in rows],
        cluster=cluster_view,
        canonical=None,
    )


candidates_router = APIRouter(prefix="/admin/duplicate-candidates", tags=["Admin Duplicates"])


@candidates_router.post("/{candidate_id}/confirm", response_model=DuplicateClusterResponse)
async def admin_confirm_duplicate(
    candidate_id: UUID,
    payload: DuplicateReviewRequest | None = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> DuplicateClusterResponse:
    """Confirm a duplicate suggestion: cluster join/merge, member status, priority recount."""
    from app.api.v1.problems import _cluster_response

    service = DuplicateService(db)
    try:
        cluster = await service.confirm(
            candidate_id, admin, payload.review_note if payload else None
        )
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    return await _cluster_response(cluster, db, include_reporter=True)


@candidates_router.post("/{candidate_id}/reject", response_model=DuplicateCandidateResponse)
async def admin_reject_duplicate(
    candidate_id: UUID,
    payload: DuplicateReviewRequest | None = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> DuplicateCandidateResponse:
    """Reject a duplicate suggestion (record preserved, never silently re-offered)."""
    from app.api.v1.problems import _candidate_response

    service = DuplicateService(db)
    try:
        row = await service.reject(candidate_id, admin, payload.review_note if payload else None)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    return _candidate_response(row, row.source_problem_id)


clusters_router = APIRouter(prefix="/admin/duplicate-clusters", tags=["Admin Duplicates"])


@clusters_router.get("", response_model=list[DuplicateClusterResponse])
async def admin_list_clusters(
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[DuplicateClusterResponse]:
    from app.api.v1.problems import _cluster_response

    service = DuplicateService(db)
    clusters = await service.clusters.list_all()
    return [await _cluster_response(c, db, include_reporter=True) for c in clusters]


@clusters_router.get("/{cluster_id}", response_model=DuplicateClusterResponse)
async def admin_get_cluster(
    cluster_id: UUID,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> DuplicateClusterResponse:
    from app.api.v1.problems import _cluster_response

    service = DuplicateService(db)
    cluster = await service.cluster_with_members(cluster_id)
    if cluster is None:
        raise HTTPException(status_code=404, detail="Cluster not found")
    return await _cluster_response(cluster, db, include_reporter=True)


recommendations_router = APIRouter(prefix="/admin/problems", tags=["Admin Recommendations"])


@recommendations_router.post(
    "/{problem_id}/recommendations/team/recalculate",
    response_model=TeamRecommendationsResponse,
)
async def admin_recalculate_team(
    problem_id: UUID,
    payload: RecalculateRequest | None = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> TeamRecommendationsResponse:
    """Re-run team recommendation (appends a new run to history). Admin only."""
    from app.api.v1.problems import _team_option_response

    _ = admin
    service = TeamRecommendationService(db)
    try:
        await service.analyze_problem_id(
            problem_id, payload.reason if payload and payload.reason else None
        )
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    problem = await ProblemService(db).problems.get_by_id(problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    rows = await service.latest_options(problem_id)
    return TeamRecommendationsResponse(
        status=problem.team_recommendation_status,
        options=[_team_option_response(r, include_private=True) for r in rows],
        canonical=None,
        message=None,
    )


@recommendations_router.post(
    "/{problem_id}/recommendations/mentor/recalculate",
    response_model=MentorRecommendationsResponse,
)
async def admin_recalculate_mentor(
    problem_id: UUID,
    payload: RecalculateRequest | None = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> MentorRecommendationsResponse:
    """Re-run mentor recommendation (appends a new run to history). Admin only."""
    from app.api.v1.problems import _mentor_response

    _ = admin
    service = MentorRecommendationService(db)
    try:
        await service.analyze_problem_id(
            problem_id, payload.reason if payload and payload.reason else None
        )
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    problem = await ProblemService(db).problems.get_by_id(problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    rows = await service.latest_ranking(problem_id)
    return MentorRecommendationsResponse(
        status=problem.mentor_recommendation_status,
        mentors=[_mentor_response(r, include_private=True) for r in rows],
        canonical=None,
        message=None,
    )


workflow_router = APIRouter(prefix="/admin/problems", tags=["Admin Workflow"])


@workflow_router.post("/{problem_id}/review/start", response_model=ReviewActionResponse)
async def admin_start_review(
    problem_id: UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ReviewActionResponse:
    """Move SUBMITTED → UNDER_REVIEW (idempotent if already reviewing)."""
    service = ReviewService(db)
    try:
        problem = await service.get_by_id_or_404(problem_id)
        problem, already = await service.start_review(problem, admin)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    return ReviewActionResponse(
        id=problem.id,
        ticket_number=problem.ticket_number,
        status=problem.status.value,
        reviewed_by=problem.reviewed_by,
        reviewed_at=problem.reviewed_at,
        approved_by=problem.approved_by,
        approved_at=problem.approved_at,
        rejection_reason=problem.rejection_reason,
        already_in_state=already,
    )


@workflow_router.post("/{problem_id}/approve", response_model=ReviewActionResponse)
async def admin_approve_problem(
    problem_id: UUID,
    payload: ApproveRequest | None = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ReviewActionResponse:
    """Move UNDER_REVIEW → APPROVED. Approval assigns nobody."""
    service = ReviewService(db)
    try:
        problem = await service.get_by_id_or_404(problem_id)
        problem = await service.approve(problem, admin, payload.note if payload else None)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    return ReviewActionResponse(
        id=problem.id,
        ticket_number=problem.ticket_number,
        status=problem.status.value,
        reviewed_by=problem.reviewed_by,
        reviewed_at=problem.reviewed_at,
        approved_by=problem.approved_by,
        approved_at=problem.approved_at,
        rejection_reason=problem.rejection_reason,
    )


@workflow_router.post("/{problem_id}/reject", response_model=ReviewActionResponse)
async def admin_reject_problem(
    problem_id: UUID,
    payload: RejectRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ReviewActionResponse:
    """Move SUBMITTED/UNDER_REVIEW/APPROVED → REJECTED with mandatory reason."""
    service = ReviewService(db)
    try:
        problem = await service.get_by_id_or_404(problem_id)
        problem = await service.reject(problem, admin, payload.reason)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    return ReviewActionResponse(
        id=problem.id,
        ticket_number=problem.ticket_number,
        status=problem.status.value,
        reviewed_by=problem.reviewed_by,
        reviewed_at=problem.reviewed_at,
        approved_by=problem.approved_by,
        approved_at=problem.approved_at,
        rejection_reason=problem.rejection_reason,
    )


@workflow_router.post("/{problem_id}/assign", response_model=AssignmentResponse)
async def admin_assign_problem(
    problem_id: UUID,
    payload: AssignRequest,
    response: Response,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AssignmentResponse:
    """Atomically assign a real team + mentor (APPROVED → ASSIGNED).

    Returns 201 on creation, 200 with idempotent_replay when the identical
    assignment already exists (safe retry, no double workload).
    """
    from app.api.v1.problems import _assignment_response

    service = AssignmentService(db)
    try:
        assignment, created = await service.assign(
            problem_id,
            admin,
            solver_ids=list(payload.solver_user_ids),
            mentor_id=payload.mentor_user_id,
            team_recommendation_id=payload.team_recommendation_id,
            mentor_recommendation_id=payload.mentor_recommendation_id,
            team_name=payload.team_name,
            team_override_reason=payload.team_override_reason,
            mentor_override_reason=payload.mentor_override_reason,
            member_roles=payload.member_roles,
        )
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    problem = await ProblemService(db).problems.get_by_id(problem_id)
    assert problem is not None
    view = _assignment_response(assignment, problem, include_private=True)
    view.idempotent_replay = not created
    response.status_code = 201 if created else 200
    return view


@workflow_router.get("/{problem_id}/assignment", response_model=AssignmentDetailResponse)
async def admin_get_assignment(
    problem_id: UUID,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AssignmentDetailResponse:
    """Active assignment (if any) plus full append-only history. Admin only."""
    from app.api.v1.problems import _assignment_response

    problem = await ProblemService(db).problems.get_by_id(problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    service = AssignmentService(db)
    active = await service.active_for_problem(problem_id)
    history = await service.history_for_problem(problem_id)
    return AssignmentDetailResponse(
        active=_assignment_response(active, problem, include_private=True)
        if active is not None
        else None,
        history=[_assignment_history_entry(a) for a in history],
    )


@workflow_router.post("/{problem_id}/assignment/reassign", response_model=AssignmentResponse)
async def admin_reassign_problem(
    problem_id: UUID,
    payload: ReassignRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AssignmentResponse:
    """Atomically replace team/mentor (workloads released + applied once)."""
    from app.api.v1.problems import _assignment_response

    service = AssignmentService(db)
    try:
        assignment = await service.reassign(
            problem_id,
            admin,
            solver_ids=list(payload.solver_user_ids),
            mentor_id=payload.mentor_user_id,
            reason=payload.reason,
            team_name=payload.team_name,
            member_roles=payload.member_roles,
        )
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    problem = await ProblemService(db).problems.get_by_id(problem_id)
    assert problem is not None
    return _assignment_response(assignment, problem, include_private=True)


@workflow_router.post("/{problem_id}/assignment/cancel", response_model=AssignmentResponse)
async def admin_cancel_assignment(
    problem_id: UUID,
    payload: CancelAssignmentRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AssignmentResponse:
    """Cancel the active assignment, releasing workloads exactly once."""
    from app.api.v1.problems import _assignment_response

    service = AssignmentService(db)
    try:
        assignment = await service.cancel(
            problem_id, admin, reason=payload.reason, return_to=payload.return_to
        )
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    problem = await ProblemService(db).problems.get_by_id(problem_id)
    assert problem is not None
    return _assignment_response(assignment, problem, include_private=True)


@workflow_router.post("/{problem_id}/close", response_model=ReviewActionResponse)
async def admin_close_problem(
    problem_id: UUID,
    payload: CloseRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ReviewActionResponse:
    """Close a RESOLVED report. Releases team/mentor workloads exactly once."""
    from app.services.solution_service import SolutionService

    service = SolutionService(db)
    try:
        problem = await service.close_problem(problem_id, admin, reason=payload.reason)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    return ReviewActionResponse(
        id=problem.id,
        ticket_number=problem.ticket_number,
        status=problem.status.value,
        reviewed_by=problem.reviewed_by,
        reviewed_at=problem.reviewed_at,
        approved_by=problem.approved_by,
        approved_at=problem.approved_at,
        rejection_reason=problem.rejection_reason,
    )


@workflow_router.get("/eligible-solvers", response_model=list[EligibleSolverSummary])
async def admin_eligible_solvers(
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[EligibleSolverSummary]:
    """All currently eligible solvers with skills for the team picker. Admin only."""
    repo = CandidateRepository(db)
    summaries: list[EligibleSolverSummary] = []
    for user in await repo.eligible_solvers():
        profile = user.student_profile
        assert profile is not None
        summaries.append(
            EligibleSolverSummary(
                user_id=user.id,
                name=user.full_name,
                availability=profile.availability_status.value,
                current_workload=profile.current_workload,
                max_workload=profile.max_workload,
                department=profile.department.value,
                academic_year=profile.academic_year,
                skills=[
                    {
                        "skill_id": str(us.skill_id),
                        "name": us.skill.name if us.skill is not None else str(us.skill_id),
                        "proficiency": us.proficiency_level,
                        "is_verified": us.is_verified,
                        "category": us.skill.category.value
                        if us.skill is not None and hasattr(us.skill.category, "value")
                        else None,
                    }
                    for us in user.user_skills
                ],
            )
        )
    return summaries
