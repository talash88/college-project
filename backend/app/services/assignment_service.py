"""Transactional assignment service (Step 9).

Admin-only decisions executed as single atomic transactions: lock the
problem, revalidate every person against LIVE data (never stale
recommendation state), create the real team + assignment, increment
workloads, transition status, log activity — then commit once. Any failure
rolls everything back: no half-created teams, no partial increments, no
status without an assignment.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import AssignmentStatus, ProblemEventType, ProblemStatus, UserRole
from app.models.assignment import ProblemAssignment
from app.models.faculty_profile import FacultyProfile
from app.models.problem import Problem
from app.models.student_profile import StudentProfile
from app.models.user import User
from app.repositories.assignment_repository import AssignmentRepository
from app.repositories.problem_repository import ActivityRepository, ProblemRepository
from app.repositories.recommendation_repository import (
    MentorRecommendationRepository,
    TeamRecommendationRepository,
)
from app.services.auth_service import AuthError
from app.services.review_service import clean_reason

logger = logging.getLogger(__name__)

REASON_MAX = 1000
TEAM_NAME_MAX = 100
ROLE_MAX = 50


def _dedupe_preserve_order(ids: list[UUID]) -> list[UUID]:
    seen: set[UUID] = set()
    ordered: list[UUID] = []
    for value in ids:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


class AssignmentService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.problems = ProblemRepository(session)
        self.assignments = AssignmentRepository(session)
        self.team_recs = TeamRecommendationRepository(session)
        self.mentor_recs = MentorRecommendationRepository(session)
        self.activities = ActivityRepository(session)

    # ---------- shared validation ----------

    def _check_team_size(self, count: int, *, override_reason: str | None) -> None:
        min_size = settings.TEAM_MIN_SIZE
        max_size = max(min_size, settings.TEAM_MAX_SIZE)
        if count == 0:
            raise AuthError(422, "At least one solver is required.")
        if count < min_size:
            if count == 1 and settings.TEAM_ALLOW_SOLO and (override_reason or "").strip():
                return
            raise AuthError(
                422,
                f"Team too small: {count} member(s), minimum is {min_size}.",
            )
        if count > max_size:
            raise AuthError(422, f"Team too large: {count} member(s), maximum is {max_size}.")

    async def _require_solver(self, user_id: UUID) -> tuple[User, StudentProfile]:
        """Live solver revalidation with a locked profile row."""
        user = await self.assignments.get_solver(user_id)
        if user is None:
            raise AuthError(404, f"Solver not found: {user_id}")
        if user.role != UserRole.SOLVER:
            raise AuthError(422, f"{user.full_name} is not a solver (role: {user.role.value}).")
        if not user.is_active:
            raise AuthError(422, f"{user.full_name} is not active.")
        profile = user.student_profile
        if profile is None:
            raise AuthError(422, f"{user.full_name} has no student profile.")
        locked = await self.assignments.lock_student_profile(profile.id)
        if locked is None:
            raise AuthError(500, "Solver vanished mid-transaction.")
        if locked.availability_status.value == "UNAVAILABLE":
            raise AuthError(422, f"{user.full_name} is currently unavailable.")
        if locked.current_workload < 0 or locked.max_workload <= 0:
            raise AuthError(422, f"{user.full_name} has inconsistent workload data.")
        if locked.current_workload >= locked.max_workload:
            raise AuthError(
                422,
                f"{user.full_name} is fully loaded "
                f"({locked.current_workload}/{locked.max_workload}).",
            )
        return user, locked

    async def _require_mentor(self, user_id: UUID) -> tuple[User, FacultyProfile]:
        user = await self.assignments.get_mentor(user_id)
        if user is None:
            raise AuthError(404, f"Mentor not found: {user_id}")
        if user.role != UserRole.MENTOR:
            raise AuthError(422, f"{user.full_name} is not a mentor (role: {user.role.value}).")
        if not user.is_active:
            raise AuthError(422, f"{user.full_name} is not active.")
        profile = user.faculty_profile
        if profile is None:
            raise AuthError(422, f"{user.full_name} has no faculty profile.")
        locked = await self.assignments.lock_faculty_profile(profile.id)
        if locked is None:
            raise AuthError(500, "Mentor vanished mid-transaction.")
        if locked.availability_status.value == "UNAVAILABLE":
            raise AuthError(422, f"{user.full_name} is currently unavailable.")
        if locked.current_workload < 0 or locked.max_workload <= 0:
            raise AuthError(422, f"{user.full_name} has inconsistent workload data.")
        if locked.current_workload >= locked.max_workload:
            raise AuthError(
                422,
                f"{user.full_name} is fully loaded "
                f"({locked.current_workload}/{locked.max_workload}).",
            )
        return user, locked

    @staticmethod
    def _clean_team_name(name: str | None) -> str | None:
        if name is None:
            return None
        text = name.strip()
        if not text:
            return None
        if len(text) > TEAM_NAME_MAX:
            raise AuthError(422, f"Team name is too long (max {TEAM_NAME_MAX} characters).")
        return text

    @staticmethod
    def _clean_roles(
        roles: dict[str, str] | None, solver_ids: list[UUID]
    ) -> dict[UUID, str | None]:
        cleaned: dict[UUID, str | None] = {}
        for sid in solver_ids:
            cleaned[sid] = None
        if not roles:
            return cleaned
        for key, value in roles.items():
            try:
                uid = UUID(str(key))
            except ValueError as exc:
                raise AuthError(422, f"Invalid member id in roles: {key}") from exc
            if uid not in cleaned:
                raise AuthError(422, "Role given for a user outside the team.")
            text = (value or "").strip()
            if len(text) > ROLE_MAX:
                raise AuthError(422, f"Team role is too long (max {ROLE_MAX} characters).")
            cleaned[uid] = text or None
        return cleaned

    async def _reject_duplicate_member(self, problem: Problem) -> None:
        """Confirmed duplicates are assigned via their canonical issue only."""
        if problem.status == ProblemStatus.DUPLICATE and problem.canonical_problem_id is not None:
            ticket = await self._canonical_ticket(problem)
            raise AuthError(
                409,
                f"This report is linked to canonical issue {ticket}. "
                "Assignment must be managed on the canonical problem.",
            )

    async def _canonical_ticket(self, problem: Problem) -> str | None:
        if problem.canonical_problem_id is None:
            return None
        canonical = await self.problems.get_by_id(problem.canonical_problem_id)
        return canonical.ticket_number if canonical else None

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

    # ---------- reads ----------

    async def active_for_problem(self, problem_id: UUID) -> ProblemAssignment | None:
        return await self.assignments.active_for_problem(problem_id)

    async def history_for_problem(self, problem_id: UUID) -> list[ProblemAssignment]:
        return await self.assignments.history_for_problem(problem_id)

    # ---------- assign ----------

    async def assign(
        self,
        problem_id: UUID,
        admin: User,
        *,
        solver_ids: list[UUID],
        mentor_id: UUID,
        team_recommendation_id: UUID | None = None,
        mentor_recommendation_id: UUID | None = None,
        team_name: str | None = None,
        team_override_reason: str | None = None,
        mentor_override_reason: str | None = None,
        member_roles: dict[str, str] | None = None,
    ) -> tuple[ProblemAssignment, bool]:
        """Assign a real team + mentor atomically. Returns (assignment, created).

        created=False means an idempotent retry: the identical assignment
        already exists and is returned unchanged (no double increment).
        """
        try:
            return await self._assign_inner(
                problem_id,
                admin,
                solver_ids=solver_ids,
                mentor_id=mentor_id,
                team_recommendation_id=team_recommendation_id,
                mentor_recommendation_id=mentor_recommendation_id,
                team_name=team_name,
                team_override_reason=team_override_reason,
                mentor_override_reason=mentor_override_reason,
                member_roles=member_roles,
            )
        except IntegrityError as exc:
            # Lost a race on the one-active-assignment constraint: whoever won
            # is the assignment of record — return it or report conflict.
            await self.session.rollback()
            logger.info("assignment race for problem %s; re-reading", problem_id)
            return await self._after_race(
                problem_id, solver_ids=solver_ids, mentor_id=mentor_id, exc=exc
            )
        except AuthError:
            await self.session.rollback()
            raise
        except Exception as exc:
            await self.session.rollback()
            logger.warning("assignment failed for problem %s: %s", problem_id, exc)
            raise AuthError(500, "Assignment failed; nothing was changed.") from exc

    async def _after_race(
        self, problem_id: UUID, *, solver_ids: list[UUID], mentor_id: UUID, exc: Exception
    ) -> tuple[ProblemAssignment, bool]:
        existing = await self.assignments.active_for_problem(problem_id)
        if existing is None:
            raise AuthError(409, "A concurrent assignment just finished; please retry.") from exc
        if self._same_assignment(existing, solver_ids, mentor_id):
            return existing, False
        raise AuthError(
            409,
            "This report was just assigned by another admin; review the current assignment.",
        ) from exc

    @staticmethod
    def _same_assignment(
        existing: ProblemAssignment, solver_ids: list[UUID], mentor_id: UUID
    ) -> bool:
        active_members = {m.user_id for m in existing.team.members if m.is_active}
        return active_members == set(solver_ids) and existing.mentor_user_id == mentor_id

    async def _assign_inner(
        self,
        problem_id: UUID,
        admin: User,
        *,
        solver_ids: list[UUID],
        mentor_id: UUID,
        team_recommendation_id: UUID | None,
        mentor_recommendation_id: UUID | None,
        team_name: str | None,
        team_override_reason: str | None,
        mentor_override_reason: str | None,
        member_roles: dict[str, str] | None,
    ) -> tuple[ProblemAssignment, bool]:
        problem = await self.assignments.get_problem_for_update(problem_id)
        if problem is None:
            raise AuthError(404, "Problem not found")
        await self._reject_duplicate_member(problem)

        solvers = _dedupe_preserve_order(list(solver_ids))
        if len(solvers) != len(list(solver_ids)):
            raise AuthError(422, "Duplicate solver in team selection.")

        # Idempotency before the status gate: a retry lands on ASSIGNED, and
        # the identical active assignment is returned, never duplicated.
        existing = await self.assignments.active_for_problem(problem_id)
        if existing is not None:
            if self._same_assignment(existing, solvers, mentor_id):
                return existing, False
            raise AuthError(
                409,
                "This report already has an active assignment; "
                "cancel or reassign it instead of creating another.",
            )

        if problem.status != ProblemStatus.APPROVED:
            raise AuthError(
                409,
                f"Only APPROVED reports can be assigned (status: {problem.status.value}).",
            )
        self._check_team_size(len(solvers), override_reason=team_override_reason)
        roles = self._clean_roles(member_roles, solvers)
        name = self._clean_team_name(team_name)

        # Recommendation references: must belong to this problem; citing a
        # recommendation while assigning different people is an override.
        team_overridden = False
        team_reason = (team_override_reason or "").strip() or None
        if team_recommendation_id is not None:
            option = await self.team_recs.get_option(team_recommendation_id)
            if option is None or option.problem_id != problem.id:
                raise AuthError(422, "Cited team recommendation does not belong to this report.")
            rec_members = {m.user_id for m in option.members}
            if rec_members != set(solvers):
                team_overridden = True
        else:
            team_overridden = True
        if team_overridden and not team_reason:
            raise AuthError(422, "Team override reason is required when not accepting a recommendation as-is.")
        if len(team_reason or "") > REASON_MAX:
            raise AuthError(422, "Team override reason is too long (max 1000 characters).")

        mentor_overridden = False
        mentor_reason = (mentor_override_reason or "").strip() or None
        if mentor_recommendation_id is not None:
            row = await self.mentor_recs.get_row(mentor_recommendation_id)
            if row is None or row.problem_id != problem.id:
                raise AuthError(422, "Cited mentor recommendation does not belong to this report.")
            if row.mentor_user_id != mentor_id:
                raise AuthError(422, "Cited mentor recommendation is for a different mentor.")
        else:
            mentor_overridden = True
        if mentor_overridden and not mentor_reason:
            raise AuthError(422, "Mentor override reason is required when not accepting a recommendation as-is.")
        if len(mentor_reason or "") > REASON_MAX:
            raise AuthError(422, "Mentor override reason is too long (max 1000 characters).")

        # Live revalidation (locked rows): never trust recommendation-time state.
        solver_profiles: list[tuple[User, StudentProfile]] = []
        for sid in solvers:
            solver_profiles.append(await self._require_solver(sid))
        mentor_user, mentor_profile = await self._require_mentor(mentor_id)

        # All validations passed: create everything, then commit once.
        team = await self.assignments.create_team(
            problem_id=problem.id, name=name, created_by=admin.id
        )
        for user, _profile in solver_profiles:
            await self.assignments.add_member(
                team_id=team.id, user_id=user.id, role_in_team=roles[user.id]
            )
        await self.assignments.create_assignment(
            problem_id=problem.id,
            team_id=team.id,
            mentor_user_id=mentor_user.id,
            source_team_recommendation_id=team_recommendation_id,
            source_mentor_recommendation_id=mentor_recommendation_id,
            assigned_by=admin.id,
            team_was_overridden=team_overridden,
            mentor_was_overridden=mentor_overridden,
            team_override_reason=team_reason,
            mentor_override_reason=mentor_reason,
        )
        for _user, profile in solver_profiles:
            profile.current_workload += 1
        mentor_profile.current_workload += 1

        old_status = problem.status
        problem.status = ProblemStatus.ASSIGNED
        member_names = ", ".join(u.full_name for u, _p in solver_profiles)
        await self._log(
            problem.id, ProblemEventType.TEAM_CREATED, admin.id, message=f"Team created: {member_names}."
        )
        await self._log(
            problem.id,
            ProblemEventType.TEAM_ASSIGNED,
            admin.id,
            message=f"Team assigned: {member_names}."
            + (" (override)" if team_overridden else " (as recommended)"),
        )
        await self._log(
            problem.id,
            ProblemEventType.MENTOR_ASSIGNED,
            admin.id,
            message=f"Mentor assigned: {mentor_user.full_name}."
            + (" (override)" if mentor_overridden else " (as recommended)"),
        )
        await self._log(
            problem.id,
            ProblemEventType.ASSIGNMENT_CREATED,
            admin.id,
            old_status=old_status.value,
            new_status=ProblemStatus.ASSIGNED.value,
            message=f"Report assigned by {admin.full_name}.",
        )
        await self.session.commit()

        refreshed = await self.assignments.active_for_problem(problem_id)
        if refreshed is None:
            raise AuthError(500, "Assignment vanished mid-transaction.")
        # Step 11 hook: assignment notifications, best-effort AFTER the core
        # commit so delivery can never break the assignment itself.
        try:
            from app.core.enums import NotificationType
            from app.services.notification_service import NotificationService

            notify = NotificationService(self.session)
            team_label = refreshed.team.name or f"Team · {problem.ticket_number}"
            for member in refreshed.team.members:
                if member.is_active:
                    await notify.notify_user(
                        member.user_id,
                        NotificationType.TEAM_ASSIGNED,
                        f"You were assigned to {problem.ticket_number}",
                        f"You joined {team_label} mentored by {mentor_user.full_name}.",
                        problem_id=problem.id,
                        related_entity_type="assignment",
                        related_entity_id=refreshed.id,
                    )
            await notify.notify_user(
                mentor_user.id,
                NotificationType.MENTOR_ASSIGNED,
                f"You mentor {problem.ticket_number}",
                f"You were assigned as mentor for {team_label}.",
                problem_id=problem.id,
                related_entity_type="assignment",
                related_entity_id=refreshed.id,
            )
            await self.session.commit()
        except Exception:
            logger.warning("assignment notifications failed for problem %s", problem_id)
            await self.session.rollback()
        return refreshed, True

    # ---------- reassign ----------

    async def reassign(
        self,
        problem_id: UUID,
        admin: User,
        *,
        solver_ids: list[UUID],
        mentor_id: UUID,
        reason: str,
        team_name: str | None = None,
        member_roles: dict[str, str] | None = None,
    ) -> ProblemAssignment:
        """Atomically replace team/mentor: old workloads released, new applied."""
        cleaned_reason = clean_reason(reason, field="Reassignment reason", max_len=REASON_MAX)
        try:
            return await self._reassign_inner(
                problem_id,
                admin,
                solver_ids=solver_ids,
                mentor_id=mentor_id,
                reason=cleaned_reason,
                team_name=team_name,
                member_roles=member_roles,
            )
        except AuthError:
            await self.session.rollback()
            raise
        except Exception as exc:
            await self.session.rollback()
            logger.warning("reassignment failed for problem %s: %s", problem_id, exc)
            raise AuthError(500, "Reassignment failed; nothing was changed.") from exc

    async def _reassign_inner(
        self,
        problem_id: UUID,
        admin: User,
        *,
        solver_ids: list[UUID],
        mentor_id: UUID,
        reason: str,
        team_name: str | None,
        member_roles: dict[str, str] | None,
    ) -> ProblemAssignment:
        problem = await self.assignments.get_problem_for_update(problem_id)
        if problem is None:
            raise AuthError(404, "Problem not found")
        await self._reject_duplicate_member(problem)
        if problem.status != ProblemStatus.ASSIGNED:
            raise AuthError(409, "Only ASSIGNED reports can be reassigned.")
        current = await self.assignments.active_for_problem(problem_id, for_update=True)
        if current is None:
            raise AuthError(409, "No active assignment to reassign.")

        solvers = _dedupe_preserve_order(list(solver_ids))
        if len(solvers) != len(list(solver_ids)):
            raise AuthError(422, "Duplicate solver in team selection.")
        self._check_team_size(len(solvers), override_reason=reason)
        roles = self._clean_roles(member_roles, solvers)
        name = self._clean_team_name(team_name)

        old_member_ids = {m.user_id for m in current.team.members if m.is_active}
        old_mentor_id = current.mentor_user_id
        if set(solvers) == old_member_ids and mentor_id == old_mentor_id:
            raise AuthError(409, "Reassignment is identical to the current assignment.")

        # Validate every incoming person live (locked). Staying members keep
        # their workload untouched; only added people need spare capacity.
        added = [sid for sid in solvers if sid not in old_member_ids]
        solver_rows: dict[UUID, tuple[User, StudentProfile]] = {}
        for sid in solvers:
            if sid in added:
                solver_rows[sid] = await self._require_solver(sid)
            else:
                user = await self.assignments.get_solver(sid)
                if user is None:
                    raise AuthError(500, "Assignment member vanished mid-transaction.")
                if user.student_profile is None:
                    raise AuthError(500, "Assignment member lost their profile mid-transaction.")
                locked = await self.assignments.lock_student_profile(user.student_profile.id)
                if locked is None:
                    raise AuthError(500, "Assignment member vanished mid-transaction.")
                solver_rows[sid] = (user, locked)
        if mentor_id != old_mentor_id:
            new_mentor, new_mentor_profile = await self._require_mentor(mentor_id)
            old_mentor_row = await self.assignments.get_mentor(old_mentor_id)
            if old_mentor_row is None:
                raise AuthError(500, "Assigned mentor vanished mid-transaction.")
            if old_mentor_row.faculty_profile is None:
                raise AuthError(500, "Assigned mentor lost their profile mid-transaction.")
            old_locked = await self.assignments.lock_faculty_profile(
                old_mentor_row.faculty_profile.id
            )
            if old_locked is None:
                raise AuthError(500, "Assigned mentor vanished mid-transaction.")
        else:
            same = await self.assignments.get_mentor(mentor_id)
            if same is None:
                raise AuthError(500, "Assigned mentor vanished mid-transaction.")
            if same.faculty_profile is None:
                raise AuthError(500, "Assigned mentor lost their profile mid-transaction.")
            locked_same = await self.assignments.lock_faculty_profile(same.faculty_profile.id)
            if locked_same is None:
                raise AuthError(500, "Assigned mentor vanished mid-transaction.")
            new_mentor, new_mentor_profile = same, locked_same
            old_locked = None

        now = datetime.now(UTC)
        # Retire the old assignment + team (history preserved, never deleted).
        current.status = AssignmentStatus.REASSIGNED.value
        current.unassigned_at = now
        current.unassigned_by = admin.id
        current.unassignment_reason = f"Reassigned: {reason}"
        await self.assignments.deactivate_team(current.team, now=now)

        # Workload math: released exactly once, applied exactly once, floor 0.
        removed = [mid for mid in old_member_ids if mid not in set(solvers)]
        for mid in removed:
            user = await self.assignments.get_solver(mid)
            if user is not None and user.student_profile is not None:
                locked = await self.assignments.lock_student_profile(user.student_profile.id)
                if locked is not None:
                    locked.current_workload = max(0, locked.current_workload - 1)
        for sid in added:
            _user, profile = solver_rows[sid]
            profile.current_workload += 1
        if mentor_id != old_mentor_id and old_locked is not None:
            old_locked.current_workload = max(0, old_locked.current_workload - 1)
            new_mentor_profile.current_workload += 1

        team_changed = set(solvers) != old_member_ids
        mentor_changed = mentor_id != old_mentor_id
        team = await self.assignments.create_team(
            problem_id=problem.id, name=name, created_by=admin.id
        )
        for sid in solvers:
            user, _profile = solver_rows[sid]
            await self.assignments.add_member(
                team_id=team.id, user_id=user.id, role_in_team=roles[sid]
            )
        # Provenance: carry forward unchanged sides, mark changed sides.
        await self.assignments.create_assignment(
            problem_id=problem.id,
            team_id=team.id,
            mentor_user_id=mentor_id,
            source_team_recommendation_id=current.source_team_recommendation_id,
            source_mentor_recommendation_id=current.source_mentor_recommendation_id,
            assigned_by=admin.id,
            team_was_overridden=True if team_changed else current.team_was_overridden,
            mentor_was_overridden=True if mentor_changed else current.mentor_was_overridden,
            team_override_reason=(f"Reassignment: {reason}" if team_changed else current.team_override_reason),
            mentor_override_reason=(
                f"Reassignment: {reason}" if mentor_changed else current.mentor_override_reason
            ),
        )
        member_names = ", ".join(solver_rows[sid][0].full_name for sid in solvers)
        # Step 10: removed members lose workspace access immediately; their
        # unfinished tasks are unassigned (never silently unusable) while
        # authorship/history is preserved.
        if removed:
            from app.services.workspace_service import WorkspaceService

            await WorkspaceService(self.session).handle_team_change(
                problem.id, set(removed), admin.id
            )
        await self._log(
            problem.id,
            ProblemEventType.ASSIGNMENT_UPDATED,
            admin.id,
            message=f"Reassigned by {admin.full_name}: {reason}. Team now: {member_names}.",
        )
        if team_changed:
            await self._log(
                problem.id, ProblemEventType.TEAM_ASSIGNED, admin.id, message=f"Team reassigned: {member_names}."
            )
        if mentor_changed:
            await self._log(
                problem.id,
                ProblemEventType.MENTOR_ASSIGNED,
                admin.id,
                message=f"Mentor reassigned: {new_mentor.full_name}.",
            )
        await self.session.commit()
        refreshed = await self.assignments.active_for_problem(problem_id)
        if refreshed is None:
            raise AuthError(500, "Assignment vanished mid-transaction.")
        return refreshed

    # ---------- cancel ----------

    async def cancel(
        self,
        problem_id: UUID,
        admin: User,
        *,
        reason: str,
        return_to: str = "APPROVED",
    ) -> ProblemAssignment:
        """Cancel the active assignment, releasing workloads exactly once."""
        cleaned_reason = clean_reason(reason, field="Cancellation reason", max_len=REASON_MAX)
        if return_to not in ("APPROVED", "UNDER_REVIEW"):
            raise AuthError(422, "Assignment can only return to APPROVED or UNDER_REVIEW.")
        try:
            return await self._cancel_inner(
                problem_id, admin, reason=cleaned_reason, return_to=return_to
            )
        except AuthError:
            await self.session.rollback()
            raise
        except Exception as exc:
            await self.session.rollback()
            logger.warning("cancellation failed for problem %s: %s", problem_id, exc)
            raise AuthError(500, "Cancellation failed; nothing was changed.") from exc

    async def _cancel_inner(
        self, problem_id: UUID, admin: User, *, reason: str, return_to: str
    ) -> ProblemAssignment:
        problem = await self.assignments.get_problem_for_update(problem_id)
        if problem is None:
            raise AuthError(404, "Problem not found")
        await self._reject_duplicate_member(problem)
        if problem.status != ProblemStatus.ASSIGNED:
            raise AuthError(409, "Only ASSIGNED reports have an assignment to cancel.")
        current = await self.assignments.active_for_problem(problem_id, for_update=True)
        if current is None:
            raise AuthError(409, "No active assignment to cancel.")

        now = datetime.now(UTC)
        current.status = AssignmentStatus.CANCELLED.value
        current.unassigned_at = now
        current.unassigned_by = admin.id
        current.unassignment_reason = reason
        # Release workloads exactly once (guarded by the ACTIVE check + lock above).
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
        await self.assignments.deactivate_team(current.team, now=now)

        old_status = problem.status
        problem.status = ProblemStatus(return_to)
        await self._log(
            problem.id,
            ProblemEventType.ASSIGNMENT_CANCELLED,
            admin.id,
            old_status=old_status.value,
            new_status=return_to,
            message=f"Assignment cancelled by {admin.full_name}: {reason}",
        )
        await self.session.commit()
        history = await self.assignments.history_for_problem(problem_id)
        cancelled = next((a for a in history if a.id == current.id), None)
        if cancelled is None:
            raise AuthError(500, "Assignment vanished mid-transaction.")
        return cancelled
