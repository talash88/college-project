"""Explainable priority persistence (Step 6).

The math lives in app/ml/priority/scorer.py (pure, unit-tested); this
service persists audit rows, maintains the problem cache, and supports
recalculation. History is never rewritten.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.priority.config import ALGORITHM_VERSION, default_config
from app.ml.priority.scorer import calculate_priority
from app.models.problem import Problem
from app.models.problem_analysis import ProblemPriorityAnalysis
from app.repositories.analysis_repository import PriorityAnalysisRepository
from app.repositories.problem_repository import ClassificationRepository, ProblemRepository
from app.services.auth_service import AuthError

logger = logging.getLogger(__name__)


class PriorityService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.problems = ProblemRepository(session)
        self.analyses = PriorityAnalysisRepository(session)
        self.classifications = ClassificationRepository(session)

    async def _category_for(self, problem: Problem) -> tuple[str | None, str | None]:
        latest = await self.classifications.latest_for_problem(problem.id)
        if latest is None:
            return None, None
        return latest.final_category, latest.predicted_category

    async def analyze(
        self,
        problem: Problem,
        recalculation_reason: str | None = None,
        duplicate_count: int = 0,
    ) -> ProblemPriorityAnalysis:
        """Score a problem. duplicate_count = admin-confirmed additional cluster
        reports (0 for members and unclustered reports — no inflation)."""
        config = default_config()
        final_category, predicted_category = await self._category_for(problem)
        result = calculate_priority(
            title=problem.title,
            description=problem.description,
            affected_people_count=problem.affected_people_count,
            submitted_at=problem.submitted_at,
            status=problem.status.value,
            final_category=final_category,
            predicted_category=predicted_category,
            duplicate_count=duplicate_count,
            config=config,
        )
        components = {c.component: float(c.contribution) for c in result.components}
        details: dict[str, object] = {
            "components": [
                {
                    "component": c.component,
                    "raw_value": c.raw_value,
                    "contribution": c.contribution,
                    "max_contribution": c.max_contribution,
                    "reason": c.reason,
                }
                for c in result.components
            ],
            "reasons": result.reasons,
            "weights": {
                "severity": config.weight_severity,
                "affected_people": config.weight_affected,
                "pending_age": config.weight_age,
                "category_context": config.weight_category,
                "duplicate_impact": config.weight_duplicate,
            },
            "level_boundaries": {
                "low_max": config.level_low_max,
                "medium_max": config.level_medium_max,
                "high_max": config.level_high_max,
            },
        }
        row = await self.analyses.create(
            problem_id=problem.id,
            score=float(result.score),
            priority_level=result.level,
            components=components,
            component_details=details,
            algorithm_version=ALGORITHM_VERSION,
            status="COMPLETED",
            recalculation_reason=recalculation_reason,
            calculated_at=datetime.now(UTC),
        )
        problem.priority_score = float(result.score)
        problem.priority_level = result.level
        problem.priority_status = "COMPLETED"
        await self.session.commit()
        return row

    async def analyze_problem_id(
        self,
        problem_id: UUID,
        recalculation_reason: str | None = None,
        duplicate_count: int = 0,
    ) -> ProblemPriorityAnalysis:
        problem = await self.problems.get_by_id(problem_id)
        if problem is None:
            raise AuthError(404, "Problem not found")
        if duplicate_count == 0:
            # Admin recalculations must preserve the real confirmed-duplicate
            # contribution instead of silently resetting it to zero.
            from app.repositories.duplicate_repository import ClusterRepository

            duplicate_count = await ClusterRepository(self.session).confirmed_other_count(
                problem_id
            )
        try:
            return await self.analyze(problem, recalculation_reason, duplicate_count)
        except AuthError:
            raise
        except Exception as exc:
            logger.warning("priority analysis failed for problem %s: %s", problem_id, exc)
            raise AuthError(500, "Priority analysis failed") from exc

    async def latest_for(self, problem_id: UUID) -> ProblemPriorityAnalysis | None:
        return await self.analyses.latest_for_problem(problem_id)

    async def history_for(self, problem_id: UUID) -> list[ProblemPriorityAnalysis]:
        return await self.analyses.history_for_problem(problem_id)
