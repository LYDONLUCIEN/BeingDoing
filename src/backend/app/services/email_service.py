"""
邮件发送服务（SMTP）
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from app.config.settings import settings


class EmailService:
    """基于 SMTP 的邮件发送服务。"""

    @staticmethod
    async def send_password_reset_code(to_email: str, code: str, valid_minutes: int = 5) -> None:
        subject = "【寻录】密码重置验证码"
        body = (
            f"您好，\n\n"
            f"您正在重置寻录账号密码。\n"
            f"本次验证码为：{code}\n"
            f"有效期：{valid_minutes} 分钟。\n\n"
            f"如果这不是您的操作，请忽略本邮件。\n"
        )
        await EmailService.send_email(to_email=to_email, subject=subject, body_text=body)

    @staticmethod
    async def send_email(to_email: str, subject: str, body_text: str) -> None:
        missing = [
            k for k, v in {
                "SMTP_HOST": settings.SMTP_HOST,
                "SMTP_USER": settings.SMTP_USER,
                "SMTP_PASS": settings.SMTP_PASS,
            }.items() if not v
        ]
        if missing:
            raise ValueError(f"邮件服务未配置完整：缺少 {', '.join(missing)}")

        from_email = settings.SMTP_FROM_EMAIL or settings.SMTP_USER
        from_name = settings.SMTP_FROM_NAME or "xunlu"

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = formataddr((from_name, from_email))
        msg["To"] = to_email
        msg.set_content(body_text)

        await EmailService._send_via_smtp(msg)

    @staticmethod
    async def _send_via_smtp(msg: EmailMessage) -> None:
        def _send():
            host = settings.SMTP_HOST
            port = int(settings.SMTP_PORT or 465)
            timeout = int(settings.SMTP_TIMEOUT_SECONDS or 20)
            user = settings.SMTP_USER
            password = settings.SMTP_PASS

            if settings.SMTP_USE_SSL:
                with smtplib.SMTP_SSL(host, port, timeout=timeout) as server:
                    server.login(user, password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(host, port, timeout=timeout) as server:
                    server.ehlo()
                    if settings.SMTP_USE_TLS:
                        server.starttls()
                        server.ehlo()
                    server.login(user, password)
                    server.send_message(msg)

        import asyncio
        await asyncio.to_thread(_send)
