from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.problem_analysis import (
    ProblemPriorityAnalysis,
    ProblemRequiredSkill,
    ProblemSkillAnalysis,
    SkillEmbedding,
)


class PriorityAnalysisRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        problem_id: UUID,
        score: float | None,
        priority_level: str | None,
        components: dict[str, float],
        component_details: dict[str, object],
        algorithm_version: str,
        status: str,
        recalculation_reason: str | None,
        calculated_at: datetime,
    ) -> ProblemPriorityAnalysis:
        row = ProblemPriorityAnalysis(
            problem_id=problem_id,
            score=score,
            priority_level=priority_level,
            severity_component=components.get("severity", 0.0),
            affected_people_component=components.get("affected_people", 0.0),
            age_component=components.get("pending_age", 0.0),
            category_component=components.get("category_context", 0.0),
            duplicate_component=components.get("duplicate_impact", 0.0),
            component_details=component_details,
            algorithm_version=algorithm_version,
            status=status,
            recalculation_reason=recalculation_reason,
            calculated_at=calculated_at,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def latest_for_problem(self, problem_id: UUID) -> ProblemPriorityAnalysis | None:
        result = await self.session.execute(
            select(ProblemPriorityAnalysis)
            .where(ProblemPriorityAnalysis.problem_id == problem_id)
            .order_by(ProblemPriorityAnalysis.created_at.desc())
        )
        return result.scalars().first()

    async def history_for_problem(self, problem_id: UUID) -> list[ProblemPriorityAnalysis]:
        result = await self.session.execute(
            select(ProblemPriorityAnalysis)
            .where(ProblemPriorityAnalysis.problem_id == problem_id)
            .order_by(ProblemPriorityAnalysis.created_at.asc())
        )
        return list(result.scalars().all())


class SkillEmbeddingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def active_for_version(self, model_version: str) -> list[SkillEmbedding]:
        from app.models.skill import Skill

        result = await self.session.execute(
            select(SkillEmbedding)
            .join(Skill, Skill.id == SkillEmbedding.skill_id)
            .options(selectinload(SkillEmbedding.skill))
            .where(
                SkillEmbedding.model_version == model_version,
                Skill.is_active.is_(True),
            )
            .order_by(Skill.name.asc())
        )
        return list(result.scalars().all())

    async def count_for_version(self, model_version: str) -> int:
        from sqlalchemy import func

        result = await self.session.execute(
            select(func.count())
            .select_from(SkillEmbedding)
            .where(SkillEmbedding.model_version == model_version)
        )
        return result.scalar_one()


class SkillAnalysisRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        problem_id: UUID,
        model_name: str,
        model_version: str,
        status: str,
        recalculation_reason: str | None,
    ) -> ProblemSkillAnalysis:
        row = ProblemSkillAnalysis(
            problem_id=problem_id,
            model_name=model_name,
            model_version=model_version,
            status=status,
            recalculation_reason=recalculation_reason,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def add_required_skill(
        self,
        *,
        analysis_id: UUID,
        problem_id: UUID,
        skill_id: UUID,
        score: float,
        match_type: str,
        reason: str | None,
        model_name: str,
        model_version: str,
    ) -> ProblemRequiredSkill:
        row = ProblemRequiredSkill(
            analysis_id=analysis_id,
            problem_id=problem_id,
            skill_id=skill_id,
            score=score,
            match_type=match_type,
            reason=reason,
            model_name=model_name,
            model_version=model_version,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def latest_for_problem(self, problem_id: UUID) -> ProblemSkillAnalysis | None:
        result = await self.session.execute(
            select(ProblemSkillAnalysis)
            .where(ProblemSkillAnalysis.problem_id == problem_id)
            .order_by(ProblemSkillAnalysis.created_at.desc())
        )
        return result.scalars().first()

    async def required_skills_for_analysis(self, analysis_id: UUID) -> list[ProblemRequiredSkill]:
        result = await self.session.execute(
            select(ProblemRequiredSkill)
            .options(selectinload(ProblemRequiredSkill.skill))
            .where(ProblemRequiredSkill.analysis_id == analysis_id)
            .order_by(ProblemRequiredSkill.score.desc())
        )
        return list(result.scalars().all())
