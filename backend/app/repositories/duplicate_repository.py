from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import DuplicateDecisionStatus, ProblemStatus
from app.models.problem import Problem
from app.models.problem_duplicate import (
    DuplicateCluster,
    DuplicateClusterMember,
    ProblemDuplicateCandidate,
    ProblemEmbedding,
)

ACTIVE_SEARCH_STATUSES = (
    ProblemStatus.SUBMITTED,
    ProblemStatus.UNDER_REVIEW,
    ProblemStatus.APPROVED,
    ProblemStatus.ASSIGNED,
    ProblemStatus.IN_PROGRESS,
    ProblemStatus.AWAITING_VERIFICATION,
    ProblemStatus.DUPLICATE,
)


def order_pair(a: UUID, b: UUID) -> tuple[UUID, UUID]:
    return (a, b) if str(a) < str(b) else (b, a)


class ProblemEmbeddingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, problem_id: UUID, model_version: str) -> ProblemEmbedding | None:
        result = await self.session.execute(
            select(ProblemEmbedding).where(
                ProblemEmbedding.problem_id == problem_id,
                ProblemEmbedding.model_version == model_version,
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        problem_id: UUID,
        vector: list[float],
        model_name: str,
        model_version: str,
        source_text_hash: str,
    ) -> ProblemEmbedding:
        existing = await self.get(problem_id, model_version)
        if existing is None:
            row = ProblemEmbedding(
                problem_id=problem_id,
                embedding=vector,
                model_name=model_name,
                model_version=model_version,
                source_text_hash=source_text_hash,
            )
            self.session.add(row)
            await self.session.flush()
            return row
        existing.embedding = vector
        existing.model_name = model_name
        existing.source_text_hash = source_text_hash
        await self.session.flush()
        return existing

    async def missing_problem_ids(self, model_version: str, limit: int = 500) -> list[UUID]:
        """Problems without a current-version embedding (backfill source)."""
        subquery = select(ProblemEmbedding.problem_id).where(
            ProblemEmbedding.model_version == model_version
        )
        result = await self.session.execute(
            select(Problem.id).where(Problem.id.not_in(subquery)).limit(limit)
        )
        return list(result.scalars().all())

    async def search_neighbors(
        self,
        *,
        vector: list[float],
        exclude_problem_id: UUID,
        model_version: str,
        limit: int,
    ) -> list[tuple[Problem, float]]:
        """pgvector cosine search over in-scope reports with current embeddings."""
        distance = ProblemEmbedding.embedding.cosine_distance(vector).label("distance")
        result = await self.session.execute(
            select(Problem, distance)
            .join(ProblemEmbedding, ProblemEmbedding.problem_id == Problem.id)
            .options(selectinload(Problem.reporter))
            .where(
                Problem.id != exclude_problem_id,
                Problem.status.in_(ACTIVE_SEARCH_STATUSES),
                ProblemEmbedding.model_version == model_version,
            )
            .order_by(distance)
            .limit(limit)
        )
        return [(problem, 1.0 - float(dist)) for problem, dist in result.all()]


class CandidateRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_pair(self, a: UUID, b: UUID) -> list[ProblemDuplicateCandidate]:
        first, second = order_pair(a, b)
        result = await self.session.execute(
            select(ProblemDuplicateCandidate).where(
                ProblemDuplicateCandidate.source_problem_id == first,
                ProblemDuplicateCandidate.candidate_problem_id == second,
            )
        )
        return list(result.scalars().all())

    async def create(
        self,
        *,
        source_problem_id: UUID,
        candidate_problem_id: UUID,
        triggered_by_problem_id: UUID,
        semantic_similarity: float,
        location_score: float | None,
        category_support_score: float | None,
        final_match_score: float,
        embedding_version: str,
        algorithm_version: str,
    ) -> ProblemDuplicateCandidate:
        first, second = order_pair(source_problem_id, candidate_problem_id)
        row = ProblemDuplicateCandidate(
            source_problem_id=first,
            candidate_problem_id=second,
            triggered_by_problem_id=triggered_by_problem_id,
            semantic_similarity=semantic_similarity,
            location_score=location_score,
            category_support_score=category_support_score,
            final_match_score=final_match_score,
            decision_status=DuplicateDecisionStatus.PENDING,
            embedding_version=embedding_version,
            algorithm_version=algorithm_version,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def get(self, candidate_id: UUID) -> ProblemDuplicateCandidate | None:
        result = await self.session.execute(
            select(ProblemDuplicateCandidate)
            .options(
                selectinload(ProblemDuplicateCandidate.source_problem),
                selectinload(ProblemDuplicateCandidate.candidate_problem),
            )
            .where(ProblemDuplicateCandidate.id == candidate_id)
        )
        return result.scalar_one_or_none()

    async def pending_triggered_by(self, problem_id: UUID) -> list[ProblemDuplicateCandidate]:
        """Live PENDING suggestions triggered by one report's own analysis."""
        result = await self.session.execute(
            select(ProblemDuplicateCandidate).where(
                ProblemDuplicateCandidate.triggered_by_problem_id == problem_id,
                ProblemDuplicateCandidate.decision_status == DuplicateDecisionStatus.PENDING,
            )
        )
        return list(result.scalars().all())

    async def visible_for_problem(
        self, problem_id: UUID, *, include_decided: bool
    ) -> list[ProblemDuplicateCandidate]:
        """Candidates for a report, newest first.

        Owners see only PENDING suggestions triggered by their own report's
        analysis (their report is the new one needing triage) — never reporter
        identity, attachments or internal notes (enforced above this layer).
        Admins (include_decided) see every pair touching the report, including
        decided ones, from either direction.
        """
        stmt = (
            select(ProblemDuplicateCandidate)
            .options(
                selectinload(ProblemDuplicateCandidate.source_problem),
                selectinload(ProblemDuplicateCandidate.candidate_problem),
            )
            .where(
                or_(
                    ProblemDuplicateCandidate.source_problem_id == problem_id,
                    ProblemDuplicateCandidate.candidate_problem_id == problem_id,
                )
            )
        )
        if not include_decided:
            stmt = stmt.where(
                ProblemDuplicateCandidate.decision_status == DuplicateDecisionStatus.PENDING,
                ProblemDuplicateCandidate.triggered_by_problem_id == problem_id,
            )
        result = await self.session.execute(
            stmt.order_by(ProblemDuplicateCandidate.final_match_score.desc())
        )
        return list(result.scalars().all())


class ClusterRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, *, created_by: UUID | None) -> DuplicateCluster:
        cluster = DuplicateCluster(created_by=created_by)
        self.session.add(cluster)
        await self.session.flush()
        cluster.cluster_number = f"DC-{cluster.seq:04d}"
        await self.session.flush()
        return cluster

    async def get(self, cluster_id: UUID) -> DuplicateCluster | None:
        result = await self.session.execute(
            select(DuplicateCluster)
            .options(
                selectinload(DuplicateCluster.members).selectinload(DuplicateClusterMember.problem),
                selectinload(DuplicateCluster.canonical_problem),
            )
            .where(DuplicateCluster.id == cluster_id)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[DuplicateCluster]:
        result = await self.session.execute(
            select(DuplicateCluster)
            .options(
                selectinload(DuplicateCluster.members),
                selectinload(DuplicateCluster.canonical_problem),
            )
            .order_by(DuplicateCluster.created_at.desc())
        )
        return list(result.scalars().all())

    async def membership_for_problem(self, problem_id: UUID) -> DuplicateClusterMember | None:
        result = await self.session.execute(
            select(DuplicateClusterMember)
            .options(selectinload(DuplicateClusterMember.cluster))
            .where(DuplicateClusterMember.problem_id == problem_id)
        )
        return result.scalar_one_or_none()

    async def members_of(self, cluster_id: UUID) -> list[DuplicateClusterMember]:
        result = await self.session.execute(
            select(DuplicateClusterMember)
            .options(selectinload(DuplicateClusterMember.problem))
            .where(DuplicateClusterMember.cluster_id == cluster_id)
            .order_by(DuplicateClusterMember.joined_at.asc())
        )
        return list(result.scalars().all())

    async def add_member(
        self,
        *,
        cluster_id: UUID,
        problem_id: UUID,
        confirmed_by: UUID | None,
        is_canonical: bool,
    ) -> DuplicateClusterMember:
        member = DuplicateClusterMember(
            cluster_id=cluster_id,
            problem_id=problem_id,
            confirmed_by=confirmed_by,
            is_canonical=is_canonical,
        )
        self.session.add(member)
        await self.session.flush()
        return member

    async def set_canonical(self, cluster: DuplicateCluster, problem_id: UUID) -> None:
        members = await self.members_of(cluster.id)
        for member in members:
            member.is_canonical = member.problem_id == problem_id
        cluster.canonical_problem_id = problem_id
        await self.session.flush()

    async def move_member(
        self, member: DuplicateClusterMember, *, to_cluster_id: UUID, is_canonical: bool
    ) -> None:
        member.cluster_id = to_cluster_id
        member.is_canonical = is_canonical
        await self.session.flush()

    async def delete(self, cluster: DuplicateCluster) -> None:
        await self.session.delete(cluster)
        await self.session.flush()

    async def confirmed_other_count(self, canonical_problem_id: UUID) -> int:
        """Additional confirmed reports in the canonical's cluster."""
        membership = await self.membership_for_problem(canonical_problem_id)
        if membership is None or not membership.is_canonical:
            return 0
        result = await self.session.execute(
            select(func.count())
            .select_from(DuplicateClusterMember)
            .where(
                DuplicateClusterMember.cluster_id == membership.cluster_id,
                DuplicateClusterMember.problem_id != canonical_problem_id,
            )
        )
        return result.scalar_one()
