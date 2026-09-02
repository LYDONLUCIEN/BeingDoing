"""
报告阻塞式审核服务（ADR-0009）

- approve_report：人工/自动批复共用入口（幂等：已 approved 不重复写、不重复通知）
- notify_report_approved：站内信通知（复用 notifications 表，幂等）
- auto_approve_overdue：APScheduler 周期任务，超时 pending → auto 批复
- kick_report_generation：批复通过瞬间后台自动生成报告 markdown
  （用户报告页「生成报告」按钮仅为兜底机制；生成失败不影响批复主流程）

文案注意：auto 批复的用户侧文案与人工一致（「您的报告已审核通过」），
不暴露自动事实——这是 ADR-0009 的刻意决策，勿当 bug 修复。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feedback import Notification
from app.utils.report_registry import ReportRegistry, _report_portal_unlocked
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


def build_approved_notification_content(activation_code: str) -> str:
    """人工/自动批复同一文案（ADR-0009：用户只感知「管理员审核通过」）。

    用户侧标识用激活码（用户唯一知道的报告标识），不写内部 report_id。
    """
    return (
        "您的报告已审核通过，点击查看完整报告："
        f"{REPORT_ENTRY_PATH}\n激活码：{activation_code}"
    )


async def notify_report_approved(
    db: AsyncSession, user_id: str, report_id: str, activation_code: str = ""
) -> bool:
    """
    给用户发「报告已审核通过」站内信（复用 notifications 表）。

    幂等：同一 (user_id, report_id) 已存在 report_approved 通知则不重复发。
    去重键优先用激活码（报告↔激活码 1:1，与 report_id 语义等价），
    正文不再暴露内部 report_id；activation_code 缺失时回退 report_id（仅兼容兜底）。
    Returns: True = 新建了通知；False = 已存在跳过。
    """
    uid = (user_id or "").strip()
    rid = (report_id or "").strip()
    code = (activation_code or "").strip()
    if not uid or not rid:
        logger.warning("报告批复通知缺少 user_id/report_id，跳过: user_id=%r report_id=%r", user_id, report_id)
        return False
    dedup_key = code or rid

    existing = (
        await db.execute(
            select(Notification).where(
                Notification.user_id == uid,
                Notification.type == NOTIFICATION_TYPE,
                Notification.content.like(f"%{dedup_key}%"),
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
            content=build_approved_notification_content(dedup_key),
            read_at=None,
            related_feedback_id=None,
        )
    )
    await db.flush()
    return True


# ── 批复后自动生成报告（后台任务）─────────────────────────────

# 进行中的生成任务（强引用防 GC）
# 去重走 report_pdf_service 的单轨锁（try_acquire_generation），
# 与 export 侧审核预生成/用户手动生成共用一份登记（2026-08-15 合并）
_gen_tasks: set[asyncio.Task] = set()


async def _run_report_generation(
    report_id: str, user_id: Optional[str], base_dir: Optional[str]
) -> None:
    """后台生成并缓存报告 markdown（PDF 由下载时即时转换）。"""
    from app.services.report_pdf_service import ReportPdfService

    from app.services.report_pdf_service import release_generation

    try:
        service = ReportPdfService(base_dir=base_dir)
        await service.generate_markdown_only(report_id=report_id, user_id=user_id)
        logger.info("批复后报告自动生成完成: report_id=%s", report_id)
    except Exception as e:
        # 生成失败不影响批复主流程——用户报告页「生成报告」按钮为完全体兜底
        logger.exception(
            "批复后报告自动生成失败（用户页生成按钮兜底）: report_id=%s error=%s",
            report_id,
            e,
        )
    finally:
        release_generation(report_id)


def kick_report_generation(
    report_id: str,
    user_id: Optional[str] = None,
    base_dir: Optional[str] = None,
) -> bool:
    """批复通过瞬间后台触发生成报告 markdown（fire-and-forget）。

    - 缓存已存在时 generate_markdown_only 秒回，无副作用
    - 同一 report_id 生成中不重复触发
    - 无运行中的事件循环（同步上下文）时跳过并告警，不抛异常
    Returns: True = 已触发；False = 跳过。
    """
    from app.services.report_pdf_service import try_acquire_generation

    rid = (report_id or "").strip()
    if not rid:
        return False
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        logger.warning(
            "批复后自动生成跳过（无运行中的事件循环）: report_id=%s", rid
        )
        return False
    if not try_acquire_generation(rid):
        return False
    task = asyncio.create_task(_run_report_generation(rid, user_id, base_dir))
    _gen_tasks.add(task)
    task.add_done_callback(_gen_tasks.discard)
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
        await notify_report_approved(
            db,
            record.get("user_id") or "",
            report_id,
            record.get("activation_code") or "",
        )

    # 批复通过瞬间后台自动生成报告 markdown（用户页「生成报告」按钮仅为兜底）。
    # 五阶段未完成时跳过（未完成的报告生成出来只有占位文案，与 export 完成度门控同口径）。
    if _report_portal_unlocked(record.get("steps") or {}):
        base_dir = getattr(registry, "simple_base_dir", None)
        kick_report_generation(
            report_id,
            record.get("user_id") or None,
            str(base_dir) if base_dir else None,
        )
    else:
        logger.info("批复后自动生成跳过（五阶段未完成）: report_id=%s", report_id)
    return record


async def auto_approve_overdue(
    base_dir: Optional[str] = None,
    session_factory=None,
) -> int:
    """
    自动批复任务（APScheduler 每 REVIEW_SCAN_INTERVAL_MINUTES 分钟调用）：

    扫描全部 record.json，pending_review 且已过 deadline → approved + review_type=auto，
    并触发站内信（与人工批复同一通知函数、同一文案）+ 后台自动生成报告 markdown。
    单条失败不影响其余。

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
