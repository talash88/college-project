"""Campus problem reporting business logic (Step 4 reports + Step 5 auto-classification)."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    TERMINAL_PROBLEM_STATUSES,
    ProblemEventType,
    ProblemStatus,
    UserRole,
)
from app.models.problem import Problem, ProblemComment
from app.models.user import User
from app.repositories.problem_repository import (
    ActivityRepository,
    CommentRepository,
    ProblemRepository,
    TicketCounterRepository,
)
from app.schemas.problem import (
    DESCRIPTION_MAX,
    DESCRIPTION_MIN,
    LOCATION_MAX,
    LOCATION_MIN,
    TITLE_MAX,
    TITLE_MIN,
    CommentCreate,
    ProblemCreate,
    ProblemUpdate,
)
from app.services.auth_service import AuthError

logger = logging.getLogger(__name__)


def _clean(value: str, *, field: str, min_len: int, max_len: int) -> str:
    text = value.strip()
    if len(text) < min_len:
        raise AuthError(422, f"{field} is too short")
    if len(text) > max_len:
        raise AuthError(422, f"{field} is too long")
    return text


def _clean_optional(value: str | None, *, field: str, max_len: int) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) > max_len:
        raise AuthError(422, f"{field} is too long")
    return text


class ProblemService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.problems = ProblemRepository(session)
        self.counters = TicketCounterRepository(session)
        self.activities = ActivityRepository(session)
        self.comments = CommentRepository(session)

    @staticmethod
    def _is_admin(user: User) -> bool:
        return user.role == UserRole.ADMIN

    @staticmethod
    def _is_owner(user: User, problem: Problem) -> bool:
        return problem.reporter_id == user.id

    async def _new_ticket_number(self) -> str:
        year = datetime.now(UTC).year
        try:
            number = await self.counters.next_number(year)
        except IntegrityError:
            # Lost race inserting the year's counter row; retry once.
            await self.session.rollback()
            try:
                number = await self.counters.next_number(year)
            except IntegrityError as exc:
                await self.session.rollback()
                raise AuthError(500, "Could not generate ticket number") from exc
        return f"CX-{year}-{number:06d}"

    async def create_problem(self, user: User, data: ProblemCreate) -> Problem:
        ticket = await self._new_ticket_number()
        try:
            problem = await self.problems.create(
                ticket_number=ticket,
                title=_clean(data.title, field="Title", min_len=TITLE_MIN, max_len=TITLE_MAX),
                description=_clean(
                    data.description,
                    field="Description",
                    min_len=DESCRIPTION_MIN,
                    max_len=DESCRIPTION_MAX,
                ),
                reporter_id=user.id,
                location_text=_clean(
                    data.location_text,
                    field="Location",
                    min_len=LOCATION_MIN,
                    max_len=LOCATION_MAX,
                ),
                building=_clean_optional(data.building, field="Building", max_len=150),
                area=_clean_optional(data.area, field="Area", max_len=150),
                affected_people_count=data.affected_people_count,
            )
            await self.activities.log(
                problem_id=problem.id,
                event_type=ProblemEventType.SUBMITTED,
                actor_user_id=user.id,
                new_status=ProblemStatus.SUBMITTED.value,
                message=f"Report submitted with ticket {ticket}",
            )
            await self.session.commit()
        except AuthError:
            await self.session.rollback()
            raise
        except IntegrityError as exc:
            await self.session.rollback()
            raise AuthError(409, "Could not save problem (possible ticket collision)") from exc
        loaded = await self.problems.get_by_id(problem.id)
        if loaded is None:  # pragma: no cover - defensive
            raise AuthError(500, "Problem was created but could not be reloaded")
        # Steps 5-8: automatic analyses (classification, priority, skills,
        # duplicates, team + mentor recommendations). Each subsystem is
        # independent: a failure never loses the persisted report and never
        # blocks the other analyses.
        try:
            from app.services.classification_service import ProblemClassificationService
            from app.services.duplicate_service import DuplicateService
            from app.services.mentor_recommendation_service import MentorRecommendationService
            from app.services.priority_service import PriorityService
            from app.services.skill_extraction_service import RequiredSkillService
            from app.services.team_recommendation_service import TeamRecommendationService

            classifier = ProblemClassificationService(self.session)
            await classifier.classify(loaded)
            try:
                await PriorityService(self.session).analyze(loaded)
            except Exception:
                logger.warning("unexpected priority error for problem %s", problem.id)
            try:
                await RequiredSkillService(self.session).analyze(loaded)
            except Exception:
                logger.warning("unexpected skill extraction error for problem %s", problem.id)
            try:
                await DuplicateService(self.session).analyze(loaded)
            except Exception:
                logger.warning("unexpected duplicate analysis error for problem %s", problem.id)
            try:
                await TeamRecommendationService(self.session).analyze(loaded)
            except Exception:
                logger.warning("unexpected team recommendation error for problem %s", problem.id)
            try:
                await MentorRecommendationService(self.session).analyze(loaded)
            except Exception:
                logger.warning("unexpected mentor recommendation error for problem %s", problem.id)
        except Exception:  # defensive: report safety above all
            logger.warning("unexpected classification error for problem %s", problem.id)
        finally:
            # expire_on_commit=False keeps the pre-analysis (empty)
            # relationship snapshot on the instance; explicitly refresh the
            # collection so the response embeds the new audit row.
            await self.session.refresh(loaded, ["classifications"])
            loaded = await self.problems.get_by_id(problem.id)
            if loaded is None:  # pragma: no cover - defensive
                raise AuthError(500, "Problem was created but could not be reloaded")
        return loaded

    async def get_visible_problem(self, user: User, problem_id: UUID) -> Problem:
        """Owner, admin, active team member, or assigned mentor. Others get 404."""
        problem = await self.problems.get_by_id(problem_id)
        if problem is None:
            raise AuthError(404, "Problem not found")
        if self._is_owner(user, problem) or self._is_admin(user):
            return problem
        # Step 9: recommendation alone grants nothing; only an ACTIVE
        # assignment confers access (revoked automatically on removal).
        from app.services.assignment_service import AssignmentService

        service = AssignmentService(self.session)
        active = await service.active_for_problem(problem_id)
        if active is not None:
            if any(m.user_id == user.id and m.is_active for m in active.team.members):
                return problem
            if active.mentor_user_id == user.id:
                return problem
        # Step 11: once a report reaches verification/resolution/closure,
        # former team members and mentors keep READ-ONLY history access via
        # any past assignment (writes stay blocked by status gates).
        if problem.status in (
            ProblemStatus.AWAITING_VERIFICATION,
            ProblemStatus.RESOLVED,
            ProblemStatus.CLOSED,
        ):
            for past in await service.history_for_problem(problem_id):
                if any(m.user_id == user.id for m in past.team.members):
                    return problem
                if past.mentor_user_id == user.id:
                    return problem
        raise AuthError(404, "Problem not found")

    async def list_mine(
        self,
        user: User,
        *,
        skip: int,
        limit: int,
        status: ProblemStatus | None,
        search: str | None,
        newest_first: bool,
    ) -> tuple[list[Problem], int]:
        query = search.strip() if search else None
        return await self.problems.list_for_reporter(
            user.id,
            skip=skip,
            limit=limit,
            status=status,
            search=query or None,
            newest_first=newest_first,
        )

    async def stats_mine(self, user: User) -> tuple[int, dict[str, int]]:
        by_status = await self.problems.count_by_status(user.id)
        return sum(by_status.values()), by_status

    async def require_modifiable(self, user: User, problem_id: UUID) -> Problem:
        """Problem the user may edit/withdraw/attach to.

        Owners: only while SUBMITTED. Admins: any non-terminal status.
        """
        problem = await self.get_visible_problem(user, problem_id)
        if self._is_owner(user, problem) and not self._is_admin(user):
            if problem.status != ProblemStatus.SUBMITTED:
                raise AuthError(
                    409, f"Only SUBMITTED reports can be modified (status: {problem.status})"
                )
        elif self._is_admin(user):
            if problem.status in TERMINAL_PROBLEM_STATUSES:
                raise AuthError(
                    409, f"Terminal reports cannot be modified (status: {problem.status})"
                )
        return problem

    async def update_problem(self, user: User, problem_id: UUID, data: ProblemUpdate) -> Problem:
        problem = await self.require_modifiable(user, problem_id)
        fields = data.model_dump(exclude_unset=True)
        changed: list[str] = []
        if "title" in fields and fields["title"] is not None:
            problem.title = _clean(
                str(fields["title"]), field="Title", min_len=TITLE_MIN, max_len=TITLE_MAX
            )
            changed.append("title")
        if "description" in fields and fields["description"] is not None:
            problem.description = _clean(
                str(fields["description"]),
                field="Description",
                min_len=DESCRIPTION_MIN,
                max_len=DESCRIPTION_MAX,
            )
            changed.append("description")
        if "location_text" in fields and fields["location_text"] is not None:
            problem.location_text = _clean(
                str(fields["location_text"]),
                field="Location",
                min_len=LOCATION_MIN,
                max_len=LOCATION_MAX,
            )
            changed.append("location")
        if "building" in fields:
            problem.building = _clean_optional(fields["building"], field="Building", max_len=150)
            changed.append("building")
        if "area" in fields:
            problem.area = _clean_optional(fields["area"], field="Area", max_len=150)
            changed.append("area")
        if "affected_people_count" in fields:
            problem.affected_people_count = fields["affected_people_count"]
            changed.append("affected people")
        if not changed:
            raise AuthError(422, "No editable fields provided")
        await self.activities.log(
            problem_id=problem.id,
            event_type=ProblemEventType.EDITED,
            actor_user_id=user.id,
            message=f"Edited: {', '.join(changed)}",
        )
        await self.session.commit()
        # Step 7: embedding-relevant edits invalidate old pending suggestions.
        # Confirmed duplicates are never silently dropped (admin must undo).
        text_changed = any(
            key in ("title", "description", "location", "building", "area") for key in changed
        )
        if text_changed:
            try:
                from app.services.duplicate_service import DuplicateService

                loaded_for_dup = await self.problems.get_by_id(problem.id)
                if loaded_for_dup is not None:
                    await DuplicateService(self.session).analyze(loaded_for_dup)
            except Exception:
                logger.warning("duplicate reanalysis failed after edit of %s", problem.id)
        loaded = await self.problems.get_by_id(problem.id)
        if loaded is None:  # pragma: no cover - defensive
            raise AuthError(500, "Problem was updated but could not be reloaded")
        return loaded

    async def withdraw_problem(self, user: User, problem_id: UUID) -> Problem:
        """Soft withdrawal: status → WITHDRAWN, history preserved (no hard delete)."""
        problem = await self.require_modifiable(user, problem_id)
        old = problem.status
        problem.status = ProblemStatus.WITHDRAWN
        await self.activities.log(
            problem_id=problem.id,
            event_type=ProblemEventType.STATUS_CHANGED,
            actor_user_id=user.id,
            old_status=old.value,
            new_status=ProblemStatus.WITHDRAWN.value,
            message="Report withdrawn by "
            + (
                "admin"
                if self._is_admin(user) and not self._is_owner(user, problem)
                else "reporter"
            ),
        )
        await self.session.commit()
        loaded = await self.problems.get_by_id(problem.id)
        if loaded is None:  # pragma: no cover - defensive
            raise AuthError(500, "Problem was withdrawn but could not be reloaded")
        return loaded

    async def add_comment(
        self, user: User, problem_id: UUID, data: CommentCreate
    ) -> ProblemComment:
        problem = await self.get_visible_problem(user, problem_id)
        content = data.content.strip()
        if not content:
            raise AuthError(422, "Comment content is required")
        internal = bool(data.is_internal) and self._is_admin(user)
        comment = await self.comments.create(
            problem_id=problem.id,
            author_id=user.id,
            content=content,
            is_internal=internal,
        )
        await self.activities.log(
            problem_id=problem.id,
            event_type=ProblemEventType.COMMENT_ADDED,
            actor_user_id=user.id,
            message="Comment added" + (" (internal)" if internal else ""),
        )
        await self.session.commit()
        await self.session.refresh(comment, ["author"])
        return comment

    async def admin_list(
        self,
        *,
        skip: int,
        limit: int,
        status: ProblemStatus | None,
        reporter_id: UUID | None,
        search: str | None,
        date_from: datetime | None,
        date_to: datetime | None,
        min_affected: int | None,
        max_affected: int | None,
        newest_first: bool,
    ) -> tuple[list[Problem], int]:
        query = search.strip() if search else None
        return await self.problems.admin_list(
            skip=skip,
            limit=limit,
            status=status,
            reporter_id=reporter_id,
            search=query or None,
            date_from=date_from,
            date_to=date_to,
            min_affected=min_affected,
            max_affected=max_affected,
            newest_first=newest_first,
        )
