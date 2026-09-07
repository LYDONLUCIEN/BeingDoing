"""
报告阻塞式审核（ADR-0009）纯逻辑模块

常量直接定义在本模块（不进 settings.py，避免并行改动冲突）：
- AUTO_APPROVE_HOURS：审核固定时限（2026-09-06 起由随机 3~24h 改为统一固定 24h）
- REVIEW_SCAN_INTERVAL_MINUTES：自动批复扫描周期
- PREGEN_RETRY_MAX / PREGEN_RETRY_INTERVAL_HOURS：审核期报告预生成看门狗
  （缓存缺失且无人生成时自动重试，每小时一次、上限 3 次，保证 24h 解锁时报告已就绪）

字段落在 data/simple/reports/{report_id}/record.json：
- review_status: not_started / pending_review / approved
  （缺失 = 存量报告，祖父豁免视为 approved）
- review_deadline: ISO 截止时间（仅 pending 时有意义）
- review_type: manual / auto / None
- reviewed_by / reviewed_at: 批复人与批复时间
- pregen_retry_count / pregen_last_retry_at: 看门狗重试计数与上次重试时间（可选，缺失按 0/None）

生命周期（2026-08-23 修订，计时锚点前移）：
- 新建 record（激活/首次会话）→ not_started，不计时
- rumination v4 终选提交成功（五阶段完成）→ pending_review + 固定 24h 时限（计时起点）；
  用户进报告页（my-report-id / 审核阻塞兜底）的懒触发保留，覆盖存量 not_started
- admin 人工批复 / 超时自动批复 → approved

注意（ADR-0009 后果）：auto 批复是「善意伪装」的兜底，用户侧文案一律
「管理员审核通过」，不暴露自动事实。未来读者不要当成 bug 修掉。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── 审核常量（禁令：不写进 settings.py） ─────────────────────
AUTO_APPROVE_HOURS = 24  # 固定审核时限（2026-09-06 起，原随机 3~24h）
REVIEW_SCAN_INTERVAL_MINUTES = 10
# 审核期报告预生成看门狗：缓存缺失时自动重试，每小时一次、上限 3 次
PREGEN_RETRY_MAX = 3
PREGEN_RETRY_INTERVAL_HOURS = 1

REVIEW_STATUS_NOT_STARTED = "not_started"
REVIEW_STATUS_PENDING = "pending_review"
REVIEW_STATUS_APPROVED = "approved"

REVIEW_TYPE_MANUAL = "manual"
REVIEW_TYPE_AUTO = "auto"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def mark_review_not_started(record: dict) -> dict:
    """
    生成钩子：新建 record 时写入 not_started（不计时）。
    审核计时直到「用户进入报告页且五阶段完成」才开始（start_review）。
    存量记录不要调用（无字段 = 祖父豁免视为 approved）。
    """
    record["review_status"] = REVIEW_STATUS_NOT_STARTED
    record["review_deadline"] = None
    record["review_type"] = None
    record["reviewed_by"] = None
    record["reviewed_at"] = None
    return record


def start_review(record: dict, now: Optional[datetime] = None) -> dict:
    """
    审核计时起点：not_started → pending_review + 固定 24h 时限（2026-09-06 起，原随机 3~24h）。
    主触发点为 rumination v4 终选提交（2026-08-23 起）；
    报告页入口（my-report-id / 审核阻塞兜底）为存量懒触发兜底。
    """
    ts = now or _utcnow()
    deadline = ts + timedelta(hours=AUTO_APPROVE_HOURS)
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


def is_not_started(record: Optional[dict]) -> bool:
    """审核尚未开始（新建报告未进入报告页）。存量无字段 → False（祖父豁免）。"""
    if not record:
        return False
    return (record.get("review_status") or "").strip() == REVIEW_STATUS_NOT_STARTED


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
