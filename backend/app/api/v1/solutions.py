"""Step 11 APIs: solution submission, mentor review, reporter verification."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.solution import (
    ReadinessResponse,
    ReviewResponse,
    SafeSolutionView,
    SolutionResponse,
    SolutionReviewCreate,
    SolutionSubmit,
    VerificationCreate,
    VerificationResponse,
)
from app.services.auth_service import AuthError
from app.services.solution_service import SolutionService

router = APIRouter(prefix="/problems", tags=["Solutions"])


def _to_http(exc: AuthError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def _solution_response(row: object) -> SolutionResponse:
    from app.models.solution import ProblemSolutionSubmission

    assert isinstance(row, ProblemSolutionSubmission)
    evidence = [str(v) for v in row.evidence_attachment_ids or []]
    return SolutionResponse(
        id=row.id,
        problem_id=row.problem_id,
        assignment_id=row.assignment_id,
        submitted_by_user_id=row.submitted_by_user_id,
        submitter_name=row.submitter.full_name if row.submitter is not None else None,
        revision_number=row.revision_number,
        solution_summary=row.solution_summary,
        root_cause=row.root_cause,
        work_performed=row.work_performed,
        testing_performed=row.testing_performed,
        deployment_notes=row.deployment_notes,
        limitations=row.limitations,
        evidence_attachment_ids=evidence,
        readiness_override_reason=row.readiness_override_reason,
        status=row.status,
        submitted_at=row.submitted_at,
        updated_at=row.updated_at,
        reviews=[
            ReviewResponse(
                id=r.id,
                solution_submission_id=r.solution_submission_id,
                mentor_user_id=r.mentor_user_id,
                mentor_name=r.mentor.full_name if r.mentor is not None else None,
                decision=r.decision,
                review_comment=r.review_comment,
                is_admin_override=r.is_admin_override,
                created_at=r.created_at,
            )
            for r in sorted(row.reviews, key=lambda r: r.created_at)
        ],
    )


@router.get("/{problem_id}/solution/readiness", response_model=ReadinessResponse)
async def get_readiness(
    problem_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReadinessResponse:
    service = SolutionService(db)
    try:
        await service._read_context(problem_id, current_user)
        check = await service.readiness(problem_id)
    except AuthError as exc:
        raise _to_http(exc) from None
    return ReadinessResponse(
        ready=check["ready"],
        reasons=list(check["reasons"]),
        progress_percent=check["progress_percent"],
        done_tasks=check["done_tasks"],
        total_tasks=check["total_tasks"],
        done_milestones=check["done_milestones"],
        total_milestones=check["total_milestones"],
        blocked_tasks=check["blocked_tasks"],
    )


@router.get("/{problem_id}/solutions", response_model=list[SolutionResponse])
async def list_solutions(
    problem_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SolutionResponse]:
    service = SolutionService(db)
    try:
        rows = await service.list_submissions(problem_id, current_user)
    except AuthError as exc:
        raise _to_http(exc) from None
    return [_solution_response(r) for r in rows]


@router.post(
    "/{problem_id}/solutions", response_model=SolutionResponse, status_code=status.HTTP_201_CREATED
)
async def submit_solution(
    problem_id: UUID,
    payload: SolutionSubmit,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SolutionResponse:
    service = SolutionService(db)
    try:
        row = await service.submit_solution(
            problem_id,
            current_user,
            solution_summary=payload.solution_summary,
            root_cause=payload.root_cause,
            work_performed=payload.work_performed,
            testing_performed=payload.testing_performed,
            deployment_notes=payload.deployment_notes,
            limitations=payload.limitations,
            evidence_attachment_ids=payload.evidence_attachment_ids,
            share_evidence_with_reporter=payload.share_evidence_with_reporter,
            override_reason=payload.override_reason,
        )
    except AuthError as exc:
        raise _to_http(exc) from None
    return _solution_response(row)


@router.get("/{problem_id}/solutions/latest", response_model=SolutionResponse)
async def latest_solution(
    problem_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SolutionResponse:
    service = SolutionService(db)
    try:
        await service._read_context(problem_id, current_user)
        row = await service.solutions.latest_for_problem(problem_id)
    except AuthError as exc:
        raise _to_http(exc) from None
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No solution submitted yet")
    return _solution_response(row)


@router.post(
    "/{problem_id}/solutions/{submission_id}/review",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
async def review_solution(
    problem_id: UUID,
    submission_id: UUID,
    payload: SolutionReviewCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReviewResponse:
    service = SolutionService(db)
    try:
        review = await service.review_solution(
            problem_id,
            submission_id,
            current_user,
            decision=payload.decision,
            review_comment=payload.review_comment,
        )
    except AuthError as exc:
        raise _to_http(exc) from None
    mentor_name: str | None = None
    if review.mentor is not None:
        mentor_name = review.mentor.full_name
    return ReviewResponse(
        id=review.id,
        solution_submission_id=review.solution_submission_id,
        mentor_user_id=review.mentor_user_id,
        mentor_name=mentor_name,
        decision=review.decision,
        review_comment=review.review_comment,
        is_admin_override=review.is_admin_override,
        created_at=review.created_at,
    )


@router.get("/{problem_id}/verifications", response_model=list[VerificationResponse])
async def list_verifications(
    problem_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[VerificationResponse]:
    service = SolutionService(db)
    try:
        rows = await service.list_verifications(problem_id, current_user)
    except AuthError as exc:
        raise _to_http(exc) from None
    return [VerificationResponse.model_validate(r) for r in rows]


@router.post(
    "/{problem_id}/verifications",
    response_model=VerificationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def verify_solution(
    problem_id: UUID,
    payload: VerificationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VerificationResponse:
    service = SolutionService(db)
    try:
        row = await service.verify_solution(
            problem_id, current_user, decision=payload.decision, reason=payload.reason
        )
    except AuthError as exc:
        raise _to_http(exc) from None
    return VerificationResponse.model_validate(row)


@router.get("/{problem_id}/solution/safe", response_model=SafeSolutionView)
async def get_safe_solution(
    problem_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SafeSolutionView:
    """Reporter-safe approved solution summary for verification."""
    service = SolutionService(db)
    try:
        view = await service.safe_solution(problem_id, current_user)
    except AuthError as exc:
        raise _to_http(exc) from None
    if view is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No approved solution to verify yet"
        )
    raw_evidence = view["evidence"]
    assert isinstance(raw_evidence, list)
    evidence: list[dict[str, object]] = []
    for entry in raw_evidence:
        assert isinstance(entry, dict)
        evidence.append({str(k): v for k, v in entry.items()})
    testing = view["testing_performed"]
    limitations = view["limitations"]
    return SafeSolutionView(
        revision_number=int(str(view["revision_number"])),
        solution_summary=str(view["solution_summary"]),
        work_performed=str(view["work_performed"]),
        testing_performed=str(testing) if testing is not None else None,
        limitations=str(limitations) if limitations is not None else None,
        status=str(view["status"]),
        submitted_at=str(view["submitted_at"]),
        evidence=evidence,
    )


@router.get("/{problem_id}/solution/evidence/{file_id}/download")
async def download_shared_evidence(
    problem_id: UUID,
    file_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    service = SolutionService(db)
    try:
        file_row, data = await service.download_shared_evidence(problem_id, file_id, current_user)
    except AuthError as exc:
        raise _to_http(exc) from None
    from app.models.workspace import ProblemWorkAttachment

    assert isinstance(file_row, ProblemWorkAttachment)
    return Response(
        content=data,
        media_type=file_row.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{file_row.original_filename}"'},
    )
