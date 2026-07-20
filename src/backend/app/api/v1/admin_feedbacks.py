"""
Admin 反馈管理 API

接口：
- GET  /admin/feedbacks                 反馈列表（分页 + 筛选 type/status）
- GET  /admin/feedbacks/{id}            反馈详情（含附件签名 URL；admin 查看时自动 received → in_progress）
- PATCH /admin/feedbacks/{id}/status    改状态（received/in_progress/done）
- POST /admin/feedbacks/{id}/reply      通过站内邮件服务回复用户

全部 is_super_admin 守卫。
改状态时同步发 feedback_status_changed 通知给用户。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.models.database import get_db
from app.schemas.feedback import (
    AdminFeedbackDetailOut,
    AdminFeedbackItem,
    AdminFeedbackListOut,
    FeedbackReply,
    FeedbackStatusUpdate,
)
from app.services import feedback_service
from app.utils.super_admin import is_super_admin_user


class StandardResponse(BaseModel):
    """统一响应"""

    code: int = 200
    message: str = "success"
    data: dict

router = APIRouter(prefix="/admin/feedbacks", tags=["Admin-Feedbacks"])


def _require_admin(user: Optional[dict]) -> None:
    if not is_super_admin_user(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅超级管理员可操作",
        )


@router.get("", response_model=StandardResponse)
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
    return StandardResponse(
        code=200,
        message="success",
        data=AdminFeedbackListOut(
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
        ).model_dump(),
    )


@router.get("/{feedback_id}", response_model=StandardResponse)
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

    # admin 点开查看即视为开始处理：received → in_progress（同步发站内信通知用户）
    if feedback.status == "received":
        feedback = await feedback_service.admin_update_status(
            db=db,
            feedback_id=feedback_id,
            new_status="in_progress",
            admin_user_id=current_user["user_id"],
        )
        await db.commit()

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

    return StandardResponse(
        code=200,
        message="success",
        data=AdminFeedbackDetailOut(
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
        ).model_dump(),
    )


@router.post("/{feedback_id}/reply", response_model=StandardResponse)
async def reply_feedback(
    feedback_id: str,
    payload: FeedbackReply,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """通过站内邮件服务（SMTP）回复反馈用户"""
    _require_admin(current_user)

    try:
        await feedback_service.admin_reply_feedback(
            db=db,
            feedback_id=feedback_id,
            content=payload.content,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=502, detail="邮件发送失败，请检查 SMTP 服务后重试")

    return StandardResponse(code=200, message="回复邮件已发送", data={})


@router.patch("/{feedback_id}/status", response_model=StandardResponse)
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
    return StandardResponse(
        code=200,
        message="状态更新成功",
        data=AdminFeedbackDetailOut(
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
        ).model_dump(),
    )
