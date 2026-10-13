"""注册前置邮箱验证 + 纯手机老账号强制绑邮箱（2026-10-13 起，ADR-0026）测试

覆盖：
- 发码：未注册邮箱发验证码+链接（双形态）；已注册邮箱发通知邮件并 already_registered=True
- 发码频控：单邮箱 60 秒冷却；单 IP 每小时 10 次
- 验证码形态：验码通过签发 ticket；错码计数；过期拒绝
- 链接形态：链接仅标记验证，原页轮询领 ticket（一次性消费）
- 注册接口：无 ticket 400；ticket 与邮箱不符 400；带 ticket 注册成功即已验证 + 发试用码
- 纯手机老账号登录：签发 email_binding_required 受限 token；/auth/me 拒绝受限 token
- 绑定邮箱：发码 → 确认 → 正式 token 对；占用邮箱拒绝；受限 token 绑定后失效

使用独立 in-memory SQLite + monkeypatch 替换 AsyncSessionLocal；
激活码数据根指向 tmp_path，邮件 mock，不污染真实数据。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.main  # noqa: F401  先导入 app.main，规避 simple_chat 包循环导入
import app.utils.simple_activation_manager as sam
import app.utils.trial_codes as trial_codes
from app.api.v1 import auth as auth_module
from app.main import app
from app.models.database import Base
from app.models.user import User
from app.services import auth_service as as_mod
from app.services.auth_service import AuthService
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
    send_register_mock = AsyncMock(return_value=None)
    send_exists_mock = AsyncMock(return_value=None)
    send_bind_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(as_mod.EmailService, "send_register_verification", send_register_mock)
    monkeypatch.setattr(as_mod.EmailService, "send_register_exists_notice", send_exists_mock)
    monkeypatch.setattr(as_mod.EmailService, "send_bind_email_code", send_bind_mock)

    # 清进程内内存态
    as_mod._register_verifications.clear()
    as_mod._register_code_cooldowns.clear()
    as_mod._bind_email_codes.clear()
    as_mod._login_failures.clear()
    auth_module._REGISTER_ATTEMPTS.clear()
    auth_module._REGISTER_CODE_ATTEMPTS.clear()

    yield {
        "send_register_mock": send_register_mock,
        "send_exists_mock": send_exists_mock,
        "send_bind_mock": send_bind_mock,
    }

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _create_user(
    email: str | None,
    user_id: str,
    phone: str | None = None,
    email_verified: bool = True,
) -> None:
    async with _TestSessionLocal() as db:
        db.add(
            User(
                id=user_id,
                email=email,
                phone=phone,
                username=user_id,
                password_hash=AuthService.get_password_hash(PASSWORD),
                is_active=True,
                email_verified=email_verified,
                created_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()


def _get_record(email: str) -> tuple[str, dict]:
    """按邮箱找注册验证会话记录（测试辅助）"""
    for pid, rec in as_mod._register_verifications.items():
        if rec["email"] == email:
            return pid, rec
    raise AssertionError(f"未找到 {email} 的注册验证记录")


# ─── 1. 发码 ────────────────────────────────────────────────


async def test_request_register_code_sends_dual_form(_setup):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/register/code",
            json={"email": "new@test.com"},
        )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["already_registered"] is False
    assert data["pending_id"]
    mock = _setup["send_register_mock"]
    mock.assert_awaited_once()
    kwargs = mock.await_args.kwargs
    assert kwargs["to_email"] == "new@test.com"
    assert kwargs["code"] and kwargs["link_token"]
    # 会话记录已写入
    pid, rec = _get_record("new@test.com")
    assert pid == data["pending_id"]
    assert rec["verified"] is False


async def test_request_register_code_existing_email_notice(_setup):
    await _create_user("dup@test.com", "u-dup-1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/register/code",
            json={"email": "dup@test.com"},
        )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["already_registered"] is True
    assert data["pending_id"] is None
    assert "已注册" in res.json()["message"]
    # 发的是通知邮件而非验证码
    _setup["send_exists_mock"].assert_awaited_once()
    _setup["send_register_mock"].assert_not_awaited()
    assert not as_mod._register_verifications


async def test_request_register_code_cooldown(_setup):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/v1/auth/register/code", json={"email": "cd@test.com"})
        assert res.status_code == 200
        # 60 秒内重发被拒
        res = await client.post("/api/v1/auth/register/code", json={"email": "cd@test.com"})
        assert res.status_code == 400
        assert "60 秒" in res.json()["detail"]


async def test_request_register_code_ip_rate_limit(_setup):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for i in range(auth_module.REGISTER_CODE_RATE_LIMIT_PER_HOUR):
            res = await client.post(
                "/api/v1/auth/register/code",
                json={"email": f"rl{i}@test.com"},
            )
            assert res.status_code == 200
        res = await client.post(
            "/api/v1/auth/register/code",
            json={"email": "rl-blocked@test.com"},
        )
        assert res.status_code == 429
        assert "register_code_rate_limited" in res.json()["detail"]


# ─── 2. 验证码形态 → ticket → 注册 ────────────────────────────


async def test_verify_code_then_register(_setup):
    await AuthService.request_register_verification("flow@test.com")
    pid, rec = _get_record("flow@test.com")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 错码一次
        res = await client.post(
            "/api/v1/auth/register/verify",
            json={"pending_id": pid, "email": "flow@test.com", "code": "000000"},
        )
        assert res.status_code == 400
        assert "验证码错误" in res.json()["detail"]

        # 正确验证码 → ticket
        res = await client.post(
            "/api/v1/auth/register/verify",
            json={"pending_id": pid, "email": "flow@test.com", "code": rec["code"]},
        )
        assert res.status_code == 200
        ticket = res.json()["data"]["ticket"]
        assert ticket
        # 会话一次性消费
        assert not as_mod._register_verifications

        # 带 ticket 注册
        res = await client.post(
            "/api/v1/auth/register",
            json={"email": "flow@test.com", "password": PASSWORD, "ticket": ticket},
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["token"]
        assert data["email_verified"] is True

    # 落库即已验证 + 注册完成即发试用码
    async with _TestSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.email == "flow@test.com"))
        ).scalar_one()
        assert user.email_verified is True
    assert len(list_owned_codes(user.id, "flow@test.com")) == 1


async def test_register_without_ticket_rejected(_setup):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/register",
            json={"email": "noticket@test.com", "password": PASSWORD},
        )
    assert res.status_code == 400
    assert "请先完成邮箱验证" in res.json()["detail"]


async def test_register_ticket_email_mismatch(_setup):
    ticket = AuthService._create_register_ticket("a@test.com")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/register",
            json={"email": "b@test.com", "password": PASSWORD, "ticket": ticket},
        )
    assert res.status_code == 400
    assert "不一致" in res.json()["detail"]


async def test_register_ticket_forged_type_rejected(_setup):
    """access token 不能冒充 register_ticket"""
    forged = AuthService.create_access_token({"email": "forge@test.com"})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/register",
            json={"email": "forge@test.com", "password": PASSWORD, "ticket": forged},
        )
    assert res.status_code == 400
    assert "重新验证" in res.json()["detail"]


# ─── 3. 链接形态 → 轮询 → ticket ──────────────────────────────


async def test_link_verify_then_poll(_setup):
    await AuthService.request_register_verification("link@test.com")
    pid, rec = _get_record("link@test.com")
    link_token = as_mod._create_token(
        {"pid": pid, "email": "link@test.com"},
        expires_delta=timedelta(minutes=10),
        token_type="register_verify_link",
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 验证前轮询：未通过
        res = await client.post(
            "/api/v1/auth/register/poll",
            json={"pending_id": pid, "email": "link@test.com"},
        )
        assert res.json()["data"]["verified"] is False

        # 点链接（可在任意设备）
        res = await client.get(f"/api/v1/auth/register/verify-link?token={link_token}")
        assert res.status_code == 200

        # 原页轮询 → 领 ticket（一次性）
        res = await client.post(
            "/api/v1/auth/register/poll",
            json={"pending_id": pid, "email": "link@test.com"},
        )
        data = res.json()["data"]
        assert data["verified"] is True
        assert data["ticket"]
        # 再次轮询：会话已消费
        res = await client.post(
            "/api/v1/auth/register/poll",
            json={"pending_id": pid, "email": "link@test.com"},
        )
        assert res.json()["data"]["verified"] is False


async def test_verify_link_invalid_token(_setup):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/auth/register/verify-link?token=bad-token")
    assert res.status_code == 400
    assert "无效或已过期" in res.json()["detail"]


async def test_verify_code_expired(_setup):
    await AuthService.request_register_verification("exp@test.com")
    pid, rec = _get_record("exp@test.com")
    rec["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/register/verify",
            json={"pending_id": pid, "email": "exp@test.com", "code": rec["code"]},
        )
    assert res.status_code == 400
    assert "已过期" in res.json()["detail"]


# ─── 4. 纯手机老账号：强制绑定邮箱 ─────────────────────────────


async def test_phone_only_login_requires_binding(_setup):
    await _create_user(None, "u-phone-1", phone="13800138000")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/login",
            json={"phone": "13800138000", "password": PASSWORD},
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["email_binding_required"] is True
        assert data["token"]
        assert "refresh_token" not in data

        # 受限 token 不能当正式登录态用
        me = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {data['token']}"},
        )
        assert me.status_code == 401


async def test_email_login_unaffected(_setup):
    await _create_user("normal@test.com", "u-normal-1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/login",
            json={"email": "normal@test.com", "password": PASSWORD},
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert "email_binding_required" not in data
        assert data["token"]


async def _login_phone_user(client: AsyncClient, phone: str) -> str:
    res = await client.post(
        "/api/v1/auth/login",
        json={"phone": phone, "password": PASSWORD},
    )
    assert res.status_code == 200
    return res.json()["data"]["token"]


async def test_bind_email_full_flow(_setup):
    await _create_user(None, "u-bind-1", phone="13900139000")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login_phone_user(client, "13900139000")
        headers = {"Authorization": f"Bearer {token}"}

        # 发绑定验证码
        res = await client.post(
            "/api/v1/auth/bind-email/code",
            json={"email": "bind@test.com"},
            headers=headers,
        )
        assert res.status_code == 200
        _setup["send_bind_mock"].assert_awaited_once()
        code = as_mod._bind_email_codes["bind@test.com"]["code"]

        # 确认绑定 → 正式 token
        res = await client.post(
            "/api/v1/auth/bind-email/confirm",
            json={"email": "bind@test.com", "code": code},
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["email"] == "bind@test.com"
        assert data["email_verified"] is True
        new_token = data["token"]

        # 新 token 可正常使用
        me = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {new_token}"},
        )
        assert me.status_code == 200

        # 旧受限 token 即刻失效（已绑定邮箱）
        res = await client.post(
            "/api/v1/auth/bind-email/code",
            json={"email": "other@test.com"},
            headers=headers,
        )
        assert res.status_code == 401

    # 落库已验证 + 补发试用码
    async with _TestSessionLocal() as db:
        user = (await db.execute(select(User).where(User.id == "u-bind-1"))).scalar_one()
        assert user.email == "bind@test.com"
        assert user.email_verified is True
    assert len(list_owned_codes("u-bind-1", "bind@test.com")) == 1


async def test_bind_email_taken_rejected(_setup):
    await _create_user("taken@test.com", "u-other-1")
    await _create_user(None, "u-bind-2", phone="13700137000")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login_phone_user(client, "13700137000")
        res = await client.post(
            "/api/v1/auth/bind-email/code",
            json={"email": "taken@test.com"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 400
        assert "已被其他账号使用" in res.json()["detail"]


async def test_bind_email_wrong_code(_setup):
    await _create_user(None, "u-bind-3", phone="13600136000")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login_phone_user(client, "13600136000")
        headers = {"Authorization": f"Bearer {token}"}
        await client.post(
            "/api/v1/auth/bind-email/code",
            json={"email": "bind3@test.com"},
            headers=headers,
        )
        res = await client.post(
            "/api/v1/auth/bind-email/confirm",
            json={"email": "bind3@test.com", "code": "000000"},
            headers=headers,
        )
        assert res.status_code == 400
        assert "验证码错误" in res.json()["detail"]


async def test_bind_email_requires_restricted_token(_setup):
    """普通 access token / 无 token 不能调绑定端点"""
    await _create_user("full@test.com", "u-full-1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/login",
            json={"email": "full@test.com", "password": PASSWORD},
        )
        normal_token = res.json()["data"]["token"]
        res = await client.post(
            "/api/v1/auth/bind-email/code",
            json={"email": "x@test.com"},
            headers={"Authorization": f"Bearer {normal_token}"},
        )
        assert res.status_code == 401
        res = await client.post("/api/v1/auth/bind-email/code", json={"email": "x@test.com"})
        assert res.status_code == 401
