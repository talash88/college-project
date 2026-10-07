"""Team workspace service (Step 10).

Real collaborative work on ASSIGNED problems: tasks, milestones, progress
updates, work files, and internal discussion. Every write requires an
ACTIVE assignment; cancelled/reassigned history is preserved read-only
for admins. Progress is always derived from live task/milestone state —
never supplied by the client.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import (
    MILESTONE_TRANSITIONS,
    TASK_TRANSITIONS,
    MilestoneStatus,
    ProblemEventType,
    ProblemStatus,
    TaskPriority,
    TaskStatus,
    UserRole,
)
from app.models.assignment import ProblemAssignment
from app.models.problem import Problem, ProblemComment
from app.models.user import User
from app.models.workspace import (
    ProblemMilestone,
    ProblemProgressUpdate,
    ProblemTask,
    ProblemWorkAttachment,
)
from app.repositories.problem_repository import ActivityRepository, CommentRepository
from app.repositories.workspace_repository import (
    MilestoneRepository,
    ProgressRepository,
    TaskRepository,
    WorkAttachmentRepository,
    compute_progress,
    get_problem_locked,
    has_work_started,
)
from app.schemas.workspace import (
    MilestoneCreate,
    MilestoneUpdate,
    ProgressCreate,
    TaskCreate,
    TaskUpdate,
)
from app.services.auth_service import AuthError
from app.services.problem_service import ProblemService
from app.storage.base import sanitize_filename, sniff_mime
from app.storage.local import LocalAttachmentStorage, resolve_storage_dir

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 1024 * 1024  # 1 MiB
MAX_WORK_FILES_PER_PROBLEM = 20


@dataclass
class WorkspaceContext:
    problem: Problem
    assignment: ProblemAssignment | None
    is_admin: bool
    is_mentor: bool
    is_member: bool
    active_member_ids: set[UUID]


def _role_label(user: User, ctx: WorkspaceContext) -> str:
    if user.role == UserRole.ADMIN:
        return "Admin"
    if ctx.is_mentor and user.id == (ctx.assignment.mentor_user_id if ctx.assignment else None):
        return "Mentor"
    return "Team"


class WorkspaceService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.problems = ProblemService(session)
        self.tasks = TaskRepository(session)
        self.milestones = MilestoneRepository(session)
        self.progress = ProgressRepository(session)
        self.work_files = WorkAttachmentRepository(session)
        self.activities = ActivityRepository(session)
        self.comments = CommentRepository(session)
        self.storage = LocalAttachmentStorage(resolve_storage_dir(settings.STORAGE_DIR))
        self.max_bytes = settings.MAX_ATTACHMENT_SIZE_MB * 1024 * 1024
        self.allowed = set(settings.ALLOWED_ATTACHMENT_MIME_TYPES)

    # ---------- context & access ----------

    async def _context(self, problem_id: UUID, user: User) -> WorkspaceContext:
        """Resolve the workspace context. 404 when the problem is invisible;
        the reporter and outsiders never reach workspace internals."""
        from app.services.assignment_service import AssignmentService

        problem = await self.problems.get_visible_problem(user, problem_id)
        is_admin = user.role == UserRole.ADMIN
        assignment = await AssignmentService(self.session).active_for_problem(problem_id)
        active_member_ids: set[UUID] = set()
        if assignment is not None:
            active_member_ids = {
                m.user_id for m in assignment.team.members if m.is_active
            }
        is_mentor = assignment is not None and assignment.mentor_user_id == user.id
        is_member = user.id in active_member_ids
        return WorkspaceContext(
            problem=problem,
            assignment=assignment,
            is_admin=is_admin,
            is_mentor=is_mentor,
            is_member=is_member,
            active_member_ids=active_member_ids,
        )

    def _require_insider(self, ctx: WorkspaceContext, user: User) -> None:
        """Workspace internals: active team member, assigned mentor, or admin."""
        if ctx.is_admin or ctx.is_mentor or ctx.is_member:
            return
        raise AuthError(403, "Only the assigned team, mentor, or an admin can access the workspace.")

    def _require_active_assignment(self, ctx: WorkspaceContext) -> ProblemAssignment:
        if ctx.assignment is None:
            raise AuthError(
                409,
                "No active assignment for this report; workspace work is paused "
                "until it is (re-)assigned.",
            )
        return ctx.assignment

    async def require_read(
        self, problem_id: UUID, user: User
    ) -> WorkspaceContext:
        """Read access to workspace internals (reporter excluded: safe view only)."""
        from app.services.assignment_service import AssignmentService

        ctx = await self._context(problem_id, user)
        if ctx.is_admin:
            return ctx
        if (ctx.is_mentor or ctx.is_member) and ctx.assignment is not None:
            return ctx
        # Step 11: verification/resolution/closure history stays readable for
        # past members/mentors (writes remain blocked by status gates).
        # Removed members during active work still lose access immediately.
        if ctx.problem.status in (
            ProblemStatus.AWAITING_VERIFICATION,
            ProblemStatus.RESOLVED,
            ProblemStatus.CLOSED,
        ):
            history = await AssignmentService(self.session).history_for_problem(ctx.problem.id)
            involved = any(
                any(m.user_id == user.id for m in past.team.members)
                or past.mentor_user_id == user.id
                for past in history
            )
            if involved:
                return ctx
            if ctx.problem.reporter_id == user.id:
                raise AuthError(
                    403, "Reporters see the safe progress view only, not the workspace."
                )
            raise AuthError(404, "Problem not found")
        self._require_insider(ctx, user)
        return ctx  # unreachable: _require_insider always raises here

    async def require_write(
        self, problem_id: UUID, user: User
    ) -> WorkspaceContext:
        """Write access: insider plus an ACTIVE assignment (history preserved)."""
        from app.services.assignment_service import AssignmentService

        ctx = await self._context(problem_id, user)
        try:
            self._require_insider(ctx, user)
        except AuthError:
            # Step 11: past members/mentors get a clear read-only signal on
            # resolved/closed reports instead of a bare 403.
            if ctx.problem.status in (ProblemStatus.RESOLVED, ProblemStatus.CLOSED):
                history = await AssignmentService(self.session).history_for_problem(
                    ctx.problem.id
                )
                involved = any(
                    any(m.user_id == user.id for m in past.team.members)
                    or past.mentor_user_id == user.id
                    for past in history
                )
                if involved:
                    raise AuthError(
                        409,
                        f"Workspace is read-only while the report is {ctx.problem.status.value}.",
                    ) from None
            raise
        self._require_active_assignment(ctx)
        problem = ctx.problem
        if problem.status not in (ProblemStatus.ASSIGNED, ProblemStatus.IN_PROGRESS):
            raise AuthError(
                409,
                f"Workspace work is paused while the report is {problem.status.value}.",
            )
        return ctx

    # ---------- progress & work-start ----------

    async def current_progress(self, problem_id: UUID) -> tuple[float, int, int, int, int]:
        tasks = await self.tasks.list_for_problem(problem_id)
        milestones = await self.milestones.list_for_problem(problem_id)
        return compute_progress(tasks, milestones)

    async def _sync_progress(self, problem: Problem) -> float:
        percent, _, _, _, _ = await self.current_progress(problem.id)
        problem.progress_percent = percent
        return percent

    async def _maybe_start_work(
        self, problem_id: UUID, actor: UUID | None, *, trigger: str
    ) -> bool:
        """ASSIGNED → IN_PROGRESS exactly once, guarded by the WORK_STARTED event."""
        problem = await get_problem_locked(self.session, problem_id)
        if problem is None or problem.status != ProblemStatus.ASSIGNED:
            return False
        if await has_work_started(self.session, problem_id):
            return False
        old = problem.status
        problem.status = ProblemStatus.IN_PROGRESS
        await self.activities.log(
            problem_id=problem.id,
            event_type=ProblemEventType.WORK_STARTED,
            actor_user_id=actor,
            old_status=old.value,
            new_status=ProblemStatus.IN_PROGRESS.value,
            message=f"Work started ({trigger}).",
        )
        await self.session.flush()
        return True

    async def _log(
        self,
        problem_id: UUID,
        event: ProblemEventType,
        actor: UUID | None,
        *,
        message: str | None = None,
    ) -> None:
        await self.activities.log(
            problem_id=problem_id,
            event_type=event,
            actor_user_id=actor,
            message=message,
        )
        await self.session.flush()

    # ---------- tasks ----------

    def _require_valid_assignee(self, ctx: WorkspaceContext, assignee_id: UUID) -> None:
        """Assignees must be ACTIVE members of this problem's active team."""
        assert ctx.assignment is not None
        if assignee_id not in ctx.active_member_ids:
            raise AuthError(
                422,
                "Task assignee must be an active member of this problem's team.",
            )
        if ctx.is_mentor and assignee_id == ctx.assignment.mentor_user_id:
            raise AuthError(422, "The mentor cannot be a task assignee.")
        if assignee_id == ctx.assignment.mentor_user_id:
            raise AuthError(422, "The mentor cannot be a task assignee.")

    def _check_task_create_assignment(
        self, ctx: WorkspaceContext, user: User, assignee_id: UUID | None
    ) -> None:
        if assignee_id is None:
            return
        self._require_valid_assignee(ctx, assignee_id)
        if ctx.is_admin or ctx.is_mentor:
            return
        # Solver rule: may create unassigned tasks or assign to self only.
        if assignee_id != user.id:
            raise AuthError(403, "Team members may only assign tasks to themselves.")

    def _can_touch_task(self, ctx: WorkspaceContext, user: User, task: ProblemTask) -> bool:
        if ctx.is_admin or ctx.is_mentor:
            return True
        return task.created_by_user_id == user.id or task.assigned_to_user_id == user.id

    @staticmethod
    def _validate_task_transition(task: ProblemTask, target: str, *, actor_is_privileged: bool) -> None:
        if target == task.status:
            return
        if task.status == "DONE":
            if not actor_is_privileged:
                raise AuthError(403, "Only the mentor or an admin can reopen a completed task.")
            if target in ("TODO", "IN_PROGRESS"):
                return
            raise AuthError(409, f"Cannot move task from DONE to {target}.")
        try:
            current = TaskStatus(task.status)
            wanted = TaskStatus(target)
        except ValueError as exc:
            raise AuthError(422, f"Unknown task status: {target}") from exc
        if wanted not in TASK_TRANSITIONS[current]:
            raise AuthError(
                409,
                f"Cannot move task from {current.value} to {wanted.value}.",
            )

    async def create_task(self, problem_id: UUID, user: User, data: TaskCreate) -> ProblemTask:
        ctx = await self.require_write(problem_id, user)
        assignment = self._require_active_assignment(ctx)
        self._check_task_create_assignment(ctx, user, data.assigned_to_user_id)
        title = data.title.strip()
        if len(title) < 3:
            raise AuthError(422, "Task title is too short")
        task = await self.tasks.create(
            problem_id=ctx.problem.id,
            team_id=assignment.team_id,
            title=title,
            description=(data.description or "").strip() or None,
            assigned_to_user_id=data.assigned_to_user_id,
            created_by_user_id=user.id,
            status=TaskStatus.TODO.value,
            priority=TaskPriority(data.priority).value,
            due_date=data.due_date,
            order_index=data.order_index
            if data.order_index is not None
            else await self.tasks.next_order_index(ctx.problem.id),
            blocker_reason=None,
        )
        await self._log(
            ctx.problem.id, ProblemEventType.TASK_CREATED, user.id, message=f"Task created: {title}."
        )
        await self._sync_progress(ctx.problem)
        await self.session.commit()
        if task.assigned_to_user_id is not None and task.assigned_to_user_id != user.id:
            # Step 11 hook: task-assignment notification, best-effort AFTER
            # the core commit so delivery can never break task creation.
            task_id, ticket = task.id, ctx.problem.ticket_number
            try:
                from app.core.enums import NotificationType
                from app.services.notification_service import NotificationService

                await NotificationService(self.session).notify_user(
                    task.assigned_to_user_id,
                    NotificationType.TASK_ASSIGNED,
                    f"Task assigned on {ticket}",
                    f"'{title}' was assigned to you by {user.full_name}.",
                    problem_id=ctx.problem.id,
                    related_entity_type="task",
                    related_entity_id=task_id,
                )
                await self.session.commit()
            except Exception:
                logger.warning("task assignment notification failed for problem %s", ticket)
                await self.session.rollback()
        refreshed = await self.tasks.get(task.id)
        assert refreshed is not None
        return refreshed

    async def update_task(
        self, problem_id: UUID, task_id: UUID, user: User, data: TaskUpdate
    ) -> ProblemTask:
        ctx = await self.require_write(problem_id, user)
        task = await self.tasks.get(task_id)
        if task is None or task.problem_id != ctx.problem.id:
            raise AuthError(404, "Task not found")
        privileged = ctx.is_admin or ctx.is_mentor
        if not self._can_touch_task(ctx, user, task):
            raise AuthError(403, "Only the task assignee, creator, mentor, or admin can edit it.")

        fields = data.model_dump(exclude_unset=True)
        new_status = fields.get("status")
        new_assignee = fields.get("assigned_to_user_id") if "assigned_to_user_id" in fields else None
        assignee_touched = "assigned_to_user_id" in fields

        if assignee_touched:
            if new_assignee is None:
                if not privileged and task.assigned_to_user_id not in (None, user.id):
                    raise AuthError(403, "Only the mentor or an admin can unassign someone else's task.")
                task.assigned_to_user_id = None
            else:
                self._require_valid_assignee(ctx, new_assignee)
                if not privileged:
                    current = task.assigned_to_user_id
                    if new_assignee != user.id or current not in (None, user.id):
                        raise AuthError(403, "Team members may only assign tasks to themselves.")
                old_assignee = task.assigned_to_user_id
                task.assigned_to_user_id = new_assignee
                if old_assignee != new_assignee:
                    await self._log(
                        ctx.problem.id,
                        ProblemEventType.TASK_REASSIGNED,
                        user.id,
                        message=f"Task reassigned: {task.title}.",
                    )

        if "title" in fields and fields["title"] is not None:
            title = str(fields["title"]).strip()
            if len(title) < 3:
                raise AuthError(422, "Task title is too short")
            task.title = title
        if "description" in fields:
            task.description = (fields["description"] or "").strip() or None
        if "priority" in fields and fields["priority"] is not None:
            task.priority = TaskPriority(str(fields["priority"])).value
        if "due_date" in fields:
            task.due_date = fields["due_date"]
        if "order_index" in fields and fields["order_index"] is not None:
            task.order_index = int(fields["order_index"])

        status_changed = False
        if new_status is not None and new_status != task.status:
            self._validate_task_transition(task, str(new_status), actor_is_privileged=privileged)
            if str(new_status) == "BLOCKED" and not (fields.get("blocker_reason") or task.blocker_reason):
                raise AuthError(422, "A blocker reason is required to block a task.")
            old_status = task.status
            task.status = str(new_status)
            now = datetime.now(UTC)
            if task.status == "IN_PROGRESS" and old_status != "IN_PROGRESS":
                task.started_at = task.started_at or now
            if task.status == "DONE":
                task.completed_at = now
            status_changed = True
        if "blocker_reason" in fields:
            reason = (fields["blocker_reason"] or "").strip() or None
            if task.status == "BLOCKED" and not reason:
                raise AuthError(422, "A blocker reason is required while a task is blocked.")
            task.blocker_reason = reason

        event: ProblemEventType | None = None
        if status_changed:
            if task.status == "IN_PROGRESS":
                event = ProblemEventType.TASK_STARTED
            elif task.status == "BLOCKED":
                event = ProblemEventType.TASK_BLOCKED
            elif task.status == "DONE":
                event = ProblemEventType.TASK_COMPLETED
            elif task.status == "CANCELLED":
                event = ProblemEventType.TASK_CANCELLED
            else:
                event = ProblemEventType.TASK_UPDATED
        elif assignee_touched or any(k in fields for k in ("title", "description", "priority", "due_date")):
            event = ProblemEventType.TASK_UPDATED
        if event is not None:
            await self._log(
                ctx.problem.id, event, user.id, message=f"Task {task.status.lower()}: {task.title}."
            )
        await self._sync_progress(ctx.problem)
        await self.session.commit()

        if task.status == "IN_PROGRESS":
            await self._maybe_start_work(ctx.problem.id, user.id, trigger=f"task '{task.title}' started")
            await self.session.commit()
        if task.status == "BLOCKED" and ctx.assignment is not None:
            # Step 11 hook: blocked-task notification, best-effort AFTER core commit.
            task_id, ticket = task.id, ctx.problem.ticket_number
            blocker_text = task.blocker_reason or "No reason given."
            try:
                from app.core.enums import NotificationType
                from app.services.notification_service import NotificationService

                notify = NotificationService(self.session)
                await notify.notify_team(
                    ctx.assignment,
                    NotificationType.TASK_BLOCKED,
                    f"Task blocked on {ticket}",
                    f"'{task.title}' is blocked: {blocker_text}",
                    problem_id=ctx.problem.id,
                    exclude_user_id=user.id,
                    related_entity_type="task",
                    related_entity_id=task_id,
                )
                await notify.notify_mentor(
                    ctx.assignment,
                    NotificationType.TASK_BLOCKED,
                    f"Task blocked on {ticket}",
                    f"'{task.title}' is blocked: {blocker_text}",
                    problem_id=ctx.problem.id,
                    related_entity_type="task",
                    related_entity_id=task_id,
                )
                await self.session.commit()
            except Exception:
                logger.warning("task blocked notification failed for problem %s", ticket)
                await self.session.rollback()
        refreshed = await self.tasks.get(task.id)
        assert refreshed is not None
        return refreshed

    async def cancel_task(self, problem_id: UUID, task_id: UUID, user: User) -> ProblemTask:
        ctx = await self.require_write(problem_id, user)
        task = await self.tasks.get(task_id)
        if task is None or task.problem_id != ctx.problem.id:
            raise AuthError(404, "Task not found")
        if not self._can_touch_task(ctx, user, task):
            raise AuthError(403, "Only the task assignee, creator, mentor, or admin can cancel it.")
        self._validate_task_transition(
            task, "CANCELLED", actor_is_privileged=ctx.is_admin or ctx.is_mentor
        )
        task.status = TaskStatus.CANCELLED.value
        await self._log(
            ctx.problem.id, ProblemEventType.TASK_CANCELLED, user.id, message=f"Task cancelled: {task.title}."
        )
        await self._sync_progress(ctx.problem)
        await self.session.commit()
        refreshed = await self.tasks.get(task.id)
        assert refreshed is not None
        return refreshed

    # ---------- milestones ----------

    def _require_milestone_authority(self, ctx: WorkspaceContext) -> None:
        if not (ctx.is_admin or ctx.is_mentor):
            raise AuthError(403, "Only the mentor or an admin can manage milestones.")

    async def create_milestone(
        self, problem_id: UUID, user: User, data: MilestoneCreate
    ) -> ProblemMilestone:
        ctx = await self.require_write(problem_id, user)
        self._require_milestone_authority(ctx)
        title = data.title.strip()
        if len(title) < 3:
            raise AuthError(422, "Milestone title is too short")
        row = await self.milestones.create(
            problem_id=ctx.problem.id,
            title=title,
            description=(data.description or "").strip() or None,
            target_date=data.target_date,
            status=MilestoneStatus.PLANNED.value,
            order_index=data.order_index
            if data.order_index is not None
            else await self.milestones.next_order_index(ctx.problem.id),
            created_by=user.id,
        )
        await self._log(
            ctx.problem.id, ProblemEventType.MILESTONE_CREATED, user.id, message=f"Milestone created: {title}."
        )
        await self._sync_progress(ctx.problem)
        await self.session.commit()
        refreshed = await self.milestones.get(row.id)
        assert refreshed is not None
        return refreshed

    @staticmethod
    def _validate_milestone_transition(row: ProblemMilestone, target: str) -> None:
        if target == row.status:
            return
        try:
            current = MilestoneStatus(row.status)
            wanted = MilestoneStatus(target)
        except ValueError as exc:
            raise AuthError(422, f"Unknown milestone status: {target}") from exc
        if wanted not in MILESTONE_TRANSITIONS[current]:
            raise AuthError(409, f"Cannot move milestone from {current.value} to {wanted.value}.")

    async def update_milestone(
        self, problem_id: UUID, milestone_id: UUID, user: User, data: MilestoneUpdate
    ) -> ProblemMilestone:
        ctx = await self.require_write(problem_id, user)
        self._require_milestone_authority(ctx)
        row = await self.milestones.get(milestone_id)
        if row is None or row.problem_id != ctx.problem.id:
            raise AuthError(404, "Milestone not found")
        fields = data.model_dump(exclude_unset=True)
        if "title" in fields and fields["title"] is not None:
            title = str(fields["title"]).strip()
            if len(title) < 3:
                raise AuthError(422, "Milestone title is too short")
            row.title = title
        if "description" in fields:
            row.description = (fields["description"] or "").strip() or None
        if "target_date" in fields:
            row.target_date = fields["target_date"]
        if "order_index" in fields and fields["order_index"] is not None:
            row.order_index = int(fields["order_index"])
        status_changed = False
        if fields.get("status") is not None and fields["status"] != row.status:
            self._validate_milestone_transition(row, str(fields["status"]))
            row.status = str(fields["status"])
            if row.status == "COMPLETED":
                row.completed_at = datetime.now(UTC)
            status_changed = True
        if status_changed:
            event = {
                "IN_PROGRESS": ProblemEventType.MILESTONE_STARTED,
                "COMPLETED": ProblemEventType.MILESTONE_COMPLETED,
                "MISSED": ProblemEventType.MILESTONE_MISSED,
            }.get(row.status, ProblemEventType.MILESTONE_CREATED)
            await self._log(
                ctx.problem.id, event, user.id, message=f"Milestone {row.status.lower()}: {row.title}."
            )
        else:
            await self._log(
                ctx.problem.id,
                ProblemEventType.MILESTONE_CREATED,
                user.id,
                message=f"Milestone updated: {row.title}.",
            )
        await self._sync_progress(ctx.problem)
        await self.session.commit()
        if row.status == "IN_PROGRESS":
            await self._maybe_start_work(
                ctx.problem.id, user.id, trigger=f"milestone '{row.title}' started"
            )
            await self.session.commit()
        refreshed = await self.milestones.get(row.id)
        assert refreshed is not None
        return refreshed

    # ---------- progress updates ----------

    async def post_progress(
        self, problem_id: UUID, user: User, data: ProgressCreate
    ) -> ProblemProgressUpdate:
        ctx = await self.require_write(problem_id, user)
        summary = data.summary.strip()
        if len(summary) < 5:
            raise AuthError(422, "Progress summary is too short")
        percent = await self._sync_progress(ctx.problem)
        row = await self.progress.create(
            problem_id=ctx.problem.id,
            author_user_id=user.id,
            summary=summary,
            details=(data.details or "").strip() or None,
            blockers=(data.blockers or "").strip() or None,
            next_steps=(data.next_steps or "").strip() or None,
            progress_snapshot=percent,
        )
        await self._log(
            ctx.problem.id, ProblemEventType.PROGRESS_UPDATED, user.id, message=f"Progress update: {summary[:200]}"
        )
        await self.session.commit()
        await self._maybe_start_work(ctx.problem.id, user.id, trigger="first progress update")
        await self.session.commit()
        latest = await self.progress.latest_for_problem(ctx.problem.id)
        assert latest is not None
        return latest if latest.id == row.id else row

    # ---------- work files ----------

    async def _read_limited(self, upload: UploadFile) -> bytes:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = await upload.read(_CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > self.max_bytes:
                raise AuthError(413, f"File too large (max {settings.MAX_ATTACHMENT_SIZE_MB} MB)")
            chunks.append(chunk)
        return b"".join(chunks)

    async def upload_work_file(
        self,
        problem_id: UUID,
        user: User,
        upload: UploadFile,
        *,
        task_id: UUID | None = None,
        description: str | None = None,
        is_knowledge_shareable: bool = False,
    ) -> ProblemWorkAttachment:
        ctx = await self.require_write(problem_id, user)
        existing = await self.work_files.list_for_problem(ctx.problem.id)
        if len(existing) >= MAX_WORK_FILES_PER_PROBLEM:
            raise AuthError(409, f"At most {MAX_WORK_FILES_PER_PROBLEM} work files per report")
        if task_id is not None:
            task = await self.tasks.get(task_id)
            if task is None or task.problem_id != ctx.problem.id:
                raise AuthError(404, "Task not found for this report")

        declared = (upload.content_type or "").split(";")[0].strip().lower()
        if declared not in self.allowed:
            raise AuthError(415, f"Unsupported file type: {declared or 'unknown'}")
        data = await self._read_limited(upload)
        if not data:
            raise AuthError(422, "Uploaded file is empty")
        sniffed = sniff_mime(data)
        if sniffed != declared:
            raise AuthError(415, "File content does not match its declared type")

        original = sanitize_filename(upload.filename or "upload")
        stored = self.storage.build_stored_filename(declared)
        await self.storage.save(stored, data)
        try:
            row = await self.work_files.create(
                problem_id=ctx.problem.id,
                task_id=task_id,
                uploaded_by=user.id,
                original_filename=original,
                storage_key=stored,
                mime_type=declared,
                size_bytes=len(data),
                description=(description or "").strip() or None,
                is_reporter_visible=False,
                is_knowledge_shareable=bool(is_knowledge_shareable),
            )
            await self._log(
                ctx.problem.id,
                ProblemEventType.WORK_FILE_ADDED,
                user.id,
                message=f"Work file added: {original}",
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            await self.storage.delete(stored)
            raise
        refreshed = await self.work_files.get(row.id)
        assert refreshed is not None
        return refreshed

    async def delete_work_file(self, problem_id: UUID, file_id: UUID, user: User) -> None:
        ctx = await self.require_write(problem_id, user)
        row = await self.work_files.get(file_id)
        if row is None or row.problem_id != ctx.problem.id:
            raise AuthError(404, "Work file not found")
        if not (ctx.is_admin or ctx.is_mentor or row.uploaded_by == user.id):
            raise AuthError(403, "Only the uploader, mentor, or admin can remove a work file.")
        name = row.original_filename
        storage_key = row.storage_key
        await self.work_files.delete(row)
        await self._log(
            ctx.problem.id, ProblemEventType.WORK_FILE_REMOVED, user.id, message=f"Work file removed: {name}"
        )
        await self.session.commit()
        await self.storage.delete(storage_key)

    async def set_work_file_shareable(
        self, problem_id: UUID, file_id: UUID, user: User, *, shareable: bool
    ) -> ProblemWorkAttachment:
        """Opt a work file into/out of knowledge sharing. Default private.

        Only the uploader, the mentor, or an admin may change the flag.
        """
        ctx = await self.require_write(problem_id, user)
        row = await self.work_files.get(file_id)
        if row is None or row.problem_id != ctx.problem.id:
            raise AuthError(404, "Work file not found")
        if not (ctx.is_admin or ctx.is_mentor or row.uploaded_by == user.id):
            raise AuthError(403, "Only the uploader, mentor, or admin can share a work file.")
        row.is_knowledge_shareable = bool(shareable)
        await self.session.commit()
        refreshed = await self.work_files.get(row.id)
        assert refreshed is not None
        return refreshed

    async def read_work_file(self, problem_id: UUID, file_id: UUID, user: User) -> tuple[ProblemWorkAttachment, bytes]:
        ctx = await self.require_read(problem_id, user)
        row = await self.work_files.get(file_id)
        if row is None or row.problem_id != ctx.problem.id:
            raise AuthError(404, "Work file not found")
        if "/" in row.storage_key or "\\" in row.storage_key:
            raise AuthError(500, "Stored file reference is invalid")
        from pathlib import Path

        root = resolve_storage_dir(settings.STORAGE_DIR)
        target = root / Path(row.storage_key).name
        try:
            import asyncio

            data = await asyncio.to_thread(target.read_bytes)
        except FileNotFoundError as exc:
            raise AuthError(404, "Stored file is missing") from exc
        return row, data

    # ---------- internal discussion (reuses ProblemComment.is_internal) ----------

    async def list_discussion(self, problem_id: UUID, user: User) -> list[ProblemComment]:
        ctx = await self.require_read(problem_id, user)
        problem = await self.problems.problems.get_by_id(ctx.problem.id)
        assert problem is not None
        return sorted(
            [c for c in problem.comments if c.is_internal], key=lambda c: c.created_at
        )

    async def post_discussion(self, problem_id: UUID, user: User, content: str) -> ProblemComment:
        ctx = await self.require_write(problem_id, user)
        text = content.strip()
        if not text:
            raise AuthError(422, "Discussion message is required")
        if len(text) > 2000:
            raise AuthError(422, "Discussion message is too long (max 2000 characters).")
        comment = await self.comments.create(
            problem_id=ctx.problem.id,
            author_id=user.id,
            content=text,
            is_internal=True,
        )
        await self._log(
            ctx.problem.id, ProblemEventType.COMMENT_ADDED, user.id, message="Workspace discussion message."
        )
        await self.session.commit()
        await self.session.refresh(comment, ["author"])
        return comment

    # ---------- reassignment integration ----------

    async def handle_team_change(
        self, problem_id: UUID, removed_user_ids: set[UUID], actor: UUID | None
    ) -> int:
        """Unassign active tasks of removed members; history/authorship preserved."""
        unassigned = 0
        for user_id in removed_user_ids:
            rows = await self.tasks.active_for_assignee(problem_id, user_id)
            for task in rows:
                task.assigned_to_user_id = None
                await self.activities.log(
                    problem_id=problem_id,
                    event_type=ProblemEventType.TASK_REASSIGNED,
                    actor_user_id=actor,
                    message=f"Task unassigned after team change: {task.title}.",
                )
                unassigned += 1
        if unassigned:
            await self.session.flush()
        return unassigned

    @staticmethod
    def role_label_for(user: User, ctx: WorkspaceContext) -> str:
        return _role_label(user, ctx)
