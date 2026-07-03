"""
邮箱退信黑名单数据模型

记录已知不可达邮箱，群发时按 status='blocked' 过滤。
来源：
- auto: BounceScanner 扫描退信邮件自动添加
- manual: admin 手动添加（直接拉黑）

字段说明：
- bounce_type: hard（550 用户不存在，永久）| soft（邮箱满/临时不可达，可恢复）
- status: blocked（拉黑，群发跳过）| unblocked（解封，记录保留供审计）
- bounce_count: 累计退信次数（auto 扫到同一邮箱多次会累加）
- source: auto | manual
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.models.database import Base


class EmailBounce(Base):
    """邮箱退信黑名单表

    Attributes:
        email: 邮箱地址（小写 normalized，主键）
        bounce_type: hard | soft
        status: blocked | unblocked
        bounce_count: 累计退信次数
        last_bounce_at: 最近一次退信时间
        reason: 退信原文摘要 / 手动添加时的备注
        source: auto（扫描自动）| manual（手动添加）
        notes: 备注字段（手动添加可填）
        created_at / updated_at: 通用时间戳
    """

    __tablename__ = "email_bounces"

    email = Column(String(255), primary_key=True)
    bounce_type = Column(String(10), default="hard", nullable=False)
    status = Column(String(20), default="blocked", nullable=False)
    bounce_count = Column(Integer, default=1, nullable=False)
    last_bounce_at = Column(DateTime, nullable=True)
    reason = Column(Text, nullable=True)
    source = Column(String(20), default="auto", nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
