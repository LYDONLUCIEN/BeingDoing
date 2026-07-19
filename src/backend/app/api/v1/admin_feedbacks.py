"""
Admin 反馈管理 API

接口：
- GET  /admin/feedbacks                 反馈列表（分页 + 筛选 type/status）
- GET  /admin/feedbacks/{id}            反馈详情（含附件签名 URL）
- PATCH /admin/feedbacks/{id}/status    改状态（received/in_progress/done）

全部 is_super_admin 守卫。
改状态时同步发 feedback_status_changed 通知给用户。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.models.database import get_db
from app.schemas.feedback import (
    AdminFeedbackDetailOut,
    AdminFeedbackItem,
    AdminFeedbackListOut,
    FeedbackStatusUpdate,
)
from app.services import feedback_service
from app.utils.super_admin import is_super_admin_user

router = APIRouter(prefix="/admin/feedbacks", tags=["Admin-Feedbacks"])


def _require_admin(user: Optional[dict]) -> None:
    if not is_super_admin_user(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅超级管理员可操作",
        )


@router.get("", response_model=AdminFeedbackListOut)
async def list_feedbacks(
    type: Optional[str] = Query(None, description="bug / idea"),
    status_: Optional[str] = Query(None, description="received / in_progress / done", alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """管理员反馈列表"""
    _require_admin(current_user)

    if type and type not in {"bug", "idea"}:
        raise HTTPException(status_code=400, detail="type 必须是 bug 或 idea")
    if status_ and status_ not in {"received", "in_progress", "done"}:
        raise HTTPException(status_code=400, detail="status 无效")

    items, total = await feedback_service.admin_list_feedbacks(
        db=db,
        type_=type,
        status_=status_,
        page=page,
        page_size=page_size,
    )
    return AdminFeedbackListOut(
        items=[
            AdminFeedbackItem(
                id=f.id,
                user_id=f.user_id,
                user_email=f.user_email,
                username=None,  # 简化：不做 join，admin 看到 email 就够
                type=f.type,
                content=f.content,
                status=f.status,
                attachments_count=0,  # 列表页不查附件数，避免 N+1
                created_at=f.created_at,
                updated_at=f.updated_at,
            )
            for f in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{feedback_id}", response_model=AdminFeedbackDetailOut)
async def get_feedback_detail(
    feedback_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """管理员拉反馈详情（含附件签名 URL）"""
    _require_admin(current_user)

    result = await feedback_service.admin_get_feedback_detail(db, feedback_id)
    if result is None:
        raise HTTPException(status_code=404, detail="反馈不存在")
    feedback, attachments = result

    # 给每个附件生成签名 URL
    attachments_out = []
    for att in attachments:
        try:
            signed_url = await feedback_service.get_attachment_signed_url(att)
        except Exception:
            signed_url = ""  # OSS 异常时不阻塞详情，前端显示「图片加载失败」
        attachments_out.append(
            {
                "id": att.id,
                "signed_url": signed_url,
                "size_bytes": att.size_bytes,
                "content_type": att.content_type,
            }
        )

    return AdminFeedbackDetailOut(
        id=feedback.id,
        user_id=feedback.user_id,
        user_email=feedback.user_email,
        username=None,
        type=feedback.type,
        content=feedback.content,
        status=feedback.status,
        created_at=feedback.created_at,
        updated_at=feedback.updated_at,
        attachments=attachments_out,
    )


@router.patch("/{feedback_id}/status", response_model=AdminFeedbackDetailOut)
async def update_feedback_status(
    feedback_id: str,
    payload: FeedbackStatusUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """改状态（同步发通知给用户）"""
    _require_admin(current_user)

    try:
        feedback = await feedback_service.admin_update_status(
            db=db,
            feedback_id=feedback_id,
            new_status=payload.status,
            admin_user_id=current_user["user_id"],
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await db.commit()

    # 返回更新后的详情（不含附件，简化）
    return AdminFeedbackDetailOut(
        id=feedback.id,
        user_id=feedback.user_id,
        user_email=feedback.user_email,
        username=None,
        type=feedback.type,
        content=feedback.content,
        status=feedback.status,
        created_at=feedback.created_at,
        updated_at=feedback.updated_at,
        attachments=[],
    )
