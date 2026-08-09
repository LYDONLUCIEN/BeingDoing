"""
激活码过期扫描任务（ADR-0015）

每天定时扫描已过期（含懒过期转正）的完整码，给激活人（owner）发送
「免费领取 7 天续期」通知：站内信 + 邮件（无邮箱只发站内信）。

幂等：以 ActivationRecord.free_renewal_offered_at 为标记，每码只发一次；
存量已过期码在首次扫描时全量补发。

通知与邮件全部成功后才写 offered 标记，单条失败下次扫描重试，不中断整体。
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.config.settings import settings
from app.models.database import AsyncSessionLocal
from app.models.feedback import Notification
from app.models.user import User
from app.services.email_service import EmailService
from app.utils.simple_activation_manager import (
    SimpleActivationManager,
    get_simple_base_dir,
)

logger = logging.getLogger(__name__)

NOTIFY_TYPE = "activation_expired"
NOTIFY_TITLE = "你的激活码已到期"


def _claim_url(code: str) -> str:
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/dashboard/codes?free_renewal={code}"


def _build_notify_content(code: str) -> str:
    return (
        f"你的激活码 {code} 已到期。\n\n"
        f"作为首次到期福利，你可以免费领取 7 天延期（每个激活码限领一次）：\n"
        f"{_claim_url(code)}\n\n"
        "之后如需继续延期，可在「我的激活码」页付费续期（9.9 元 / 7 天）。"
    )


def _build_email(code: str) -> tuple[str, str, str]:
    """Returns (subject, body_text, body_html)"""
    link = _claim_url(code)
    subject = "【寻路·OpenLife】你的激活码已到期，可免费领取 7 天延期"
    body_text = (
        "您好，\n\n"
        f"您的寻路·OpenLife 激活码 {code} 已到期。\n\n"
        "作为首次到期福利，您可以免费领取 7 天延期（每个激活码限领一次）。\n"
        f"请点击以下链接领取：\n\n{link}\n\n"
        "之后如需继续延期，可在「我的激活码」页付费续期（9.9 元 / 7 天）。\n\n"
        "如果这不是您的操作，请忽略本邮件。\n"
    )
    body_html = (
        '<html><body style="font-family: sans-serif; line-height: 1.6; color: #333;">'
        "<p>您好，</p>"
        f"<p>您的寻路·OpenLife 激活码 <b>{code}</b> 已到期。</p>"
        "<p>作为首次到期福利，您可以<b>免费领取 7 天延期</b>（每个激活码限领一次）：</p>"
        f'<p><a href="{link}" style="display: inline-block; padding: 10px 24px; '
        'background-color: #4F46E5; color: #ffffff; text-decoration: none; '
        'border-radius: 6px;">免费领取 7 天延期</a></p>'
        "<p>如果按钮无法点击，请复制以下链接到浏览器打开：<br>"
        f'<a href="{link}">{link}</a></p>'
        "<p>之后如需继续延期，可在「我的激活码」页付费续期（9.9 元 / 7 天）。</p>"
        "<p>如果这不是您的操作，请忽略本邮件。</p>"
        "</body></html>"
    )
    return subject, body_text, body_html


async def scan_expired_activations() -> dict:
    """扫描已过期完整码并发送免费续期通知。

    Returns:
        {"expired_pending": N, "notified": M, "email_sent": K, "skipped": S, "failed": F}
    """
    mgr = SimpleActivationManager(base_dir=str(get_simple_base_dir()))
    pending = mgr.mark_expired_and_list_pending_free_renewal()
    stats = {
        "expired_pending": len(pending),
        "notified": 0,
        "email_sent": 0,
        "skipped": 0,
        "failed": 0,
    }
    if not pending:
        logger.info("activation expiry scan: no pending expired codes")
        return stats

    async with AsyncSessionLocal() as db:
        for rec in pending:
            try:
                if not rec.owner_user_id:
                    stats["skipped"] += 1
                    # 无激活人的码不会再有通知对象，直接标记避免每轮重复扫描
                    mgr.mark_free_renewal_offered(rec.code)
                    continue
                user = (
                    await db.execute(select(User).where(User.id == rec.owner_user_id))
                ).scalar_one_or_none()
                if user is None:
                    stats["skipped"] += 1
                    mgr.mark_free_renewal_offered(rec.code)
                    continue

                # 先邮件后站内信：邮件失败时不落站内信、不打标记，下次扫描整体重试，
                # 避免「站内信已落库但邮件失败」导致重发重复站内信
                if user.email:
                    subject, body_text, body_html = _build_email(rec.code)
                    await EmailService.send_email(
                        to_email=user.email,
                        subject=subject,
                        body_text=body_text,
                        body_html=body_html,
                    )
                    stats["email_sent"] += 1

                # 站内信（必发）
                db.add(
                    Notification(
                        user_id=user.id,
                        type=NOTIFY_TYPE,
                        title=NOTIFY_TITLE,
                        content=_build_notify_content(rec.code),
                        read_at=None,
                    )
                )
                await db.commit()

                mgr.mark_free_renewal_offered(rec.code)
                stats["notified"] += 1
            except Exception as e:
                stats["failed"] += 1
                logger.error(
                    "activation expiry notify failed: code=%s err=%s", rec.code, e
                )
                await db.rollback()

    logger.info(
        "activation expiry scan done: pending=%s notified=%s email=%s skipped=%s failed=%s",
        stats["expired_pending"],
        stats["notified"],
        stats["email_sent"],
        stats["skipped"],
        stats["failed"],
    )
    return stats
