"""
反馈与站内信相关的 Pydantic schema
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------- 反馈 ----------

class FeedbackCreate(BaseModel):
    # 注意：字段长度/类型校验放到 service 层，统一返回 400
    # （FastAPI schema 层校验会返回 422，跟项目错误响应风格不一致）
    type: str = Field(..., description="反馈类型：bug / idea")
    content: str = Field(..., description="反馈内容 5-2000 字")
    attachment_ids: List[str] = Field(
        default_factory=list, description="已上传的附件 ID，最多 3 个"
    )


class FeedbackAttachmentOut(BaseModel):
    id: str
    preview_url: str
    size_bytes: int
    content_type: str


class FeedbackOut(BaseModel):
    id: str
    type: str
    content: str
    status: str
    created_at: datetime
    due_at: Optional[datetime] = None


class AttachmentUploadOut(BaseModel):
    id: str
    preview_url: str
    size_bytes: int
    content_type: str


# ---------- 通知 ----------

class NotificationOut(BaseModel):
    id: str
    type: str
    title: str
    content: str
    read_at: Optional[datetime]
    related_feedback_id: Optional[str]
    created_at: datetime


class NotificationListOut(BaseModel):
    items: List[NotificationOut]
    total: int
    page: int
    page_size: int
    unread_count: int


class UnreadCountOut(BaseModel):
    count: int


# ---------- 管理员侧 ----------

class AdminFeedbackItem(BaseModel):
    id: str
    user_id: str
    user_email: str
    username: Optional[str]
    type: str
    content: str
    status: str
    attachments_count: int
    created_at: datetime
    updated_at: datetime
    due_at: Optional[datetime] = None
    assignee_id: Optional[str] = None
    assignee_email: Optional[str] = None


class AdminFeedbackListOut(BaseModel):
    items: List[AdminFeedbackItem]
    total: int
    page: int
    page_size: int


class AdminFeedbackDetailOut(BaseModel):
    id: str
    user_id: str
    user_email: str
    username: Optional[str]
    type: str
    content: str
    status: str
    created_at: datetime
    updated_at: datetime
    due_at: Optional[datetime] = None
    assignee_id: Optional[str] = None
    assignee_email: Optional[str] = None
    attachments: List[dict]  # [{"id": ..., "signed_url": ..., "size_bytes": ..., "content_type": ...}]


class FeedbackStatusUpdate(BaseModel):
    status: str = Field(..., description="received / in_progress / done")


class FeedbackAssigneeUpdate(BaseModel):
    assignee_id: Optional[str] = Field(
        None, description="处理人 user_id（必须是 super_admin）；null 表示清除"
    )


class AdminAssigneeOut(BaseModel):
    user_id: str
    email: str


class FeedbackReply(BaseModel):
    # 长度校验放 service 层，统一返回 400
    content: str = Field(..., description="回复正文，将通过站内邮件服务发送给用户")
