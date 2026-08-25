"""
已登录用户修改密码测试（POST /api/v1/auth/password/change）

口径（详见 auth_service.change_password 文档字符串）：
- 需登录；校验旧密码 → 更新 hash → 撤销全部 refresh token（强制下线）→ 站内信 + 邮件通知
- 新密码 ≥6 位，且不能与旧密码相同
- 旧密码错误复用登录防爆破锁定：lock_key 与登录一致（email 小写），失败计数互通，
  1 小时滑窗 5 次失败锁 15 分钟（423 + {"type": "login_locked"}）；锁定期间旧密码正确也拒绝

使用独立 in-memory SQLite + monkeypatch 替换 AsyncSessionLocal/engine；
_login_failures 进程内内存每个测试前清空；邮件发送 mock 掉。
"""

import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.main import app
from app.models.database import Base
from app.models.feedback import Notification
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services import auth_service as as_mod
from app.services.auth_service import AuthService

# ─── 测试专用引擎 + 会话工厂 ──────────────────────────────────

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
_TestSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)

USER_ID = "user-chpwd-1"
EMAIL = "chpwd@test.com"
OLD_PASSWORD = "OldPass123"
NEW_PASSWORD = "NewPass456"


@pytest.fixture(autouse=True)
async def _setup(monkeypatch):
    """每个测试前：建表 + 插测试用户 + monkeypatch DB + 清空锁定内存 + mock 邮件"""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    monkeypatch.setattr(as_mod, "AsyncSessionLocal", _TestSessionLocal)
    monkeypatch.setattr(as_mod, "engine", _test_engine)
    as_mod._login_failures.clear()
    as_mod._refresh_schema_ready = False

    sent_emails = []

    async def _fake_send_password_changed_notice(to_email: str) -> None:
        sent_emails.append(to_email)

    monkeypatch.setattr(
        as_mod.EmailService, "send_password_changed_notice", _fake_send_password_changed_notice
    )

    async with _TestSessionLocal() as db:
        db.add(
            User(
                id=USER_ID,
                email=EMAIL,
                username="chpwduser",
                password_hash=AuthService.get_password_hash(OLD_PASSWORD),
                is_active=True,
            )
        )
        await db.commit()

    yield {"sent_emails": sent_emails}

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _login(client: AsyncClient, email: str, password: str):
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


async def _change(
    client: AsyncClient, token: str, old_password: str, new_password: str
):
    return await client.post(
        "/api/v1/auth/password/change",
        json={"old_password": old_password, "new_password": new_password},
        headers={"Authorization": f"Bearer {token}"},
    )


async def _login_token(client: AsyncClient) -> str:
    res = await _login(client, EMAIL, OLD_PASSWORD)
    assert res.status_code == 200
    return res.json()["data"]["token"]


# ─── 成功路径 ────────────────────────────────────────────────


async def test_change_password_success():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login_token(client)
        res = await _change(client, token, OLD_PASSWORD, NEW_PASSWORD)
        assert res.status_code == 200
        assert res.json()["code"] == 200

        # 旧密码登录失败，新密码登录成功
        res_old = await _login(client, EMAIL, OLD_PASSWORD)
        assert res_old.status_code == 401
        res_new = await _login(client, EMAIL, NEW_PASSWORD)
        assert res_new.status_code == 200


