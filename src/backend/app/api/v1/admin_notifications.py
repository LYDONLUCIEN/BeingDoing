"""
Admin 通知邮件群发 API

接口：
- POST /admin/notifications/email  创建群发任务，立即返回 task_id（后台异步发送）
- GET  /admin/notifications/email/{task_id}  查询进度
- GET  /admin/notifications/email  历史任务列表（分页）

全部 _is_super_admin 守卫。
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.v1.auth import get_current_user
from app.services.notification_service import NotificationService
from app.utils.super_admin import is_super_admin_user

router = APIRouter(prefix="/admin/notifications", tags=["Admin-Notifications"])


def _is_super_admin(user: Optional[dict]) -> bool:
    """超级管理员校验"""
    return is_super_admin_user(user)


class UserFilter(BaseModel):
    """收件人筛选条件

    所有字段可选，不传 = 不限。全选 = 全部留空。
    """

    is_active: Optional[bool] = Field(None, description="按用户是否活跃筛选（true 仅活跃用户）")
    profile_completed: Optional[bool] = Field(None, description="按 profile 是否完成筛选")
    created_after: Optional[str] = Field(
        None, description="注册时间下界，ISO 格式（如 2026-01-01）"
    )


class CreateNotificationRequest(BaseModel):
    """创建群发任务请求"""

    subject: str = Field(..., min_length=1, max_length=255, description="邮件主题")
    body: str = Field(..., min_length=1, description="邮件正文（纯文本）")
    user_filter: UserFilter = Field(default_factory=UserFilter, description="收件人筛选")


@router.post("/email")
async def create_notification_email(
    payload: CreateNotificationRequest,
    background_tasks: BackgroundTasks,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """创建通知邮件群发任务

    - 同步：建 task 记录 + 展开收件人列表落库
    - 异步：BackgroundTasks 调 run_batch 逐封发送
    - 立即返回 task_id，前端轮询 GET /{task_id}

    Returns:
        {task_id, total}
    """
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")

    user_filter_dict = payload.user_filter.model_dump(exclude_none=True)
    try:
        task_id = await NotificationService.create_task(
            subject=payload.subject,
            body=payload.body,
            user_filter=user_filter_dict,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 交给后台异步发送
    background_tasks.add_task(NotificationService.run_batch, task_id)

    return {"task_id": task_id}


@router.get("/email/{task_id}")
async def get_notification_status(
    task_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """查询单个群发任务的进度详情"""
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")

    status = await NotificationService.get_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="任务不存在")
    return status


@router.get("/email")
async def list_notification_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: Optional[dict] = Depends(get_current_user),
):
    """分页查询历史任务列表"""
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")

    return await NotificationService.list_tasks(page=page, page_size=page_size)
