"""Institutional Knowledge Repository service (Step 12).

Content originates ONLY from real verified solved problems:
CLOSED + mentor-approved final solution + reporter-confirmed RESOLVED.
Duplicate members never get their own entries (canonical only).

Search math (documented, deterministic):
- keyword_score = matched_terms / total_terms over lowercase alphanumeric
  tokens (len >= 2); a term matches when it is a case-insensitive substring
  of the entry's searchable text.
- semantic_similarity = cosine(entry_embedding, query_embedding) via pgvector
  (both sides L2-normalized, so 1 - cosine_distance).
- HYBRID final = 0.75 * semantic + 0.25 * keyword (weights from settings).
  Candidates are kept when semantic >= threshold OR keyword > 0.
- SEMANTIC keeps semantic >= threshold. KEYWORD keeps keyword > 0.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import ProblemEventType, ProblemStatus
from app.models.knowledge import KnowledgeEntry
from app.models.problem import Problem
from app.models.problem_analysis import ProblemRequiredSkill
from app.models.solution import ProblemSolutionSubmission
from app.models.user import User
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.problem_repository import ActivityRepository, ClassificationRepository
from app.repositories.solution_repository import (
    ReviewRepository,
    SolutionRepository,
    VerificationRepository,
)
from app.repositories.workspace_repository import WorkAttachmentRepository
from app.services.auth_service import AuthError

logger = logging.getLogger(__name__)

SEARCH_MODES = ("ALL", "HYBRID", "KEYWORD", "SEMANTIC")
SORT_ORDERS = ("relevance", "newest", "oldest")
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_FAR_FUTURE = datetime(2100, 1, 1, tzinfo=UTC)


def _tokens(text: str) -> list[str]:
    import re

    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) >= 2]


def format_knowledge_text(
    *,
    title: str,
    problem: str,
    category: str | None,
    location: str | None,
    root_cause: str | None,
    solution: str | None,
    work_performed: str | None,
    skills: list[str],
) -> str:
    """Deterministic semantic text. Never includes identities or internals."""
    parts = [f"Title: {title.strip()}", f"Problem: {problem.strip()}"]
    if category:
        parts.append(f"Category: {category.strip()}")
    if location:
        parts.append(f"Location: {location.strip()}")
    if root_cause:
        parts.append(f"Root Cause: {root_cause.strip()}")
    if solution:
        parts.append(f"Solution: {solution.strip()}")
    if work_performed:
        parts.append(f"Work Performed: {work_performed.strip()}")
    if skills:
        parts.append("Skills: " + ", ".join(s.strip() for s in skills if s.strip()))
    return "\n".join(parts)


def source_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def keyword_score(searchable: str, terms: list[str]) -> float:
    if not terms:
        return 1.0
    lowered = searchable.lower()
    matched = sum(1 for t in terms if t in lowered)
    return matched / len(terms)


def searchable_text(entry: KnowledgeEntry) -> str:
    return "\n".join(
        part
        for part in [
            entry.title,
            entry.problem_summary,
            entry.root_cause or "",
            entry.solution_summary,
            entry.work_performed,
        ]
        if part
    )


class KnowledgeService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.entries = KnowledgeRepository(session)
        self.solutions = SolutionRepository(session)
        self.reviews = ReviewRepository(session)
        self.verifications = VerificationRepository(session)
        self.classifications = ClassificationRepository(session)
        self.work_files = WorkAttachmentRepository(session)
        self.activities = ActivityRepository(session)

    # ---------- eligibility ----------

    async def _final_submission(
        self, problem: Problem
    ) -> ProblemSolutionSubmission | None:
        return await self.solutions.latest_for_problem(problem.id)

    async def check_eligibility(self, problem: Problem) -> tuple[bool, str]:
        """Strict publication rule (documented in STEP_12 doc)."""
        if problem.status != ProblemStatus.CLOSED:
            return False, f"problem status is {problem.status.value}, must be CLOSED"
        if problem.canonical_problem_id is not None:
            return False, "confirmed duplicate member; only the canonical issue publishes"
        final = await self._final_submission(problem)
        if final is None:
            return False, "no solution submission found"
        approved = [
            r for r in await self.reviews.list_for_submission(final.id) if r.decision == "APPROVED"
        ]
        if not approved:
            return False, "final solution was never mentor-approved"
        verifications = await self.verifications.list_for_problem(problem.id)
        confirmed = any(
            v.decision == "RESOLVED" and v.solution_submission_id == final.id
            for v in verifications
        )
        if not confirmed:
            return False, "reporter never confirmed this final solution as RESOLVED"
        return True, "eligible"

    # ---------- snapshot ----------

    async def _category_of(self, problem: Problem) -> str | None:
        latest = await self.classifications.latest_for_problem(problem.id)
        if latest is None:
            return None
        return latest.final_category or latest.predicted_category

    async def _required_skills(self, problem: Problem) -> list[ProblemRequiredSkill]:
        from app.services.skill_extraction_service import RequiredSkillService

        latest, rows = await RequiredSkillService(self.session).latest_with_skills(problem.id)
        if latest is None or latest.status != "COMPLETED":
            return []
        return rows

    @staticmethod
    def _location_summary(problem: Problem) -> str | None:
        parts = [problem.location_text, problem.building, problem.area]
        joined = ", ".join(p.strip() for p in parts if p and p.strip())
        return joined or None

    @staticmethod
    def _duration_minutes(problem: Problem) -> int | None:
        end = problem.resolved_at or problem.closed_at
        if problem.submitted_at is None or end is None:
            return None
        delta = (end - problem.submitted_at).total_seconds() / 60
        return max(0, int(delta))

    async def _team_and_mentor(self, problem: Problem) -> tuple[list[str], str | None, str | None]:
        from app.repositories.assignment_repository import AssignmentRepository

        history = await AssignmentRepository(self.session).history_for_problem(problem.id)
        if not history:
            return [], None, None
        assignment = history[0]
        names = sorted(
            {
                m.user.full_name
                for m in assignment.team.members
                if m.user is not None and m.user.full_name
            }
        )
        mentor_name = assignment.mentor.full_name if assignment.mentor is not None else None
        designation = None
        if assignment.mentor is not None and assignment.mentor.faculty_profile is not None:
            designation = assignment.mentor.faculty_profile.designation
        return names, mentor_name, designation

    async def _shareable_evidence(
        self, problem: Problem, submission: ProblemSolutionSubmission
    ) -> list[dict[str, object]]:
        files = []
        for raw in submission.evidence_attachment_ids or []:
            try:
                file_id = UUID(str(raw))
            except (ValueError, AttributeError, TypeError):
                continue
            row = await self.work_files.get(file_id)
            if (
                row is None
                or row.problem_id != problem.id
                or not row.is_knowledge_shareable
            ):
                continue
            files.append(
                {
                    "file_id": str(row.id),
                    "original_filename": row.original_filename,
                    "mime_type": row.mime_type,
                    "size_bytes": row.size_bytes,
                }
            )
        return files

    async def _build_snapshot(self, problem: Problem) -> dict[str, object]:
        final = await self._final_submission(problem)
        assert final is not None
        category = await self._category_of(problem)
        skill_rows = await self._required_skills(problem)
        skill_names = sorted(
            {
                r.skill.name
                for r in skill_rows
                if r.skill is not None and r.skill.name
            }
        )
        team_names, mentor_name, designation = await self._team_and_mentor(problem)
        text = format_knowledge_text(
            title=problem.title,
            problem=problem.description,
            category=category,
            location=self._location_summary(problem),
            root_cause=final.root_cause,
            solution=final.solution_summary,
            work_performed=final.work_performed,
            skills=skill_names,
        )
        return {
            "final": final,
            "category": category,
            "skill_rows": skill_rows,
            "text": text,
            "text_hash": source_text_hash(text),
            "fields": {
                "title": problem.title,
                "problem_summary": problem.description,
                "final_category": category,
                "location_summary": self._location_summary(problem),
                "root_cause": final.root_cause,
                "solution_summary": final.solution_summary,
                "work_performed": final.work_performed,
                "testing_performed": final.testing_performed,
                "deployment_notes": final.deployment_notes,
                "known_limitations": final.limitations,
                "resolution_duration_minutes": self._duration_minutes(problem),
                "team_names": team_names,
                "mentor_name": mentor_name,
                "mentor_designation": designation,
                "evidence_files": await self._shareable_evidence(problem, final),
                "source_solution_submission_id": final.id,
                "source_text_hash": source_text_hash(text),
            },
        }

    def _encode(self, text: str) -> list[float]:
        from app.ml.skills.embeddings import get_embedding_model

        model = get_embedding_model()
        vector = model.encode(text, normalize_embeddings=True, show_progress_bar=False)
        return [float(x) for x in vector.tolist()]

    async def _log(
        self,
        problem_id: UUID,
        event: ProblemEventType,
        actor: UUID | None,
        message: str | None,
    ) -> None:
        await self.activities.log(
            problem_id=problem_id,
            event_type=event,
            actor_user_id=actor,
            message=message,
        )
        await self.session.flush()

    # ---------- publication ----------

    async def publish_for_problem(
        self, problem_id: UUID, *, actor_id: UUID | None = None
    ) -> str:
        """Idempotent publish. Never raises: failures become FAILED entries."""
        from app.repositories.problem_repository import ProblemRepository

        problem = await ProblemRepository(self.session).get_by_id(problem_id)
        if problem is None:
            return "NOT_FOUND"
        eligible, reason = await self.check_eligibility(problem)
        if not eligible:
            return f"INELIGIBLE: {reason}"
        existing = await self.entries.get_by_problem(problem.id)
        if existing is not None and existing.publication_status == "PUBLISHED":
            if existing.source_text_hash is not None:
                await self._refresh_embedding_if_stale(existing, actor_id)
            return "PUBLISHED"
        try:
            return await self._publish_inner(problem, existing, actor_id=actor_id)
        except AuthError:
            raise
        except Exception as exc:
            logger.warning("knowledge publication failed for problem %s: %s", problem.id, exc)
            await self.session.rollback()
            await self._mark_failed(problem, existing, f"publication error: {exc}")
            return "FAILED"

    async def _publish_inner(
        self, problem: Problem, existing: KnowledgeEntry | None, *, actor_id: UUID | None
    ) -> str:
        # Note: ARCHIVED entries are only revived through unarchive(), which
        # deliberately calls publish_for_problem. retry() blocks ARCHIVED
        # explicitly; the close hook and backfill never see archived rows
        # (hook fires once at close; backfill skips problems with entries).
        snapshot = await self._build_snapshot(problem)
        raw_fields = snapshot["fields"]
        assert isinstance(raw_fields, dict)
        fields: dict[str, object] = raw_fields
        raw_text = snapshot["text"]
        assert isinstance(raw_text, str)
        raw_hash = snapshot["text_hash"]
        assert isinstance(raw_hash, str)
        raw_rows = snapshot["skill_rows"]
        assert isinstance(raw_rows, list)
        if existing is None:
            number = await self.entries.next_entry_number()
            entry = await self.entries.create(
                problem_id=problem.id,
                entry_number=number,
                public_id=f"KB-{number:06d}",
                publication_status="PUBLISHED",
                is_published=True,
                published_at=datetime.now(UTC),
                **fields,
            )
            created = True
        else:
            for key, value in fields.items():
                setattr(existing, key, value)
            existing.publication_status = "PUBLISHED"
            existing.is_published = True
            existing.published_at = datetime.now(UTC)
            existing.archived_at = None
            existing.failure_reason = None
            await self.entries.clear_skills(existing.id)
            entry = existing
            created = False
        for row in raw_rows:
            await self.entries.add_skill(
                entry_id=entry.id,
                skill_id=row.skill_id,
                relevance_score=float(row.score),
            )
        vector = self._encode(raw_text)
        await self.entries.upsert_embedding(
            entry_id=entry.id,
            vector=vector,
            model_name=settings.SKILL_EMBEDDING_MODEL,
            version=settings.KNOWLEDGE_EMBEDDING_VERSION,
            source_hash=raw_hash,
        )
        entry.updated_at = datetime.now(UTC)
        await self.session.commit()
        await self._log(
            problem.id,
            ProblemEventType.KNOWLEDGE_ENTRY_PUBLISHED,
            actor_id,
            f"Knowledge article {entry.public_id} published"
            + ("" if created else " (republished)"),
        )
        await self.session.commit()
        return "PUBLISHED"

    async def _refresh_embedding_if_stale(
        self, entry: KnowledgeEntry, actor_id: UUID | None
    ) -> None:
        """Rebuild the snapshot+embedding when source content changed."""
        from app.repositories.problem_repository import ProblemRepository

        problem = await ProblemRepository(self.session).get_by_id(entry.problem_id)
        if problem is None:
            return
        snapshot = await self._build_snapshot(problem)
        new_hash = snapshot["text_hash"]
        assert isinstance(new_hash, str)
        if new_hash == (entry.embedding.source_text_hash if entry.embedding else None):
            return
        new_fields = snapshot["fields"]
        assert isinstance(new_fields, dict)
        for key, value in new_fields.items():
            setattr(entry, key, value)
        await self.entries.clear_skills(entry.id)
        new_rows = snapshot["skill_rows"]
        assert isinstance(new_rows, list)
        for row in new_rows:
            await self.entries.add_skill(
                entry_id=entry.id,
                skill_id=row.skill_id,
                relevance_score=float(row.score),
            )
        new_text = snapshot["text"]
        assert isinstance(new_text, str)
        vector = self._encode(new_text)
        await self.entries.upsert_embedding(
            entry_id=entry.id,
            vector=vector,
            model_name=settings.SKILL_EMBEDDING_MODEL,
            version=settings.KNOWLEDGE_EMBEDDING_VERSION,
            source_hash=new_hash,
        )
        entry.updated_at = datetime.now(UTC)
        await self.session.commit()
        await self._log(
            problem.id,
            ProblemEventType.KNOWLEDGE_ENTRY_REPUBLISHED,
            actor_id,
            f"Knowledge article {entry.public_id} refreshed after source changes.",
        )
        await self.session.commit()

    async def _mark_failed(
        self, problem: Problem, existing: KnowledgeEntry | None, reason: str
    ) -> None:
        # No fabricated content: a FAILED row is only recorded when the final
        # verified submission still exists. Otherwise just log the activity.
        try:
            final = await self._final_submission(problem)
            if final is None:
                await self._log(
                    problem.id, ProblemEventType.KNOWLEDGE_PUBLICATION_FAILED, None, reason[:500]
                )
                await self.session.commit()
                return
            if existing is None:
                number = await self.entries.next_entry_number()
                await self.entries.create(
                    problem_id=problem.id,
                    entry_number=number,
                    public_id=f"KB-{number:06d}",
                    title=problem.title,
                    problem_summary=problem.description,
                    solution_summary="",
                    work_performed="",
                    source_solution_submission_id=final.id,
                    publication_status="FAILED",
                    is_published=False,
                    failure_reason=reason[:1000],
                )
            else:
                existing.publication_status = "FAILED"
                existing.is_published = False
                existing.failure_reason = reason[:1000]
            await self.session.commit()
            await self._log(
                problem.id, ProblemEventType.KNOWLEDGE_PUBLICATION_FAILED, None, reason[:500]
            )
            await self.session.commit()
        except Exception as exc:
            await self.session.rollback()
            logger.warning("could not record knowledge failure for %s: %s", problem.id, exc)

    # ---------- admin: retry / archive ----------

    async def retry(self, entry_id: UUID, admin_id: UUID) -> str:
        entry = await self.entries.get(entry_id)
        if entry is None:
            raise AuthError(404, "Knowledge entry not found")
        if entry.publication_status == "ARCHIVED":
            raise AuthError(409, "Archived entries must be unarchived first")
        return await self.publish_for_problem(entry.problem_id, actor_id=admin_id)

    async def archive(self, entry_id: UUID, admin_id: UUID) -> None:
        entry = await self.entries.get(entry_id)
        if entry is None:
            raise AuthError(404, "Knowledge entry not found")
        entry.publication_status = "ARCHIVED"
        entry.is_published = False
        entry.archived_at = datetime.now(UTC)
        await self.session.commit()
        await self._log(
            entry.problem_id,
            ProblemEventType.KNOWLEDGE_ENTRY_ARCHIVED,
            admin_id,
            f"Knowledge article {entry.public_id} archived.",
        )
        await self.session.commit()

    async def unarchive(self, entry_id: UUID, admin_id: UUID) -> str:
        entry = await self.entries.get(entry_id)
        if entry is None:
            raise AuthError(404, "Knowledge entry not found")
        if entry.publication_status != "ARCHIVED":
            raise AuthError(409, "Only archived entries can be unarchived")
        status = await self.publish_for_problem(entry.problem_id, actor_id=admin_id)
        if status == "PUBLISHED":
            await self._log(
                entry.problem_id,
                ProblemEventType.KNOWLEDGE_ENTRY_REPUBLISHED,
                admin_id,
                f"Knowledge article {entry.public_id} restored from archive.",
            )
            await self.session.commit()
        return status

    # ---------- search ----------

    async def search(
        self,
        *,
        q: str | None,
        mode: str,
        category: str | None,
        skill_id: UUID | None,
        location: str | None,
        published_from: datetime | None,
        published_to: datetime | None,
        sort: str,
        page: int,
        page_size: int,
    ) -> dict[str, object]:
        mode = (mode or "ALL").upper()
        if mode == "ALL":
            mode = "HYBRID"
        if mode not in SEARCH_MODES:
            raise AuthError(422, f"Unknown search_mode: {mode}")
        if sort not in SORT_ORDERS:
            raise AuthError(422, f"Unknown sort: {sort}")
        page = max(1, page)
        page_size = min(max(1, page_size), 50)

        candidates = await self.entries.published_entries(
            final_category=category,
            skill_id=skill_id,
            location=location,
            published_from=published_from,
            published_to=published_to,
        )
        terms = _tokens(q or "")
        query_vector: list[float] | None = None
        semantic_available = True
        if mode in ("SEMANTIC", "HYBRID") and terms:
            try:
                query_vector = self._encode(q or "")
            except Exception as exc:
                logger.warning("knowledge semantic search unavailable: %s", exc)
                semantic_available = False
                if mode == "SEMANTIC":
                    return {
                        "items": [],
                        "total": 0,
                        "semantic_available": False,
                        "error": "Semantic search is temporarily unavailable; try keyword mode.",
                    }

        scored: list[tuple[float, float, float, KnowledgeEntry]] = []
        for entry in candidates:
            sem = 0.0
            if query_vector is not None and entry.embedding is not None:
                sem = self._cosine(entry.embedding.embedding, query_vector)
            kw = keyword_score(searchable_text(entry), terms)
            if mode == "SEMANTIC":
                if sem < settings.KNOWLEDGE_SEMANTIC_MIN_SCORE:
                    continue
                final = sem
            elif mode == "KEYWORD":
                if terms and kw <= 0:
                    continue
                final = kw
            else:  # HYBRID
                if terms and (
                    sem < settings.KNOWLEDGE_SEMANTIC_MIN_SCORE and kw <= 0
                ):
                    continue
                final = (
                    settings.KNOWLEDGE_HYBRID_SEMANTIC_WEIGHT * sem
                    + settings.KNOWLEDGE_HYBRID_KEYWORD_WEIGHT * kw
                )
            scored.append((final, sem, kw, entry))

        if sort == "relevance":
            scored.sort(key=lambda t: (-t[0], -(t[3].published_at or _EPOCH).timestamp()))
        elif sort == "oldest":
            scored.sort(key=lambda t: ((t[3].published_at or _FAR_FUTURE).timestamp()))
        else:  # newest (also the default when no query terms rank results)
            scored.sort(key=lambda t: (-(t[3].published_at or _EPOCH).timestamp()))

        total = len(scored)
        start = (page - 1) * page_size
        window = scored[start : start + page_size]
        return {
            "items": [
                {
                    "entry": entry,
                    "relevance": round(final, 4),
                    "semantic_similarity": round(sem, 4),
                    "keyword_score": round(kw, 4),
                }
                for final, sem, kw, entry in window
            ],
            "total": total,
            "semantic_available": semantic_available,
        }

    @staticmethod
    def _cosine(stored: object, query: list[float]) -> float:
        if stored is None or isinstance(stored, (str, bytes)):
            return 0.0
        try:
            values = [float(x) for x in cast(Iterable[float], stored)]
        except (TypeError, ValueError):
            return 0.0
        if len(values) != len(query) or not values:
            return 0.0
        dot = sum(a * b for a, b in zip(values, query, strict=True))
        return max(-1.0, min(1.0, dot))

    # ---------- related ----------

    async def related(self, entry_id: UUID, *, limit: int = 5) -> list[dict[str, object]]:
        entry = await self.entries.get(entry_id)
        if entry is None or entry.embedding is None:
            raise AuthError(404, "Knowledge entry not found")
        base = [float(x) for x in entry.embedding.embedding]
        scored = []
        for other in await self.entries.published_entries():
            if other.id == entry.id or other.embedding is None:
                continue
            sim = self._cosine(other.embedding.embedding, base)
            scored.append((sim, other))
        scored.sort(key=lambda t: -t[0])
        return [
            {"entry": other, "semantic_similarity": round(sim, 4)}
            for sim, other in scored[: max(1, min(limit, 20))]
        ]

    async def related_for_problem(
        self, problem_id: UUID, user: User, *, limit: int = 5
    ) -> dict[str, object]:
        from app.services.problem_service import ProblemService

        problem = await ProblemService(self.session).get_visible_problem(user, problem_id)
        skill_rows = await self._required_skills(problem)
        text = format_knowledge_text(
            title=problem.title,
            problem=problem.description,
            category=await self._category_of(problem),
            location=self._location_summary(problem),
            root_cause=None,
            solution=None,
            work_performed=None,
            skills=sorted(
                {r.skill.name for r in skill_rows if r.skill is not None and r.skill.name}
            ),
        )
        try:
            query_vector = self._encode(text)
        except Exception as exc:
            logger.warning("related-solutions semantic search unavailable: %s", exc)
            return {"items": [], "semantic_available": False}
        scored = []
        for entry in await self.entries.published_entries():
            if entry.problem_id == problem.id or entry.embedding is None:
                continue
            sim = self._cosine(entry.embedding.embedding, query_vector)
            if sim < settings.KNOWLEDGE_SEMANTIC_MIN_SCORE:
                continue
            scored.append((sim, entry))
        scored.sort(key=lambda t: -t[0])
        return {
            "items": [
                {"entry": entry, "semantic_similarity": round(sim, 4)}
                for sim, entry in scored[: max(1, min(limit, 20))]
            ],
            "semantic_available": True,
        }
