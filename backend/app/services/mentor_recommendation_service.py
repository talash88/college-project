"""Faculty mentor recommendation service (Step 8).

Advisory only: ranks eligible MENTORs with an explainable 0-100 score built
from semantic specialization similarity (existing Sentence Transformer, 35),
required-skill match (30), category/domain overlap (15), availability (10),
and workload (10). No assignment, no workload changes.
"""

import asyncio
import logging
import uuid
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import ProblemEventType, ProblemStatus, RecommendationStatus
from app.ml.recommendations.mentor_scoring import (
    MentorInput,
    MentorScore,
    MentorSkillInput,
    mentor_text,
    problem_text_for_mentor,
    score_mentor,
)
from app.ml.recommendations.scoring import RequiredSkillInput
from app.ml.skills.embeddings import EmbeddingModelUnavailableError, get_embedding_model
from app.ml.skills.matcher import cosine
from app.models.problem import Problem
from app.models.recommendation import MentorRecommendation
from app.repositories.problem_repository import ClassificationRepository, ProblemRepository
from app.repositories.recommendation_repository import (
    CandidateRepository,
    MentorRecommendationRepository,
)
from app.services.auth_service import AuthError

logger = logging.getLogger(__name__)


class MentorRecommendationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.problems = ProblemRepository(session)
        self.classifications = ClassificationRepository(session)
        self.candidates = CandidateRepository(session)
        self.recommendations = MentorRecommendationRepository(session)

    # ---------- inputs ----------

    async def _category_of(self, problem: Problem) -> str | None:
        latest = await self.classifications.latest_for_problem(problem.id)
        if latest is None:
            return None
        return latest.final_category or latest.predicted_category

    async def _required_inputs(self, problem: Problem) -> tuple[list[RequiredSkillInput], str | None]:
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
    def _mentor_input(user: object) -> MentorInput:
        from app.models.user import User

        assert isinstance(user, User)
        profile = user.faculty_profile
        assert profile is not None
        return MentorInput(
            user_id=str(user.id),
            name=user.full_name,
            availability=profile.availability_status.value,
            current_workload=profile.current_workload,
            max_workload=profile.max_workload,
            department=profile.department.value,
            designation=profile.designation,
            specialization=profile.specialization,
            skills=tuple(
                MentorSkillInput(
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

    def _encode(self, text: str) -> list[float]:
        model = get_embedding_model()
        vector = model.encode([text], normalize_embeddings=True, show_progress_bar=False)[0]
        return [float(x) for x in vector.tolist()]

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
        problem.mentor_recommendation_status = status.value
        await self.session.commit()
        return status

    # ---------- analysis ----------

    async def analyze(
        self, problem: Problem, recalculation_reason: str | None = None
    ) -> RecommendationStatus:
        """Rank eligible mentors. Never raises for data issues."""
        if problem.status == ProblemStatus.DUPLICATE and problem.canonical_problem_id is not None:
            return RecommendationStatus(problem.mentor_recommendation_status)
        try:
            return await self._analyze_inner(problem, recalculation_reason)
        except AuthError:
            raise
        except Exception as exc:
            logger.warning("mentor recommendation failed for problem %s: %s", problem.id, exc)
            problem.mentor_recommendation_status = RecommendationStatus.FAILED.value
            await self.session.commit()
            return RecommendationStatus.FAILED

    async def _analyze_inner(
        self, problem: Problem, recalculation_reason: str | None
    ) -> RecommendationStatus:
        required, category = await self._required_inputs(problem)
        if not required:
            return await self._record_status(problem, RecommendationStatus.INSUFFICIENT_DATA)

        eligible = await self.candidates.eligible_mentors()
        if not eligible:
            return await self._record_status(problem, RecommendationStatus.NO_ELIGIBLE_CANDIDATES)

        mentors = [self._mentor_input(u) for u in eligible]
        problem_repr = problem_text_for_mentor(
            problem.title,
            problem.description,
            category,
            [r.name for r in required],
        )
        try:
            problem_vector = await asyncio.to_thread(self._encode, problem_repr)
        except EmbeddingModelUnavailableError as exc:
            logger.warning("mentor semantic model unavailable for problem %s: %s", problem.id, exc)
            return await self._record_status(problem, RecommendationStatus.FAILED)
        mentor_vectors: dict[str, list[float]] = {}
        try:
            texts = [mentor_text(m) for m in mentors]
            model_vectors = await asyncio.to_thread(
                self._encode_many, texts
            )
            for mentor, vector in zip(mentors, model_vectors, strict=True):
                mentor_vectors[mentor.user_id] = vector
        except EmbeddingModelUnavailableError as exc:
            logger.warning("mentor semantic model unavailable for problem %s: %s", problem.id, exc)
            return await self._record_status(problem, RecommendationStatus.FAILED)

        required_tuple = tuple(required)
        scored: list[tuple[MentorInput, MentorScore]] = []
        for mentor in mentors:
            semantic = cosine(problem_vector, mentor_vectors[mentor.user_id])
            scored.append(
                (
                    mentor,
                    score_mentor(
                        mentor,
                        required_tuple,
                        category,
                        semantic,
                        weight_specialization=settings.MENTOR_WEIGHT_SPECIALIZATION,
                        weight_skill=settings.MENTOR_WEIGHT_SKILL,
                        weight_category=settings.MENTOR_WEIGHT_CATEGORY,
                        weight_availability=settings.MENTOR_WEIGHT_AVAILABILITY,
                        weight_workload=settings.MENTOR_WEIGHT_WORKLOAD,
                    ),
                )
            )
        # Deterministic ranking: higher score, then lower workload ratio, then UUID.
        scored.sort(
            key=lambda pair: (
                -pair[1].total,
                pair[0].current_workload / max(1, pair[0].max_workload),
                pair[0].user_id,
            )
        )

        run_id = uuid.uuid4()
        for mentor, mentor_score in scored:
            await self.recommendations.create(
                problem_id=problem.id,
                run_id=run_id,
                mentor_user_id=uuid.UUID(mentor.user_id),
                score=mentor_score.total,
                specialization_score=mentor_score.specialization,
                skill_match_score=mentor_score.skill,
                category_score=mentor_score.category,
                availability_score=mentor_score.availability,
                workload_score=mentor_score.workload,
                semantic_similarity=mentor_score.semantic_similarity,
                algorithm_version=settings.MENTOR_ALGORITHM_VERSION,
                reason_data={
                    "name": mentor.name,
                    "designation": mentor.designation,
                    "specialization": mentor.specialization,
                    "department": mentor.department,
                    "availability": mentor.availability,
                    "current_workload": mentor.current_workload,
                    "max_workload": mentor.max_workload,
                    "semantic_similarity": mentor_score.semantic_similarity,
                    "matched_skills": [
                        {
                            "skill_id": d.required_skill_id,
                            "name": d.required_skill_name,
                            "relevance": d.relevance,
                            "match_kind": d.match_kind,
                            "proficiency": d.proficiency,
                            "proficiency_label": d.proficiency_label,
                        }
                        for d in mentor_score.skill_details
                    ],
                },
            )

        problem.mentor_recommendation_status = RecommendationStatus.COMPLETED.value
        await self.session.commit()
        best = scored[0][0].name if scored else "none"
        await self._log(
            problem.id,
            ProblemEventType.MENTOR_RECOMMENDATION_COMPLETED,
            f"Ranked {len(scored)} mentor candidate(s); top: {best}"
            + (f" ({recalculation_reason})" if recalculation_reason else ""),
        )
        await self.session.commit()
        return RecommendationStatus.COMPLETED

    def _encode_many(self, texts: list[str]) -> list[list[float]]:
        model = get_embedding_model()
        vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [[float(x) for x in row.tolist()] for row in vectors]

    # ---------- reads ----------

    async def latest_ranking(self, problem_id: UUID) -> list[MentorRecommendation]:
        run_id = await self.recommendations.latest_run_id(problem_id)
        if run_id is None:
            return []
        return await self.recommendations.for_run(run_id)

    async def history(self, problem_id: UUID) -> list[dict[str, object]]:
        return await self.recommendations.history_run_ids(problem_id)

    async def analyze_problem_id(
        self, problem_id: UUID, recalculation_reason: str | None = None
    ) -> RecommendationStatus:
        problem = await self.problems.get_by_id(problem_id)
        if problem is None:
            raise AuthError(404, "Problem not found")
        return await self.analyze(problem, recalculation_reason)
