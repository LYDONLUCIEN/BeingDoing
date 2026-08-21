"""
登录防爆破测试

口径（详见 auth_service 模块注释）：
- 按登录标识（email 小写 / phone）计数，不存在的账号同样计入（防枚举旁路）
- 1 小时滑动窗口内累计 5 次失败 → 锁 15 分钟（固定时长，期间重试不续期）
- 锁定期间一律拒绝（即使密码正确）；成功登录清零
- 锁定时返回 423 + JSON detail：{"type": "login_locked", "retry_after_seconds": N}
- 普通失败统一文案「邮箱/手机号或密码错误」，不区分用户不存在 / 密码错误

使用独立 in-memory SQLite + monkeypatch 替换 AsyncSessionLocal；
_login_failures 进程内内存每个测试前清空。
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.main import app
from app.models.database import Base
from app.models.user import User
from app.services import auth_service as as_mod
from app.services.auth_service import AuthService

# ─── 测试专用引擎 + 会话工厂 ──────────────────────────────────

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
_TestSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)

USER_ID = "user-lock-1"
EMAIL = "lock@test.com"
PASSWORD = "Passw0rd!"


@pytest.fixture(autouse=True)
async def _setup(monkeypatch):
    """每个测试前：建表 + 插测试用户 + monkeypatch DB + 清空锁定内存"""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    monkeypatch.setattr(as_mod, "AsyncSessionLocal", _TestSessionLocal)
    monkeypatch.setattr(as_mod, "engine", _test_engine)
    as_mod._login_failures.clear()

    now = datetime.now(timezone.utc)
    async with _TestSessionLocal() as db:
        db.add(
            User(
                id=USER_ID,
                email=EMAIL,
                username="lockuser",
                password_hash=AuthService.get_password_hash(PASSWORD),
                is_active=True,
                created_at=now,
            )
        )
        await db.commit()

    yield

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _login(client: AsyncClient, email: str, password: str):
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


# ─── 连续失败 → 锁定 ─────────────────────────────────────────


async def test_five_failures_lock_account():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 前 4 次：401 + 统一文案
        for _ in range(4):
            res = await _login(client, EMAIL, "wrong-pass")
            assert res.status_code == 401
            assert res.json()["detail"] == as_mod.LOGIN_FAIL_MESSAGE

        # 第 5 次：423 + JSON detail
        res = await _login(client, EMAIL, "wrong-pass")
        assert res.status_code == 423
        detail = json.loads(res.json()["detail"])
        assert detail["type"] == "login_locked"
        assert 0 < detail["retry_after_seconds"] <= as_mod.LOGIN_LOCK_SECONDS

        # 锁定期间：即使密码正确也一律拒绝
        res = await _login(client, EMAIL, PASSWORD)
        assert res.status_code == 423


async def test_nonexistent_account_also_locked():
    """不存在的账号同样计入锁定（否则可被用来枚举账号是否存在）"""
    ghost = "ghost@test.com"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(4):
            res = await _login(client, ghost, "whatever")
            assert res.status_code == 401
            assert res.json()["detail"] == as_mod.LOGIN_FAIL_MESSAGE

        res = await _login(client, ghost, "whatever")
        assert res.status_code == 423
        detail = json.loads(res.json()["detail"])
        assert detail["type"] == "login_locked"


async def test_unified_error_message():
    """用户不存在与密码错误返回完全一致的响应（防枚举）"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res_ghost = await _login(client, "ghost@test.com", "whatever")
        res_wrong = await _login(client, EMAIL, "wrong-pass")
    assert res_ghost.status_code == res_wrong.status_code == 401
    assert res_ghost.json()["detail"] == res_wrong.json()["detail"]


# ─── 成功登录清零 ────────────────────────────────────────────


async def test_successful_login_clears_failures():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(4):
            res = await _login(client, EMAIL, "wrong-pass")
            assert res.status_code == 401

        # 成功登录 → 计数清零
        res = await _login(client, EMAIL, PASSWORD)
        assert res.status_code == 200

        # 再错 4 次不应锁定（若未清零，这里第 4 次就会凑满窗口内 5+ 次）
        for _ in range(4):
            res = await _login(client, EMAIL, "wrong-pass")
            assert res.status_code == 401


# ─── 滑动窗口与锁定到期（单元级，直接操作内存结构）─────────────


def test_sliding_window_expires_old_failures():
    """1 小时前的失败不计入窗口"""
    key = EMAIL
    now = datetime.now(timezone.utc)
    # 4 次失败发生在 61 分钟前（窗口外）
    as_mod._login_failures[key] = {
        "fails": [now - timedelta(minutes=61)] * 4,
        "locked_until": None,
    }
    assert as_mod._record_login_failure(key) == 0  # 窗口内仅 1 次，不锁
    # 再补 3 次到窗口内 4 次，仍不锁
    for _ in range(3):
        assert as_mod._record_login_failure(key) == 0
    # 第 5 次触发锁定
    assert as_mod._record_login_failure(key) == as_mod.LOGIN_LOCK_SECONDS
    assert as_mod._get_login_lock_remaining(key) > 0


def test_lock_expiry_clears_record():
    """锁定到期后自动解锁并清零"""
    key = EMAIL
    as_mod._login_failures[key] = {
        "fails": [datetime.now(timezone.utc)] * 5,
        "locked_until": datetime.now(timezone.utc) - timedelta(seconds=1),  # 已过期
    }
    assert as_mod._get_login_lock_remaining(key) == 0
    assert key not in as_mod._login_failures
