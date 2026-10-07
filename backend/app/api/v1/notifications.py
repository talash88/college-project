"""Step 11 notification APIs: users access ONLY their own notifications."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.notification import (
    MarkAllReadResponse,
    NotificationListResponse,
    NotificationResponse,
    UnreadCountResponse,
)
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationListResponse:
    service = NotificationService(db)
    items, total = await service.list_for_user(
        current_user.id, unread_only=unread_only, limit=limit, offset=offset
    )
    return NotificationListResponse(
        items=[NotificationResponse.model_validate(n) for n in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UnreadCountResponse:
    service = NotificationService(db)
    return UnreadCountResponse(unread_count=await service.unread_count(current_user.id))


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_read(
    notification_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationResponse:
    """Mark ONE own notification read. Another user's id → 404 (IDOR-safe)."""
    service = NotificationService(db)
    row = await service.repo.get_for_recipient(notification_id, current_user.id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    if row.read_at is None:
        row.read_at = datetime.now(UTC)
        await db.commit()
    return NotificationResponse.model_validate(row)


@router.post("/read-all", response_model=MarkAllReadResponse)
async def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MarkAllReadResponse:
    service = NotificationService(db)
    try:
        marked = await service.repo.mark_all_read(current_user.id)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Could not mark notifications read") from exc
    return MarkAllReadResponse(marked_read=marked)
