"""
通知邮件群发任务相关数据模型

包含两张表：
- notification_tasks: 群发任务主表（含进度统计、状态）
- notification_recipients: 收件人明细（每封邮件一条记录，含发送结果）

进度落 SQLite，服务重启后可扫描 status='running' 的任务标记为 interrupted。
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.database import Base


class NotificationTask(Base):
    """通知邮件群发任务表

    Attributes:
        task_id: 任务唯一 ID（UUID，主键）
        subject: 邮件主题
        body: 邮件正文
        filter_json: 收件人筛选条件 JSON（is_active / profile_completed / created_after）
        total: 收件人总数
        sent: 已成功发送数
        failed: 发送失败数
        status: 任务状态（pending/running/completed/interrupted/failed）
        created_at / updated_at: 通用时间戳
        started_at: 开始发送时间
        finished_at: 结束时间（完成或中断）
    """

    __tablename__ = "notification_tasks"

    task_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    subject = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    filter_json = Column(Text, nullable=True)  # JSON 字符串，存筛选快照
    total = Column(Integer, default=0, nullable=False)
    sent = Column(Integer, default=0, nullable=False)
    failed = Column(Integer, default=0, nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    # 关系
    recipients = relationship(
        "NotificationRecipient",
        back_populates="task",
        cascade="all, delete-orphan",
    )


class NotificationRecipient(Base):
    """通知邮件收件人明细表

    Attributes:
        id: 自增主键（SQLite INTEGER PK）
        task_id: 所属任务 ID（外键 → notification_tasks.task_id）
        user_id: 收件人用户 ID
        email: 收件人邮箱（冗余存，便于失败追溯）
        status: 单条发送状态（pending/sent/failed）
        error_msg: 失败原因（status=failed 时填）
        created_at: 记录创建时间
    """

    __tablename__ = "notification_recipients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(
        String(36),
        ForeignKey("notification_tasks.task_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(String(36), nullable=True)
    email = Column(String(255), nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    error_msg = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # 关系
    task = relationship("NotificationTask", back_populates="recipients")
