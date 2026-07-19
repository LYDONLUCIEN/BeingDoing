"""
反馈附件孤儿清理任务

场景：用户在浮窗上传了截图，但最终没提交反馈（关掉浏览器、网络断了）。
这些附件 feedback_id IS NULL，占用 OSS 存储。

定时清理：超过 FEEDBACK_ORPHAN_CLEANUP_DAYS 天未关联反馈的，从 DB 和 OSS 都删。
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config.settings import settings
from app.core.storage import get_storage
from app.models.database import AsyncSessionLocal
from app.models.feedback import FeedbackAttachment

logger = logging.getLogger(__name__)


async def cleanup_orphan_attachments() -> dict:
    """
    清理孤儿附件。

    Returns:
        {"scanned": N, "deleted_db": N, "deleted_oss_ok": N, "deleted_oss_fail": N}
    """
    cutoff = datetime.now(timezone.utc) - timedelta(
        days=settings.FEEDBACK_ORPHAN_CLEANUP_DAYS
    )
    storage = get_storage()

    stats = {"scanned": 0, "deleted_db": 0, "deleted_oss_ok": 0, "deleted_oss_fail": 0}

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(FeedbackAttachment).where(
                FeedbackAttachment.feedback_id.is_(None),
                FeedbackAttachment.created_at < cutoff,
            )
        )
        orphans = list(result.scalars().all())
        stats["scanned"] = len(orphans)

        if not orphans:
            logger.info("orphan cleanup: no orphans found")
            return stats

        for att in orphans:
            # 先删 OSS（失败不阻塞 DB 删除，下次再清）
            if storage is not None:
                try:
                    await storage.delete(att.oss_key)
                    stats["deleted_oss_ok"] += 1
                except Exception as e:
                    stats["deleted_oss_fail"] += 1
                    logger.warning(
                        "orphan cleanup: OSS delete failed for key=%s: %s",
                        att.oss_key,
                        e,
                    )

            await db.delete(att)
            stats["deleted_db"] += 1

        await db.commit()

    logger.info(
        "orphan cleanup done: scanned=%s deleted_db=%s oss_ok=%s oss_fail=%s",
        stats["scanned"], stats["deleted_db"],
        stats["deleted_oss_ok"], stats["deleted_oss_fail"],
    )
    return stats
