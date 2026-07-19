"""
用户侧站内信（通知）API

- GET  /notifications/unread_count            未读数（页面刷新调）
- GET  /notifications                          通知列表（分页）
- POST /notifications/{id}/read                标记单条已读
- POST /notifications/read_all                 全部已读
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.models.database import get_db
from app.schemas.feedback import (
    NotificationListOut,
    NotificationOut,
    UnreadCountOut,
)
from app.services import feedback_service

router = APIRouter(prefix="/notifications", tags=["站内信"])


@router.get("/unread_count", response_model=UnreadCountOut)
async def unread_count(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count = await feedback_service.get_unread_count(db, current_user["user_id"])
    return UnreadCountOut(count=count)


@router.get("", response_model=NotificationListOut)
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total, unread_count = await feedback_service.list_notifications(
        db=db,
        user_id=current_user["user_id"],
        page=page,
        page_size=page_size,
        unread_only=unread_only,
    )
    return NotificationListOut(
        items=[
            NotificationOut(
                id=n.id,
                type=n.type,
                title=n.title,
                content=n.content,
                read_at=n.read_at,
                related_feedback_id=n.related_feedback_id,
                created_at=n.created_at,
            )
            for n in items
        ],
        total=total,
        page=page,
        page_size=page_size,
        unread_count=unread_count,
    )


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await feedback_service.mark_read(db, current_user["user_id"], notification_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return None


@router.post("/read_all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await feedback_service.mark_all_read(db, current_user["user_id"])
    await db.commit()
    return None
