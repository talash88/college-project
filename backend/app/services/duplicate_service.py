"""Semantic duplicate detection service (Step 7).

Embeddings (all-MiniLM-L6-v2, 384-dim, pgvector) → cosine neighbors →
hybrid match score → PENDING candidates → admin confirm/reject → clusters.
No auto-merge ever: even a 0.99 match stays a candidate until confirmed.
"""

import asyncio
import logging
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import (
    DuplicateAnalysisStatus,
    DuplicateDecisionStatus,
    ProblemEventType,
    ProblemStatus,
)
from app.ml.duplicates.text import (
    category_support,
    final_match_score,
    format_duplicate_text,
    location_support,
    normalize_location,
    source_text_hash,
)
from app.ml.skills.embeddings import EmbeddingModelUnavailableError, get_embedding_model
from app.models.problem import Problem
from app.models.problem_duplicate import (
    DuplicateCluster,
    DuplicateClusterMember,
    ProblemDuplicateCandidate,
)
from app.models.user import User
from app.repositories.duplicate_repository import (
    CandidateRepository,
    ClusterRepository,
    ProblemEmbeddingRepository,
)
from app.repositories.problem_repository import ClassificationRepository, ProblemRepository
from app.services.auth_service import AuthError

logger = logging.getLogger(__name__)


