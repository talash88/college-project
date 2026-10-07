"""Admin review workflow service (Step 9).

Centralized status-transition validator plus start-review / approve / reject
actions. Every decision is auditable via problem audit fields AND activity
events. Reporters only ever see the safe rejection reason.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ProblemEventType, ProblemStatus
from app.models.problem import Problem
from app.models.user import User
from app.repositories.problem_repository import ActivityRepository, ProblemRepository
from app.services.auth_service import AuthError

logger = logging.getLogger(__name__)

# Central transition table: action -> (allowed from-states, to-state).
# Anything not listed here is rejected with 409 — the frontend must never
# mutate status directly.
TRANSITIONS: dict[str, tuple[frozenset[ProblemStatus], ProblemStatus]] = {
    "start_review": (frozenset({ProblemStatus.SUBMITTED}), ProblemStatus.UNDER_REVIEW),
    "approve": (frozenset({ProblemStatus.UNDER_REVIEW}), ProblemStatus.APPROVED),
    "reject": (
        frozenset({ProblemStatus.SUBMITTED, ProblemStatus.UNDER_REVIEW, ProblemStatus.APPROVED}),
        ProblemStatus.REJECTED,
    ),
}

REJECTION_REASON_MAX = 1000


def validate_transition(from_status: ProblemStatus, action: str) -> ProblemStatus:
    """Return the target state for an action, or raise 409."""
    rule = TRANSITIONS.get(action)
    if rule is None:
        raise AuthError(422, f"Unknown review action: {action}")
    allowed, target = rule
    if from_status not in allowed:
        allowed_names = ", ".join(sorted(s.value for s in allowed))
        raise AuthError(
            409,
            f"Cannot '{action}' a report with status {from_status.value} "
            f"(allowed from: {allowed_names}).",
        )
    return target


def clean_reason(reason: str | None, *, field: str = "Reason", max_len: int = 1000) -> str:
    text = (reason or "").strip()
    if not text:
        raise AuthError(422, f"{field} is required.")
    if len(text) > max_len:
        raise AuthError(422, f"{field} is too long (max {max_len} characters).")
    return text


class ReviewService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.problems = ProblemRepository(session)
        self.activities = ActivityRepository(session)

    async def _log(
        self,
        problem_id: UUID,
        event: ProblemEventType,
        actor: UUID,
        *,
        old_status: ProblemStatus,
        new_status: ProblemStatus,
        message: str | None = None,
    ) -> None:
        await self.activities.log(
            problem_id=problem_id,
            event_type=event,
            actor_user_id=actor,
            old_status=old_status.value,
            new_status=new_status.value,
            message=message,
        )

    async def start_review(self, problem: Problem, admin: User) -> tuple[Problem, bool]:
        """SUBMITTED → UNDER_REVIEW. Idempotent: already-reviewing returns (problem, True)."""
        if problem.status == ProblemStatus.UNDER_REVIEW:
            return problem, True
        target = validate_transition(problem.status, "start_review")
        old = problem.status
        problem.status = target
        problem.reviewed_by = admin.id
        problem.reviewed_at = datetime.now(UTC)
        await self.session.commit()
        await self._log(
            problem.id,
            ProblemEventType.REVIEW_STARTED,
            admin.id,
            old_status=old,
            new_status=target,
            message=f"Review started by {admin.full_name}.",
        )
        await self.session.commit()
        return problem, False

    async def approve(
        self, problem: Problem, admin: User, note: str | None = None
    ) -> Problem:
        """UNDER_REVIEW → APPROVED. Approval does not assign anyone."""
        target = validate_transition(problem.status, "approve")
        old = problem.status
        problem.status = target
        problem.approved_by = admin.id
        problem.approved_at = datetime.now(UTC)
        message = f"Approved by {admin.full_name}."
        cleaned_note = (note or "").strip()
        if cleaned_note:
            if len(cleaned_note) > 1000:
                raise AuthError(422, "Approval note is too long (max 1000 characters).")
            message += f" Note: {cleaned_note}"
        await self.session.commit()
        await self._log(
            problem.id,
            ProblemEventType.PROBLEM_APPROVED,
            admin.id,
            old_status=old,
            new_status=target,
            message=message,
        )
        await self.session.commit()
        return problem

    async def reject(self, problem: Problem, admin: User, reason: str | None) -> Problem:
        """SUBMITTED/UNDER_REVIEW/APPROVED → REJECTED with mandatory safe reason."""
        cleaned = clean_reason(reason, field="Rejection reason", max_len=REJECTION_REASON_MAX)
        target = validate_transition(problem.status, "reject")
        old = problem.status
        problem.status = target
        problem.rejection_reason = cleaned
        await self.session.commit()
        await self._log(
            problem.id,
            ProblemEventType.PROBLEM_REJECTED,
            admin.id,
            old_status=old,
            new_status=target,
            message=f"Rejected by {admin.full_name}: {cleaned}",
        )
        await self.session.commit()
        return problem

    async def get_by_id_or_404(self, problem_id: UUID) -> Problem:
        problem = await self.problems.get_by_id(problem_id)
        if problem is None:
            raise AuthError(404, "Problem not found")
        return problem
