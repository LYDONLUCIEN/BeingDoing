"""注册强制邮箱验证（2026-09-27 起）测试

覆盖：
- 注册自动发送验证邮件（响应带 verification_email_sent；冷却已记录）
- 发信失败不阻断注册（verification_email_sent=false，token 正常签发）
- 纯手机注册被 400 拒绝
- 注册不再发试用码；verify_email_token 验证通过才发（幂等，发码失败不阻断验证）
- journeys 懒补发：未验证用户不补发、已验证用户正常补发
- 注册接口 IP 频控（单 IP 每小时 5 次，第 6 次 429）
- SMTP 认证失败告警：站内信 + 当天幂等；发信钩子仅对认证失败触发

使用独立 in-memory SQLite + monkeypatch 替换各模块的 AsyncSessionLocal；
激活码数据根指向 tmp_path，邮件 mock，不污染真实数据。
"""

from __future__ import annotations

import smtplib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.main  # noqa: F401  先导入 app.main，规避 simple_chat 包循环导入
import app.utils.simple_activation_manager as sam
import app.utils.trial_codes as trial_codes
from app.api.v1 import auth as auth_module
from app.api.v1 import simple_auth as simple_auth_module
from app.main import app
from app.models.database import Base
from app.models.feedback import Notification
from app.models.user import User
from app.services import auth_service as as_mod
from app.services import email_service as es_mod
from app.services import smtp_health_monitor as shm_mod
from app.services.auth_service import AuthService
from app.utils.simple_activation_manager import SimpleActivationManager
from app.utils.trial_codes import list_owned_codes

# ─── 测试专用引擎 + 会话工厂 ──────────────────────────────────

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
_TestSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)

PASSWORD = "Passw0rd!"


@pytest.fixture(autouse=True)
async def _setup(monkeypatch, tmp_path):
    """每个测试前：建表 + monkeypatch DB/激活码根/邮件 + 清内存态"""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    monkeypatch.setattr(as_mod, "AsyncSessionLocal", _TestSessionLocal)
    monkeypatch.setattr(as_mod, "engine", _test_engine)
    monkeypatch.setattr(shm_mod, "AsyncSessionLocal", _TestSessionLocal)

    # 激活码生产/测试根 → tmp_path
    prod_base = tmp_path / "simple"
    (prod_base / "reports").mkdir(parents=True)
    test_base = tmp_path / "test_simple"
    (test_base / "reports").mkdir(parents=True)
    monkeypatch.setattr(sam, "get_simple_base_dir", lambda: prod_base)
    monkeypatch.setattr(sam, "get_simple_test_base_dir", lambda: test_base)
    monkeypatch.setattr(trial_codes, "get_simple_base_dir", lambda: prod_base)
    monkeypatch.setattr(trial_codes, "get_simple_test_base_dir", lambda: test_base)

    # 邮件 mock（默认成功）
    send_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(as_mod.EmailService, "send_email_verification", send_mock)

    # 清进程内内存态（冷却 / IP 频控）
    as_mod._email_verify_cooldowns.clear()
    auth_module._REGISTER_ATTEMPTS.clear()

    yield {"prod_base": prod_base, "send_mock": send_mock}

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _create_user(email: str, user_id: str, email_verified: bool = False) -> None:
    async with _TestSessionLocal() as db:
        db.add(
            User(
                id=user_id,
                email=email,
                username=user_id,
                password_hash=AuthService.get_password_hash(PASSWORD),
                is_active=True,
                email_verified=email_verified,
                created_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()


# ─── 1. 注册自动发验证邮件 ──────────────────────────────────


async def test_register_sends_verification_email(_setup):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/register",
            json={"email": "new@test.com", "password": PASSWORD},
        )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["verification_email_sent"] is True
    assert data["token"]
    # 自动发信被调用，目标邮箱正确
    send_mock = _setup["send_mock"]
    send_mock.assert_awaited_once()
    assert send_mock.await_args.kwargs["to_email"] == "new@test.com"
    # 冷却已记录（立即手动重发会被 5 分钟冷却拦）
    assert "new@test.com" in as_mod._email_verify_cooldowns


async def test_register_survives_email_send_failure(_setup, monkeypatch):
    monkeypatch.setattr(
        as_mod.EmailService,
        "send_email_verification",
        AsyncMock(side_effect=smtplib.SMTPAuthenticationError(550, b"User has no permission")),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/register",
            json={"email": "fail@test.com", "password": PASSWORD},
        )
    # 发信失败不阻断注册
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["verification_email_sent"] is False
    assert data["token"]


async def test_register_phone_only_rejected(_setup):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/register",
            json={"phone": "13800138000", "password": PASSWORD},
        )
    assert res.status_code == 400
    assert "请使用邮箱注册" in res.json()["detail"]


