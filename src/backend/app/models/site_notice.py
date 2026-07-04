"""
站内公告数据模型

存储站内通知（banner / modal / popup / announcement 等）。
当前主要用于：
- 维护计划 banner：升级前 24~48 小时挂顶部窄条，点击「了解更多」弹 Modal

字段说明：
- type: banner | modal | popup | announcement（预留扩展，目前只用 banner）
- severity: info | warn | urgent（决定窄条配色）
- start_at / end_at: 生效时间窗口；当前时间落在此区间内才显示
- dismissible: 是否允许用户关闭（关闭后 localStorage 记 notice.id + updated_at，版本变再弹）
- is_active: 软开关，运营可临时下线某条通知
- channels_json: 多渠道入口，JSON 字符串，形如
    [{"type":"wechat","qr_url":"https://img.../qr.png"},
     {"type":"blog","url":"https://..."},
     {"type":"xiaohongshu","url":"https://..."}]
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Text, Boolean

from app.models.database import Base


def _new_id() -> str:
    return uuid.uuid4().hex


class SiteNotice(Base):
    """站内公告表

    Attributes:
        id: uuid hex 主键
        type: banner | modal | popup | announcement
        title: 窄条上显示的一行标题（≤120 字）
        content_md: Modal 正文，markdown
        severity: info | warn | urgent
        start_at / end_at: 生效时间窗口（UTC aware）
        dismissible: 是否允许用户关闭
        is_active: 是否启用
        channels_json: 多渠道入口 JSON 字符串
        created_at / updated_at: 通用时间戳
    """

    __tablename__ = "site_notices"

    id = Column(String(32), primary_key=True, default=_new_id)
    type = Column(String(20), default="banner", nullable=False)
    title = Column(String(120), nullable=False)
    content_md = Column(Text, nullable=True)
    severity = Column(String(10), default="info", nullable=False)
    start_at = Column(DateTime, nullable=True)
    end_at = Column(DateTime, nullable=True)
    dismissible = Column(Boolean, default=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    channels_json = Column(Text, nullable=True)  # JSON 字符串
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
