"""
邮件发送服务（SMTP）
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from app.config.settings import settings

# 统一注脚（2026-09-21 起）：163 发送邮箱不接收回复，咨询统一引导到 Outlook 邮箱。
# 在 send_email 一处注入，覆盖全部邮件（验证码/支付交付/续期/群发等），新邮件自动带上。
NOREPLY_NOTICE_TEXT = (
    "\n——\n"
    "本邮箱为系统发送邮箱，不接收回复。如有任何问题，请联系：openlife.lab@outlook.com\n"
)
NOREPLY_NOTICE_HTML = (
    '<hr style="border:none;border-top:1px solid #e5e5e5;margin:16px 0;">'
    '<p style="font-size:12px;color:#999;">本邮箱为系统发送邮箱，不接收回复。'
    '如有任何问题，请联系：<a href="mailto:openlife.lab@outlook.com" '
    'style="color:#999;">openlife.lab@outlook.com</a></p>'
)


def _append_noreply_notice_html(body_html: str) -> str:
    """把注脚插到 </body> 前（无 </body> 时直接追加），保证出现在邮件最下方。"""
    lower = body_html.lower()
    idx = lower.rfind("</body>")
    if idx != -1:
        return body_html[:idx] + NOREPLY_NOTICE_HTML + body_html[idx:]
    return body_html + NOREPLY_NOTICE_HTML


class EmailService:
    """基于 SMTP 的邮件发送服务。"""

    @staticmethod
    async def send_password_reset_code(to_email: str, code: str, valid_minutes: int = 5) -> None:
        subject = "【寻路·OpenLife】密码重置验证码"
        body = (
            f"您好，\n\n"
            f"您正在重置寻路·OpenLife账号密码。\n"
            f"本次验证码为：{code}\n"
            f"有效期：{valid_minutes} 分钟。\n\n"
            f"如果这不是您的操作，请忽略本邮件。\n"
        )
        await EmailService.send_email(to_email=to_email, subject=subject, body_text=body)

    @staticmethod
    async def send_account_recovery_code(
        to_email: str, code: str, valid_minutes: int = 5
    ) -> None:
        subject = "【寻路·OpenLife】账号恢复验证码"
        body = (
            f"您好，\n\n"
            f"您正在恢复已注销的寻路·OpenLife账号。\n"
            f"本次验证码为：{code}\n"
            f"有效期：{valid_minutes} 分钟。\n\n"
            f"如果这不是您的操作，请忽略本邮件。\n"
        )
        await EmailService.send_email(to_email=to_email, subject=subject, body_text=body)

    @staticmethod
    async def send_password_changed_notice(to_email: str) -> None:
        subject = "【寻路·OpenLife】密码修改通知"
        body = (
            "您好，\n\n"
            "您的寻路·OpenLife账号密码刚刚完成修改，\n"
            "全部登录会话已下线，需使用新密码重新登录。\n\n"
            "如果这不是您的操作，请立即通过登录弹窗的「忘记密码」重置密码，并联系我们处理。\n"
        )
        await EmailService.send_email(to_email=to_email, subject=subject, body_text=body)

    @staticmethod
    async def send_account_restored_notice(to_email: str) -> None:
        subject = "【寻路·OpenLife】账号已恢复"
        body = (
            f"您好，\n\n"
            f"您的寻路·OpenLife账号已由管理员恢复，\n"
            f"账号数据与激活码绑定关系均已还原，现在可以正常登录使用。\n\n"
            f"如果这不是您的预期操作，请立即联系我们。\n"
        )
        await EmailService.send_email(to_email=to_email, subject=subject, body_text=body)

    @staticmethod
    async def send_email_verification(to_email: str, token: str) -> None:
        base_url = settings.FRONTEND_URL.rstrip("/")
        link = f"{base_url}/verify-email?token={token}"
        subject = "【寻路·OpenLife】邮箱验证"
        body = (
            f"您好，\n\n"
            f"感谢您注册寻路·OpenLife！请点击以下链接验证您的邮箱：\n\n"
            f"{link}\n\n"
            f"链接 24 小时内有效。如果这不是您的操作，请忽略本邮件。\n"
        )
        # HTML 版本：保证各邮箱客户端中链接可点击（multipart/alternative，纯文本兜底）
        body_html = (
            "<html><body style=\"font-family: sans-serif; line-height: 1.6; color: #333;\">"
            "<p>您好，</p>"
            "<p>感谢您注册寻路·OpenLife！请点击下方按钮验证您的邮箱：</p>"
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
        from_name = settings.SMTP_FROM_NAME or "OpenLife"

        # 统一追加「不接收回复」注脚（纯文本 + HTML 都加）
        body_text = body_text + NOREPLY_NOTICE_TEXT
        if body_html:
            body_html = _append_noreply_notice_html(body_html)

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