# ─── 2. 试用码发放时机 ──────────────────────────────────────


async def test_register_does_not_grant_trial_code(_setup):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/register",
            json={"email": "nocode@test.com", "password": PASSWORD},
        )
    assert res.status_code == 200
    uid = res.json()["data"]["user_id"]
    assert list_owned_codes(uid, "nocode@test.com") == []


async def test_verify_email_token_grants_trial_code(_setup):
    await _create_user("vfy@test.com", "u-vfy-1", email_verified=False)
    token = AuthService.create_email_verify_token(
        data={"sub": "u-vfy-1", "email": "vfy@test.com"}
    )

    result = await AuthService.verify_email_token(token)
    assert result["already_verified"] is False

    # 验证通过 → 自动补发 1 个试用码并绑定
    owned = list_owned_codes("u-vfy-1", "vfy@test.com")
    assert len(owned) == 1

    # 重复验证不重复发
    result2 = await AuthService.verify_email_token(token)
    assert result2["already_verified"] is True
    assert len(list_owned_codes("u-vfy-1", "vfy@test.com")) == 1

    # 用户已置为已验证
    async with _TestSessionLocal() as db:
        user = (await db.execute(select(User).where(User.id == "u-vfy-1"))).scalar_one()
    assert user.email_verified is True


async def test_verify_grant_failure_does_not_block_verification(_setup, monkeypatch):
    await _create_user("vfy2@test.com", "u-vfy-2", email_verified=False)

    def boom(user):
        raise RuntimeError("disk full")

    monkeypatch.setattr(trial_codes, "ensure_trial_code_for_user", boom)

    token = AuthService.create_email_verify_token(
        data={"sub": "u-vfy-2", "email": "vfy2@test.com"}
    )
    result = await AuthService.verify_email_token(token)
    assert result["already_verified"] is False  # 验证本身成功

    async with _TestSessionLocal() as db:
        user = (await db.execute(select(User).where(User.id == "u-vfy-2"))).scalar_one()
    assert user.email_verified is True  # 发码失败不影响验证结果


async def test_journeys_no_lazy_grant_for_unverified(_setup):
    cu = {"user_id": "u-unv", "email": "unv@test.com", "email_verified": False}
    out = await simple_auth_module.list_user_journeys(current_user=cu)
    assert out.data["journeys"] == []
    assert list_owned_codes("u-unv", "unv@test.com") == []


async def test_journeys_lazy_grant_for_verified(_setup):
    cu = {"user_id": "u-vok", "email": "vok@test.com", "email_verified": True}
    out = await simple_auth_module.list_user_journeys(current_user=cu)
    assert len(out.data["journeys"]) == 1
    assert len(list_owned_codes("u-vok", "vok@test.com")) == 1


# ─── 3. 注册 IP 频控 ────────────────────────────────────────


async def test_register_ip_rate_limit(_setup):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for i in range(auth_module.REGISTER_RATE_LIMIT_PER_HOUR):
            res = await client.post(
                "/api/v1/auth/register",
                json={"email": f"rl{i}@test.com", "password": PASSWORD},
            )
            assert res.status_code == 200
        # 超限 → 429
        res = await client.post(
            "/api/v1/auth/register",
            json={"email": "rl-blocked@test.com", "password": PASSWORD},
        )
        assert res.status_code == 429
        assert "register_rate_limited" in res.json()["detail"]


