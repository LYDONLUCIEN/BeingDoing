"""_friendly_email_send_error 错误分类测试（2026-09-27 起）

背景：163 授权码失效/账号被风控时，SMTP 登录阶段返回
「550 User has no permission」，异常类型是 SMTPAuthenticationError
（SMTPResponseException 子类，smtp_code=550），此前被误判为
「收件人不存在/被服务器拒收」，误导用户以为自己邮箱有问题。
"""

import smtplib

from app.services.auth_service import _friendly_email_send_error


class TestAuthFailureClassification:
    """认证失败（含 163 的 550 User has no permission）→ 邮件服务账号异常"""

    def test_auth_error_550_is_not_recipient_refused(self):
        # 163 授权码失效/被风控时的真实形态：550 + SMTPAuthenticationError
        exc = smtplib.SMTPAuthenticationError(550, b"User has no permission")
        err = _friendly_email_send_error(exc, "验证")
        assert isinstance(err, ValueError)
        assert "认证异常" in str(err)
        assert "联系管理员" in str(err)
        # 关键：不能再提示「该邮箱可能不存在」误导用户
        assert "拒收" not in str(err)
        assert "邮箱可能不存在" not in str(err)

    def test_auth_error_535_generic(self):
        exc = smtplib.SMTPAuthenticationError(535, b"Authentication failed")
        err = _friendly_email_send_error(exc, "密码重置")
        assert "认证异常" in str(err)
        assert "拒收" not in str(err)


class TestRecipientRefusedClassification:
    """收件人 550 拒收 → 维持原有文案"""

    def test_recipients_refused(self):
        exc = smtplib.SMTPRecipientsRefused({"a@b.com": (550, b"Mailbox not found")})
        err = _friendly_email_send_error(exc, "验证")
        assert "拒收" in str(err)
        assert "联系管理员" in str(err)

    def test_response_550_non_auth(self):
        # 投递阶段的 550（非认证异常）仍按拒收处理
        exc = smtplib.SMTPSenderRefused(550, b"spam rejected", "noreply@x.com")
        err = _friendly_email_send_error(exc, "验证")
        assert "拒收" in str(err)


class TestOtherFailures:
    """其余异常 → 稍后重试文案"""

    def test_generic_exception(self):
        err = _friendly_email_send_error(ConnectionError("timeout"), "恢复")
        assert "稍后重试" in str(err)

    def test_smtp_response_non_550(self):
        exc = smtplib.SMTPResponseException(451, b"temporary failure")
        err = _friendly_email_send_error(exc, "验证")
        assert "稍后重试" in str(err)
