"""
反馈超时扫描任务

每天定时扫描「已过承诺时限（due_at）且未完结（status != done）」的反馈，
给所有 super_admin 发站内信提醒（feedback_overdue）。

幂等：同一条反馈同一天（北京时间）只提醒一次——以当天是否已存在
feedback_overdue 通知为准，避免服务重启/补跑造成刷屏。

存量老反馈 due_at IS NULL，不参与扫描。
"""
import logging
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import func, select

from app.models.database import AsyncSessionLocal
from app.models.feedback import Feedback, Notification
from app.services.feedback_service import (
    OVERDUE_TITLE_FOR_ADMIN,
    SHANGHAI_TZ,
    _get_super_admin_ids,
    as_utc,
)

logger = logging.getLogger(__name__)


async def scan_overdue_feedbacks() -> dict:
    """
    扫描超时反馈并通知所有 super_admin。

    Returns:
        {"overdue": N, "notified": M, "skipped_already_notified": K}
    """
    now = datetime.now(timezone.utc)
    # 北京时间今天 00:00（转 UTC），用于「今天是否已提醒过」的幂等判断
    today_start = datetime.combine(
        now.astimezone(SHANGHAI_TZ).date(), time(0, 0, 0), tzinfo=SHANGHAI_TZ
    ).astimezone(timezone.utc)

    stats = {"overdue": 0, "notified": 0, "skipped_already_notified": 0}

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Feedback).where(
                Feedback.due_at.isnot(None),
                Feedback.status != "done",
                Feedback.due_at < now.replace(tzinfo=None),
            )
        )
        overdue_items = list(result.scalars().all())
        stats["overdue"] = len(overdue_items)

        if not overdue_items:
            logger.info("feedback overdue scan: no overdue feedback")
            return stats

        admin_ids = await _get_super_admin_ids(db)
        if not admin_ids:
            logger.warning("feedback overdue scan: no super_admin found, skip notify")
            return stats

        for f in overdue_items:
            # 幂等：今天（北京时间）已提醒过该反馈则跳过
            exists_q = await db.execute(
                select(func.count(Notification.id)).where(
                    Notification.type == "feedback_overdue",
                    Notification.related_feedback_id == f.id,
                    Notification.created_at >= today_start,
                )
            )
            if int(exists_q.scalar_one()) > 0:
                stats["skipped_already_notified"] += 1
                continue

            due_local = as_utc(f.due_at).astimezone(SHANGHAI_TZ)
            preview = f.content if len(f.content) <= 60 else f.content[:60] + "…"
            content = (
                f"来自 {f.user_email} 的反馈已超过承诺处理时限"
                f"（截止 {due_local.month} 月 {due_local.day} 日）：\n\n"
                f"{preview}\n\n请尽快在 admin 后台处理并回复用户。"
            )
            for admin_id in admin_ids:
                if admin_id == f.user_id:
                    continue
                db.add(
                    Notification(
                        user_id=admin_id,
                        type="feedback_overdue",
                        title=OVERDUE_TITLE_FOR_ADMIN,
                        content=content,
                        read_at=None,
                        related_feedback_id=f.id,
                    )
                )
            stats["notified"] += 1

        await db.commit()

    logger.info(
        "feedback overdue scan done: overdue=%s notified=%s skipped=%s",
        stats["overdue"], stats["notified"], stats["skipped_already_notified"],
    )
    return stats
