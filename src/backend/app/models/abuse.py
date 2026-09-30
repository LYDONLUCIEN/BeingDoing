"""
用户滥用检测模型（滥用事件流水 + 滥用处置状态机）

- AbuseEvent：用户行为事件流水（发消息 / 删对话），供硬阈值窗口聚合
- AbuseState：用户处置状态机（warned → frozen），由 admin 裁决恢复（删行即 normal）

口径：
- 任一规则首次触发 → warned（响应 429 + 站内信 + 邮件）；
- warned 之后再次触发任一规则 → frozen（403 + revoke 激活码 + 通知超管）；
- created_at 统一存 UTC naive datetime，窗口聚合直接用 SQL 比较。
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.models.database import Base


def _utcnow() -> datetime:
    """UTC naive 时间（与窗口聚合的 SQL 比较口径一致）"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AbuseEvent(Base):
    """用户行为事件流水（滥用检测的原始数据）"""

    __tablename__ = "abuse_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), nullable=False, index=True)
    event_type = Column(String(30), nullable=False)  # message / thread_delete
    phase = Column(String(30), nullable=True)  # 触发时所在阶段（thread_delete 必填）
    detail = Column(Text, nullable=True)  # JSON 字符串，附加信息
    created_at = Column(DateTime, default=_utcnow, index=True)


class AbuseState(Base):
    """用户滥用处置状态（warned / frozen；无行 = 正常）"""

    __tablename__ = "abuse_states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), unique=True, nullable=False, index=True)
    status = Column(String(20), nullable=False)  # warned / frozen
    warned_at = Column(DateTime, nullable=True)
    warned_rule = Column(String(50), nullable=True)  # 首次触发的规则名
    frozen_at = Column(DateTime, nullable=True)
    frozen_rule = Column(String(50), nullable=True)  # 触发冻结的规则名
    frozen_activation_code = Column(String(64), nullable=True)  # 被 revoke 的激活码
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
