"""
refresh token 轮换宽限期测试（REFRESH_TOKEN_ROTATE_GRACE_SECONDS）

背景：前端存在多条 refresh 通道（axios 拦截器 single-flight / 聊天页流式自建 fetch），
access token 到期瞬间多通道并发 refresh，携带同一旧 refresh token：
- 第一个请求成功轮换（旧 token 置 revoked_reason="rotated"）
- 第二个请求被判"重放攻击"撤销整个 token 族 → 用户 1 小时后准时掉线

修复：宽限期（默认 10s）内重放已轮换旧 token 视为正常并发刷新，照常换发；
宽限窗外重放维持撤销整族的防盗语义；窗口锚定首次轮换时间，重放不续期。

测试模式同 test_change_password.py：独立 in-memory SQLite + monkeypatch 替换
AsyncSessionLocal/engine。
"""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.main import app
from app.models.database import Base
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services import auth_service as as_mod
from app.services.auth_service import AuthService

# ─── 测试专用引擎 + 会话工厂 ──────────────────────────────────

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
_TestSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)

USER_ID = "user-refresh-1"
EMAIL = "refresh@test.com"
PASSWORD = "Pass123456"


@pytest.fixture(autouse=True)
async def _setup(monkeypatch):
    """每个测试前：建表 + 插测试用户 + monkeypatch DB + 清空锁定内存"""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    monkeypatch.setattr(as_mod, "AsyncSessionLocal", _TestSessionLocal)
    monkeypatch.setattr(as_mod, "engine", _test_engine)
    as_mod._login_failures.clear()
    as_mod._refresh_schema_ready = False

    async with _TestSessionLocal() as db:
        db.add(
            User(
                id=USER_ID,
                email=EMAIL,
                username="refreshuser",
                password_hash=AuthService.get_password_hash(PASSWORD),
                is_active=True,
            )
        )
        await db.commit()

    yield

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _login_get_refresh_token(client: AsyncClient) -> str:
    """登录并取出 cookie 里的 refresh token"""
    res = await client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert res.status_code == 200
    token = client.cookies.get("bd_refresh_token")
    assert token
    return token


async def _refresh(client: AsyncClient, refresh_token: str):
    """显式用 body 传 refresh token（优先于 cookie，可精确模拟"重放旧 token"）"""
    return await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})


async def _family_tokens() -> list[RefreshToken]:
    async with _TestSessionLocal() as db:
        return list(
            (
                await db.execute(select(RefreshToken).where(RefreshToken.user_id == USER_ID))
            )
            .scalars()
            .all()
        )


# ─── 宽限期行为 ──────────────────────────────────────────────


async def test_rotate_and_reuse_within_grace_ok():
    """宽限期内重放已轮换旧 token：视为并发刷新，照常换发，不撤族"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        old_token = await _login_get_refresh_token(client)

        # 第一次 refresh：正常轮换，拿到新 refresh token
        res1 = await _refresh(client, old_token)
        assert res1.status_code == 200
        new_token = client.cookies.get("bd_refresh_token")
        assert new_token and new_token != old_token

        # 宽限期内用旧 token 重放（模拟并发双通道 refresh 的第二个请求）
        res2 = await _refresh(client, old_token)
        assert res2.status_code == 200, res2.text
        assert res2.json()["data"]["token"]

        # 第一次换到的新 token 不被株连，仍可使用
        res3 = await _refresh(client, new_token)
        assert res3.status_code == 200, res3.text

        # 族内无 reuse_detected 撤销
        rows = await _family_tokens()
        assert all(r.revoked_reason != "reuse_detected" for r in rows)


async def test_reuse_after_grace_revokes_family(monkeypatch):
    """宽限窗外重放已轮换旧 token：维持防盗语义，撤销整族"""
    monkeypatch.setattr(as_mod, "REFRESH_TOKEN_ROTATE_GRACE_SECONDS", 0)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        old_token = await _login_get_refresh_token(client)

        res1 = await _refresh(client, old_token)
        assert res1.status_code == 200
        new_token = client.cookies.get("bd_refresh_token")
        assert new_token and new_token != old_token

        # 宽限为 0：旧 token 重放立即触发撤族
        res2 = await _refresh(client, old_token)
        assert res2.status_code == 401
        assert "已失效" in res2.json()["detail"]

        # 整族（含刚签发的新 token）全部被撤销
        rows = await _family_tokens()
        assert rows and all(r.is_revoked for r in rows)
        assert any(r.revoked_reason == "reuse_detected" for r in rows)

        # 新 token 同样不可用
        res3 = await _refresh(client, new_token)
        assert res3.status_code == 401


async def test_grace_window_not_extended_by_replay(monkeypatch):
    """宽限窗口锚定首次轮换时间：反复重放不给窗口续期"""
    monkeypatch.setattr(as_mod, "REFRESH_TOKEN_ROTATE_GRACE_SECONDS", 1)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        old_token = await _login_get_refresh_token(client)

        res1 = await _refresh(client, old_token)
        assert res1.status_code == 200

        # 0.6s 后重放：宽限内（距首次轮换 0.6s < 1s）
        await asyncio.sleep(0.6)
        res2 = await _refresh(client, old_token)
        assert res2.status_code == 200, res2.text

        # 再 0.6s 后重放：距首次轮换 1.2s > 1s，
        # 若重放会续期窗口则此处仍判宽限内（距上次重放 0.6s < 1s）→ 可区分两种实现
        await asyncio.sleep(0.6)
        res3 = await _refresh(client, old_token)
        assert res3.status_code == 401
        assert "已失效" in res3.json()["detail"]


async def test_normal_rotate_flow_unchanged():
    """常规链路回归：登录 → refresh 轮换 → 新 token 可继续 refresh"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        t1 = await _login_get_refresh_token(client)
        res1 = await _refresh(client, t1)
        assert res1.status_code == 200
        t2 = client.cookies.get("bd_refresh_token")
        assert t2 and t2 != t1

        res2 = await _refresh(client, t2)
        assert res2.status_code == 200
        t3 = client.cookies.get("bd_refresh_token")
        assert t3 and t3 != t2
