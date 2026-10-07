"""Solution submission + mentor review + reporter verification + closure (Step 11).

Controlled lifecycle (central transition map below):

    IN_PROGRESS --submit--> IN_PROGRESS (revision recorded)
    IN_PROGRESS --mentor approve--> AWAITING_VERIFICATION
    IN_PROGRESS --mentor request changes--> IN_PROGRESS (new revision expected)
    AWAITING_VERIFICATION --reporter yes--> RESOLVED
    AWAITING_VERIFICATION --reporter no--> IN_PROGRESS (assignment stays ACTIVE)
    RESOLVED --admin close--> CLOSED (workloads released exactly once)

Transactional strategy: every mutating flow commits state changes AND its
notifications in ONE transaction, so a notification failure rolls the whole
decision back instead of leaving e.g. RESOLVED with released workloads and
no audit trail.

Readiness policy (documented, enforced on submit unless an admin overrides
with an audited reason): no BLOCKED active tasks, every non-cancelled
HIGH/CRITICAL task DONE, every non-cancelled milestone COMPLETED, and live
progress >= 80%. We deliberately do NOT demand blind 100%: LOW/MEDIUM
tasks may remain open.
"""

import logging
from datetime import UTC, datetime
from typing import TypedDict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    NotificationType,
    ProblemEventType,
    ProblemStatus,
    ReviewDecision,
    SolutionStatus,
    UserRole,
    VerificationDecision,
)
from app.models.assignment import ProblemAssignment
from app.models.problem import Problem
from app.models.solution import (
    MentorSolutionReview,
    ProblemResolutionVerification,
    ProblemSolutionSubmission,
)
from app.models.user import User
from app.models.workspace import ProblemWorkAttachment
from app.repositories.assignment_repository import AssignmentRepository
from app.repositories.problem_repository import ActivityRepository
from app.repositories.solution_repository import (
    ReviewRepository,
    SolutionRepository,
    VerificationRepository,
)
from app.repositories.workspace_repository import (
    MilestoneRepository,
    TaskRepository,
    WorkAttachmentRepository,
    compute_progress,
)
from app.services.auth_service import AuthError
from app.services.notification_service import NotificationService
from app.services.problem_service import ProblemService
from app.services.review_service import clean_reason

logger = logging.getLogger(__name__)

READINESS_MIN_PROGRESS = 80.0


class ReadinessCheck(TypedDict):
    """Typed readiness payload for the solution UI and submit guard."""

    ready: bool
    reasons: list[str]
    progress_percent: float
    done_tasks: int
    total_tasks: int
    done_milestones: int
    total_milestones: int
    blocked_tasks: int

# Central Step 11 transition table: action -> (allowed from-states, to-state).
SOLUTION_TRANSITIONS: dict[str, tuple[frozenset[ProblemStatus], ProblemStatus]] = {
    "mentor_approve": (frozenset({ProblemStatus.IN_PROGRESS}), ProblemStatus.AWAITING_VERIFICATION),
    "mentor_request_changes": (frozenset({ProblemStatus.IN_PROGRESS}), ProblemStatus.IN_PROGRESS),
    "reporter_confirm": (
        frozenset({ProblemStatus.AWAITING_VERIFICATION}),
        ProblemStatus.RESOLVED,
    ),
    "reporter_reject": (
        frozenset({ProblemStatus.AWAITING_VERIFICATION}),
        ProblemStatus.IN_PROGRESS,
    ),
    "admin_close": (frozenset({ProblemStatus.RESOLVED}), ProblemStatus.CLOSED),
}


def validate_solution_transition(from_status: ProblemStatus, action: str) -> ProblemStatus:
    """Return the target state for a Step 11 action, or raise 409."""
    rule = SOLUTION_TRANSITIONS.get(action)
    if rule is None:
        raise AuthError(422, f"Unknown solution action: {action}")
    allowed, target = rule
    if from_status not in allowed:
        allowed_names = ", ".join(sorted(s.value for s in allowed))
        raise AuthError(
            409,
            f"Cannot '{action}' a report with status {from_status.value} "
            f"(allowed from: {allowed_names}).",
        )
    return target


