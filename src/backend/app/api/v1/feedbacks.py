"""
用户侧反馈 API

- POST /feedbacks                    提交反馈
- POST /feedbacks/attachments        上传截图（孤儿模式）
- DELETE /feedbacks/attachments/{id} 删除截图（未关联的才能删）
"""
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.models.database import get_db
from app.schemas.feedback import (
    AttachmentUploadOut,
    FeedbackCreate,
    FeedbackOut,
)
from app.services import feedback_service


class StandardResponse(BaseModel):
    """统一响应"""

    code: int = 200
    message: str = "success"
    data: dict

router = APIRouter(prefix="/feedbacks", tags=["用户反馈"])


@router.post("", response_model=StandardResponse, status_code=status.HTTP_201_CREATED)
async def create_feedback(
    payload: FeedbackCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """提交反馈"""
    user_id = current_user["user_id"]
    user_email = current_user.get("email") or ""

    try:
        feedback = await feedback_service.create_feedback(
            db=db,
            user_id=user_id,
            user_email=user_email,
            type_=payload.type,
            content=payload.content,
            attachment_ids=payload.attachment_ids,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await db.commit()
    return StandardResponse(
        code=201,
        message="反馈提交成功",
        data=FeedbackOut(
            id=feedback.id,
            type=feedback.type,
            content=feedback.content,
            status=feedback.status,
            created_at=feedback.created_at,
        ).model_dump(),
    )


@router.post(
    "/attachments",
    response_model=StandardResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传截图（孤儿模式，未关联到任何反馈）"""
    user_id = current_user["user_id"]

    # 校验 content_type
    ct = (file.content_type or "").lower()
    file_bytes = await file.read()
    size = len(file_bytes)

    try:
        att = await feedback_service.upload_attachment(
            db=db,
            user_id=user_id,
            file_data=file_bytes,
            content_type=ct,
            size_bytes=size,
        )
        signed_url = await feedback_service.get_attachment_signed_url(att)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    await db.commit()
    return StandardResponse(
        code=201,
        message="上传成功",
        data=AttachmentUploadOut(
            id=att.id,
            preview_url=signed_url,
            size_bytes=att.size_bytes,
            content_type=att.content_type,
        ).model_dump(),
    )


@router.delete(
    "/attachments/{attachment_id}", response_model=StandardResponse
)
async def delete_attachment(
    attachment_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除截图（只能删自己的 + 未关联反馈的）"""
    user_id = current_user["user_id"]
    try:
        await feedback_service.delete_attachment(db, user_id, attachment_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await db.commit()
    return StandardResponse(code=200, message="删除成功", data={})
