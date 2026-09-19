"""
登录防爆破测试

口径（详见 auth_service 模块注释，2026-09-18 起阶梯锁定 + 每小时整窗重置）：
- 按登录标识（email 小写 / phone）计数，不存在的账号同样计入（防枚举旁路）
- 前 5 次失败不锁；第 6/7/8/9 次失败后分别锁 1/2/5/10 分钟，第 9 次起恒锁 10 分钟
- 每小时整窗重置：从首次失败起满 1 小时清零，重新有连续 5 次机会
- 锁定期间一律拒绝（即使密码正确），锁定期重试不计数、不续期；成功登录清零
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


# ─── 连续失败 → 阶梯锁定 ──────────────────────────────────────


async def test_sixth_failure_locks_one_minute():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 前 5 次：401 + 统一文案（免费机会，不锁）
        for _ in range(5):
            res = await _login(client, EMAIL, "wrong-pass")
            assert res.status_code == 401
            assert res.json()["detail"] == as_mod.LOGIN_FAIL_MESSAGE

        # 第 6 次：423 + JSON detail，锁 1 分钟
        res = await _login(client, EMAIL, "wrong-pass")
        assert res.status_code == 423
        detail = json.loads(res.json()["detail"])
        assert detail["type"] == "login_locked"
        assert 0 < detail["retry_after_seconds"] <= as_mod.LOGIN_LOCK_LADDER_SECONDS[0]

        # 锁定期间：即使密码正确也一律拒绝
        res = await _login(client, EMAIL, PASSWORD)
        assert res.status_code == 423


async def test_nonexistent_account_also_locked():
    """不存在的账号同样计入锁定（否则可被用来枚举账号是否存在）"""
    ghost = "ghost@test.com"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(5):
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
        for _ in range(5):
            res = await _login(client, EMAIL, "wrong-pass")
            assert res.status_code == 401

        # 成功登录 → 计数清零
        res = await _login(client, EMAIL, PASSWORD)
        assert res.status_code == 200

        # 再错 5 次不应锁定（若未清零，这里第 1 次就会凑满 6 次触发锁定）
        for _ in range(5):
            res = await _login(client, EMAIL, "wrong-pass")
            assert res.status_code == 401


# ─── 阶梯 / 整窗重置 / 锁定到期（单元级，直接操作内存结构）─────


def _make_rec(fails: int, first_fail_at=None, locked_until=None):
    return {
        "first_fail_at": first_fail_at or datetime.now(timezone.utc),
        "fails": fails,
        "locked_until": locked_until,
    }


def test_lock_ladder_progression():
    """阶梯：第 6/7/8/9 次失败后锁 1/2/5/10 分钟，第 9 次起恒 10 分钟"""
    key = EMAIL
    expected = as_mod.LOGIN_LOCK_LADDER_SECONDS  # (60, 120, 300, 600)
    # 前 5 次免费
    for _ in range(as_mod.LOGIN_FAIL_FREE_ATTEMPTS):
        assert as_mod._record_login_failure(key) == 0
    # 第 6/7/8/9 次：1/2/5/10 分钟
    for lock_seconds in expected:
        assert as_mod._record_login_failure(key) == lock_seconds
    # 第 10、11 次：恒 10 分钟
    assert as_mod._record_login_failure(key) == expected[-1]
    assert as_mod._record_login_failure(key) == expected[-1]
    assert as_mod._get_login_lock_remaining(key) > 0


def test_window_resets_one_hour_after_first_failure():
    """整窗重置：从首次失败起满 1 小时清零，重新有连续 5 次机会"""
    key = EMAIL
    now = datetime.now(timezone.utc)
    # 5 次失败的首次发生在 61 分钟前（窗口已过期）
    as_mod._login_failures[key] = _make_rec(
        fails=5, first_fail_at=now - timedelta(minutes=61)
    )
    assert as_mod._record_login_failure(key) == 0  # 重置后仅 1 次，不锁
    assert as_mod._login_failures[key]["fails"] == 1
    # 重置后继续错到第 5 次仍不锁，第 6 次才锁
    for _ in range(4):
        assert as_mod._record_login_failure(key) == 0
    assert as_mod._record_login_failure(key) == as_mod.LOGIN_LOCK_LADDER_SECONDS[0]


def test_lock_expiry_keeps_window_count():
    """锁定到期只解锁不清零：窗口内计数保留，下一次失败沿阶梯递增"""
    key = EMAIL
    now = datetime.now(timezone.utc)
    as_mod._login_failures[key] = _make_rec(
        fails=6, first_fail_at=now, locked_until=now - timedelta(seconds=1)  # 锁已过期
    )
    assert as_mod._get_login_lock_remaining(key) == 0
    # 记录保留（窗口未过期），第 7 次失败 → 锁 2 分钟
    assert as_mod._record_login_failure(key) == as_mod.LOGIN_LOCK_LADDER_SECONDS[1]


def test_window_reset_after_lock_expired_clears_record():
    """锁与窗口都已过期：下一次尝试时清零并移除记录"""
    key = EMAIL
    now = datetime.now(timezone.utc)
    as_mod._login_failures[key] = _make_rec(
        fails=9,
        first_fail_at=now - timedelta(minutes=61),
        locked_until=now - timedelta(seconds=1),
    )
    assert as_mod._get_login_lock_remaining(key) == 0
    assert key not in as_mod._login_failures
