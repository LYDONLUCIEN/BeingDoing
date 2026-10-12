"""历史沉淀 A/B 分配表映射（实验已退役）。

保留用于读取历史记录、账户删除及迁移链兼容；运行时不再分配或覆盖记录。
version/source/ratio_at_assignment 仅说明当时的实验分组，不决定当前路由。
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, String

from app.models.database import Base


def _new_id() -> str:
    return uuid.uuid4().hex


class RuminationAbAssignment(Base):
    """Rumination v3/v4 分组分配记录

    Attributes:
        id: uuid hex 主键
        report_id: 报告 ID（唯一，一个 report 只分配一次）
        user_id: 用户 ID（冗余，便于按用户聚合统计）
        version: 'v3' | 'v4'
        source: 'forced' | 'ab'
        ratio_at_assignment: 分配时的 v4 比例配置值
        created_at / updated_at: 通用时间戳
    """

    __tablename__ = "rumination_ab_assignments"

    id = Column(String(32), primary_key=True, default=_new_id)
    report_id = Column(String(64), nullable=False, unique=True, index=True)
    user_id = Column(String(64), nullable=True, index=True)
    version = Column(String(4), nullable=False)
    source = Column(String(8), nullable=False)
    ratio_at_assignment = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
