"""Knowledge Repository APIs (Step 12).

Public repository browsing is authenticated (any role); admin manages
publication lifecycle. Related-solutions for open problems follow existing
problem visibility rules.
"""

from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, require_admin
from app.core.config import settings
from app.db.session import get_db
from app.models.knowledge import KnowledgeEntry
from app.models.user import User
from app.schemas.knowledge import (
    AdminKnowledgeEntryResponse,
    KnowledgeEntryDetail,
    KnowledgeEntrySummary,
    KnowledgeEvidenceFile,
    KnowledgeSearchResponse,
    KnowledgeSkillSummary,
    PublicationActionResponse,
    RelatedKnowledgeItem,
    RelatedSolutionsResponse,
)
from app.services.auth_service import AuthError
from app.services.knowledge_service import KnowledgeService
from app.storage.local import resolve_storage_dir

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])
admin_router = APIRouter(prefix="/admin/knowledge", tags=["Admin Knowledge"])


def _to_http(exc: AuthError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def _skill_views(entry: KnowledgeEntry) -> list[KnowledgeSkillSummary]:
    views = []
    for link in entry.skills:
        if link.skill is None:
            continue
        views.append(
            KnowledgeSkillSummary(
                skill_id=link.skill_id,
                name=link.skill.name,
                relevance_score=link.relevance_score,
            )
        )
    return views


def _preview(text: str, limit: int = 300) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[:limit].rstrip() + "…"


def _summary(
    entry: KnowledgeEntry,
    *,
    relevance: float | None = None,
    semantic: float | None = None,
    keyword: float | None = None,
) -> KnowledgeEntrySummary:
    return KnowledgeEntrySummary(
        id=entry.id,
        public_id=entry.public_id,
        title=entry.title,
        problem_preview=_preview(entry.problem_summary),
        final_category=entry.final_category,
        location_summary=entry.location_summary,
        skills=_skill_views(entry),
        resolution_duration_minutes=entry.resolution_duration_minutes,
        published_at=entry.published_at,
        relevance=relevance,
        semantic_similarity=semantic,
        keyword_score=keyword,
    )


def _evidence_views(entry: KnowledgeEntry) -> list[KnowledgeEvidenceFile]:
    files = []
    for raw in entry.evidence_files or []:
        try:
            files.append(
                KnowledgeEvidenceFile(
                    file_id=UUID(str(raw["file_id"])),
                    original_filename=str(raw["original_filename"]),
                    mime_type=str(raw.get("mime_type", "application/octet-stream")),
                    size_bytes=int(raw.get("size_bytes", 0)),
                )
            )
        except (KeyError, ValueError, AttributeError, TypeError):
            continue
    return files


@router.get("", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    q: str | None = Query(None, max_length=500),
    search_mode: Literal["ALL", "HYBRID", "KEYWORD", "SEMANTIC"] = Query("ALL"),
    category: str | None = Query(None, max_length=50),
    skill_id: UUID | None = Query(None),
    location: str | None = Query(None, max_length=200),
    published_from: datetime | None = Query(None),
    published_to: datetime | None = Query(None),
    sort: Literal["relevance", "newest", "oldest"] = Query("newest"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeSearchResponse:
    """Search published knowledge. Any authenticated role. No internals."""
    del current_user
    service = KnowledgeService(db)
    try:
        result = await service.search(
            q=q,
            mode=search_mode,
            category=category,
            skill_id=skill_id,
            location=location,
            published_from=published_from,
            published_to=published_to,
            sort=sort if (q or search_mode in ("SEMANTIC", "HYBRID")) else "newest",
            page=page,
            page_size=page_size,
        )
    except AuthError as exc:
        raise _to_http(exc) from None
    items = result["items"]
    assert isinstance(items, list)
    total = result["total"]
    assert isinstance(total, int)
    return KnowledgeSearchResponse(
        items=[
            _summary(
                _row_entry(row),
                relevance=_num(row.get("relevance")) if isinstance(row, dict) else None,
                semantic=_num(row.get("semantic_similarity")) if isinstance(row, dict) else None,
                keyword=_num(row.get("keyword_score")) if isinstance(row, dict) else None,
            )
            for row in items
        ],
        total=total,
        page=page,
        page_size=page_size,
        search_mode=search_mode,
        semantic_available=bool(result.get("semantic_available", True)),
        error=str(result["error"]) if result.get("error") else None,
    )


def _num(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _row_entry(row: object) -> KnowledgeEntry:
    assert isinstance(row, dict)
    entry = row["entry"]
    assert isinstance(entry, KnowledgeEntry)
    return entry


def _row_score(row: object, key: str) -> float:
    assert isinstance(row, dict)
    value = _num(row.get(key))
    assert value is not None
    return value


@router.get("/{entry_ref}", response_model=KnowledgeEntryDetail)
async def get_knowledge_entry(
    entry_ref: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeEntryDetail:
    """Safe full article by UUID or public KB id. Any authenticated role."""
    del current_user
    service = KnowledgeService(db)
    entry = await _resolve_entry(service, entry_ref)
    if entry is None or not entry.is_published or entry.publication_status != "PUBLISHED":
        raise HTTPException(status_code=404, detail="Knowledge entry not found")
    related = await service.related(entry.id, limit=5)
    return KnowledgeEntryDetail(
        id=entry.id,
        public_id=entry.public_id,
        title=entry.title,
        problem_summary=entry.problem_summary,
        final_category=entry.final_category,
        location_summary=entry.location_summary,
        root_cause=entry.root_cause,
        solution_summary=entry.solution_summary,
        work_performed=entry.work_performed,
        testing_performed=entry.testing_performed,
        deployment_notes=entry.deployment_notes,
        known_limitations=entry.known_limitations,
        skills=_skill_views(entry),
        resolution_duration_minutes=entry.resolution_duration_minutes,
        team_names=[str(n) for n in entry.team_names or []],
        mentor_name=entry.mentor_name,
        mentor_designation=entry.mentor_designation,
        evidence_files=_evidence_views(entry),
        published_at=entry.published_at,
        related=[
            RelatedKnowledgeItem(
                entry=_summary(_row_entry(row)),
                semantic_similarity=_row_score(row, "semantic_similarity"),
            )
            for row in related
        ],
    )


async def _resolve_entry(service: KnowledgeService, ref: str) -> KnowledgeEntry | None:
    try:
        entry_id = UUID(ref)
    except (ValueError, AttributeError, TypeError):
        entry_id = None
    if entry_id is not None:
        entry = await service.entries.get(entry_id)
        if entry is not None:
            return entry
    return await service.entries.get_by_public_id(ref.upper())


@router.get("/{entry_ref}/related", response_model=RelatedSolutionsResponse)
async def related_knowledge(
    entry_ref: str,
    limit: int = Query(5, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RelatedSolutionsResponse:
    """Semantically related published articles (never itself, never archived)."""
    del current_user
    service = KnowledgeService(db)
    entry = await _resolve_entry(service, entry_ref)
    if entry is None or not entry.is_published or entry.publication_status != "PUBLISHED":
        raise HTTPException(status_code=404, detail="Knowledge entry not found")
    try:
        related = await service.related(entry.id, limit=limit)
    except AuthError as exc:
        raise _to_http(exc) from None
    return RelatedSolutionsResponse(
        items=[
            RelatedKnowledgeItem(
                entry=_summary(_row_entry(row)),
                semantic_similarity=_row_score(row, "semantic_similarity"),
            )
            for row in related
        ],
        semantic_available=True,
    )


@router.get("/{entry_ref}/evidence/{file_id}/download")
async def download_knowledge_evidence(
    entry_ref: str,
    file_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Download explicitly shareable evidence. Authenticated; revocable."""
    del current_user
    service = KnowledgeService(db)
    entry = await _resolve_entry(service, entry_ref)
    if entry is None or not entry.is_published or entry.publication_status != "PUBLISHED":
        raise HTTPException(status_code=404, detail="Knowledge entry not found")
    snapshot_ids = set()
    for raw in entry.evidence_files or []:
        try:
            snapshot_ids.add(str(UUID(str(raw["file_id"]))))
        except (KeyError, ValueError, AttributeError, TypeError):
            continue
    if str(file_id) not in snapshot_ids:
        raise HTTPException(status_code=404, detail="Evidence file not found")
    row = await service.work_files.get(file_id)
    if (
        row is None
        or row.problem_id != entry.problem_id
        or not row.is_knowledge_shareable
    ):
        raise HTTPException(status_code=404, detail="Evidence file not found")
    if "/" in row.storage_key or "\\" in row.storage_key:
        raise HTTPException(status_code=500, detail="Stored file reference is invalid")
    target = resolve_storage_dir(settings.STORAGE_DIR) / Path(row.storage_key).name
    try:
        import asyncio

        data = await asyncio.to_thread(target.read_bytes)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Stored file is missing") from exc
    return Response(
        content=data,
        media_type=row.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{row.original_filename}"'},
    )


@admin_router.get("", response_model=list[AdminKnowledgeEntryResponse])
async def admin_list_knowledge(
    publication_status: Literal["PENDING", "PUBLISHED", "FAILED", "ARCHIVED"] | None = Query(None),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AdminKnowledgeEntryResponse]:
    """All entries incl. failed/archived. Admin only."""
    service = KnowledgeService(db)
    rows = await service.entries.admin_list(publication_status=publication_status)
    return [
        AdminKnowledgeEntryResponse(
            id=row.id,
            public_id=row.public_id,
            problem_id=row.problem_id,
            problem_ticket=row.problem.ticket_number if row.problem is not None else None,
            title=row.title,
            publication_status=row.publication_status,
            is_published=row.is_published,
            published_at=row.published_at,
            archived_at=row.archived_at,
            failure_reason=row.failure_reason,
            created_at=row.created_at,
        )
        for row in rows
    ]


@admin_router.post("/{entry_id}/retry", response_model=PublicationActionResponse)
async def admin_retry_publication(
    entry_id: UUID,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> PublicationActionResponse:
    service = KnowledgeService(db)
    try:
        status = await service.retry(entry_id, _admin.id)
    except AuthError as exc:
        raise _to_http(exc) from None
    entry = await service.entries.get(entry_id)
    assert entry is not None
    return PublicationActionResponse(
        entry_id=entry.id, public_id=entry.public_id, publication_status=status
    )


@admin_router.patch("/{entry_id}/archive", response_model=PublicationActionResponse)
async def admin_archive_entry(
    entry_id: UUID,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> PublicationActionResponse:
    service = KnowledgeService(db)
    try:
        await service.archive(entry_id, _admin.id)
    except AuthError as exc:
        raise _to_http(exc) from None
    entry = await service.entries.get(entry_id)
    assert entry is not None
    return PublicationActionResponse(
        entry_id=entry.id,
        public_id=entry.public_id,
        publication_status=entry.publication_status,
    )


@admin_router.patch("/{entry_id}/unarchive", response_model=PublicationActionResponse)
async def admin_unarchive_entry(
    entry_id: UUID,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> PublicationActionResponse:
    service = KnowledgeService(db)
    try:
        status = await service.unarchive(entry_id, _admin.id)
    except AuthError as exc:
        raise _to_http(exc) from None
    entry = await service.entries.get(entry_id)
    assert entry is not None
    return PublicationActionResponse(
        entry_id=entry.id, public_id=entry.public_id, publication_status=status
    )
