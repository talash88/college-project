"""Admin analytics service (Step 13).

Every metric is a real PostgreSQL aggregation over existing tables — no
precomputed counters, no fabricated values, no predictions. Descriptive only.

Definitions (also documented in docs/STEP_13_ANALYTICS.md):
- OPEN = SUBMITTED, UNDER_REVIEW, APPROVED, ASSIGNED, IN_PROGRESS,
  AWAITING_VERIFICATION. Terminal statuses are never counted as open.
- Category per problem = latest classification's final_category, else its
  predicted_category, else "UNCLASSIFIED" (never silently dropped).
- Resolution duration = resolved_at (else closed_at) minus submitted_at, only
  for RESOLVED/CLOSED problems with both timestamps.
- Duplicate reduction ratio = confirmed duplicate problems / all problems.
- Avoided assignments = confirmed duplicate members with no assignment row.
- Skill demand uses the latest COMPLETED skill analysis per problem only.
- Overdue = unfinished (not DONE/CANCELLED, not COMPLETED/CANCELLED/MISSED)
  with due/target date before now (UTC, computed at query time).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import Integer, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.enums import AvailabilityStatus
from app.models.assignment import ProblemAssignment
from app.models.faculty_profile import FacultyProfile
from app.models.knowledge import KnowledgeEntry
from app.models.problem import Problem
from app.models.problem_analysis import ProblemRequiredSkill, ProblemSkillAnalysis
from app.models.problem_classification import ProblemClassification
from app.models.problem_duplicate import (
    DuplicateCluster,
    DuplicateClusterMember,
    ProblemDuplicateCandidate,
)
from app.models.skill import Skill
from app.models.solution import (
    MentorSolutionReview,
    ProblemResolutionVerification,
    ProblemSolutionSubmission,
)
from app.models.student_profile import StudentProfile
from app.models.user import User
from app.models.workspace import ProblemMilestone, ProblemTask

logger = logging.getLogger(__name__)

OPEN_STATUSES = (
    "SUBMITTED",
    "UNDER_REVIEW",
    "APPROVED",
    "ASSIGNED",
    "IN_PROGRESS",
    "AWAITING_VERIFICATION",
)
UNFINISHED_TASKS = ("TODO", "IN_PROGRESS", "BLOCKED")
UNFINISHED_MILESTONES = ("PLANNED", "IN_PROGRESS")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---------- shared scope ----------

    async def _scoped_ids(
        self,
        *,
        date_from: datetime | None,
        date_to: datetime | None,
        category: str | None,
        location: str | None,
    ) -> set[UUID] | None:
        """Problem ids in scope, or None when no scoping filter is active."""
        if date_from is None and date_to is None and not category and not location:
            return None
        stmt = select(Problem.id)
        if date_from is not None:
            stmt = stmt.where(Problem.submitted_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(Problem.submitted_at <= date_to)
        if location:
            stmt = stmt.where(Problem.location_text.ilike(f"%{location}%"))
        ids = set((await self.session.execute(stmt)).scalars().all())
        if category:
            cats = await self._category_map(ids)
            ids = {pid for pid, cat in cats.items() if cat == category}
        return ids

    async def _category_map(self, ids: set[UUID] | None) -> dict[UUID, str]:
        """Resolved category per problem: final else predicted else UNCLASSIFIED."""
        ranked = (
            select(
                ProblemClassification.problem_id,
                ProblemClassification.final_category,
                ProblemClassification.predicted_category,
                func.row_number()
                .over(
                    partition_by=ProblemClassification.problem_id,
                    order_by=ProblemClassification.created_at.desc(),
                )
                .label("rn"),
            )
        ).subquery()
        stmt = (
            select(
                Problem.id,
                func.coalesce(
                    ranked.c.final_category,
                    ranked.c.predicted_category,
                    "UNCLASSIFIED",
                ),
            )
            .outerjoin(
                ranked, (ranked.c.problem_id == Problem.id) & (ranked.c.rn == 1)
            )
        )
        if ids is not None:
            stmt = stmt.where(Problem.id.in_(ids))
        rows = (await self.session.execute(stmt)).all()
        return {UUID(str(pid)): str(cat) for pid, cat in rows}

    # ---------- overview ----------

    async def overview(
        self,
        *,
        date_from: datetime | None,
        date_to: datetime | None,
        category: str | None,
        location: str | None,
    ) -> dict[str, object]:
        ids = await self._scoped_ids(
            date_from=date_from, date_to=date_to, category=category, location=location
        )
        scope: list[Any] = [] if ids is None else [Problem.id.in_(ids)]
        total = (
            await self.session.execute(
                select(func.count()).select_from(Problem).where(*scope)
            )
        ).scalar_one()
        by_status = (
            (
                await self.session.execute(
                    select(Problem.status, func.count())
                    .select_from(Problem)
                    .where(*scope)
                    .group_by(Problem.status)
                )
            ).all()
        )
        status_counts = {str(s): int(c) for s, c in by_status}
        open_count = sum(status_counts.get(s, 0) for s in OPEN_STATUSES)
        high = (
            await self.session.execute(
                select(func.count())
                .select_from(Problem)
                .where(Problem.priority_level == "HIGH", *scope)
            )
        ).scalar_one()
        critical = (
            await self.session.execute(
                select(func.count())
                .select_from(Problem)
                .where(Problem.priority_level == "CRITICAL", *scope)
            )
        ).scalar_one()
        resolved = status_counts.get("RESOLVED", 0) + status_counts.get("CLOSED", 0)
        active_assignments = (
            await self.session.execute(
                select(func.count())
                .select_from(ProblemAssignment)
                .where(ProblemAssignment.status == "ACTIVE")
            )
        ).scalar_one()
        clusters = (
            await self.session.execute(select(func.count()).select_from(DuplicateCluster))
        ).scalar_one()
        published = (
            await self.session.execute(
                select(func.count()).select_from(KnowledgeEntry).where(
                    KnowledgeEntry.is_published.is_(True),
                    KnowledgeEntry.publication_status == "PUBLISHED",
                )
            )
        ).scalar_one()
        return {
            "total_problems": int(total),
            "open_problems": open_count,
            "status_counts": status_counts,
            "high_priority": int(high),
            "critical_priority": int(critical),
            "resolved_problems": resolved,
            "avg_resolution_seconds": await self._avg_resolution_seconds(ids),
            "active_assignments": int(active_assignments),
            "duplicate_clusters": int(clusters),
            "published_knowledge": int(published),
        }

    async def _avg_resolution_seconds(self, ids: set[UUID] | None) -> float | None:
        end = func.coalesce(Problem.resolved_at, Problem.closed_at)
        stmt = select(func.avg(func.extract("epoch", end - Problem.submitted_at))).select_from(
            Problem
        ).where(
            Problem.status.in_(("RESOLVED", "CLOSED")),
            Problem.submitted_at.is_not(None),
            end.is_not(None),
        )
        if ids is not None:
            stmt = stmt.where(Problem.id.in_(ids))
        value: object = (await self.session.execute(stmt)).scalar_one()
        return float(value) if value is not None and isinstance(value, (int, float)) else None

    # ---------- trends ----------

    async def trends(
        self,
        *,
        date_from: datetime | None,
        date_to: datetime | None,
        granularity: str,
    ) -> dict[str, object]:
        end = date_to or _utcnow()
        start = date_from or (end - timedelta(days=30))
        if granularity not in ("day", "week"):
            granularity = "day" if (end - start).days <= 62 else "week"
        trunc = func.date_trunc(granularity, Problem.submitted_at)
        reported_rows = (
            (
                await self.session.execute(
                    select(trunc.label("bucket"), func.count())
                    .select_from(Problem)
                    .where(Problem.submitted_at >= start, Problem.submitted_at <= end)
                    .group_by("bucket")
                    .order_by("bucket")
                )
            ).all()
        )
        end_col = func.coalesce(Problem.resolved_at, Problem.closed_at)
        rtrunc = func.date_trunc(granularity, end_col)
        resolved_rows = (
            (
                await self.session.execute(
                    select(rtrunc.label("bucket"), func.count())
                    .select_from(Problem)
                    .where(
                        Problem.status.in_(("RESOLVED", "CLOSED")),
                        end_col.is_not(None),
                        end_col >= start,
                        end_col <= end,
                    )
                    .group_by("bucket")
                    .order_by("bucket")
                )
            ).all()
        )
        reported = {b.isoformat(): int(c) for b, c in reported_rows if b is not None}
        resolved = {b.isoformat(): int(c) for b, c in resolved_rows if b is not None}
        buckets = self._fill_buckets(start, end, granularity)
        return {
            "granularity": granularity,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "buckets": [
                {
                    "bucket": b,
                    "reported": reported.get(b, 0),
                    "resolved": resolved.get(b, 0),
                }
                for b in buckets
            ],
        }

    @staticmethod
    def _fill_buckets(start: datetime, end: datetime, granularity: str) -> list[str]:
        step = timedelta(days=1 if granularity == "day" else 7)
        cursor = datetime(start.year, start.month, start.day, tzinfo=UTC)
        out = []
        while cursor <= end:
            out.append(cursor.isoformat())
            cursor += step
        return out

    # ---------- categories ----------

    async def categories(
        self,
        *,
        date_from: datetime | None,
        date_to: datetime | None,
        location: str | None,
    ) -> dict[str, object]:
        ids = await self._scoped_ids(
            date_from=date_from, date_to=date_to, category=None, location=location
        )
        cats = await self._category_map(ids)
        counts: dict[str, int] = {}
        for cat in cats.values():
            counts[cat] = counts.get(cat, 0) + 1
        total = sum(counts.values())
        items = [
            {
                "category": cat,
                "count": count,
                "percentage": round(100.0 * count / total, 1) if total else 0.0,
            }
            for cat, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ]
        return {"total": total, "items": items}

    # ---------- locations ----------

    async def locations(
        self,
        *,
        date_from: datetime | None,
        date_to: datetime | None,
        limit: int = 10,
        search: str | None = None,
    ) -> dict[str, object]:
        filt: list[Any] = [Problem.location_text.is_not(None)]
        if date_from is not None:
            filt.append(Problem.submitted_at >= date_from)
        if date_to is not None:
            filt.append(Problem.submitted_at <= date_to)
        if search:
            filt.append(func.lower(func.trim(Problem.location_text)).ilike(f"%{search.lower()}%"))
        rows = (
            (
                await self.session.execute(
                    select(
                        func.lower(func.trim(Problem.location_text)).label("norm"),
                        func.count().label("count"),
                        func.sum(func.cast(Problem.status.in_(OPEN_STATUSES), Integer)).label(
                            "open_count"
                        ),
                        func.sum(
                            func.cast(Problem.status.in_(("RESOLVED", "CLOSED")), Integer)
                        ).label("resolved_count"),
                    )
                    .where(*filt)
                    .group_by("norm")
                    .order_by(func.count().desc())
                    .limit(limit)
                )
            ).all()
        )
        # One bounded detail query per hotspot (limit small): display spelling,
        # problem ids for exact latest-category aggregation.
        items = []
        for norm, count, open_c, resolved_c in rows:
            detail = (
                await self.session.execute(
                    select(Problem.id, Problem.location_text)
                    .where(func.lower(func.trim(Problem.location_text)) == norm)
                    .order_by(Problem.created_at.desc())
                )
            ).all()
            if not detail:
                continue
            display = str(detail[0][1])
            cats = await self._category_map({UUID(str(pid)) for pid, _ in detail})
            top: dict[str, int] = {}
            for cat in cats.values():
                top[cat] = top.get(cat, 0) + 1
            common = [c for c, _ in sorted(top.items(), key=lambda kv: (-kv[1], kv[0]))[:2]]
            items.append(
                {
                    "location": display,
                    "count": int(count),
                    "open_count": int(open_c or 0),
                    "resolved_count": int(resolved_c or 0),
                    "common_categories": common,
                }
            )
        return {"items": items}

    # ---------- priority ----------

    async def priorities(
        self,
        *,
        date_from: datetime | None,
        date_to: datetime | None,
        category: str | None,
        location: str | None,
    ) -> dict[str, object]:
        ids = await self._scoped_ids(
            date_from=date_from, date_to=date_to, category=category, location=location
        )
        scope: list[Any] = [] if ids is None else [Problem.id.in_(ids)]
        rows = (
            (
                await self.session.execute(
                    select(Problem.priority_level, func.count())
                    .select_from(Problem)
                    .where(Problem.priority_level.is_not(None), *scope)
                    .group_by(Problem.priority_level)
                )
            ).all()
        )
        counts = {str(level): int(c) for level, c in rows}
        avg_score: object = (
            await self.session.execute(
                select(func.avg(Problem.priority_score))
                .select_from(Problem)
                .where(Problem.priority_score.is_not(None), *scope)
            )
        ).scalar_one()
        hot = (
            (
                await self.session.execute(
                    select(Problem)
                    .where(
                        Problem.priority_level.in_(("HIGH", "CRITICAL")),
                        Problem.status.in_(OPEN_STATUSES),
                        *scope,
                    )
                    .order_by(
                        func.coalesce(Problem.priority_score, 0).desc(),
                        Problem.submitted_at.asc(),
                    )
                    .limit(10)
                )
            )
            .scalars()
            .all()
        )
        return {
            "counts": counts,
            "average_score": round(float(avg_score), 2)
            if isinstance(avg_score, (int, float))
            else None,
            "high_critical_open": [
                {
                    "problem_id": str(p.id),
                    "ticket_number": p.ticket_number,
                    "title": p.title,
                    "priority_level": p.priority_level,
                    "priority_score": p.priority_score,
                    "status": str(p.status.value if hasattr(p.status, "value") else p.status),
                    "submitted_at": p.submitted_at.isoformat() if p.submitted_at else None,
                }
                for p in hot
            ],
        }

    # ---------- resolution ----------

    async def resolution(
        self,
        *,
        date_from: datetime | None,
        date_to: datetime | None,
        category: str | None,
        location: str | None,
    ) -> dict[str, object]:
        ids = await self._scoped_ids(
            date_from=date_from, date_to=date_to, category=category, location=location
        )
        end = func.coalesce(Problem.resolved_at, Problem.closed_at)
        seconds = func.extract("epoch", end - Problem.submitted_at)
        filt: list[Any] = [
            Problem.status.in_(("RESOLVED", "CLOSED")),
            Problem.submitted_at.is_not(None),
            end.is_not(None),
        ]
        if ids is not None:
            filt.append(Problem.id.in_(ids))
        row = (
            await self.session.execute(
                select(
                    func.count().label("n"),
                    func.avg(seconds).label("avg"),
                    func.min(seconds).label("min"),
                    func.max(seconds).label("max"),
                    func.percentile_cont(0.5).within_group(seconds).label("median"),
                    func.percentile_cont(0.9).within_group(seconds).label("p90"),
                )
                .select_from(Problem)
                .where(*filt)
            )
        ).one()
        return {
            "count": int(row.n or 0),
            "average_seconds": float(row.avg) if row.avg is not None else None,
            "median_seconds": float(row.median) if row.median is not None else None,
            "min_seconds": float(row.min) if row.min is not None else None,
            "max_seconds": float(row.max) if row.max is not None else None,
            "p90_seconds": float(row.p90) if row.p90 is not None else None,
        }

    # ---------- duplicates ----------

    async def duplicates(self) -> dict[str, object]:
        confirmed = (
            await self.session.execute(
                select(func.count()).select_from(Problem).where(Problem.status == "DUPLICATE")
            )
        ).scalar_one()
        total_problems = (
            await self.session.execute(select(func.count()).select_from(Problem))
        ).scalar_one()
        cluster_ids = (
            (await self.session.execute(select(DuplicateCluster.id))).scalars().all()
        )
        member_counts = []
        for cid in cluster_ids:
            n = (
                await self.session.execute(
                    select(func.count())
                    .select_from(DuplicateClusterMember)
                    .where(DuplicateClusterMember.cluster_id == cid)
                )
            ).scalar_one()
            if int(n) > 0:
                member_counts.append(int(n))
        pending = (
            await self.session.execute(
                select(func.count())
                .select_from(ProblemDuplicateCandidate)
                .where(ProblemDuplicateCandidate.decision_status == "PENDING")
            )
        ).scalar_one()
        decided_confirmed = (
            await self.session.execute(
                select(func.count())
                .select_from(ProblemDuplicateCandidate)
                .where(ProblemDuplicateCandidate.decision_status == "CONFIRMED_DUPLICATE")
            )
        ).scalar_one()
        decided_rejected = (
            await self.session.execute(
                select(func.count())
                .select_from(ProblemDuplicateCandidate)
                .where(ProblemDuplicateCandidate.decision_status == "REJECTED")
            )
        ).scalar_one()
        decided_total = int(decided_confirmed) + int(decided_rejected)
        assigned_ids = set(
            (
                await self.session.execute(select(ProblemAssignment.problem_id).distinct())
            ).scalars().all()
        )
        member_problem_ids = set(
            (
                await self.session.execute(select(DuplicateClusterMember.problem_id).distinct())
            ).scalars().all()
        )
        avoided = len([pid for pid in member_problem_ids if pid not in assigned_ids])
        return {
            "confirmed_duplicate_problems": int(confirmed),
            "duplicate_reduction_ratio": round(int(confirmed) / int(total_problems), 4)
            if total_problems
            else 0.0,
            "active_clusters": len(member_counts),
            "average_reports_per_cluster": round(sum(member_counts) / len(member_counts), 2)
            if member_counts
            else 0.0,
            "largest_cluster_size": max(member_counts) if member_counts else 0,
            "pending_candidates": int(pending),
            "confirmed_candidates": int(decided_confirmed),
            "rejected_candidates": int(decided_rejected),
            "confirmation_rate": round(int(decided_confirmed) / decided_total, 4)
            if decided_total
            else None,
            "avoided_assignments": avoided,
        }

    # ---------- skills ----------

    async def skill_demand(self, *, limit: int = 10) -> dict[str, object]:
        """Latest COMPLETED analysis per problem only (no history double-count)."""
        ranked = (
            select(
                ProblemSkillAnalysis.problem_id,
                ProblemSkillAnalysis.id.label("analysis_id"),
                func.row_number()
                .over(
                    partition_by=ProblemSkillAnalysis.problem_id,
                    order_by=ProblemSkillAnalysis.created_at.desc(),
                )
                .label("rn"),
            )
            .where(ProblemSkillAnalysis.status == "COMPLETED")
            .subquery()
        )
        rows = (
            (
                await self.session.execute(
                    select(
                        ProblemRequiredSkill.skill_id,
                        func.count(distinct(ProblemRequiredSkill.problem_id)).label("problems"),
                        func.avg(ProblemRequiredSkill.score).label("avg_score"),
                    )
                    .join(ranked, ranked.c.analysis_id == ProblemRequiredSkill.analysis_id)
                    .where(ranked.c.rn == 1)
                    .group_by(ProblemRequiredSkill.skill_id)
                    .order_by(func.count(distinct(ProblemRequiredSkill.problem_id)).desc())
                    .limit(limit)
                )
            ).all()
        )
        items = []
        for skill_id, problems, avg_score in rows:
            skill = await self.session.get(Skill, skill_id)
            items.append(
                {
                    "skill_id": str(skill_id),
                    "name": skill.name if skill else str(skill_id),
                    "category": str(skill.category.value)
                    if skill is not None and hasattr(skill.category, "value")
                    else None,
                    "problems": int(problems),
                    "avg_relevance": round(float(avg_score), 4)
                    if isinstance(avg_score, (int, float))
                    else None,
                }
            )
        return {"items": items}

    # ---------- workloads ----------

    async def workloads(self) -> dict[str, object]:
        solvers = await self._availability_stats(
            StudentProfile.current_workload,
            StudentProfile.max_workload,
            StudentProfile.availability_status,
        )
        mentors = await self._availability_stats(
            FacultyProfile.current_workload,
            FacultyProfile.max_workload,
            FacultyProfile.availability_status,
        )
        dist = (
            (
                await self.session.execute(
                    select(StudentProfile.current_workload, func.count())
                    .group_by(StudentProfile.current_workload)
                    .order_by(StudentProfile.current_workload)
                )
            ).all()
        )
        top_solvers = (
            (
                await self.session.execute(
                    select(
                        User.full_name,
                        StudentProfile.current_workload,
                        StudentProfile.max_workload,
                    )
                    .join(StudentProfile, StudentProfile.user_id == User.id)
                    .where(StudentProfile.current_workload > 0)
                    .order_by(StudentProfile.current_workload.desc())
                    .limit(10)
                )
            ).all()
        )
        top_mentors = (
            (
                await self.session.execute(
                    select(
                        User.full_name,
                        FacultyProfile.current_workload,
                        FacultyProfile.max_workload,
                    )
                    .join(FacultyProfile, FacultyProfile.user_id == User.id)
                    .where(FacultyProfile.current_workload > 0)
                    .order_by(FacultyProfile.current_workload.desc())
                    .limit(10)
                )
            ).all()
        )
        return {
            "solvers": solvers,
            "mentors": mentors,
            "solver_workload_distribution": [
                {"current_workload": int(w), "people": int(n)} for w, n in dist
            ],
            "busiest_solvers": [
                {"name": n, "current_workload": int(c), "max_workload": int(m)}
                for n, c, m in top_solvers
            ],
            "busiest_mentors": [
                {"name": n, "current_workload": int(c), "max_workload": int(m)}
                for n, c, m in top_mentors
            ],
        }

    async def _availability_stats(
        self,
        workload_col: InstrumentedAttribute[int],
        max_col: InstrumentedAttribute[int],
        avail_col: InstrumentedAttribute[AvailabilityStatus],
    ) -> dict[str, object]:
        rows = (
            (
                await self.session.execute(
                    select(
                        avail_col,
                        func.count().label("n"),
                        func.sum(workload_col).label("used"),
                        func.sum(max_col).label("capacity"),
                    ).group_by(avail_col)
                )
            ).all()
        )
        by_status = {
            str(status): {
                "count": int(n),
                "used": int(used or 0),
                "capacity": int(cap or 0),
            }
            for status, n, used, cap in rows
        }
        total_used = sum(v["used"] for v in by_status.values())
        total_cap = sum(v["capacity"] for v in by_status.values())
        return {
            "by_availability": by_status,
            "total_used": total_used,
            "total_capacity": total_cap,
            "utilization": round(total_used / total_cap, 4) if total_cap else 0.0,
        }

    # ---------- assignments & overrides ----------

    async def assignments(self) -> dict[str, object]:
        by_status = (
            (
                await self.session.execute(
                    select(ProblemAssignment.status, func.count()).group_by(
                        ProblemAssignment.status
                    )
                )
            ).all()
        )
        counts = {str(s): int(c) for s, c in by_status}
        total = sum(counts.values())
        team_over = (
            await self.session.execute(
                select(func.count())
                .select_from(ProblemAssignment)
                .where(ProblemAssignment.team_was_overridden.is_(True))
            )
        ).scalar_one()
        mentor_over = (
            await self.session.execute(
                select(func.count())
                .select_from(ProblemAssignment)
                .where(ProblemAssignment.mentor_was_overridden.is_(True))
            )
        ).scalar_one()
        return {
            "counts": counts,
            "total": total,
            "team_override_count": int(team_over),
            "team_override_rate": round(int(team_over) / total, 4) if total else None,
            "team_accepted_count": total - int(team_over),
            "mentor_override_count": int(mentor_over),
            "mentor_override_rate": round(int(mentor_over) / total, 4) if total else None,
            "mentor_accepted_count": total - int(mentor_over),
        }

    # ---------- classification ops + model quality ----------

    async def classification(self) -> dict[str, object]:
        from app.models.problem_classification import ProblemClassification

        by_status = (
            (
                await self.session.execute(
                    select(ProblemClassification.status, func.count()).group_by(
                        ProblemClassification.status
                    )
                )
            ).all()
        )
        counts = {str(s): int(c) for s, c in by_status}
        total = sum(counts.values())
        reviewed = (
            await self.session.execute(
                select(func.count())
                .select_from(ProblemClassification)
                .where(ProblemClassification.reviewed_by.is_not(None))
            )
        ).scalar_one()
        overridden = (
            await self.session.execute(
                select(func.count())
                .select_from(ProblemClassification)
                .where(
                    ProblemClassification.final_category.is_not(None),
                    ProblemClassification.predicted_category.is_not(None),
                    ProblemClassification.final_category
                    != ProblemClassification.predicted_category,
                )
            )
        ).scalar_one()
        return {
            "counts": counts,
            "total": total,
            "low_confidence": counts.get("LOW_CONFIDENCE", 0),
            "low_confidence_rate": round(counts.get("LOW_CONFIDENCE", 0) / total, 4)
            if total
            else None,
            "failed": counts.get("FAILED", 0),
            "reviewed": int(reviewed),
            "override_count": int(overridden),
            "override_rate": round(int(overridden) / int(reviewed), 4) if reviewed else None,
            "model_quality": self._model_quality(),
        }

    @staticmethod
    def _model_quality() -> dict[str, object]:
        """Stored offline evaluation artifacts (never recalculated here)."""
        base = Path(__file__).parent.parent.parent / "ml" / "artifacts" / "problem_classifier"
        try:
            metrics = json.loads((base / "metrics.json").read_text())
            metadata = json.loads((base / "metadata.json").read_text())
        except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
            logger.warning("classifier artifacts unavailable: %s", exc)
            return {"available": False, "note": "Development evaluation artifacts not found."}
        per_class = metrics.get("per_class", {})
        pairs: list[tuple[str, float]] = []
        for label, vals in per_class.items():
            if isinstance(vals, dict):
                try:
                    pairs.append((str(label), float(vals.get("f1", 0.0))))
                except (TypeError, ValueError):
                    pairs.append((str(label), 0.0))
        pairs.sort(key=lambda item: item[1])
        weakest = [{"label": label, "f1": f1} for label, f1 in pairs]
        return {
            "available": True,
            "label": "Development Evaluation Dataset (not production accuracy)",
            "model_version": metadata.get("model_version"),
            "base_model": metadata.get("base_model"),
            "dataset_version": metadata.get("dataset_version"),
            "train_samples": metadata.get("train_samples"),
            "val_samples": metadata.get("val_samples"),
            "test_samples": metadata.get("test_samples"),
            "test_accuracy": metrics.get("accuracy"),
            "macro_f1": metrics.get("macro_f1"),
            "weighted_f1": metrics.get("weighted_f1"),
            "confidence_threshold": 0.60,
            "per_class_f1": weakest,
        }

    # ---------- verification & revisions ----------

    async def verification(self) -> dict[str, object]:
        resolved = (
            await self.session.execute(
                select(func.count())
                .select_from(ProblemResolutionVerification)
                .where(ProblemResolutionVerification.decision == "RESOLVED")
            )
        ).scalar_one()
        rejected = (
            await self.session.execute(
                select(func.count())
                .select_from(ProblemResolutionVerification)
                .where(ProblemResolutionVerification.decision == "NOT_RESOLVED")
            )
        ).scalar_one()
        total = int(resolved) + int(rejected)
        first_try = (
            await self.session.execute(
                select(func.count(distinct(ProblemSolutionSubmission.problem_id))).where(
                    ProblemSolutionSubmission.revision_number == 1,
                    ProblemSolutionSubmission.status.in_(("MENTOR_APPROVED", "VERIFIED")),
                )
            )
        ).scalar_one()
        max_rev_rows = (
            (
                await self.session.execute(
                    select(
                        ProblemSolutionSubmission.problem_id,
                        func.max(ProblemSolutionSubmission.revision_number).label("mx"),
                    ).group_by(ProblemSolutionSubmission.problem_id)
                )
            ).all()
        )
        revs = [int(mx) for _, mx in max_rev_rows]
        changes_requested = (
            await self.session.execute(
                select(func.count())
                .select_from(MentorSolutionReview)
                .where(MentorSolutionReview.decision == "CHANGES_REQUESTED")
            )
        ).scalar_one()
        return {
            "resolved_confirmations": int(resolved),
            "not_resolved_responses": int(rejected),
            "reopen_rate": round(int(rejected) / total, 4) if total else None,
            "resolved_on_first_submission": int(first_try),
            "average_revisions": round(sum(revs) / len(revs), 2) if revs else None,
            "mentor_changes_requested": int(changes_requested),
        }

    # ---------- knowledge ----------

    async def knowledge(self) -> dict[str, object]:
        by_status = (
            (
                await self.session.execute(
                    select(KnowledgeEntry.publication_status, func.count()).group_by(
                        KnowledgeEntry.publication_status
                    )
                )
            ).all()
        )
        counts = {str(s): int(c) for s, c in by_status}
        cat_rows = (
            (
                await self.session.execute(
                    select(KnowledgeEntry.final_category, func.count())
                    .where(
                        KnowledgeEntry.is_published.is_(True),
                        KnowledgeEntry.publication_status == "PUBLISHED",
                    )
                    .group_by(KnowledgeEntry.final_category)
                    .order_by(func.count().desc())
                )
            ).all()
        )
        return {
            "counts": counts,
            "published": counts.get("PUBLISHED", 0),
            "archived": counts.get("ARCHIVED", 0),
            "failed": counts.get("FAILED", 0),
            "top_categories": [
                {"category": str(c or "UNCLASSIFIED"), "count": int(n)} for c, n in cat_rows
            ],
        }

    # ---------- operations (tasks/milestones/pending) ----------

    async def operations(self) -> dict[str, object]:
        now = _utcnow()
        task_rows = (
            (
                await self.session.execute(
                    select(ProblemTask.status, func.count()).group_by(ProblemTask.status)
                )
            ).all()
        )
        task_counts = {str(s): int(c) for s, c in task_rows}
        blocked = (
            (
                await self.session.execute(
                    select(ProblemTask.id, ProblemTask.problem_id, ProblemTask.title)
                    .where(ProblemTask.status == "BLOCKED")
                    .order_by(ProblemTask.updated_at.desc())
                    .limit(10)
                )
            ).all()
        )
        overdue_tasks = (
            (
                await self.session.execute(
                    select(
                        ProblemTask.id,
                        ProblemTask.problem_id,
                        ProblemTask.title,
                        ProblemTask.due_date,
                    )
                    .where(
                        ProblemTask.status.in_(UNFINISHED_TASKS),
                        ProblemTask.due_date.is_not(None),
                        ProblemTask.due_date < now,
                    )
                    .order_by(ProblemTask.due_date.asc())
                    .limit(10)
                )
            ).all()
        )
        ms_rows = (
            (
                await self.session.execute(
                    select(ProblemMilestone.status, func.count()).group_by(
                        ProblemMilestone.status
                    )
                )
            ).all()
        )
        ms_counts = {str(s): int(c) for s, c in ms_rows}
        overdue_ms = (
            (
                await self.session.execute(
                    select(
                        ProblemMilestone.id,
                        ProblemMilestone.problem_id,
                        ProblemMilestone.title,
                        ProblemMilestone.target_date,
                    )
                    .where(
                        ProblemMilestone.status.in_(UNFINISHED_MILESTONES),
                        ProblemMilestone.target_date.is_not(None),
                        ProblemMilestone.target_date < now,
                    )
                    .order_by(ProblemMilestone.target_date.asc())
                    .limit(10)
                )
            ).all()
        )
        upcoming_ms = (
            (
                await self.session.execute(
                    select(
                        ProblemMilestone.id,
                        ProblemMilestone.problem_id,
                        ProblemMilestone.title,
                        ProblemMilestone.target_date,
                    )
                    .where(
                        ProblemMilestone.status.in_(UNFINISHED_MILESTONES),
                        ProblemMilestone.target_date.is_not(None),
                        ProblemMilestone.target_date >= now,
                        ProblemMilestone.target_date <= now + timedelta(days=7),
                    )
                    .order_by(ProblemMilestone.target_date.asc())
                    .limit(10)
                )
            ).all()
        )
        pending_dupes = (
            await self.session.execute(
                select(func.count())
                .select_from(ProblemDuplicateCandidate)
                .where(ProblemDuplicateCandidate.decision_status == "PENDING")
            )
        ).scalar_one()
        return {
            "task_counts": task_counts,
            "blocked_tasks": [
                {"id": str(i), "problem_id": str(p), "title": t} for i, p, t in blocked
            ],
            "overdue_tasks": [
                {
                    "id": str(i),
                    "problem_id": str(p),
                    "title": t,
                    "due_date": d.isoformat() if d else None,
                }
                for i, p, t, d in overdue_tasks
            ],
            "milestone_counts": ms_counts,
            "overdue_milestones": [
                {
                    "id": str(i),
                    "problem_id": str(p),
                    "title": t,
                    "target_date": d.isoformat() if d else None,
                }
                for i, p, t, d in overdue_ms
            ],
            "upcoming_milestones": [
                {
                    "id": str(i),
                    "problem_id": str(p),
                    "title": t,
                    "target_date": d.isoformat() if d else None,
                }
                for i, p, t, d in upcoming_ms
            ],
            "pending_duplicate_reviews": int(pending_dupes),
        }

    # ---------- dashboard snapshot ----------

    async def dashboard(
        self,
        *,
        date_from: datetime | None,
        date_to: datetime | None,
        category: str | None,
        location: str | None,
    ) -> dict[str, object]:
        return {
            "generated_at": _utcnow().isoformat(),
            "filters": {
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
                "category": category,
                "location": location,
            },
            "overview": await self.overview(
                date_from=date_from, date_to=date_to, category=category, location=location
            ),
            "categories": await self.categories(
                date_from=date_from, date_to=date_to, location=location
            ),
            "priorities": await self.priorities(
                date_from=date_from, date_to=date_to, category=category, location=location
            ),
            "resolution": await self.resolution(
                date_from=date_from, date_to=date_to, category=category, location=location
            ),
            "locations": await self.locations(
                date_from=date_from, date_to=date_to, search=location
            ),
            "duplicates": await self.duplicates(),
            "skill_demand": await self.skill_demand(),
            "workloads": await self.workloads(),
            "assignments": await self.assignments(),
            "classification": await self.classification(),
            "verification": await self.verification(),
            "knowledge": await self.knowledge(),
            "operations": await self.operations(),
        }

    # ---------- CSV rows ----------

    async def problem_rows(
        self,
        *,
        date_from: datetime | None,
        date_to: datetime | None,
        category: str | None,
        location: str | None,
    ) -> list[dict[str, object]]:
        ids = await self._scoped_ids(
            date_from=date_from, date_to=date_to, category=category, location=location
        )
        stmt = select(Problem).order_by(Problem.submitted_at.asc())
        if ids is not None:
            stmt = stmt.where(Problem.id.in_(ids))
        problems = (await self.session.execute(stmt)).scalars().all()
        cats = await self._category_map({p.id for p in problems} if problems else set())
        rows: list[dict[str, object]] = []
        for p in problems:
            end = p.resolved_at or p.closed_at
            duration = None
            if p.submitted_at is not None and end is not None:
                duration = int((end - p.submitted_at).total_seconds())
            row: dict[str, object] = {
                "ticket_number": p.ticket_number,
                "title": p.title,
                "category": cats.get(p.id, "UNCLASSIFIED"),
                "priority_level": p.priority_level or "",
                "priority_score": p.priority_score if p.priority_score is not None else "",
                "status": str(p.status.value if hasattr(p.status, "value") else p.status),
                "location_text": p.location_text or "",
                "building": p.building or "",
                "area": p.area or "",
                "submitted_at": p.submitted_at.isoformat() if p.submitted_at else "",
                "resolved_at": p.resolved_at.isoformat() if p.resolved_at else "",
                "closed_at": p.closed_at.isoformat() if p.closed_at else "",
                "resolution_seconds": duration if duration is not None else "",
            }
            rows.append(row)
        return rows

    async def skill_rows(self) -> list[dict[str, object]]:
        demand = await self.skill_demand(limit=100)
        items = demand["items"]
        assert isinstance(items, list)
        rows: list[dict[str, object]] = []
        for item in items:
            assert isinstance(item, dict)
            row: dict[str, object] = {
                "skill_name": str(item.get("name", "")),
                "category": str(item.get("category", "") or ""),
                "problems": item.get("problems", 0),
                "avg_relevance": item.get("avg_relevance", "") or "",
            }
            rows.append(row)
        return rows
