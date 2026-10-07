"""Knowledge Repository data access (Step 12)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.knowledge import KnowledgeEmbedding, KnowledgeEntry, KnowledgeEntrySkill

_ENTRY_OPTIONS = (
    selectinload(KnowledgeEntry.skills).selectinload(KnowledgeEntrySkill.skill),
    selectinload(KnowledgeEntry.embedding),
)


class KnowledgeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, entry_id: UUID) -> KnowledgeEntry | None:
        result = await self.session.execute(
            select(KnowledgeEntry).options(*_ENTRY_OPTIONS).where(KnowledgeEntry.id == entry_id)
        )
        return result.scalar_one_or_none()

    async def get_by_problem(self, problem_id: UUID) -> KnowledgeEntry | None:
        result = await self.session.execute(
            select(KnowledgeEntry)
            .options(*_ENTRY_OPTIONS)
            .where(KnowledgeEntry.problem_id == problem_id)
        )
        return result.scalar_one_or_none()

    async def get_by_public_id(self, public_id: str) -> KnowledgeEntry | None:
        result = await self.session.execute(
            select(KnowledgeEntry)
            .options(*_ENTRY_OPTIONS)
            .where(KnowledgeEntry.public_id == public_id)
        )
        return result.scalar_one_or_none()

    async def next_entry_number(self) -> int:
        return int(
            (
                await self.session.execute(
                    select(func.nextval("knowledge_entry_number_seq"))
                )
            ).scalar_one()
        )

    async def create(self, **fields: object) -> KnowledgeEntry:
        row = KnowledgeEntry(**fields)
        self.session.add(row)
        await self.session.flush()
        return row

    async def add_skill(
        self, *, entry_id: UUID, skill_id: UUID, relevance_score: float | None
    ) -> KnowledgeEntrySkill:
        row = KnowledgeEntrySkill(
            knowledge_entry_id=entry_id,
            skill_id=skill_id,
            relevance_score=relevance_score,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def clear_skills(self, entry_id: UUID) -> None:
        for row in (
            (
                await self.session.execute(
                    select(KnowledgeEntrySkill).where(
                        KnowledgeEntrySkill.knowledge_entry_id == entry_id
                    )
                )
            )
            .scalars()
            .all()
        ):
            await self.session.delete(row)
        await self.session.flush()

    async def upsert_embedding(
        self,
        *,
        entry_id: UUID,
        vector: list[float],
        model_name: str,
        version: str,
        source_hash: str,
    ) -> KnowledgeEmbedding:
        existing = (
            (
                await self.session.execute(
                    select(KnowledgeEmbedding).where(
                        KnowledgeEmbedding.knowledge_entry_id == entry_id
                    )
                )
            ).scalar_one_or_none()
        )
        if existing is None:
            row = KnowledgeEmbedding(
                knowledge_entry_id=entry_id,
                embedding=vector,
                embedding_model=model_name,
                embedding_version=version,
                source_text_hash=source_hash,
            )
            self.session.add(row)
            await self.session.flush()
            return row
        existing.embedding = vector
        existing.embedding_model = model_name
        existing.embedding_version = version
        existing.source_text_hash = source_hash
        await self.session.flush()
        return existing

    async def published_entries(
        self,
        *,
        final_category: str | None = None,
        skill_id: UUID | None = None,
        location: str | None = None,
        published_from: datetime | None = None,
        published_to: datetime | None = None,
    ) -> list[KnowledgeEntry]:
        """All published entries with optional filters (single query, no N+1)."""
        stmt = (
            select(KnowledgeEntry)
            .options(*_ENTRY_OPTIONS)
            .where(
                KnowledgeEntry.is_published.is_(True),
                KnowledgeEntry.publication_status == "PUBLISHED",
            )
        )
        if final_category:
            stmt = stmt.where(KnowledgeEntry.final_category == final_category)
        if skill_id is not None:
            stmt = stmt.where(
                KnowledgeEntry.id.in_(
                    select(KnowledgeEntrySkill.knowledge_entry_id).where(
                        KnowledgeEntrySkill.skill_id == skill_id
                    )
                )
            )
        if location:
            stmt = stmt.where(KnowledgeEntry.location_summary.ilike(f"%{location}%"))
        if published_from is not None:
            stmt = stmt.where(KnowledgeEntry.published_at >= published_from)
        if published_to is not None:
            stmt = stmt.where(KnowledgeEntry.published_at <= published_to)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def admin_list(
        self, *, publication_status: str | None = None
    ) -> list[KnowledgeEntry]:
        from app.models.problem import Problem

        stmt = (
            select(KnowledgeEntry)
            .options(*_ENTRY_OPTIONS, selectinload(KnowledgeEntry.problem))
            .outerjoin(Problem, Problem.id == KnowledgeEntry.problem_id)
        )
        if publication_status:
            stmt = stmt.where(KnowledgeEntry.publication_status == publication_status)
        stmt = stmt.order_by(KnowledgeEntry.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def eligible_closed_problem_ids(self) -> list[UUID]:
        """CLOSED problems without any knowledge entry yet (backfill candidates)."""
        from app.models.problem import Problem

        result = await self.session.execute(
            select(Problem.id)
            .outerjoin(KnowledgeEntry, KnowledgeEntry.problem_id == Problem.id)
            .where(Problem.status == "CLOSED", KnowledgeEntry.id.is_(None))
            .order_by(Problem.closed_at.asc().nulls_last(), Problem.created_at.asc())
        )
        return list(result.scalars().all())