async def test_change_password_revokes_all_refresh_tokens():
    """修改成功后全部 refresh token 被撤销（含当前会话）→ refresh 返回 401"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _login(client, EMAIL, OLD_PASSWORD)  # 落一个 refresh token（cookie）
        token = (await _login(client, EMAIL, OLD_PASSWORD)).json()["data"]["token"]

        res = await _change(client, token, OLD_PASSWORD, NEW_PASSWORD)
        assert res.status_code == 200

        async with _TestSessionLocal() as db:
            rows = (
                (await db.execute(select(RefreshToken).where(RefreshToken.user_id == USER_ID)))
                .scalars()
                .all()
            )
        assert rows and all(r.is_revoked for r in rows)
        assert all(r.revoked_reason == "password_changed" for r in rows)

        # cookie 里的 refresh token 已失效
        res_refresh = await client.post("/api/v1/auth/refresh", json={})
        assert res_refresh.status_code == 401


async def test_change_password_sends_notification_and_email(_setup):
    sent_emails = _setup["sent_emails"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login_token(client)
        res = await _change(client, token, OLD_PASSWORD, NEW_PASSWORD)
        assert res.status_code == 200

    # 站内信
    async with _TestSessionLocal() as db:
        rows = (
            (
                await db.execute(
                    select(Notification).where(
                        Notification.user_id == USER_ID,
                        Notification.type == "password_changed",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert rows[0].read_at is None

    # 邮件通知
    assert sent_emails == [EMAIL]


# ─── 校验失败 ────────────────────────────────────────────────


async def test_wrong_old_password():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login_token(client)
        res = await _change(client, token, "wrong-old", NEW_PASSWORD)
        assert res.status_code == 400
        assert res.json()["detail"] == "旧密码不正确"

        # 密码未被修改
        res_login = await _login(client, EMAIL, OLD_PASSWORD)
        assert res_login.status_code == 200


@pytest.mark.parametrize(
    "old_pwd, new_pwd, detail",
    [
        ("", NEW_PASSWORD, "旧密码不能为空"),
        (OLD_PASSWORD, "", "新密码不能为空"),
        (OLD_PASSWORD, "12345", "新密码至少 6 位"),
        (OLD_PASSWORD, OLD_PASSWORD, "新密码不能与旧密码相同"),
    ],
)
async def test_validation_errors(old_pwd, new_pwd, detail):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login_token(client)
        res = await _change(client, token, old_pwd, new_pwd)
        assert res.status_code == 400
        assert res.json()["detail"] == detail


async def test_unauthenticated_rejected():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/password/change",
            json={"old_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
        )
        assert res.status_code == 401


# ─── 防爆破锁定（复用登录机制） ──────────────────────────────


async def test_five_wrong_old_passwords_lock():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login_token(client)
        for _ in range(4):
            res = await _change(client, token, "wrong-old", NEW_PASSWORD)
            assert res.status_code == 400

        res = await _change(client, token, "wrong-old", NEW_PASSWORD)
        assert res.status_code == 423
        detail = json.loads(res.json()["detail"])
        assert detail["type"] == "login_locked"
        assert 0 < detail["retry_after_seconds"] <= as_mod.LOGIN_LOCK_SECONDS

        # 锁定期间：即使旧密码正确也一律拒绝
        res = await _change(client, token, OLD_PASSWORD, NEW_PASSWORD)
        assert res.status_code == 423


async def test_lock_shared_with_login_failures():
    """失败计数与登录互通：4 次登录失败 + 1 次改密旧密码错误 → 锁定"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(4):
            res = await _login(client, EMAIL, "wrong-pass")
            assert res.status_code == 401

        # 用独立会话拿一个合法 token（登录成功会清零计数，所以先登录再制造失败）
        token = await _login_token(client)
        for _ in range(4):
            res = await _login(client, EMAIL, "wrong-pass")
            assert res.status_code == 401

        res = await _change(client, token, "wrong-old", NEW_PASSWORD)
        assert res.status_code == 423
        detail = json.loads(res.json()["detail"])
        assert detail["type"] == "login_locked"


async def test_successful_change_clears_failures():
    """修改成功清零失败计数"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login_token(client)
        for _ in range(4):
            res = await _change(client, token, "wrong-old", NEW_PASSWORD)
            assert res.status_code == 400

        res = await _change(client, token, OLD_PASSWORD, NEW_PASSWORD)
        assert res.status_code == 200
        assert EMAIL not in as_mod._login_failures
