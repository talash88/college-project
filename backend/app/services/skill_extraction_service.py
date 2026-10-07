"""Required-skill extraction service (Step 6).

Hybrid: exact phrase matching (high precision) + Sentence-BERT cosine over
pgvector-stored skill embeddings + small category bonus. Rows are created
only above threshold — relevance is never faked. Failures yield a FAILED
analysis row, never invented skills.
"""

import asyncio
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.ml.skills.embeddings import EmbeddingModelUnavailableError, get_embedding_model
from app.ml.skills.matcher import (
    SkillCandidate,
    SkillMatch,
    category_bonus,
    cosine,
    find_exact_phrases,
    problem_match_text,
    rank_candidates,
)
from app.models.problem import Problem
from app.models.problem_analysis import ProblemRequiredSkill, ProblemSkillAnalysis
from app.repositories.analysis_repository import SkillAnalysisRepository, SkillEmbeddingRepository
from app.repositories.problem_repository import ClassificationRepository, ProblemRepository
from app.services.auth_service import AuthError

logger = logging.getLogger(__name__)


class RequiredSkillService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.problems = ProblemRepository(session)
        self.analyses = SkillAnalysisRepository(session)
        self.embeddings = SkillEmbeddingRepository(session)
        self.classifications = ClassificationRepository(session)

    async def _record_failure(
        self, problem: Problem, reason: str, recalc: str | None
    ) -> ProblemSkillAnalysis:
        logger.warning("skill extraction failed for problem %s: %s", problem.id, reason)
        row = await self.analyses.create(
            problem_id=problem.id,
            model_name=settings.SKILL_EMBEDDING_MODEL,
            model_version=settings.SKILL_EXTRACTOR_VERSION,
            status="FAILED",
            recalculation_reason=recalc,
        )
        problem.required_skills_status = "FAILED"
        await self.session.commit()
        return row

    def _encode(self, text: str) -> list[float]:
        model = get_embedding_model()
        vector = model.encode([text], normalize_embeddings=True, show_progress_bar=False)[0]
        return [float(x) for x in vector.tolist()]

    async def analyze(
        self, problem: Problem, recalculation_reason: str | None = None
    ) -> ProblemSkillAnalysis:
        # Snapshot plain data: ORM instances must not cross threads.
        title = problem.title
        description = problem.description
        problem_id = problem.id
        latest = await self.classifications.latest_for_problem(problem.id)
        category = (latest.final_category or latest.predicted_category) if latest else None

        stored = await self.embeddings.active_for_version(settings.SKILL_EMBEDDING_VERSION)
        if not stored:
            return await self._record_failure(
                problem, "no skill embeddings built", recalculation_reason
            )

        match_text = problem_match_text(title, description, category)
        try:
            problem_vector = await asyncio.to_thread(self._encode, match_text)
        except EmbeddingModelUnavailableError as exc:
            return await self._record_failure(problem, str(exc), recalculation_reason)
        except Exception as exc:
            return await self._record_failure(
                problem, f"{type(exc).__name__}: {exc}", recalculation_reason
            )

        candidates: list[SkillCandidate] = []
        for row in stored:
            skill = row.skill
            semantic = cosine(problem_vector, list(row.embedding))
            exact = find_exact_phrases(match_text, skill.name)
            candidates.append(
                SkillCandidate(
                    skill_id=skill.id,
                    skill_name=skill.name,
                    skill_category=skill.category.value,
                    semantic_score=round(semantic, 4),
                    exact_phrase=exact,
                    category_bonus=category_bonus(category, skill.category.value),
                )
            )
        matches: list[SkillMatch] = rank_candidates(candidates)

        analysis = await self.analyses.create(
            problem_id=problem_id,
            model_name=settings.SKILL_EMBEDDING_MODEL,
            model_version=settings.SKILL_EXTRACTOR_VERSION,
            status="COMPLETED",
            recalculation_reason=recalculation_reason,
        )
        for match in matches:
            await self.analyses.add_required_skill(
                analysis_id=analysis.id,
                problem_id=problem_id,
                skill_id=match.skill_id,
                score=match.score,
                match_type=match.match_type,
                reason=match.reason,
                model_name=settings.SKILL_EMBEDDING_MODEL,
                model_version=settings.SKILL_EXTRACTOR_VERSION,
            )
        problem.required_skills_status = "COMPLETED"
        await self.session.commit()
        return analysis

    async def analyze_problem_id(
        self, problem_id: UUID, recalculation_reason: str | None = None
    ) -> ProblemSkillAnalysis:
        problem = await self.problems.get_by_id(problem_id)
        if problem is None:
            raise AuthError(404, "Problem not found")
        try:
            return await self.analyze(problem, recalculation_reason)
        except AuthError:
            raise
        except Exception as exc:
            logger.warning("skill extraction failed for problem %s: %s", problem_id, exc)
            raise AuthError(500, "Skill extraction failed") from exc

    async def latest_with_skills(
        self, problem_id: UUID
    ) -> tuple[ProblemSkillAnalysis | None, list[ProblemRequiredSkill]]:
        latest = await self.analyses.latest_for_problem(problem_id)
        if latest is None:
            return None, []
        required = await self.analyses.required_skills_for_analysis(latest.id)
        return latest, required
