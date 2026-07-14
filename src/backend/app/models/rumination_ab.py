"""
Rumination v3/v4 分组分配数据模型

一个 report_id 一条记录，首次进入 rumination 时写入，后续只读。
保证同一用户在同一 report 下看到的版本稳定（v3 或 v4）。

字段说明：
- version: 'v3' | 'v4'（该 report 应走的 rumination 版本）
- source: 'forced'（配置强制）| 'ab'（按比例随机分配）
- ratio_at_assignment: 分配时 RUMINATION_AB_V4_RATIO 的值（ab 模式留痕，便于事后回溯）
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
