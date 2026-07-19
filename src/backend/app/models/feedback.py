"""
反馈与站内信相关模型

包含三张表：
- Feedback：用户提交的反馈（bug/产品想法）
- FeedbackAttachment：反馈截图（OSS 对象元信息）
- Notification：站内信（用户↔管理员双向通知）

注意：与现有 notification.py 中的 NotificationTask/NotificationRecipient（邮件群发任务）
是不同的东西，不要混淆。
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text

from app.models.database import Base


class Feedback(Base):
    """用户提交的反馈（主楼）"""
    __tablename__ = "feedbacks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # 冗余快取，admin 后台直接显示，不用 join users 表
    user_email = Column(String(255), nullable=False)
    type = Column(String(20), nullable=False)  # bug / idea
    content = Column(Text, nullable=False)     # 5~2000 字
    status = Column(String(20), default="received", nullable=False)
    # received → in_progress → done（admin 手动改）

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        # 用户看自己历史 / admin 列表筛选
        Index("ix_feedbacks_user_id_created_at", "user_id", "created_at"),
        Index("ix_feedbacks_status_updated_at", "status", "updated_at"),
    )


class FeedbackAttachment(Base):
    """反馈截图（OSS 对象元信息，不存图片本身）"""
    __tablename__ = "feedback_attachments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # 孤儿模式：用户先传图，feedback_id 暂为 NULL；提交反馈时回填
    feedback_id = Column(
        String(36),
        ForeignKey("feedbacks.id", ondelete="CASCADE"),
        nullable=True,
    )
    uploader_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # OSS 对象 key，如 feedbacks/temp/2026/07/16/uuid.png
    oss_key = Column(String(255), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    # image/jpeg | image/png | image/webp
    content_type = Column(String(50), nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_feedback_attachments_feedback_id", "feedback_id"),
        # 孤儿清理用：按上传人和时间筛选
        Index(
            "ix_feedback_attachments_uploader_created",
            "uploader_user_id",
            "created_at",
        ),
    )


class Notification(Base):
    """
    站内信（通知，双向）

    收件人 user_id 既可以是普通用户，也可以是 admin（每个 super_admin 各一条）。
    type 区分通知类型，related_feedback_id 关联到触发源（可空）。
    """
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    type = Column(String(30), nullable=False)
    # feedback_auto_ack / feedback_new / feedback_status_changed / announcement
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    # NULL = 未读；非空 = 已读时间
    read_at = Column(DateTime, nullable=True)
    related_feedback_id = Column(
        String(36),
        ForeignKey("feedbacks.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        # 用户拉列表 + 未读查询用
        Index("ix_notifications_user_id_created_at", "user_id", "created_at"),
        Index("ix_notifications_user_id_read_at", "user_id", "read_at"),
    )
