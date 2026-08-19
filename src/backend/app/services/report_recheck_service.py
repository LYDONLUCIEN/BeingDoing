"""
报告复核体系（2026-08-18，tasks/report-review-plan.md）

核心原则：用户不能重新生成，管理员也不能随意重新生成——
重新生成必须挂在用户主动发起的复核单上，新稿（staging）经 admin
确认发布后才对用户可见；发布前用户始终看到旧版报告（不锁定）。

数据模型：record.json 的 `recheck_requests` 列表（append-only），
每个复核单：
    id / status / description / feedback_id / requested_by /
    requested_at / updated_at / closed_at / reject_reason / regen_error

状态机：
    pending → regenerating → pending_confirm → done
      ↑__________|（LLM 生成失败退回 pending，可重试）
      └──────────→ rejected（驳回必须填理由）

双写：提交复核时同步创建一条 Feedback 工单（type=bug，内容含报告编号），
保证 admin 在反馈列表可见、不漏单；复核单关闭时工单置 done。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feedback import Feedback, Notification
from app.models.user import User
from app.services import feedback_service
from app.utils.report_registry import ReportRegistry, _report_portal_unlocked
from app.utils.report_review import REVIEW_STATUS_APPROVED, get_review_status

logger = logging.getLogger(__name__)

# ── 状态常量 ─────────────────────────────────────────────────

RECHECK_STATUS_PENDING = "pending"
RECHECK_STATUS_REGENERATING = "regenerating"
RECHECK_STATUS_PENDING_CONFIRM = "pending_confirm"
RECHECK_STATUS_DONE = "done"
RECHECK_STATUS_REJECTED = "rejected"

# 未关闭（复核进行中）的状态：admin「重新生成」按钮仅在这些状态下出现
RECHECK_OPEN_STATUSES = {
    RECHECK_STATUS_PENDING,
    RECHECK_STATUS_REGENERATING,
    RECHECK_STATUS_PENDING_CONFIRM,
}

NOTIFY_TYPE_DONE = "report_recheck_done"
NOTIFY_TYPE_REJECTED = "report_recheck_rejected"

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── 读取 ─────────────────────────────────────────────────────


def list_recheck_requests(report: dict) -> List[dict]:
    reqs = (report or {}).get("recheck_requests")
    return reqs if isinstance(reqs, list) else []


def get_current_recheck(report: dict) -> Optional[dict]:
    """当前未关闭的复核单（无则 None）。"""
    for req in reversed(list_recheck_requests(report)):
        if req.get("status") in RECHECK_OPEN_STATUSES:
            return req
    return None


def get_recheck_status(report: dict) -> Optional[str]:
    """admin 列表用：当前复核状态（无未关闭复核单为 None）。"""
    cur = get_current_recheck(report)
    return cur.get("status") if cur else None


def _find_request(report: dict, request_id: str) -> Optional[dict]:
    for req in list_recheck_requests(report):
        if req.get("id") == request_id:
            return req
    return None


# ── 提交（用户侧）─────────────────────────────────────────────


def compose_recheck_feedback_content(
    report_id: str, activation_code: str, description: str
) -> str:
    desc = (description or "").strip() or "（用户未填写）"
    return (
        f"【报告复核申请】报告编号：{report_id}；激活码：{activation_code}。\n"
        f"问题描述：{desc}"
    )


def compose_download_issue_feedback_content(
    report_id: str, activation_code: str, description: str
) -> str:
    desc = (description or "").strip() or "（用户未填写）"
    return (
        f"【报告下载/打开失败】报告编号：{report_id}；激活码：{activation_code}。\n"
        f"用户描述：{desc}"
    )


async def submit_recheck(
    db: AsyncSession,
    registry: ReportRegistry,
    report: dict,
    *,
    user_id: str,
    user_email: str,
    description: str,
) -> dict:
    """用户提交复核申请（内容问题）。

    Raises:
        ValueError: 状态不允许（报告未批复/有未关闭复核单/当日已申请）
    """
    report_id = (report.get("report_id") or "").strip()
    if get_review_status(report) != REVIEW_STATUS_APPROVED:
        raise ValueError("报告尚未审核通过，暂不能申请复核")
    if not _report_portal_unlocked(report.get("steps") or {}):
        raise ValueError("报告尚未解锁，暂不能申请复核")
    if get_current_recheck(report) is not None:
        raise ValueError("已有复核申请在处理中，请等待处理完成")

    # 频率限制：同一报告每个自然日（Asia/Shanghai）最多 1 次
    today = datetime.now(SHANGHAI_TZ).date()
    for req in list_recheck_requests(report):
        at = (req.get("requested_at") or "").strip()
        if not at:
            continue
        try:
            req_date = datetime.fromisoformat(at.replace("Z", "+00:00")).astimezone(
                SHANGHAI_TZ
            ).date()
        except ValueError:
            continue
        if req_date == today:
            raise ValueError("每份报告每天最多申请 1 次复核，请明天再来")

    # 双写 Feedback 工单（type=bug：与「反馈 bug」同流程——auto_ack + admin 通知 + SLA）
    feedback = await feedback_service.create_feedback(
        db=db,
        user_id=user_id,
        user_email=user_email,
        type_="bug",
        content=compose_recheck_feedback_content(
            report_id, report.get("activation_code") or "", description
        ),
        attachment_ids=[],
    )

    entry = {
        "id": uuid.uuid4().hex[:8],
        "status": RECHECK_STATUS_PENDING,
        "description": (description or "").strip(),
        "feedback_id": feedback.id,
        "requested_by": user_id,
        "requested_at": _now_iso(),
        "updated_at": _now_iso(),
        "closed_at": None,
        "reject_reason": None,
        "regen_error": None,
    }
    reqs = list_recheck_requests(report)
    reqs.append(entry)
    report["recheck_requests"] = reqs
    registry.save_record(report)
    logger.info("报告复核申请已提交: report_id=%s recheck_id=%s", report_id, entry["id"])
    return entry


# ── 状态流转（admin 侧）──────────────────────────────────────


def _update_request(registry: ReportRegistry, report_id: str, **fields) -> Optional[dict]:
    """更新当前未关闭复核单并保存，返回 (record, request) 或 None。"""
    record = registry.get_report_by_id(report_id)
    if not record:
        return None
    cur = get_current_recheck(record)
    if cur is None:
        return None
    cur.update(fields)
    cur["updated_at"] = _now_iso()
    registry.save_record(record)
    return record


def mark_regenerating(registry: ReportRegistry, report_id: str) -> Optional[dict]:
    return _update_request(
        registry, report_id, status=RECHECK_STATUS_REGENERATING, regen_error=None
    )


def mark_pending_confirm(registry: ReportRegistry, report_id: str) -> Optional[dict]:
    return _update_request(registry, report_id, status=RECHECK_STATUS_PENDING_CONFIRM)


def mark_regen_failed(registry: ReportRegistry, report_id: str, error: str) -> Optional[dict]:
    """LLM 生成失败 → 退回 pending（admin 可重试）。"""
    return _update_request(
        registry,
        report_id,
        status=RECHECK_STATUS_PENDING,
        regen_error=(error or "")[:500],
    )


# ── staging 重新生成（后台任务）───────────────────────────────

# 进行中的 staging 生成任务：report_id → {"status": "pending"|"done"|"error", "error": str|None}
# 与 export._pdf_tasks 隔离（用户侧状态查询不受 admin 复核生成影响），
# 但共用 report_pdf_service 单轨锁（同一报告不并发两个生成任务）。
_staging_tasks: dict = {}


def get_staging_task_status(report_id: str) -> Optional[dict]:
    return _staging_tasks.get((report_id or "").strip())


async def _run_staging_generation(
    report_id: str, user_id: Optional[str], base_dir: Optional[str]
) -> None:
    from app.services.report_pdf_service import ReportPdfService, release_generation

    registry = ReportRegistry(base_dir=base_dir) if base_dir else ReportRegistry()
    try:
        service = ReportPdfService(base_dir=base_dir)
        await service.generate_staging_markdown(report_id, user_id=user_id)
        mark_pending_confirm(registry, report_id)
        _staging_tasks[report_id] = {"status": "done", "error": None}
        logger.info("复核新稿生成完成（待 admin 确认）: report_id=%s", report_id)
    except Exception as e:
        logger.exception("复核新稿生成失败: report_id=%s", report_id)
        mark_regen_failed(registry, report_id, str(e))
        _staging_tasks[report_id] = {"status": "error", "error": str(e)}
    finally:
        release_generation(report_id)


def kick_recheck_regeneration(
    registry: ReportRegistry,
    report_id: str,
    user_id: Optional[str] = None,
) -> bool:
    """admin 触发复核重新生成（生成到 staging，不触碰用户可见的正式缓存）。

    要求存在未关闭复核单；同一报告生成中（任意路径）不并发。
    Returns: True = 已触发；False = 跳过（无复核单/生成中/无事件循环）。
    """
    from app.services.report_pdf_service import is_generation_inflight, try_acquire_generation

    rid = (report_id or "").strip()
    if not rid:
        return False
    record = registry.get_report_by_id(rid)
    if not record or get_current_recheck(record) is None:
        return False
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("复核重新生成跳过（无运行中的事件循环）: report_id=%s", rid)
        return False
    if is_generation_inflight(rid):
        return False
    if not try_acquire_generation(rid):
        return False
    mark_regenerating(registry, rid)
    _staging_tasks[rid] = {"status": "pending", "error": None}
    base_dir = getattr(registry, "simple_base_dir", None)
    task = asyncio.create_task(
        _run_staging_generation(rid, user_id, str(base_dir) if base_dir else None)
    )
    task.add_done_callback(lambda _t: None)  # 强引用防 GC（状态表已持有结果）
    return True


# ── 发布 / 驳回 ───────────────────────────────────────────────


async def _close_feedback(db: AsyncSession, feedback_id: Optional[str]) -> None:
    """复核单关闭时同步关闭 Feedback 工单（不另发 feedback_status_changed 通知，
    用户通知统一走 report_recheck_done / report_recheck_rejected）。"""
    fid = (feedback_id or "").strip()
    if not fid:
        return
    result = await db.execute(select(Feedback).where(Feedback.id == fid))
    feedback = result.scalar_one_or_none()
    if feedback is not None and feedback.status != "done":
        feedback.status = "done"
        await db.flush()


async def _notify_user(
    db: AsyncSession, user_id: str, *, type_: str, title: str, content: str
) -> None:
    uid = (user_id or "").strip()
    if not uid:
        return
    db.add(
        Notification(
            user_id=uid,
            type=type_,
            title=title,
            content=content,
            read_at=None,
            related_feedback_id=None,
        )
    )
    await db.flush()


async def _send_email_to_user(
    db: AsyncSession, user_id: str, *, subject: str, body_text: str
) -> None:
    """给用户注册邮箱发邮件；SMTP 未配置或发送失败只记日志，不阻塞主流程。"""
    from app.services.email_service import EmailService

    result = await db.execute(select(User).where(User.id == (user_id or "").strip()))
    user = result.scalar_one_or_none()
    email = (getattr(user, "email", None) or "").strip() if user else ""
    if not email:
        logger.warning("复核邮件跳过（用户无邮箱）: user_id=%s", user_id)
        return
    try:
        await EmailService.send_email(to_email=email, subject=subject, body_text=body_text)
    except Exception:
        logger.exception("复核邮件发送失败: user_id=%s", user_id)


async def publish_recheck(
    db: AsyncSession,
    registry: ReportRegistry,
    report_id: str,
    *,
    admin_id: Optional[str],
) -> dict:
    """确认发布：staging 原子替换正式缓存，用户同步看到新报告。

    Raises:
        ValueError: 无待确认复核单 / staging 不存在
    """
    from app.services.report_pdf_service import ReportPdfService

    record = registry.get_report_by_id(report_id)
    if not record:
        raise LookupError("报告不存在")
    cur = get_current_recheck(record)
    if cur is None:
        raise ValueError("该报告没有进行中的复核")
    if cur.get("status") != RECHECK_STATUS_PENDING_CONFIRM:
        raise ValueError("新稿尚未生成完成，暂不能确认发布")

    base_dir = getattr(registry, "simple_base_dir", None)
    service = ReportPdfService(base_dir=str(base_dir) if base_dir else None)
    if not service.publish_staging(report_id):
        raise ValueError("新稿文件不存在，请重新生成")

    cur["status"] = RECHECK_STATUS_DONE
    cur["closed_at"] = _now_iso()
    cur["updated_at"] = _now_iso()
    registry.save_record(record)

    user_id = record.get("user_id") or ""
    await _close_feedback(db, cur.get("feedback_id"))
    await _notify_user(
        db,
        user_id,
        type_=NOTIFY_TYPE_DONE,
        title="报告复核已完成",
        content=(
            "您申请复核的报告已完成更新，请重新下载查看最新版本："
            "/explore/report/view\n"
            f"报告编号：{report_id}"
        ),
    )
    await _send_email_to_user(
        db,
        user_id,
        subject="【寻路·OpenLife】您的报告已完成复核更新",
        body_text=(
            "您好，\n\n"
            "您申请复核的报告已完成内容更新，登录后进入报告页重新下载即可查看最新版本。\n\n"
            f"报告编号：{report_id}\n\n"
            "—— 寻路·OpenLife 团队"
        ),
    )
    logger.info("复核发布完成: report_id=%s admin=%s", report_id, admin_id)
    return cur


async def reject_recheck(
    db: AsyncSession,
    registry: ReportRegistry,
    report_id: str,
    *,
    admin_id: Optional[str],
    reason: str,
) -> dict:
    """驳回复核（必须填理由）：站内信告知用户，清理 staging。"""
    from app.services.report_pdf_service import ReportPdfService

    reason = (reason or "").strip()
    if not reason:
        raise ValueError("驳回必须填写理由")

    record = registry.get_report_by_id(report_id)
    if not record:
        raise LookupError("报告不存在")
    cur = get_current_recheck(record)
    if cur is None:
        raise ValueError("该报告没有进行中的复核")

    cur["status"] = RECHECK_STATUS_REJECTED
    cur["reject_reason"] = reason
    cur["closed_at"] = _now_iso()
    cur["updated_at"] = _now_iso()
    registry.save_record(record)

    base_dir = getattr(registry, "simple_base_dir", None)
    ReportPdfService(base_dir=str(base_dir) if base_dir else None).discard_staging(report_id)

    user_id = record.get("user_id") or ""
    await _close_feedback(db, cur.get("feedback_id"))
    await _notify_user(
        db,
        user_id,
        type_=NOTIFY_TYPE_REJECTED,
        title="报告复核申请已回复",
        content=(
            "您的报告复核申请经管理员评估后未予重新生成，理由如下：\n\n"
            f"{reason}\n\n"
            f"报告编号：{report_id}\n"
            "如有疑问可通过反馈通道继续与我们联系。"
        ),
    )
    logger.info("复核已驳回: report_id=%s admin=%s", report_id, admin_id)
    return cur
