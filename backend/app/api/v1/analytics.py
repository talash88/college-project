"""Admin analytics APIs (Step 13). ADMIN-only; aggregates, no internals."""

import csv
import io
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_admin
from app.db.session import get_db
from app.models.user import User
from app.services.analytics_service import AnalyticsService
from app.services.auth_service import AuthError

router = APIRouter(prefix="/admin/analytics", tags=["Admin Analytics"])

PROBLEM_CSV_COLUMNS = [
    "ticket_number",
    "title",
    "category",
    "priority_level",
    "priority_score",
    "status",
    "location_text",
    "building",
    "area",
    "submitted_at",
    "resolved_at",
    "closed_at",
    "resolution_seconds",
]

SKILL_CSV_COLUMNS = ["skill_name", "category", "problems", "avg_relevance"]


def _to_http(exc: AuthError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def _parse_preset(preset: str | None) -> tuple[datetime | None, datetime | None]:
    from datetime import UTC, timedelta

    if not preset or preset == "all":
        return None, None
    now = datetime.now(UTC)
    days = {"7d": 7, "30d": 30, "90d": 90, "1y": 365}.get(preset)
    if days is None:
        raise HTTPException(status_code=422, detail=f"Unknown preset: {preset}")
    return now - timedelta(days=days), now


@router.get("/dashboard")
async def analytics_dashboard(
    preset: Literal["7d", "30d", "90d", "1y", "all"] | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    category: str | None = Query(None, max_length=50),
    location: str | None = Query(None, max_length=200),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Coherent dashboard snapshot in one request (admin only)."""
    start, end = _parse_preset(preset)
    service = AnalyticsService(db)
    try:
        return await service.dashboard(
            date_from=date_from or start,
            date_to=date_to or end,
            category=category,
            location=location,
        )
    except AuthError as exc:
        raise _to_http(exc) from None


@router.get("/trends")
async def analytics_trends(
    preset: Literal["7d", "30d", "90d", "1y", "all"] | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    granularity: Literal["day", "week"] | None = Query(None),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Reported vs resolved buckets for drilldown (admin only)."""
    start, end = _parse_preset(preset)
    service = AnalyticsService(db)
    try:
        return await service.trends(
            date_from=date_from or start,
            date_to=date_to or end,
            granularity=granularity or "",
        )
    except AuthError as exc:
        raise _to_http(exc) from None


def _csv_cell(value: object) -> object:
    """Neutralize spreadsheet formula injection (OWASP CSV guidance).

    Only strings beginning with = + - @ (after optional whitespace) or
    containing tab/CR are prefixed with a single quote; ordinary text,
    numbers, and empty cells pass through untouched.
    """
    if not isinstance(value, str):
        return value
    stripped = value.lstrip(" \t")
    if stripped[:1] in ("=", "+", "-", "@") or "\t" in value or "\r" in value:
        return "'" + value
    return value


def _csv_response(filename: str, columns: list[str], rows: list[dict[str, object]]) -> Response:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({col: _csv_cell(row.get(col, "")) for col in columns})
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/problems.csv")
async def export_problems_csv(
    preset: Literal["7d", "30d", "90d", "1y", "all"] | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    category: str | None = Query(None, max_length=50),
    location: str | None = Query(None, max_length=200),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Problem analytics CSV (admin only). No emails, IDs, comments, or tokens."""
    start, end = _parse_preset(preset)
    service = AnalyticsService(db)
    try:
        rows = await service.problem_rows(
            date_from=date_from or start,
            date_to=date_to or end,
            category=category,
            location=location,
        )
    except AuthError as exc:
        raise _to_http(exc) from None
    return _csv_response("problems.csv", PROBLEM_CSV_COLUMNS, rows)


@router.get("/export/skills.csv")
async def export_skills_csv(
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Skill demand CSV (admin only). Aggregates only."""
    service = AnalyticsService(db)
    try:
        rows = await service.skill_rows()
    except AuthError as exc:
        raise _to_http(exc) from None
    return _csv_response("skill-demand.csv", SKILL_CSV_COLUMNS, rows)
