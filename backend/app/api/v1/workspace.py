"""Team workspace APIs (Step 10): tasks, milestones, progress, files, discussion."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.workspace import (
    ProblemMilestone,
    ProblemProgressUpdate,
    ProblemTask,
    ProblemWorkAttachment,
)
from app.schemas.problem import CommentResponse
from app.schemas.workspace import (
    DiscussionCreate,
    MilestoneCreate,
    MilestoneResponse,
    MilestoneUpdate,
    ProgressCreate,
    ProgressResponse,
    PublicProgressResponse,
    PublicProgressUpdateView,
    PublicSolutionView,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
    WorkFileResponse,
    WorkspaceMemberView,
    WorkspaceMentorView,
    WorkspaceOverviewResponse,
    WorkspaceProgressView,
    WorkspaceTeamView,
)
from app.services.auth_service import AuthError
from app.services.skill_extraction_service import RequiredSkillService
from app.services.workspace_service import WorkspaceContext, WorkspaceService

router = APIRouter(prefix="/problems", tags=["Workspace"])


def _to_http(exc: AuthError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def _is_overdue(due: datetime | None, finished: bool) -> bool:
    if due is None or finished:
        return False
    now = datetime.now(UTC)
    aware = due if due.tzinfo is not None else due.replace(tzinfo=UTC)
    return aware < now


def _task_response(task: ProblemTask) -> TaskResponse:
    assignee = task.assignee
    creator = task.creator
    finished = task.status in ("DONE", "CANCELLED")
    return TaskResponse(
        id=task.id,
        problem_id=task.problem_id,
        team_id=task.team_id,
        title=task.title,
        description=task.description,
        assigned_to_user_id=task.assigned_to_user_id,
        assignee_name=assignee.full_name if assignee is not None else None,
        created_by_user_id=task.created_by_user_id,
        creator_name=creator.full_name if creator is not None else None,
        status=task.status,
        priority=task.priority,
        due_date=task.due_date,
        order_index=task.order_index,
        blocker_reason=task.blocker_reason,
        is_overdue=_is_overdue(task.due_date, finished),
        created_at=task.created_at,
        updated_at=task.updated_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
    )


def _milestone_response(row: ProblemMilestone) -> MilestoneResponse:
    finished = row.status in ("COMPLETED", "CANCELLED")
    return MilestoneResponse(
        id=row.id,
        problem_id=row.problem_id,
        title=row.title,
        description=row.description,
        target_date=row.target_date,
        status=row.status,
        order_index=row.order_index,
        created_by=row.created_by,
        is_overdue=_is_overdue(row.target_date, finished),
        created_at=row.created_at,
        updated_at=row.updated_at,
        completed_at=row.completed_at,
    )


def _progress_response(row: ProblemProgressUpdate, ctx: WorkspaceContext) -> ProgressResponse:
    author = row.author
    role = None
    if author is not None:
        role = WorkspaceService.role_label_for(author, ctx)
    return ProgressResponse(
        id=row.id,
        problem_id=row.problem_id,
        author_user_id=row.author_user_id,
        author_name=author.full_name if author is not None else None,
        author_role=role,
        summary=row.summary,
        details=row.details,
        blockers=row.blockers,
        next_steps=row.next_steps,
        progress_snapshot=row.progress_snapshot,
        created_at=row.created_at,
    )


def _work_file_response(row: ProblemWorkAttachment, uploader_name: str | None) -> WorkFileResponse:
    return WorkFileResponse(
        id=row.id,
        problem_id=row.problem_id,
        task_id=row.task_id,
        uploaded_by=row.uploaded_by,
        uploader_name=uploader_name,
        original_filename=row.original_filename,
        mime_type=row.mime_type,
        size_bytes=row.size_bytes,
        description=row.description,
        is_knowledge_shareable=bool(row.is_knowledge_shareable),
        created_at=row.created_at,
    )


# ---------- overview ----------


@router.get("/{problem_id}/workspace", response_model=WorkspaceOverviewResponse)
async def get_workspace(
    problem_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceOverviewResponse:
    service = WorkspaceService(db)
    try:
        ctx = await service.require_read(problem_id, current_user)
    except AuthError as exc:
        raise _to_http(exc) from None
    problem = ctx.problem
    percent, done_tasks, total_tasks, done_ms, total_ms = await service.current_progress(problem.id)
    _, required_rows = await RequiredSkillService(db).latest_with_skills(problem.id)
    skill_names = [r.skill.name for r in required_rows if r.skill is not None]
    team_view = None
    mentor_view = None
    assigned_at = None
    if ctx.assignment is not None:
        team = ctx.assignment.team
        team_view = WorkspaceTeamView(
            id=team.id,
            name=team.name,
            display_label=team.name or f"Team · {problem.ticket_number}",
            members=[
                WorkspaceMemberView(
                    user_id=m.user_id,
                    name=m.user.full_name if m.user is not None else None,
                    role_in_team=m.role_in_team or "Member",
                    joined_at=m.joined_at,
                )
                for m in sorted(team.members, key=lambda m: m.joined_at)
                if m.is_active
            ],
        )
        mentor = ctx.assignment.mentor
        profile = mentor.faculty_profile if mentor is not None else None
        mentor_view = WorkspaceMentorView(
            name=mentor.full_name if mentor is not None else None,
            designation=profile.designation if profile is not None else None,
            specialization=profile.specialization if profile is not None else None,
        )
        assigned_at = ctx.assignment.assigned_at
    return WorkspaceOverviewResponse(
        problem_id=problem.id,
        ticket_number=problem.ticket_number,
        title=problem.title,
        status=problem.status.value,
        priority_level=problem.priority_level,
        priority_score=problem.priority_score,
        predicted_category=problem.predicted_category,
        required_skills=skill_names,
        team=team_view,
        mentor=mentor_view,
        assigned_at=assigned_at,
        progress=WorkspaceProgressView(
            percent=percent,
            done_tasks=done_tasks,
            total_tasks=total_tasks,
            done_milestones=done_ms,
            total_milestones=total_ms,
        ),
    )


# ---------- tasks ----------


@router.get("/{problem_id}/tasks", response_model=list[TaskResponse])
async def list_tasks(
    problem_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TaskResponse]:
    service = WorkspaceService(db)
    try:
        ctx = await service.require_read(problem_id, current_user)
        rows = await service.tasks.list_for_problem(ctx.problem.id)
    except AuthError as exc:
        raise _to_http(exc) from None
    return [_task_response(t) for t in rows]


@router.post("/{problem_id}/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    problem_id: UUID,
    payload: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    service = WorkspaceService(db)
    try:
        task = await service.create_task(problem_id, current_user, payload)
    except AuthError as exc:
        raise _to_http(exc) from None
    return _task_response(task)


@router.patch("/{problem_id}/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    problem_id: UUID,
    task_id: UUID,
    payload: TaskUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    service = WorkspaceService(db)
    try:
        task = await service.update_task(problem_id, task_id, current_user, payload)
    except AuthError as exc:
        raise _to_http(exc) from None
    return _task_response(task)


@router.delete("/{problem_id}/tasks/{task_id}", response_model=TaskResponse)
async def cancel_task(
    problem_id: UUID,
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    """Cancel a task (soft: status → CANCELLED, history preserved)."""
    service = WorkspaceService(db)
    try:
        task = await service.cancel_task(problem_id, task_id, current_user)
    except AuthError as exc:
        raise _to_http(exc) from None
    return _task_response(task)


# ---------- milestones ----------


@router.get("/{problem_id}/milestones", response_model=list[MilestoneResponse])
async def list_milestones(
    problem_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MilestoneResponse]:
    service = WorkspaceService(db)
    try:
        ctx = await service.require_read(problem_id, current_user)
        rows = await service.milestones.list_for_problem(ctx.problem.id)
    except AuthError as exc:
        raise _to_http(exc) from None
    return [_milestone_response(m) for m in rows]


@router.post(
    "/{problem_id}/milestones",
    response_model=MilestoneResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_milestone(
    problem_id: UUID,
    payload: MilestoneCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MilestoneResponse:
    service = WorkspaceService(db)
    try:
        row = await service.create_milestone(problem_id, current_user, payload)
    except AuthError as exc:
        raise _to_http(exc) from None
    return _milestone_response(row)


@router.patch("/{problem_id}/milestones/{milestone_id}", response_model=MilestoneResponse)
async def update_milestone(
    problem_id: UUID,
    milestone_id: UUID,
    payload: MilestoneUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MilestoneResponse:
    service = WorkspaceService(db)
    try:
        row = await service.update_milestone(problem_id, milestone_id, current_user, payload)
    except AuthError as exc:
        raise _to_http(exc) from None
    return _milestone_response(row)


# ---------- progress updates ----------


@router.get("/{problem_id}/progress-updates", response_model=list[ProgressResponse])
async def list_progress_updates(
    problem_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ProgressResponse]:
    service = WorkspaceService(db)
    try:
        ctx = await service.require_read(problem_id, current_user)
        rows = await service.progress.list_for_problem(ctx.problem.id, limit=limit)
    except AuthError as exc:
        raise _to_http(exc) from None
    return [_progress_response(r, ctx) for r in rows]


@router.post(
    "/{problem_id}/progress-updates",
    response_model=ProgressResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_progress_update(
    problem_id: UUID,
    payload: ProgressCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProgressResponse:
    service = WorkspaceService(db)
    try:
        row = await service.post_progress(problem_id, current_user, payload)
        ctx = await service.require_read(problem_id, current_user)
    except AuthError as exc:
        raise _to_http(exc) from None
    return _progress_response(row, ctx)


# ---------- work files ----------


@router.get("/{problem_id}/work-files", response_model=list[WorkFileResponse])
async def list_work_files(
    problem_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WorkFileResponse]:
    service = WorkspaceService(db)
    try:
        ctx = await service.require_read(problem_id, current_user)
        rows = await service.work_files.list_for_problem(ctx.problem.id)
    except AuthError as exc:
        raise _to_http(exc) from None
    return [_work_file_response(r, None) for r in rows]


@router.post(
    "/{problem_id}/work-files",
    response_model=WorkFileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_work_file(
    problem_id: UUID,
    file: UploadFile = File(...),
    task_id: UUID | None = Form(None),
    description: str | None = Form(None),
    is_knowledge_shareable: bool = Form(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkFileResponse:
    service = WorkspaceService(db)
    try:
        row = await service.upload_work_file(
            problem_id,
            current_user,
            file,
            task_id=task_id,
            description=description,
            is_knowledge_shareable=is_knowledge_shareable,
        )
    except AuthError as exc:
        raise _to_http(exc) from None
    return _work_file_response(row, current_user.full_name)


@router.patch("/{problem_id}/work-files/{file_id}/shareable", response_model=WorkFileResponse)
async def set_work_file_shareable(
    problem_id: UUID,
    file_id: UUID,
    shareable: bool = Query(True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkFileResponse:
    """Opt a work file into/out of Knowledge Repository sharing (default private)."""
    service = WorkspaceService(db)
    try:
        row = await service.set_work_file_shareable(
            problem_id, file_id, current_user, shareable=shareable
        )
    except AuthError as exc:
        raise _to_http(exc) from None
    uploader = await db.get(User, row.uploaded_by)
    return _work_file_response(
        row, uploader.full_name if uploader is not None else current_user.full_name
    )


@router.delete("/{problem_id}/work-files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_work_file(    problem_id: UUID,
    file_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = WorkspaceService(db)
    try:
        await service.delete_work_file(problem_id, file_id, current_user)
    except AuthError as exc:
        raise _to_http(exc) from None
    return None


@router.get("/{problem_id}/work-files/{file_id}/download")
async def download_work_file(
    problem_id: UUID,
    file_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    service = WorkspaceService(db)
    try:
        row, data = await service.read_work_file(problem_id, file_id, current_user)
    except AuthError as exc:
        raise _to_http(exc) from None
    return Response(
        content=data,
        media_type=row.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{row.original_filename}"'},
    )


# ---------- internal discussion ----------


@router.get("/{problem_id}/discussion", response_model=list[CommentResponse])
async def list_discussion(
    problem_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CommentResponse]:
    service = WorkspaceService(db)
    try:
        rows = await service.list_discussion(problem_id, current_user)
    except AuthError as exc:
        raise _to_http(exc) from None
    return [
        CommentResponse(
            id=c.id,
            problem_id=c.problem_id,
            author_id=c.author_id,
            author_name=c.author.full_name if c.author is not None else None,
            content=c.content,
            is_internal=c.is_internal,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in rows
    ]


@router.post(
    "/{problem_id}/discussion",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_discussion(
    problem_id: UUID,
    payload: DiscussionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommentResponse:
    service = WorkspaceService(db)
    try:
        comment = await service.post_discussion(problem_id, current_user, payload.content)
    except AuthError as exc:
        raise _to_http(exc) from None
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


# ---------- reporter-safe public progress ----------


@router.get("/{problem_id}/public-progress", response_model=PublicProgressResponse)
async def get_public_progress(
    problem_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PublicProgressResponse:
    """Safe progress for the reporter (and anyone with problem visibility).

    Exposes counts, the cached-then-recomputed percent, team/mentor names,
    and public-safe update summaries — never internal tasks, blockers,
    discussion, files, identifiers, or workload data.
    """
    from app.services.assignment_service import AssignmentService
    from app.services.problem_service import ProblemService

    problems = ProblemService(db)
    try:
        problem = await problems.get_visible_problem(current_user, problem_id)
    except AuthError as exc:
        raise _to_http(exc) from None

    service = WorkspaceService(db)
    percent, done_tasks, total_tasks, done_ms, total_ms = await service.current_progress(problem.id)
    assignment_service = AssignmentService(db)
    assignment = await assignment_service.active_for_problem(problem.id)
    team_name = None
    member_names: list[str] = []
    mentor_name = None
    mentor_id = None
    if assignment is not None:
        team_name = assignment.team.name or f"Team · {problem.ticket_number}"
        member_names = [
            m.user.full_name
            for m in sorted(assignment.team.members, key=lambda m: m.joined_at)
            if m.is_active and m.user is not None
        ]
        if assignment.mentor is not None:
            mentor_name = assignment.mentor.full_name
        mentor_id = assignment.mentor_user_id
    else:
        # Step 11: closed reports keep their last team/mentor names visible.
        history = await assignment_service.history_for_problem(problem.id)
        if history:
            last = history[0]
            team_name = last.team.name or f"Team · {problem.ticket_number}"
            member_names = [
                m.user.full_name
                for m in sorted(last.team.members, key=lambda m: m.joined_at)
                if m.user is not None
            ]
            if last.mentor is not None:
                mentor_name = last.mentor.full_name
            mentor_id = last.mentor_user_id
    updates = await service.progress.list_for_problem(problem.id, limit=5)
    safe_updates = [
        PublicProgressUpdateView(
            summary=u.summary,
            progress_snapshot=u.progress_snapshot,
            author_role=(
                "Mentor"
                if u.author_user_id == mentor_id
                else ("Admin" if u.author is not None and u.author.role.value == "ADMIN" else "Team")
            ),
            created_at=u.created_at,
        )
        for u in updates
    ]
    from app.services.solution_service import SolutionService

    safe_view = await SolutionService(db).safe_solution(problem.id, current_user)
    solution = None
    if safe_view is not None:
        raw_evidence = safe_view["evidence"]
        assert isinstance(raw_evidence, list)
        evidence: list[dict[str, object]] = []
        for entry in raw_evidence:
            assert isinstance(entry, dict)
            evidence.append({str(k): v for k, v in entry.items()})
        testing = safe_view["testing_performed"]
        limitations = safe_view["limitations"]
        solution = PublicSolutionView(
            revision_number=int(str(safe_view["revision_number"])),
            solution_summary=str(safe_view["solution_summary"]),
            work_performed=str(safe_view["work_performed"]),
            testing_performed=str(testing) if testing is not None else None,
            limitations=str(limitations) if limitations is not None else None,
            status=str(safe_view["status"]),
            submitted_at=str(safe_view["submitted_at"]),
            evidence=evidence,
        )
    return PublicProgressResponse(
        problem_id=problem.id,
        ticket_number=problem.ticket_number,
        title=problem.title,
        status=problem.status.value,
        progress_percent=percent,
        completed_tasks=done_tasks,
        total_tasks=total_tasks,
        completed_milestones=done_ms,
        total_milestones=total_ms,
        team_name=team_name,
        team_member_names=member_names,
        mentor_name=mentor_name,
        assignment_active=assignment is not None,
        recent_updates=safe_updates,
        solution=solution,
    )
