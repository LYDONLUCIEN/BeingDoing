"""
SMTP 故障告警（2026-09-27 起）

背景：163 授权码失效/账号被风控时，SMTP 登录阶段返回
「550 User has no permission」（SMTPAuthenticationError），全站邮件断流，
但用户侧只能看到发送失败，运维无感知（曾导致注册验证邮件静默断流事故）。

本模块在邮件发送捕获到 SMTPAuthenticationError 时，给所有 super_admin
发站内信提醒检查 SMTP_USER/SMTP_PASS（授权码）配置。

幂等：同一天（北京时间）只提醒一次——以当天是否已存在
smtp_auth_failed 通知为准，避免发信重试/批量任务造成刷屏。

挂载点：EmailService._send_via_smtp 的 async 包装层（email_service.py）。
"""
import logging
import smtplib
from datetime import datetime, time, timezone

from sqlalchemy import func, select

from app.models.database import AsyncSessionLocal
from app.models.feedback import Notification
from app.services.feedback_service import SHANGHAI_TZ, _get_super_admin_ids

logger = logging.getLogger(__name__)

SMTP_AUTH_FAILED_NOTIFICATION_TYPE = "smtp_auth_failed"
SMTP_AUTH_FAILED_TITLE = "邮件服务认证失败告警"


async def notify_smtp_auth_failed(exc: smtplib.SMTPAuthenticationError) -> int:
    """SMTP 认证失败告警：给所有 super_admin 发站内信（当天幂等）。

    Args:
        exc: 触发告警的认证异常（用于日志与通知内容）

    Returns:
        实际发出的通知条数；已提醒过/无超管/自身出错时返回 0。
        任何内部失败只记日志，绝不抛出（不能影响原发信异常链路）。
    """
    try:
        now = datetime.now(timezone.utc)
        today_start = datetime.combine(
            now.astimezone(SHANGHAI_TZ).date(), time(0, 0, 0), tzinfo=SHANGHAI_TZ
        ).astimezone(timezone.utc)

        async with AsyncSessionLocal() as db:
            # 幂等：今天（北京时间）已提醒过则跳过
            exists_q = await db.execute(
                select(func.count(Notification.id)).where(
                    Notification.type == SMTP_AUTH_FAILED_NOTIFICATION_TYPE,
                    Notification.created_at >= today_start,
                )
            )
            if int(exists_q.scalar_one()) > 0:
                logger.info("smtp auth failed alert: already notified today, skip")
                return 0

            admin_ids = await _get_super_admin_ids(db)
            if not admin_ids:
                logger.warning("smtp auth failed alert: no super_admin found, skip notify")
                return 0

            content = (
                f"邮件发送在 SMTP 认证阶段被服务器拒绝"
                f"（{exc.smtp_code} {exc.smtp_error!r}）。\n\n"
                "通常是发信邮箱的客户端授权码失效、SMTP 服务被关闭或账号被风控。\n"
                "这会导致注册验证、密码重置等全部邮件断流，请尽快检查 "
                "SMTP_USER / SMTP_PASS（授权码）配置，必要时到邮箱服务商后台"
                "重新开启 SMTP 服务并生成新授权码。"
            )
            notified = 0
            for admin_id in admin_ids:
                db.add(
                    Notification(
                        user_id=admin_id,
                        type=SMTP_AUTH_FAILED_NOTIFICATION_TYPE,
                        title=SMTP_AUTH_FAILED_TITLE,
                        content=content,
                        read_at=None,
                    )
                )
                notified += 1
            await db.commit()

        logger.warning("smtp auth failed alert: notified %d super_admin(s)", notified)
        return notified
    except Exception:
        logger.exception("smtp auth failed alert error")
        return 0