# ─── 4. SMTP 认证失败告警 ────────────────────────────────────


async def test_smtp_auth_alert_notify_and_idempotent(_setup, monkeypatch):
    monkeypatch.setattr(
        shm_mod, "_get_super_admin_ids", AsyncMock(return_value=["admin-1", "admin-2"])
    )
    exc = smtplib.SMTPAuthenticationError(550, b"User has no permission")

    notified = await shm_mod.notify_smtp_auth_failed(exc)
    assert notified == 2

    async with _TestSessionLocal() as db:
        rows = (
            (await db.execute(select(Notification)))
            .scalars()
            .all()
        )
    assert len(rows) == 2
    assert all(r.type == shm_mod.SMTP_AUTH_FAILED_NOTIFICATION_TYPE for r in rows)
    assert {r.user_id for r in rows} == {"admin-1", "admin-2"}

    # 当天幂等：第二次不再发
    assert await shm_mod.notify_smtp_auth_failed(exc) == 0
    async with _TestSessionLocal() as db:
        count = len((await db.execute(select(Notification))).scalars().all())
    assert count == 2


async def test_smtp_auth_alert_never_raises(_setup, monkeypatch):
    # 无超管 + DB 异常都不应抛出
    monkeypatch.setattr(shm_mod, "_get_super_admin_ids", AsyncMock(side_effect=RuntimeError))
    exc = smtplib.SMTPAuthenticationError(535, b"auth failed")
    assert await shm_mod.notify_smtp_auth_failed(exc) == 0


async def test_send_via_smtp_triggers_alert_on_auth_error(_setup, monkeypatch):
    """_send_via_smtp 仅在认证失败时触发告警，其他 SMTP 错误不触发，且原异常照常抛出"""
    monkeypatch.setattr(es_mod.settings, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(es_mod.settings, "SMTP_USER", "u@test")
    monkeypatch.setattr(es_mod.settings, "SMTP_PASS", "x")
    monkeypatch.setattr(es_mod.settings, "SMTP_USE_SSL", True)

    class _FakeSMTP:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, u, p):
            raise smtplib.SMTPAuthenticationError(550, b"User has no permission")

    alert_mock = AsyncMock(return_value=1)
    monkeypatch.setattr(es_mod.smtplib, "SMTP_SSL", _FakeSMTP)
    monkeypatch.setattr(shm_mod, "notify_smtp_auth_failed", alert_mock)

    from email.message import EmailMessage

    msg = EmailMessage()
    msg["To"] = "x@test.com"
    msg.set_content("hi")

    with pytest.raises(smtplib.SMTPAuthenticationError):
        await es_mod.EmailService._send_via_smtp(msg)
    alert_mock.assert_awaited_once()


async def test_send_via_smtp_no_alert_on_non_auth_error(_setup, monkeypatch):
    monkeypatch.setattr(es_mod.settings, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(es_mod.settings, "SMTP_USER", "u@test")
    monkeypatch.setattr(es_mod.settings, "SMTP_PASS", "x")
    monkeypatch.setattr(es_mod.settings, "SMTP_USE_SSL", True)

    class _FakeSMTP:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, u, p):
            pass

        def send_message(self, m):
            raise smtplib.SMTPResponseException(451, b"temporary failure")

    alert_mock = AsyncMock(return_value=1)
    monkeypatch.setattr(es_mod.smtplib, "SMTP_SSL", _FakeSMTP)
    monkeypatch.setattr(shm_mod, "notify_smtp_auth_failed", alert_mock)

    from email.message import EmailMessage

    msg = EmailMessage()
    msg["To"] = "x@test.com"
    msg.set_content("hi")

    with pytest.raises(smtplib.SMTPResponseException):
        await es_mod.EmailService._send_via_smtp(msg)
    alert_mock.assert_not_awaited()
