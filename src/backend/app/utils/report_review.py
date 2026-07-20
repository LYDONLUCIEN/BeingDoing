"""
报告阻塞式审核（ADR-0009）纯逻辑模块

常量直接定义在本模块（不进 settings.py，避免并行改动冲突）：
- AUTO_APPROVE_MIN_HOURS / AUTO_APPROVE_MAX_HOURS：生成时随机审核时限区间
- REVIEW_SCAN_INTERVAL_MINUTES：自动批复扫描周期

字段落在 data/simple/reports/{report_id}/record.json：
- review_status: pending_review / approved（缺失 = 存量报告，祖父豁免视为 approved）
- review_deadline: ISO 截止时间（仅 pending 时有意义）
- review_type: manual / auto / None
- reviewed_by / reviewed_at: 批复人与批复时间

注意（ADR-0009 后果）：auto 批复是「善意伪装」的兜底，用户侧文案一律
「管理员审核通过」，不暴露自动事实。未来读者不要当成 bug 修掉。
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── 审核常量（禁令：不写进 settings.py） ─────────────────────
AUTO_APPROVE_MIN_HOURS = 3
AUTO_APPROVE_MAX_HOURS = 24
REVIEW_SCAN_INTERVAL_MINUTES = 10

REVIEW_STATUS_PENDING = "pending_review"
REVIEW_STATUS_APPROVED = "approved"

REVIEW_TYPE_MANUAL = "manual"
REVIEW_TYPE_AUTO = "auto"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def init_review_fields(record: dict, now: Optional[datetime] = None) -> dict:
    """
    生成钩子：为新报告写入审核字段（pending_review + 随机 3~24h 时限）。
    仅在新建 record 时调用；存量记录不要调用（祖父豁免）。
    """
    ts = now or _utcnow()
    deadline = ts + timedelta(hours=random.uniform(AUTO_APPROVE_MIN_HOURS, AUTO_APPROVE_MAX_HOURS))
    record["review_status"] = REVIEW_STATUS_PENDING
    record["review_deadline"] = deadline.isoformat()
    record["review_type"] = None
    record["reviewed_by"] = None
    record["reviewed_at"] = None
    return record


def get_review_status(record: Optional[dict]) -> str:
    """审核状态；存量报告无字段 → approved（祖父豁免）。"""
    if not record:
        return REVIEW_STATUS_APPROVED
    status = (record.get("review_status") or "").strip()
    return status or REVIEW_STATUS_APPROVED


def is_pending_review(record: Optional[dict]) -> bool:
    return get_review_status(record) == REVIEW_STATUS_PENDING


def parse_review_deadline(record: dict) -> Optional[datetime]:
    """解析 review_deadline 为 tz-aware datetime；失败返回 None。"""
    raw = (record.get("review_deadline") or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def is_review_overdue(record: dict, now: Optional[datetime] = None) -> bool:
    """
    pending 且已过 deadline → True。
    deadline 缺失/无法解析时按过期处理（避免报告永久卡死在审核中）。
    """
    if not is_pending_review(record):
        return False
    deadline = parse_review_deadline(record)
    if deadline is None:
        logger.warning(
            "report %s 处于 pending_review 但 review_deadline 缺失/非法，按过期处理",
            record.get("report_id"),
        )
        return True
    return (now or _utcnow()) >= deadline


def pending_review_payload(record: dict) -> dict:
    """用户侧阻塞响应 payload（HTTP 200，由前端展示「审核中」）。"""
    return {
        "review_status": REVIEW_STATUS_PENDING,
        "review_deadline": record.get("review_deadline"),
    }
