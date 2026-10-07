"""Student team recommendation service (Step 8).

Advisory only: evaluates deterministic TEAM COMBINATIONS over real data
(Step 6 required skills, user proficiency/verification, availability,
workload, department) and persists the top options with full score
breakdowns. No randomness, no workload changes, no assignment.
"""

import logging
import uuid
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import ProblemEventType, ProblemStatus, RecommendationStatus
from app.ml.recommendations.scoring import (
    RequiredSkillInput,
    SolverInput,
    SolverSkillInput,
    score_team,
)
from app.ml.recommendations.team_search import search_teams
from app.models.problem import Problem
from app.models.recommendation import TeamRecommendation
from app.repositories.problem_repository import ClassificationRepository, ProblemRepository
from app.repositories.recommendation_repository import (
    CandidateRepository,
    TeamRecommendationRepository,
)
from app.services.auth_service import AuthError

logger = logging.getLogger(__name__)


class TeamRecommendationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.problems = ProblemRepository(session)
        self.classifications = ClassificationRepository(session)
        self.candidates = CandidateRepository(session)
        self.recommendations = TeamRecommendationRepository(session)

    # ---------- inputs ----------

    async def _category_of(self, problem: Problem) -> str | None:
        latest = await self.classifications.latest_for_problem(problem.id)
        if latest is None:
            return None
        return latest.final_category or latest.predicted_category

    async def _required_inputs(self, problem: Problem) -> tuple[list[RequiredSkillInput], str | None]:
        """Latest COMPLETED Step 6 extraction only; never fabricated."""
        from app.services.skill_extraction_service import RequiredSkillService

        latest, rows = await RequiredSkillService(self.session).latest_with_skills(problem.id)
        if latest is None or latest.status != "COMPLETED" or not rows:
            return [], await self._category_of(problem)
        inputs: list[RequiredSkillInput] = []
        for row in rows:
            skill = row.skill
            inputs.append(
                RequiredSkillInput(
                    skill_id=str(row.skill_id),
                    name=skill.name if skill is not None else str(row.skill_id),
                    relevance=float(row.score),
                    category=skill.category.value
                    if skill is not None and hasattr(skill.category, "value")
                    else (str(skill.category) if skill is not None else None),
                )
            )
        return inputs, await self._category_of(problem)

    @staticmethod
    def _solver_input(user: object) -> SolverInput:
        from app.models.user import User

        assert isinstance(user, User)
        profile = user.student_profile
        assert profile is not None
        return SolverInput(
            user_id=str(user.id),
            name=user.full_name,
            availability=profile.availability_status.value,
            current_workload=profile.current_workload,
            max_workload=profile.max_workload,
            department=profile.department.value,
            academic_year=profile.academic_year,
            skills=tuple(
                SolverSkillInput(
                    skill_id=str(us.skill_id),
                    name=us.skill.name if us.skill is not None else str(us.skill_id),
                    proficiency=us.proficiency_level,
                    is_verified=bool(us.is_verified),
                    category=us.skill.category.value
                    if us.skill is not None and hasattr(us.skill.category, "value")
                    else None,
                )
                for us in user.user_skills
            ),
        )

    def _weights(self) -> dict[str, float]:
        return {
            "coverage": settings.TEAM_WEIGHT_COVERAGE,
            "proficiency": settings.TEAM_WEIGHT_PROFICIENCY,
            "availability": settings.TEAM_WEIGHT_AVAILABILITY,
            "workload": settings.TEAM_WEIGHT_WORKLOAD,
            "verified": settings.TEAM_WEIGHT_VERIFIED,
            "domain": settings.TEAM_WEIGHT_DOMAIN,
        }

    def _sizes(self) -> tuple[int, int, bool]:
        min_size = settings.TEAM_MIN_SIZE
        max_size = max(min_size, settings.TEAM_MAX_SIZE)
        return min_size, max_size, settings.TEAM_ALLOW_SOLO

    async def _log(self, problem_id: UUID, event: ProblemEventType, message: str | None) -> None:
        from app.repositories.problem_repository import ActivityRepository

        await ActivityRepository(self.session).log(
            problem_id=problem_id,
            event_type=event,
            actor_user_id=None,
            message=message,
        )

    async def _record_status(
        self, problem: Problem, status: RecommendationStatus
    ) -> RecommendationStatus:
        problem.team_recommendation_status = status.value
        await self.session.commit()
        return status

    # ---------- analysis ----------

    async def analyze(
        self, problem: Problem, recalculation_reason: str | None = None
    ) -> RecommendationStatus:
        """Recommend up to N team options. Never raises for data issues."""
        if problem.status == ProblemStatus.DUPLICATE and problem.canonical_problem_id is not None:
            # Duplicate members are served through the canonical issue.
            return RecommendationStatus(problem.team_recommendation_status)
        try:
            return await self._analyze_inner(problem, recalculation_reason)
        except AuthError:
            raise
        except Exception as exc:
            logger.warning("team recommendation failed for problem %s: %s", problem.id, exc)
            problem.team_recommendation_status = RecommendationStatus.FAILED.value
            await self.session.commit()
            return RecommendationStatus.FAILED

    async def _analyze_inner(
        self, problem: Problem, recalculation_reason: str | None
    ) -> RecommendationStatus:
        required, category = await self._required_inputs(problem)
        if not required:
            return await self._record_status(problem, RecommendationStatus.INSUFFICIENT_DATA)

        eligible = await self.candidates.eligible_solvers()
        min_size, max_size, allow_solo = self._sizes()
        smallest = 1 if allow_solo else min_size
        if len(eligible) < smallest:
            return await self._record_status(problem, RecommendationStatus.NO_ELIGIBLE_CANDIDATES)

        solvers = [self._solver_input(u) for u in eligible]
        options = search_teams(
            solvers,
            required,
            category,
            min_size=min_size,
            max_size=max_size,
            allow_solo=allow_solo,
            num_options=settings.TEAM_NUM_OPTIONS,
            pool_size=settings.TEAM_CANDIDATE_POOL,
            weights=self._weights(),
        )
        if not options:
            return await self._record_status(problem, RecommendationStatus.NO_ELIGIBLE_CANDIDATES)

        run_id = uuid.uuid4()
        weight_kwargs = {
            "weight_coverage": settings.TEAM_WEIGHT_COVERAGE,
            "weight_proficiency": settings.TEAM_WEIGHT_PROFICIENCY,
            "weight_availability": settings.TEAM_WEIGHT_AVAILABILITY,
            "weight_workload": settings.TEAM_WEIGHT_WORKLOAD,
            "weight_verified": settings.TEAM_WEIGHT_VERIFIED,
            "weight_domain": settings.TEAM_WEIGHT_DOMAIN,
        }
        required_tuple = tuple(required)
        for option in options:
            row = await self.recommendations.create_option(
                problem_id=problem.id,
                run_id=run_id,
                algorithm_version=settings.TEAM_ALGORITHM_VERSION,
                score=option.score.total,
                skill_coverage_score=option.score.coverage,
                proficiency_score=option.score.proficiency,
                availability_score=option.score.availability,
                workload_score=option.score.workload,
                verified_skill_score=option.score.verified,
                domain_score=option.score.domain,
                coverage_percent=option.score.coverage_percent,
                team_size=len(option.members),
                missing_skills=list(option.score.missing_skill_names),
            )
            for member in option.members:
                solo = score_team((member,), required_tuple, category, **weight_kwargs)
                covered: list[dict[str, object]] = []
                high_relevance: list[str] = []
                for detail in option.score.per_skill:
                    if detail.best_member_id != member.user_id:
                        continue
                    relevance = float(detail.relevance)
                    covered.append(
                        {
                            "skill_id": detail.required_skill_id,
                            "name": detail.required_skill_name,
                            "relevance": relevance,
                            "match_kind": detail.match_kind,
                            "proficiency": detail.proficiency,
                            "proficiency_label": detail.proficiency_label,
                            "verified": detail.verified,
                        }
                    )
                    if relevance >= 0.7:
                        high_relevance.append(detail.required_skill_name)
                await self.recommendations.add_member(
                    recommendation_id=row.id,
                    user_id=uuid.UUID(member.user_id),
                    individual_score=solo.total,
                    covered_skills=covered,
                    reason_data={
                        "name": member.name,
                        "availability": member.availability,
                        "current_workload": member.current_workload,
                        "max_workload": member.max_workload,
                        "department": member.department,
                        "academic_year": member.academic_year,
                        "covered_count": len(covered),
                        "high_relevance_covered": high_relevance,
                    },
                )

        problem.team_recommendation_status = RecommendationStatus.COMPLETED.value
        await self.session.commit()
        await self._log(
            problem.id,
            ProblemEventType.TEAM_RECOMMENDATION_COMPLETED,
            f"Recommended {len(options)} team option(s): "
            + ", ".join(f"{o.score.total:.0f}" for o in options)
            + (f" ({recalculation_reason})" if recalculation_reason else ""),
        )
        await self.session.commit()
        return RecommendationStatus.COMPLETED

    # ---------- reads ----------

    async def latest_options(self, problem_id: UUID) -> list[TeamRecommendation]:
        run_id = await self.recommendations.latest_run_id(problem_id)
        if run_id is None:
            return []
        return await self.recommendations.options_for_run(run_id)

    async def history(self, problem_id: UUID) -> list[dict[str, object]]:
        return await self.recommendations.history_run_ids(problem_id)

    async def analyze_problem_id(
        self, problem_id: UUID, recalculation_reason: str | None = None
    ) -> RecommendationStatus:
        problem = await self.problems.get_by_id(problem_id)
        if problem is None:
            raise AuthError(404, "Problem not found")
        return await self.analyze(problem, recalculation_reason)
