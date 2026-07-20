"""
报告阻塞式审核服务（ADR-0009）

- approve_report：人工/自动批复共用入口（幂等：已 approved 不重复写、不重复通知）
- notify_report_approved：站内信通知（复用 notifications 表，幂等）
- auto_approve_overdue：APScheduler 周期任务，超时 pending → auto 批复

文案注意：auto 批复的用户侧文案与人工一致（「您的报告已审核通过」），
不暴露自动事实——这是 ADR-0009 的刻意决策，勿当 bug 修复。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feedback import Notification
from app.utils.report_registry import ReportRegistry
from app.utils.report_review import (
    REVIEW_STATUS_APPROVED,
    REVIEW_TYPE_AUTO,
    get_review_status,
    is_pending_review,
    is_review_overdue,
)

logger = logging.getLogger(__name__)

NOTIFICATION_TYPE = "report_approved"
NOTIFICATION_TITLE = "报告审核通过"
# 报告入口链接（前端 explore/report/view 页）
REPORT_ENTRY_PATH = "/explore/report/view"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_approved_notification_content(report_id: str) -> str:
    """人工/自动批复同一文案（ADR-0009：用户只感知「管理员审核通过」）。"""
    return (
        "您的报告已审核通过，点击查看完整报告："
        f"{REPORT_ENTRY_PATH}\n报告编号：{report_id}"
    )


async def notify_report_approved(
    db: AsyncSession, user_id: str, report_id: str
) -> bool:
    """
    给用户发「报告已审核通过」站内信（复用 notifications 表）。

    幂等：同一 (user_id, report_id) 已存在 report_approved 通知则不重复发。
    Returns: True = 新建了通知；False = 已存在跳过。
    """
    uid = (user_id or "").strip()
    rid = (report_id or "").strip()
    if not uid or not rid:
        logger.warning("报告批复通知缺少 user_id/report_id，跳过: user_id=%r report_id=%r", user_id, report_id)
        return False

    existing = (
        await db.execute(
            select(Notification).where(
                Notification.user_id == uid,
                Notification.type == NOTIFICATION_TYPE,
                Notification.content.like(f"%{rid}%"),
            )
        )
    ).scalars().first()
    if existing is not None:
        return False

    db.add(
        Notification(
            user_id=uid,
            type=NOTIFICATION_TYPE,
            title=NOTIFICATION_TITLE,
            content=build_approved_notification_content(rid),
            read_at=None,
            related_feedback_id=None,
        )
    )
    await db.flush()
    return True


async def approve_report(
    registry: ReportRegistry,
    report_id: str,
    *,
    review_type: str,
    reviewed_by: Optional[str],
    db: Optional[AsyncSession] = None,
) -> Optional[dict]:
    """
    批复报告（人工 manual / 自动 auto 共用）。

    幂等：已 approved 的记录直接返回，不重复写字段、不重复发通知。
    Returns: 更新后的 record；report 不存在返回 None。
    """
    record = registry.get_report_by_id(report_id)
    if record is None:
        return None
    if get_review_status(record) == REVIEW_STATUS_APPROVED:
        return record  # 幂等

    record["review_status"] = REVIEW_STATUS_APPROVED
    record["review_type"] = review_type
    record["reviewed_by"] = reviewed_by
    record["reviewed_at"] = _now_iso()
    registry.save_record(record)

    if db is not None:
        await notify_report_approved(db, record.get("user_id") or "", report_id)
    return record


async def auto_approve_overdue(
    base_dir: Optional[str] = None,
    session_factory=None,
) -> int:
    """
    自动批复任务（APScheduler 每 REVIEW_SCAN_INTERVAL_MINUTES 分钟调用）：

    扫描全部 record.json，pending_review 且已过 deadline → approved + review_type=auto，
    并触发站内信（与人工批复同一通知函数、同一文案）。单条失败不影响其余。

    Returns: 本次批复的报告数。
    """
    if session_factory is None:
        from app.models.database import AsyncSessionLocal

        session_factory = AsyncSessionLocal

    registry = ReportRegistry(base_dir=base_dir) if base_dir else ReportRegistry()
    approved_count = 0
    async with session_factory() as db:
        for record in registry.list_reports():
            rid = (record.get("report_id") or "").strip()
            if not rid or not is_pending_review(record) or not is_review_overdue(record):
                continue
            try:
                updated = await approve_report(
                    registry,
                    rid,
                    review_type=REVIEW_TYPE_AUTO,
                    reviewed_by=None,
                    db=db,
                )
                await db.commit()
                if updated is not None:
                    approved_count += 1
                    logger.info("报告超时自动批复: report_id=%s", rid)
            except Exception as e:  # 单条失败不影响其余
                await db.rollback()
                logger.exception("报告自动批复失败: report_id=%s error=%s", rid, e)
    return approved_count
