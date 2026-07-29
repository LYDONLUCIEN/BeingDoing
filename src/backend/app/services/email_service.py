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
        subject = "【寻路·LifeAsk】密码重置验证码"
        body = (
            f"您好，\n\n"
            f"您正在重置寻路·LifeAsk账号密码。\n"
            f"本次验证码为：{code}\n"
            f"有效期：{valid_minutes} 分钟。\n\n"
            f"如果这不是您的操作，请忽略本邮件。\n"
        )
        await EmailService.send_email(to_email=to_email, subject=subject, body_text=body)

    @staticmethod
    async def send_account_recovery_code(
        to_email: str, code: str, valid_minutes: int = 5
    ) -> None:
        subject = "【寻路·LifeAsk】账号恢复验证码"
        body = (
            f"您好，\n\n"
            f"您正在恢复已注销的寻路·LifeAsk账号。\n"
            f"本次验证码为：{code}\n"
            f"有效期：{valid_minutes} 分钟。\n\n"
            f"如果这不是您的操作，请忽略本邮件。\n"
        )
        await EmailService.send_email(to_email=to_email, subject=subject, body_text=body)

    @staticmethod
    async def send_email_verification(to_email: str, token: str) -> None:
        base_url = settings.FRONTEND_URL.rstrip("/")
        link = f"{base_url}/verify-email?token={token}"
        subject = "【寻路·LifeAsk】邮箱验证"
        body = (
            f"您好，\n\n"
            f"感谢您注册寻路·LifeAsk！请点击以下链接验证您的邮箱：\n\n"
            f"{link}\n\n"
            f"链接 24 小时内有效。如果这不是您的操作，请忽略本邮件。\n"
        )
        # HTML 版本：保证各邮箱客户端中链接可点击（multipart/alternative，纯文本兜底）
        body_html = (
            "<html><body style=\"font-family: sans-serif; line-height: 1.6; color: #333;\">"
            "<p>您好，</p>"
            "<p>感谢您注册寻路·LifeAsk！请点击下方按钮验证您的邮箱：</p>"
            f"<p><a href=\"{link}\" style=\"display: inline-block; padding: 10px 24px; "
            "background-color: #4F46E5; color: #ffffff; text-decoration: none; "
            "border-radius: 6px;\">验证邮箱</a></p>"
            "<p>如果按钮无法点击，请复制以下链接到浏览器打开：<br>"
            f'<a href="{link}">{link}</a></p>'
            "<p>链接 24 小时内有效。如果这不是您的操作，请忽略本邮件。</p>"
            "</body></html>"
        )
        await EmailService.send_email(
            to_email=to_email, subject=subject, body_text=body, body_html=body_html
        )

    @staticmethod
    async def send_email(
        to_email: str, subject: str, body_text: str, body_html: str | None = None
    ) -> None:
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
        from_name = settings.SMTP_FROM_NAME or "LifeAsk"

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = formataddr((from_name, from_email))
        msg["To"] = to_email
        msg.set_content(body_text)
        if body_html:
            # multipart/alternative：纯文本兜底，支持 HTML 的客户端优先渲染 HTML
            msg.add_alternative(body_html, subtype="html")

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