class DuplicateService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.problems = ProblemRepository(session)
        self.embeddings = ProblemEmbeddingRepository(session)
        self.candidates = CandidateRepository(session)
        self.clusters = ClusterRepository(session)
        self.classifications = ClassificationRepository(session)

    # ---------- embedding ----------

    def _encode(self, text: str) -> list[float]:
        model = get_embedding_model()
        vector = model.encode([text], normalize_embeddings=True, show_progress_bar=False)[0]
        return [float(x) for x in vector.tolist()]

    def _source_text(self, problem: Problem, category: str | None) -> str:
        return format_duplicate_text(
            problem.title,
            problem.description,
            problem.location_text,
            problem.building,
            problem.area,
            category,
        )

    async def _category_of(self, problem: Problem) -> str | None:
        latest = await self.classifications.latest_for_problem(problem.id)
        if latest is None:
            return None
        return latest.final_category or latest.predicted_category

    async def ensure_embedding(self, problem: Problem) -> tuple[list[float], bool]:
        """Return (vector, created). Recomputes only when source text changed."""
        category = await self._category_of(problem)
        text = self._source_text(problem, category)
        digest = source_text_hash(text)
        existing = await self.embeddings.get(problem.id, settings.PROBLEM_EMBEDDING_VERSION)
        if existing is not None and existing.source_text_hash == digest:
            return list(existing.embedding), False
        vector = await asyncio.to_thread(self._encode, text)
        row = await self.embeddings.upsert(
            problem_id=problem.id,
            vector=vector,
            model_name=settings.SKILL_EMBEDDING_MODEL,
            model_version=settings.PROBLEM_EMBEDDING_VERSION,
            source_text_hash=digest,
        )
        await self.session.commit()
        _ = row
        return vector, True

    # ---------- analysis ----------

    async def _record_failure(self, problem: Problem, reason: str) -> None:
        logger.warning("duplicate analysis failed for problem %s: %s", problem.id, reason)
        problem.duplicate_status = DuplicateAnalysisStatus.FAILED.value
        await self.session.commit()

    async def analyze(self, problem: Problem) -> DuplicateAnalysisStatus:
        """Embed + pgvector search + PENDING candidates. Never raises for AI issues.

        Pair rows are order-independent unique: reanalysis revives a STALE row
        for the same pair instead of inserting a duplicate, only this report's
        own outdated PENDING suggestions go STALE, and REJECTED/CONFIRMED pairs
        are never silently re-offered.
        """
        problem_id = problem.id
        title = problem.title
        try:
            vector, _ = await self.ensure_embedding(problem)
        except EmbeddingModelUnavailableError as exc:
            await self._record_failure(problem, str(exc))
            return DuplicateAnalysisStatus.FAILED
        except Exception as exc:
            await self._record_failure(problem, f"{type(exc).__name__}: {exc}")
            return DuplicateAnalysisStatus.FAILED

        # Snapshot plain values for scoring (no ORM across logic boundaries).
        category = await self._category_of(problem)
        my_locations = normalize_location(problem.location_text, problem.building, problem.area)

        neighbors = await self.embeddings.search_neighbors(
            vector=vector,
            exclude_problem_id=problem_id,
            model_version=settings.PROBLEM_EMBEDDING_VERSION,
            limit=settings.DUPLICATE_CANDIDATE_LIMIT * 2,
        )

        live_counterparts: set[UUID] = set()
        created = 0
        for other, semantic in neighbors:
            if semantic < settings.DUPLICATE_CANDIDATE_THRESHOLD:
                continue
            existing = await self.candidates.find_pair(problem_id, other.id)
            if any(
                r.decision_status
                in (
                    DuplicateDecisionStatus.PENDING,
                    DuplicateDecisionStatus.CONFIRMED_DUPLICATE,
                    DuplicateDecisionStatus.REJECTED,
                )
                for r in existing
            ):
                # Undecided, decided, or admin-rejected: never silently re-offer.
                # A still-live suggestion of mine stays live for my report.
                for row in existing:
                    if (
                        row.decision_status == DuplicateDecisionStatus.PENDING
                        and row.triggered_by_problem_id == problem_id
                    ):
                        live_counterparts.add(other.id)
                continue
            other_category = await self._category_of(other)
            loc = location_support(
                my_locations,
                normalize_location(other.location_text, other.building, other.area),
            )
            cat = category_support(category, other_category)
            final = final_match_score(
                semantic,
                loc,
                cat,
                semantic_weight=settings.DUPLICATE_SEMANTIC_WEIGHT,
                location_weight=settings.DUPLICATE_LOCATION_WEIGHT,
                category_weight=settings.DUPLICATE_CATEGORY_WEIGHT,
            )
            stale_rows = [
                r for r in existing if r.decision_status == DuplicateDecisionStatus.STALE
            ]
            try:
                async with self.session.begin_nested():
                    if stale_rows:
                        # Same pair suggested before and gone stale: revive the row
                        # so the order-independent unique constraint is never
                        # violated by a re-insert.
                        row = stale_rows[0]
                        row.semantic_similarity = round(semantic, 4)
                        row.location_score = round(loc, 4)
                        row.category_support_score = round(cat, 4)
                        row.final_match_score = final
                        row.decision_status = DuplicateDecisionStatus.PENDING
                        row.triggered_by_problem_id = problem_id
                        row.embedding_version = settings.PROBLEM_EMBEDDING_VERSION
                        row.algorithm_version = settings.DUPLICATE_ALGORITHM_VERSION
                        row.reviewed_by = None
                        row.reviewed_at = None
                        row.review_note = None
                    else:
                        await self.candidates.create(
                            source_problem_id=problem_id,
                            candidate_problem_id=other.id,
                            triggered_by_problem_id=problem_id,
                            semantic_similarity=round(semantic, 4),
                            location_score=round(loc, 4),
                            category_support_score=round(cat, 4),
                            final_match_score=final,
                            embedding_version=settings.PROBLEM_EMBEDDING_VERSION,
                            algorithm_version=settings.DUPLICATE_ALGORITHM_VERSION,
                        )
            except IntegrityError:
                # Lost a race with a concurrent analysis inserting the same
                # order-independent pair: the suggestion now exists, which is
                # the desired end state. Never poison the report transaction.
                logger.info(
                    "duplicate pair %s/%s already recorded; skipping insert",
                    problem_id,
                    other.id,
                )
                live_counterparts.add(other.id)
                continue
            live_counterparts.add(other.id)
            created += 1
            if created >= settings.DUPLICATE_CANDIDATE_LIMIT:
                break

        # My own suggestions that were not re-confirmed by this run are outdated.
        # Suggestions triggered by other reports are left untouched.
        for row in await self.candidates.pending_triggered_by(problem_id):
            sides = {row.source_problem_id, row.candidate_problem_id}
            if problem_id not in sides:
                continue  # pragma: no cover - defensive
            counterpart = next(s for s in sides if s != problem_id)
            if counterpart not in live_counterparts:
                row.decision_status = DuplicateDecisionStatus.STALE

        problem.duplicate_status = (
            DuplicateAnalysisStatus.POSSIBLE_DUPLICATES.value
            if live_counterparts
            else DuplicateAnalysisStatus.NO_MATCHES.value
        )
        await self.session.commit()
        _ = title
        if created:
            await self._log(
                problem_id,
                ProblemEventType.DUPLICATE_ANALYSIS_COMPLETED,
                None,
                message=f"Found {created} possible similar report(s).",
            )
            await self.session.commit()
        return DuplicateAnalysisStatus(problem.duplicate_status)

    async def analyze_problem_id(self, problem_id: UUID) -> DuplicateAnalysisStatus:
        problem = await self.problems.get_by_id(problem_id)
        if problem is None:
            raise AuthError(404, "Problem not found")
        return await self.analyze(problem)

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
        from app.repositories.problem_repository import ActivityRepository

        await ActivityRepository(self.session).log(
            problem_id=problem_id,
            event_type=event,
            actor_user_id=actor,
            old_status=old_status,
            new_status=new_status,
            message=message,
        )

    # ---------- review ----------

    async def _get_pending(self, candidate_id: UUID) -> ProblemDuplicateCandidate:
        row = await self.candidates.get(candidate_id)
        if row is None:
            raise AuthError(404, "Duplicate candidate not found")
        if row.decision_status != DuplicateDecisionStatus.PENDING:
            raise AuthError(409, f"Candidate already {row.decision_status.value.lower()}")
        return row

    @staticmethod
    def _older(a: Problem, b: Problem) -> Problem:
        key_a = (a.submitted_at, a.created_at, str(a.id))
        key_b = (b.submitted_at, b.created_at, str(b.id))
        return a if key_a <= key_b else b

    async def _recalc_canonical_priority(self, canonical: Problem, cluster_number: str) -> None:
        from app.services.priority_service import PriorityService

        count = await self.clusters.confirmed_other_count(canonical.id)
        await PriorityService(self.session).analyze(
            canonical,
            recalculation_reason=f"Duplicate cluster {cluster_number} confirmation",
            duplicate_count=count,
        )

    async def _mark_member_duplicate(
        self, member: Problem, canonical: Problem, admin: User
    ) -> None:
        old = member.status
        member.status = ProblemStatus.DUPLICATE
        member.canonical_problem_id = canonical.id
        await self._log(
            member.id,
            ProblemEventType.STATUS_CHANGED,
            admin.id,
            old_status=old.value,
            new_status=ProblemStatus.DUPLICATE.value,
            message=f"Linked to canonical issue {canonical.ticket_number}.",
        )
        await self._log(
            member.id,
            ProblemEventType.JOINED_DUPLICATE_CLUSTER,
            admin.id,
            message=f"Joined cluster as duplicate of {canonical.ticket_number}.",
        )

    async def confirm(
        self, candidate_id: UUID, admin: User, review_note: str | None
    ) -> DuplicateCluster:
        row = await self._get_pending(candidate_id)
        source = row.source_problem
        target = row.candidate_problem
        if source is None or target is None:
            raise AuthError(404, "Problem not found")

        mem_source = await self.clusters.membership_for_problem(source.id)
        mem_target = await self.clusters.membership_for_problem(target.id)

        note = review_note.strip() if review_note and review_note.strip() else None
        if note and len(note) > 1000:
            raise AuthError(422, "Review note is too long")

        if mem_source is None and mem_target is None:
            # Case A: brand-new cluster; oldest confirmed report is canonical.
            cluster = await self.clusters.create(created_by=admin.id)
            canonical = self._older(source, target)
            other = target if canonical.id == source.id else source
            await self.clusters.add_member(
                cluster_id=cluster.id,
                problem_id=canonical.id,
                confirmed_by=admin.id,
                is_canonical=True,
            )
            await self.clusters.add_member(
                cluster_id=cluster.id,
                problem_id=other.id,
                confirmed_by=admin.id,
                is_canonical=False,
            )
            await self.clusters.set_canonical(cluster, canonical.id)
            await self._mark_member_duplicate(other, canonical, admin)
        elif (
            mem_source is not None
            and mem_target is not None
            and mem_source.cluster_id == mem_target.cluster_id
        ):
            raise AuthError(409, "Both reports are already in the same cluster")
        elif mem_source is not None and mem_target is not None:
            # Case D: merge two clusters; oldest cluster survives, oldest member is canonical.
            cluster_a = await self.clusters.get(mem_source.cluster_id)
            cluster_b = await self.clusters.get(mem_target.cluster_id)
            assert cluster_a is not None
            assert cluster_b is not None
            keep, drop = (
                (cluster_a, cluster_b)
                if cluster_a.created_at <= cluster_b.created_at
                else (cluster_b, cluster_a)
            )
            for member in await self.clusters.members_of(drop.id):
                await self.clusters.move_member(member, to_cluster_id=keep.id, is_canonical=False)
            members = await self.clusters.members_of(keep.id)
            problems: list[Problem] = []
            for m in members:
                detail = await self.problems.get_by_id(m.problem_id)
                if detail is not None:
                    problems.append(detail)
            if not problems:  # pragma: no cover - defensive
                raise AuthError(500, "Merged cluster has no reports")
            canonical = problems[0]
            for p in problems[1:]:
                canonical = self._older(canonical, p)
            await self.clusters.set_canonical(keep, canonical.id)
            # Non-canonical members of the dropped cluster become DUPLICATE members
            # pointing at the surviving canonical report.
            for p in problems:
                if p.id != canonical.id:
                    p.canonical_problem_id = canonical.id
                    if p.status != ProblemStatus.DUPLICATE:
                        await self._mark_member_duplicate(p, canonical, admin)
            await self._log(
                canonical.id,
                ProblemEventType.DUPLICATE_CLUSTER_MERGED,
                admin.id,
                message=f"Merged cluster {drop.cluster_number} into {keep.cluster_number}.",
            )
            await self.session.flush()
            # Moved members still sit in drop's in-memory collection: reload it
            # first so the delete-orphan cascade cannot remove the moved rows.
            await self.session.refresh(drop, attribute_names=["members"])
            await self.clusters.delete(drop)
            cluster = keep
        else:
            # Cases B/C: join the existing cluster; its canonical is preserved.
            existing = mem_source if mem_source is not None else mem_target
            assert existing is not None
            joined = await self.clusters.get(existing.cluster_id)
            assert joined is not None
            cluster = joined
            newcomer = target if mem_source is not None else source
            await self.clusters.add_member(
                cluster_id=cluster.id,
                problem_id=newcomer.id,
                confirmed_by=admin.id,
                is_canonical=False,
            )
            fetched = (
                await self.problems.get_by_id(cluster.canonical_problem_id)
                if cluster.canonical_problem_id
                else None
            )
            if fetched is None:  # pragma: no cover - defensive
                raise AuthError(500, "Cluster has no canonical report")
            canonical = fetched
            await self._mark_member_duplicate(newcomer, canonical, admin)

        row.decision_status = DuplicateDecisionStatus.CONFIRMED_DUPLICATE
        row.reviewed_by = admin.id
        from datetime import UTC, datetime

        row.reviewed_at = datetime.now(UTC)
        row.review_note = note
        # Both directions of the pair now decided: confirm reverse PENDING rows if any.
        for other_row in await self.candidates.find_pair(source.id, target.id):
            if (
                other_row.id != row.id
                and other_row.decision_status == DuplicateDecisionStatus.PENDING
            ):
                other_row.decision_status = DuplicateDecisionStatus.CONFIRMED_DUPLICATE
                other_row.reviewed_by = admin.id
                other_row.reviewed_at = datetime.now(UTC)
        await self._log(
            source.id,
            ProblemEventType.DUPLICATE_CONFIRMED,
            admin.id,
            message=f"Confirmed duplicate of {target.ticket_number}.",
        )
        await self._log(
            target.id,
            ProblemEventType.DUPLICATE_CONFIRMED,
            admin.id,
            message=f"Confirmed duplicate of {source.ticket_number}.",
        )
        await self.session.commit()

        canonical_id = cluster.canonical_problem_id
        canonical_final = await self.problems.get_by_id(canonical_id) if canonical_id else None
        if canonical_final is not None:
            number = cluster.cluster_number or f"DC-{cluster.seq:04d}"
            await self._recalc_canonical_priority(canonical_final, number)
            await self.session.commit()
        refreshed = await self.clusters.get(cluster.id)
        assert refreshed is not None
        return refreshed

    async def reject(
        self, candidate_id: UUID, admin: User, review_note: str | None
    ) -> ProblemDuplicateCandidate:
        row = await self._get_pending(candidate_id)
        note = review_note.strip() if review_note and review_note.strip() else None
        if note and len(note) > 1000:
            raise AuthError(422, "Review note is too long")
        row.decision_status = DuplicateDecisionStatus.REJECTED
        row.reviewed_by = admin.id
        from datetime import UTC, datetime

        row.reviewed_at = datetime.now(UTC)
        row.review_note = note
        source = row.source_problem
        target = row.candidate_problem
        if source is not None and target is not None:
            await self._log(
                source.id,
                ProblemEventType.DUPLICATE_REJECTED,
                admin.id,
                message=f"Duplicate suggestion with {target.ticket_number} reviewed: not a duplicate.",
            )
            await self._log(
                target.id,
                ProblemEventType.DUPLICATE_REJECTED,
                admin.id,
                message=f"Duplicate suggestion with {source.ticket_number} reviewed: not a duplicate.",
            )
        await self.session.commit()
        return row

    # ---------- read helpers ----------

    async def duplicate_count_for_priority(self, problem: Problem) -> int:
        return await self.clusters.confirmed_other_count(problem.id)

    async def membership_for(self, problem_id: UUID) -> DuplicateClusterMember | None:
        return await self.clusters.membership_for_problem(problem_id)

    async def cluster_with_members(self, cluster_id: UUID) -> DuplicateCluster | None:
        return await self.clusters.get(cluster_id)

    async def safe_canonical_summary(self, canonical_id: UUID) -> dict[str, object] | None:
        canonical = await self.problems.get_by_id(canonical_id)
        if canonical is None:
            return None
        return {
            "id": str(canonical.id),
            "ticket_number": canonical.ticket_number,
            "title": canonical.title,
            "status": canonical.status.value,
            "location_text": canonical.location_text,
            "created_at": canonical.created_at.isoformat(),
        }