class SolutionService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.problems = ProblemService(session)
        self.assignments = AssignmentRepository(session)
        self.solutions = SolutionRepository(session)
        self.reviews = ReviewRepository(session)
        self.verifications = VerificationRepository(session)
        self.activities = ActivityRepository(session)
        self.tasks = TaskRepository(session)
        self.milestones = MilestoneRepository(session)
        self.work_files = WorkAttachmentRepository(session)
        self.notifications = NotificationService(session)

    # ---------- shared context ----------

    async def _read_context(
        self, problem_id: UUID, user: User
    ) -> tuple[Problem, ProblemAssignment | None]:
        """Visible problem + active assignment if any. Reporters excluded.

        Past members/mentors keep read access once a report reaches
        verification/resolution/closure (writes stay blocked elsewhere).
        """
        problem = await self.problems.get_visible_problem(user, problem_id)
        if user.role == UserRole.ADMIN:
            return problem, await self.assignments.active_for_problem(problem_id)
        active = await self.assignments.active_for_problem(problem_id)
        if active is not None and (
            any(m.user_id == user.id and m.is_active for m in active.team.members)
            or active.mentor_user_id == user.id
        ):
            return problem, active
        if problem.status in (
            ProblemStatus.AWAITING_VERIFICATION,
            ProblemStatus.RESOLVED,
            ProblemStatus.CLOSED,
        ):
            for past in await self.assignments.history_for_problem(problem_id):
                if any(m.user_id == user.id for m in past.team.members) or (
                    past.mentor_user_id == user.id
                ):
                    return problem, None
        if problem.reporter_id == user.id:
            raise AuthError(403, "Use the safe solution summary to verify.")
        raise AuthError(403, "Only the assigned team, mentor, or an admin can access solutions.")

    async def _write_context(
        self, problem_id: UUID, user: User
    ) -> tuple[Problem, ProblemAssignment]:
        """Active assignment required. Past members on resolved/closed reports
        get a clear read-only 409 instead of a bare 403."""
        problem, active = await self._read_context(problem_id, user)
        if active is None:
            if problem.status in (ProblemStatus.RESOLVED, ProblemStatus.CLOSED):
                raise AuthError(
                    409,
                    f"Solutions are read-only while the report is {problem.status.value}.",
                )
            raise AuthError(409, "No active assignment for this report.")
        return problem, active

    async def _log(
        self,
        problem_id: UUID,
        event: ProblemEventType,
        actor: UUID | None,
        *,
        old_status: str | None = None,
        new_status: str | None = None,
        message: str | None = None,
    ) -> None:
        await self.activities.log(
            problem_id=problem_id,
            event_type=event,
            actor_user_id=actor,
            old_status=old_status,
            new_status=new_status,
            message=message,
        )
        await self.session.flush()

    # ---------- readiness ----------

    async def readiness(self, problem_id: UUID) -> ReadinessCheck:
        """Live completion-readiness check for the solution UI."""
        tasks = await self.tasks.list_for_problem(problem_id)
        milestones = await self.milestones.list_for_problem(problem_id)
        percent, done_tasks, total_tasks, done_ms, total_ms = compute_progress(tasks, milestones)
        reasons: list[str] = []
        blocked = [t for t in tasks if t.status == "BLOCKED"]
        if blocked:
            reasons.append(f"{len(blocked)} task(s) are BLOCKED.")
        open_critical = [
            t
            for t in tasks
            if t.status not in ("DONE", "CANCELLED") and t.priority in ("HIGH", "CRITICAL")
        ]
        if open_critical:
            reasons.append(f"{len(open_critical)} HIGH/CRITICAL task(s) are not DONE.")
        open_milestones = [m for m in milestones if m.status not in ("COMPLETED", "CANCELLED")]
        if open_milestones:
            reasons.append(f"{len(open_milestones)} milestone(s) are not COMPLETED.")
        if percent < READINESS_MIN_PROGRESS:
            reasons.append(
                f"Progress is {percent}% (minimum {READINESS_MIN_PROGRESS:g}%)."
            )
        return {
            "ready": not reasons,
            "reasons": reasons,
            "progress_percent": percent,
            "done_tasks": done_tasks,
            "total_tasks": total_tasks,
            "done_milestones": done_ms,
            "total_milestones": total_ms,
            "blocked_tasks": len(blocked),
        }

    async def _validate_evidence(
        self, problem_id: UUID, evidence_ids: list[UUID]
    ) -> list[str]:
        """Evidence must reference real work attachments of this problem."""
        if not evidence_ids:
            return []
        seen: list[str] = []
        for attachment_id in evidence_ids:
            row = await self.work_files.get(attachment_id)
            if row is None or row.problem_id != problem_id:
                raise AuthError(422, "Solution evidence must reference this report's work files.")
            text = str(attachment_id)
            if text not in seen:
                seen.append(text)
        return seen

    # ---------- submit ----------

    async def submit_solution(
        self,
        problem_id: UUID,
        user: User,
        *,
        solution_summary: str,
        root_cause: str,
        work_performed: str,
        testing_performed: str | None,
        deployment_notes: str | None,
        limitations: str | None,
        evidence_attachment_ids: list[UUID],
        share_evidence_with_reporter: bool,
        override_reason: str | None,
    ) -> ProblemSolutionSubmission:
        """Active team members submit a new solution revision (IN_PROGRESS only).

        Only an ADMIN may supply override_reason to bypass readiness, and the
        reason is audited. Mentors inspect/review but never submit as students.
        """
        problem, assignment = await self._write_context(problem_id, user)
        if problem.status != ProblemStatus.IN_PROGRESS:
            raise AuthError(
                409,
                "Solutions can only be submitted while the report is IN_PROGRESS "
                f"(status: {problem.status.value}).",
            )
        is_admin = user.role == UserRole.ADMIN
        is_member = any(
            m.user_id == user.id and m.is_active for m in assignment.team.members
        )
        if not is_member and not is_admin:
            raise AuthError(403, "Only active team members can submit a solution.")
        if user.role == UserRole.MENTOR:
            raise AuthError(403, "The mentor reviews solutions; only the team submits them.")

        summary = solution_summary.strip()
        cause = root_cause.strip()
        work = work_performed.strip()
        if len(summary) < 10:
            raise AuthError(422, "Solution summary is too short (min 10 characters).")
        if len(cause) < 10:
            raise AuthError(422, "Root cause is too short (min 10 characters).")
        if len(work) < 20:
            raise AuthError(422, "Work performed is too short (min 20 characters).")

        latest = await self.solutions.latest_for_problem(problem_id)
        if latest is not None and latest.status == SolutionStatus.SUBMITTED.value:
            raise AuthError(409, "Revision is already awaiting mentor review; wait for a decision.")

        override: str | None = None
        if override_reason is not None:
            if not is_admin:
                raise AuthError(403, "Only an admin can override readiness checks.")
            override = clean_reason(override_reason, field="Override reason", max_len=1000)
        else:
            check = await self.readiness(problem_id)
            if not check["ready"]:
                reasons = "; ".join(check["reasons"])
                raise AuthError(422, f"Work is not ready for submission: {reasons}")

        evidence = await self._validate_evidence(problem_id, evidence_attachment_ids)

        try:
            revision = await self.solutions.max_revision(problem_id) + 1
            row = await self.solutions.create(
                problem_id=problem.id,
                assignment_id=assignment.id,
                submitted_by_user_id=user.id,
                revision_number=revision,
                solution_summary=summary,
                root_cause=cause,
                work_performed=work,
                testing_performed=(testing_performed or "").strip() or None,
                deployment_notes=(deployment_notes or "").strip() or None,
                limitations=(limitations or "").strip() or None,
                evidence_attachment_ids=evidence,
                readiness_override_reason=override,
                status=SolutionStatus.SUBMITTED.value,
            )
            if share_evidence_with_reporter:
                for attachment_id in evidence_attachment_ids:
                    file_row = await self.work_files.get(attachment_id)
                    if file_row is not None:
                        file_row.is_reporter_visible = True
            await self._log(
                problem.id,
                ProblemEventType.SOLUTION_SUBMITTED,
                user.id,
                message=f"Solution revision {revision} submitted by {user.full_name}."
                + (f" Readiness overridden: {override}" if override else ""),
            )
            await self.notifications.notify_mentor(
                assignment,
                NotificationType.SOLUTION_SUBMITTED,
                f"Solution submitted for {problem.ticket_number}",
                f"Revision {revision} by {user.full_name} is ready for review.",
                problem_id=problem.id,
                related_entity_type="solution",
                related_entity_id=row.id,
            )
            await self.session.commit()
        except AuthError:
            await self.session.rollback()
            raise
        except Exception as exc:
            await self.session.rollback()
            logger.warning("solution submission failed for problem %s: %s", problem_id, exc)
            raise AuthError(500, "Solution submission failed; nothing was changed.") from exc
        refreshed = await self.solutions.get(row.id)
        if refreshed is None:
            raise AuthError(500, "Solution vanished mid-transaction.")
        return refreshed

    # ---------- mentor review ----------

    async def review_solution(
        self,
        problem_id: UUID,
        submission_id: UUID,
        user: User,
        *,
        decision: str,
        review_comment: str | None,
    ) -> MentorSolutionReview:
        """Current assigned mentor approves or requests changes (IN_PROGRESS only).

        Admin override is allowed with a mandatory comment and is audited as
        an override on the review row and in the activity timeline.
        """
        problem, assignment = await self._write_context(problem_id, user)
        try:
            want = ReviewDecision(decision)
        except ValueError as exc:
            raise AuthError(422, f"Unknown review decision: {decision}") from exc
        is_admin = user.role == UserRole.ADMIN
        if assignment.mentor_user_id != user.id and not is_admin:
            raise AuthError(403, "Only the assigned mentor can review solutions.")
        submission = await self.solutions.get(submission_id)
        if submission is None or submission.problem_id != problem.id:
            raise AuthError(404, "Solution submission not found")
        if submission.status != SolutionStatus.SUBMITTED.value:
            raise AuthError(409, "This solution revision has already been reviewed.")
        comment = (review_comment or "").strip() or None
        if want == ReviewDecision.CHANGES_REQUESTED and not comment:
            raise AuthError(422, "A review comment is required when requesting changes.")
        if is_admin and assignment.mentor_user_id != user.id and not comment:
            raise AuthError(422, "An admin override review requires a comment.")
        validate_solution_transition(
            problem.status,
            "mentor_approve" if want == ReviewDecision.APPROVED else "mentor_request_changes",
        )

        try:
            review = await self.reviews.create(
                solution_submission_id=submission.id,
                mentor_user_id=user.id,
                decision=want.value,
                review_comment=comment,
                is_admin_override=is_admin and assignment.mentor_user_id != user.id,
            )
            old_status = problem.status
            if want == ReviewDecision.APPROVED:
                submission.status = SolutionStatus.MENTOR_APPROVED.value
                problem.status = ProblemStatus.AWAITING_VERIFICATION
                await self._log(
                    problem.id,
                    ProblemEventType.MENTOR_SOLUTION_APPROVED,
                    user.id,
                    old_status=old_status.value,
                    new_status=problem.status.value,
                    message=f"Solution revision {submission.revision_number} approved"
                    + (" (admin override)" if review.is_admin_override else "")
                    + (f": {comment}" if comment else "."),
                )
                await self._log(
                    problem.id,
                    ProblemEventType.REPORTER_VERIFICATION_REQUESTED,
                    user.id,
                    message=f"Reporter verification requested for {problem.ticket_number}.",
                )
                await self.notifications.notify_reporter(
                    problem,
                    NotificationType.REPORTER_VERIFICATION_REQUIRED,
                    f"Please verify {problem.ticket_number}",
                    f"The mentor approved revision {submission.revision_number}. "
                    "Has this campus problem been resolved?",
                    related_entity_type="solution",
                    related_entity_id=submission.id,
                )
            else:
                submission.status = SolutionStatus.CHANGES_REQUESTED.value
                await self._log(
                    problem.id,
                    ProblemEventType.MENTOR_CHANGES_REQUESTED,
                    user.id,
                    message=f"Changes requested on revision {submission.revision_number}: {comment}",
                )
                await self.notifications.notify_team(
                    assignment,
                    NotificationType.CHANGES_REQUESTED,
                    f"Changes requested on {problem.ticket_number}",
                    f"Revision {submission.revision_number}: {comment}",
                    problem_id=problem.id,
                    related_entity_type="solution",
                    related_entity_id=submission.id,
                )
            await self.session.commit()
        except AuthError:
            await self.session.rollback()
            raise
        except Exception as exc:
            await self.session.rollback()
            logger.warning("solution review failed for problem %s: %s", problem_id, exc)
            raise AuthError(500, "Solution review failed; nothing was changed.") from exc
        return review

    # ---------- reporter verification ----------

    async def verify_solution(
        self,
        problem_id: UUID,
        user: User,
        *,
        decision: str,
        reason: str | None,
    ) -> ProblemResolutionVerification:
        """Only the original reporter verifies (AWAITING_VERIFICATION only)."""
        problem = await self.problems.get_visible_problem(user, problem_id)
        if problem.reporter_id != user.id:
            raise AuthError(403, "Only the original reporter can verify the resolution.")
        try:
            want = VerificationDecision(decision)
        except ValueError as exc:
            raise AuthError(422, f"Unknown verification decision: {decision}") from exc
        validate_solution_transition(
            problem.status,
            "reporter_confirm" if want == VerificationDecision.RESOLVED else "reporter_reject",
        )
        latest = await self.solutions.latest_for_problem(problem_id)
        if latest is None or latest.status != SolutionStatus.MENTOR_APPROVED.value:
            raise AuthError(409, "No mentor-approved solution is awaiting verification.")
        assignment = await self.assignments.active_for_problem(problem_id)
        if assignment is None:
            raise AuthError(409, "No active assignment for this report.")
        cleaned_reason = (reason or "").strip() or None
        if want == VerificationDecision.NOT_RESOLVED and not cleaned_reason:
            raise AuthError(422, "A reason is required when the problem is not resolved.")
        if cleaned_reason and len(cleaned_reason) > 2000:
            raise AuthError(422, "Reason is too long (max 2000 characters).")

        try:
            row = await self.verifications.create(
                problem_id=problem.id,
                solution_submission_id=latest.id,
                reporter_user_id=user.id,
                decision=want.value,
                reason=cleaned_reason,
            )
            old_status = problem.status
            if want == VerificationDecision.RESOLVED:
                latest.status = SolutionStatus.VERIFIED.value
                problem.status = ProblemStatus.RESOLVED
                problem.resolved_at = datetime.now(UTC)
                await self._log(
                    problem.id,
                    ProblemEventType.REPORTER_CONFIRMED_RESOLUTION,
                    user.id,
                    old_status=old_status.value,
                    new_status=problem.status.value,
                    message=f"Reporter confirmed the resolution of {problem.ticket_number}.",
                )
                await self._log(
                    problem.id,
                    ProblemEventType.PROBLEM_RESOLVED,
                    user.id,
                    message=f"Report {problem.ticket_number} resolved.",
                )
                for recipient in self._team_and_mentor(assignment):
                    await self.notifications.notify_user(
                        recipient,
                        NotificationType.PROBLEM_RESOLVED,
                        f"{problem.ticket_number} resolved",
                        f"The reporter confirmed revision {latest.revision_number} fixed the problem.",
                        problem_id=problem.id,
                        related_entity_type="solution",
                        related_entity_id=latest.id,
                    )
            else:
                latest.status = SolutionStatus.REPORTER_REJECTED.value
                problem.status = ProblemStatus.IN_PROGRESS
                await self._log(
                    problem.id,
                    ProblemEventType.REPORTER_REJECTED_RESOLUTION,
                    user.id,
                    old_status=old_status.value,
                    new_status=problem.status.value,
                    message=f"Reporter says {problem.ticket_number} is not resolved: {cleaned_reason}",
                )
                await self.notifications.notify_team(
                    assignment,
                    NotificationType.REPORTER_REJECTED_RESOLUTION,
                    f"{problem.ticket_number} not resolved",
                    f"Reporter feedback: {cleaned_reason}",
                    problem_id=problem.id,
                    related_entity_type="solution",
                    related_entity_id=latest.id,
                )
                await self.notifications.notify_mentor(
                    assignment,
                    NotificationType.REPORTER_REJECTED_RESOLUTION,
                    f"{problem.ticket_number} not resolved",
                    f"Reporter feedback: {cleaned_reason}",
                    problem_id=problem.id,
                    related_entity_type="solution",
                    related_entity_id=latest.id,
                )
            await self.session.commit()
        except AuthError:
            await self.session.rollback()
            raise
        except Exception as exc:
            await self.session.rollback()
            logger.warning("verification failed for problem %s: %s", problem_id, exc)
            raise AuthError(500, "Verification failed; nothing was changed.") from exc
        return row

    @staticmethod
    def _team_and_mentor(assignment: ProblemAssignment) -> list[UUID]:
        ids = [m.user_id for m in assignment.team.members if m.is_active]
        ids.append(assignment.mentor_user_id)
        return ids

    # ---------- admin closure + workload release ----------

    async def close_problem(
        self, problem_id: UUID, admin: User, *, reason: str | None = None
    ) -> Problem:
        """Admin closes a RESOLVED report. Workloads release exactly once here.

        Guarded by the ACTIVE→COMPLETED assignment transition under a row
        lock: a retried close lands on CLOSED and is rejected with 409 before
        any decrement, so double release is impossible. Nothing is released
        at submit/review/verify time — only here.
        """
        problem = await self.assignments.get_problem_for_update(problem_id)
        if problem is None:
            raise AuthError(404, "Problem not found")
        validate_solution_transition(problem.status, "admin_close")
        current = await self.assignments.active_for_problem(problem_id, for_update=True)
        if current is None:
            raise AuthError(409, "No active assignment to close.")
        cleaned = (reason or "").strip() or None
        if cleaned and len(cleaned) > 1000:
            raise AuthError(422, "Close reason is too long (max 1000 characters).")

        try:
            now = datetime.now(UTC)
            current.status = "COMPLETED"
            current.unassigned_at = now
            current.unassigned_by = admin.id
            current.unassignment_reason = f"Closed: {cleaned}" if cleaned else "Closed after verification."
            for member in current.team.members:
                if not member.is_active:
                    continue
                user = await self.assignments.get_solver(member.user_id)
                if user is not None and user.student_profile is not None:
                    locked = await self.assignments.lock_student_profile(user.student_profile.id)
                    if locked is not None:
                        locked.current_workload = max(0, locked.current_workload - 1)
            mentor_user = await self.assignments.get_mentor(current.mentor_user_id)
            if mentor_user is not None and mentor_user.faculty_profile is not None:
                locked_mentor = await self.assignments.lock_faculty_profile(
                    mentor_user.faculty_profile.id
                )
                if locked_mentor is not None:
                    locked_mentor.current_workload = max(0, locked_mentor.current_workload - 1)
            old_status = problem.status
            problem.status = ProblemStatus.CLOSED
            problem.closed_at = now
            await self._log(
                problem.id,
                ProblemEventType.PROBLEM_CLOSED,
                admin.id,
                old_status=old_status.value,
                new_status=problem.status.value,
                message=f"Report closed by {admin.full_name}."
                + (f" Reason: {cleaned}" if cleaned else ""),
            )
            ticket = problem.ticket_number
            await self.notifications.notify_reporter(
                problem,
                NotificationType.PROBLEM_CLOSED,
                f"{ticket} closed",
                "Thank you — this report is now closed.",
                related_entity_type="problem",
                related_entity_id=problem.id,
            )
            for recipient in self._team_and_mentor(current):
                await self.notifications.notify_user(
                    recipient,
                    NotificationType.PROBLEM_CLOSED,
                    f"{ticket} closed",
                    "The assignment is complete and workloads were released.",
                    problem_id=problem.id,
                    related_entity_type="problem",
                    related_entity_id=problem.id,
                )
            await self.session.commit()
        except AuthError:
            await self.session.rollback()
            raise
        except Exception as exc:
            await self.session.rollback()
            logger.warning("closure failed for problem %s: %s", problem_id, exc)
            raise AuthError(500, "Closure failed; nothing was changed.") from exc
        # Step 12: best-effort knowledge publication. Closure already
        # committed above and stays valid even if publication fails; failures
        # become FAILED entries an admin can retry.
        try:
            from app.services.knowledge_service import KnowledgeService

            await KnowledgeService(self.session).publish_for_problem(problem.id)
        except Exception as exc:
            logger.warning(
                "knowledge publication hook failed for closed problem %s: %s",
                problem.id,
                exc,
            )
        return problem

    # ---------- reads ----------

    async def list_submissions(
        self, problem_id: UUID, user: User
    ) -> list[ProblemSolutionSubmission]:
        problem, _ = await self._read_context(problem_id, user)
        if user.role != UserRole.ADMIN and problem.reporter_id == user.id:
            raise AuthError(403, "Use the safe solution summary to verify.")
        return await self.solutions.list_for_problem(problem.id)

    async def latest_submission(
        self, problem_id: UUID, user: User
    ) -> ProblemSolutionSubmission | None:
        await self._read_context(problem_id, user)
        return await self.solutions.latest_for_problem(problem_id)

    async def safe_solution(self, problem_id: UUID, user: User) -> dict[str, object] | None:
        """Reporter-safe approved solution summary for verification.

        Includes only the latest MENTOR_APPROVED/VERIFIED revision's safe
        fields plus reporter-shared evidence metadata — never internal
        notes, private files, or discussion.
        """
        problem = await self.problems.get_visible_problem(user, problem_id)
        latest = await self.solutions.latest_for_problem(problem.id)
        if latest is None or latest.status not in (
            SolutionStatus.MENTOR_APPROVED.value,
            SolutionStatus.VERIFIED.value,
        ):
            return None
        evidence: list[dict[str, object]] = []
        for raw in latest.evidence_attachment_ids or []:
            try:
                attachment_id = UUID(str(raw))
            except ValueError:
                continue
            file_row = await self.work_files.get(attachment_id)
            if file_row is None or not file_row.is_reporter_visible:
                continue
            evidence.append(
                {
                    "id": str(file_row.id),
                    "original_filename": file_row.original_filename,
                    "mime_type": file_row.mime_type,
                    "size_bytes": file_row.size_bytes,
                    "description": file_row.description,
                }
            )
        return {
            "revision_number": latest.revision_number,
            "solution_summary": latest.solution_summary,
            "work_performed": latest.work_performed,
            "testing_performed": latest.testing_performed,
            "limitations": latest.limitations,
            "status": latest.status,
            "submitted_at": latest.submitted_at.isoformat(),
            "evidence": evidence,
        }

    async def download_shared_evidence(
        self, problem_id: UUID, file_id: UUID, user: User
    ) -> tuple[ProblemWorkAttachment, bytes]:
        """Reporter download of explicitly shared solution evidence."""
        from app.services.workspace_service import WorkspaceService

        problem = await self.problems.get_visible_problem(user, problem_id)
        file_row = await self.work_files.get(file_id)
        if file_row is None or file_row.problem_id != problem.id:
            raise AuthError(404, "Evidence file not found")
        if not file_row.is_reporter_visible:
            raise AuthError(403, "This file is not shared with the reporter.")
        latest = await self.solutions.latest_for_problem(problem.id)
        if latest is None or latest.status not in (
            SolutionStatus.MENTOR_APPROVED.value,
            SolutionStatus.VERIFIED.value,
        ):
            raise AuthError(403, "Evidence is available once a solution is approved.")
        if str(file_row.id) not in [str(v) for v in latest.evidence_attachment_ids or []]:
            raise AuthError(403, "This file is not part of the approved solution.")
        return await WorkspaceService(self.session).read_work_file(problem.id, file_id, user)

    async def list_verifications(
        self, problem_id: UUID, user: User
    ) -> list[ProblemResolutionVerification]:
        problem, _ = await self._read_context(problem_id, user)
        return await self.verifications.list_for_problem(problem.id)
