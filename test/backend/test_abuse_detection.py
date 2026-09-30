"""用户滥用检测与限流系统测试。

覆盖：
- 消息速率阈值触发警告（首次 429 abuse_warning）
- 警告后再次触发 → 403 abuse_frozen + 激活码被 revoke + 超管站内信
- 删除对话累计超阈值触发
- token 累计超限触发（直接往 llm_usage_logs 插数据）
- 冻结态写端点统一门控（_assert_trial_phase_allowed → 403）
- 豁免用户（_can_bypass_flow_limits 为真）不计数不触发
- fail-open：DB 异常不阻断主聊天流程
- admin 配置端点 get/set + 解冻端点恢复激活码

DB 用独立 in-memory SQLite + monkeypatch 替换各模块的 AsyncSessionLocal；
激活码数据根指向 tmp_path，邮件 mock，不污染真实数据。
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.main  # noqa: F401  先导入 app.main，规避 simple_chat 包循环导入
import app.api.v1.simple_chat_routes as simple_chat_api
import app.services.abuse_config as abuse_config
import app.services.abuse_service as abuse_service
import app.utils.simple_activation_manager as sam
from app.api.v1 import admin_abuse as admin_abuse_module
from app.api.v1.auth import get_current_user
from app.config.settings import settings
from app.main import app
from app.models.abuse import AbuseEvent, AbuseState
from app.models.database import Base
from app.models.feedback import Notification
from app.models.llm_usage import LlmUsageLog
from app.models.user import User
from app.utils.simple_activation_manager import SimpleActivationManager

# ─── 测试专用引擎 + 会话工厂 ──────────────────────────────────

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
_TestSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)

TEST_USER_ID = "pytest-abuse-user"
TEST_USER = {"user_id": TEST_USER_ID, "email": "pytest-abuse@example.com"}
ADMIN_USER = {"user_id": "pytest-abuse-admin", "email": "abuse-admin@example.com"}


@pytest.fixture(autouse=True)
async def _setup(monkeypatch, tmp_path):
    """每个测试前：建表 + monkeypatch DB/激活码根/配置路径/邮件 + 清内存态"""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    monkeypatch.setattr(abuse_service, "AsyncSessionLocal", _TestSessionLocal)
    monkeypatch.setattr(admin_abuse_module, "AsyncSessionLocal", _TestSessionLocal)

    # 激活码生产/测试根 → tmp_path
    prod_base = tmp_path / "simple"
    (prod_base / "reports").mkdir(parents=True)
    test_base = tmp_path / "test_simple"
    (test_base / "reports").mkdir(parents=True)
    monkeypatch.setattr(sam, "get_simple_base_dir", lambda: prod_base)
    monkeypatch.setattr(sam, "get_simple_test_base_dir", lambda: test_base)

    # 滥用检测配置文件 → tmp_path（不污染真实 data/）
    monkeypatch.setattr(abuse_config, "_config_path", lambda: tmp_path / "abuse_config.json")

    # 邮件 mock（默认成功）
    send_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(abuse_service.EmailService, "send_email", send_mock)

    # 超管列表 mock（默认一个超管，验证冻结通知）
    async def _fake_admin_ids(db):
        return ["pytest-abuse-admin"]

    monkeypatch.setattr("app.services.feedback_service._get_super_admin_ids", _fake_admin_ids)

    # 清进程内内存态
    abuse_service._frozen_users.clear()

    # 种一个测试用户行（冻结/警告邮件按 users.email 取地址）
    async with _TestSessionLocal() as db:
        db.add(
            User(
                id=TEST_USER_ID,
                email=TEST_USER["email"],
                username="滥用测试用户",
                password_hash="x",
            )
        )
        await db.commit()

    yield {"prod_base": prod_base, "send_mock": send_mock}

    abuse_service._frozen_users.clear()
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _make_code(prod_base, user_id: str = TEST_USER_ID) -> str:
    """在测试激活码根下创建并绑定一个完整码，返回 code。"""
    manager = SimpleActivationManager(base_dir=str(prod_base))
    rec = manager.create_activation(mode="values", ttl_minutes=180, code_type="full")
    manager.claim_owner(rec.code, {"user_id": user_id, "email": "pytest-abuse@example.com"})
    return rec.code


def _code_status(prod_base, code: str) -> str:
    manager = SimpleActivationManager(base_dir=str(prod_base))
    rec = manager.get_activation(code)
    return rec.status if rec else "(missing)"


async def _get_state(user_id: str = TEST_USER_ID):
    async with _TestSessionLocal() as db:
        return (
            await db.execute(select(AbuseState).where(AbuseState.user_id == user_id))
        ).scalar_one_or_none()


async def _notifications(user_id: str):
    async with _TestSessionLocal() as db:
        return (
            (await db.execute(select(Notification).where(Notification.user_id == user_id)))
            .scalars()
            .all()
        )


def _detail_type(exc: HTTPException):
    return json.loads(exc.detail) if isinstance(exc.detail, str) else exc.detail


# ─── 消息速率阈值 → 警告 ─────────────────────────────────────


async def test_message_rate_first_trigger_warns(_setup):
    """msg_per_minute 超过阈值首次触发 → 429 abuse_warning + 状态 warned + 用户站内信/邮件"""
    abuse_config.set_config({"msg_per_minute": 2})
    code = _make_code(_setup["prod_base"])

    # 前 2 条不触发（count > threshold 才触发）
    await abuse_service.record_and_check_message(TEST_USER_ID, code, "values")
    await abuse_service.record_and_check_message(TEST_USER_ID, code, "values")

    # 第 3 条触发警告
    with pytest.raises(HTTPException) as exc_info:
        await abuse_service.record_and_check_message(TEST_USER_ID, code, "values")
    assert exc_info.value.status_code == 429
    detail = _detail_type(exc_info.value)
    assert detail["type"] == "abuse_warning"
    assert detail["rule"] == "msg_per_minute"

    state = await _get_state()
    assert state is not None
    assert state.status == "warned"
    assert state.warned_rule == "msg_per_minute"

    notes = await _notifications(TEST_USER_ID)
    assert any(n.type == "abuse_warning" for n in notes)
    assert _setup["send_mock"].await_count >= 1  # 警告邮件已尝试发送


async def test_second_trigger_freezes_and_revokes(_setup):
    """警告后再次触发任一规则 → 403 abuse_frozen + 激活码 revoke + 超管站内信 + 内存缓存"""
    abuse_config.set_config({"msg_per_minute": 1})
    code = _make_code(_setup["prod_base"])

    await abuse_service.record_and_check_message(TEST_USER_ID, code, "values")
    with pytest.raises(HTTPException) as exc_warn:
        await abuse_service.record_and_check_message(TEST_USER_ID, code, "values")
    assert exc_warn.value.status_code == 429
    assert _code_status(_setup["prod_base"], code) == "active"  # 警告不 revoke

    # 再次触发 → 冻结
    with pytest.raises(HTTPException) as exc_frozen:
        await abuse_service.record_and_check_message(TEST_USER_ID, code, "values")
    assert exc_frozen.value.status_code == 403
    detail = _detail_type(exc_frozen.value)
    assert detail["type"] == "abuse_frozen"

    state = await _get_state()
    assert state.status == "frozen"
    assert state.frozen_rule == "msg_per_minute"
    assert state.frozen_activation_code == code
    assert _code_status(_setup["prod_base"], code) == "revoked"  # 激活码被 revoke

    # 内存缓存同步（门控热路径）
    info = abuse_service.is_frozen(TEST_USER_ID)
    assert info is not None and info["rule"] == "msg_per_minute"

    # 用户冻结站内信 + 超管告警站内信
    user_notes = await _notifications(TEST_USER_ID)
    assert any(n.type == "abuse_frozen" for n in user_notes)
    admin_notes = await _notifications("pytest-abuse-admin")
    assert any(n.type == "abuse_frozen_admin" for n in admin_notes)
    admin_note = next(n for n in admin_notes if n.type == "abuse_frozen_admin")
    assert TEST_USER_ID in admin_note.content
    assert code in admin_note.content


async def test_frozen_gate_blocks_write_endpoints(_setup):
    """冻结态门控：_assert_trial_phase_allowed 对所有写端点统一 403（纯内存检查）"""
    abuse_config.set_config({"msg_per_minute": 1})
    code = _make_code(_setup["prod_base"])
    await abuse_service.record_and_check_message(TEST_USER_ID, code, "values")
    with pytest.raises(HTTPException):
        await abuse_service.record_and_check_message(TEST_USER_ID, code, "values")
    with pytest.raises(HTTPException):
        await abuse_service.record_and_check_message(TEST_USER_ID, code, "values")
    assert abuse_service.is_frozen(TEST_USER_ID) is not None

    # rec=None 也要安全（门控不因缺激活记录而跳过冻结检查）
    with pytest.raises(HTTPException) as exc_info:
        simple_chat_api._assert_trial_phase_allowed(None, TEST_USER, "values")
    assert exc_info.value.status_code == 403
    assert _detail_type(exc_info.value)["type"] == "abuse_frozen"


# ─── 删除对话阈值 ────────────────────────────────────────────


async def test_thread_delete_threshold_triggers(_setup):
    """同一 phase 累计删除超过阈值（默认 3，第 4 次）触发警告"""
    code = _make_code(_setup["prod_base"])
    for _ in range(3):
        await abuse_service.record_and_check_thread_delete(TEST_USER_ID, code, "values")

    with pytest.raises(HTTPException) as exc_info:
        await abuse_service.record_and_check_thread_delete(TEST_USER_ID, code, "values")
    assert exc_info.value.status_code == 429
    assert _detail_type(exc_info.value)["rule"] == "thread_delete_per_phase"


async def test_thread_delete_threshold_is_per_phase(_setup):
    """删除计数按 phase 隔离：不同 phase 的删除不累计"""
    code = _make_code(_setup["prod_base"])
    for phase in ("values", "strengths", "interests"):
        for _ in range(3):
            await abuse_service.record_and_check_thread_delete(TEST_USER_ID, code, phase)
    # 每个 phase 都只删了 3 次（未超阈值），不触发
    state = await _get_state()
    assert state is None


# ─── token 累计阈值 ──────────────────────────────────────────


async def test_token_lifetime_threshold_triggers(_setup):
    """llm_usage_logs 累计 token（user_id 直存，无前缀）超阈值触发警告"""
    abuse_config.set_config({"token_lifetime": 1000})
    code = _make_code(_setup["prod_base"])
    async with _TestSessionLocal() as db:
        db.add(
            LlmUsageLog(
                user_id=TEST_USER_ID,
                scene="chat",
                prompt_tokens=800,
                completion_tokens=300,
            )
        )
        await db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await abuse_service.record_and_check_message(TEST_USER_ID, code, "values")
    assert exc_info.value.status_code == 429
    assert _detail_type(exc_info.value)["rule"] == "token_lifetime"


# ─── 豁免与 fail-open ────────────────────────────────────────


async def test_bypass_user_not_recorded(_setup, monkeypatch):
    """豁免用户（_can_bypass_flow_limits 为真）：路由层 helper 直接跳过计数"""
    calls = {"n": 0}

    async def fake_record(*args, **kwargs):
        calls["n"] += 1

    monkeypatch.setattr(abuse_service, "record_and_check_message", fake_record)
    monkeypatch.setattr(simple_chat_api, "_can_bypass_flow_limits", lambda *a: True)
    await simple_chat_api._record_abuse_message_event(None, TEST_USER, "CODE", "values")
    assert calls["n"] == 0

    monkeypatch.setattr(simple_chat_api, "_can_bypass_flow_limits", lambda *a: False)
    await simple_chat_api._record_abuse_message_event(None, TEST_USER, "CODE", "values")
    assert calls["n"] == 1


async def test_db_error_fails_open(_setup, monkeypatch):
    """DB 异常不阻断主聊天流程（fail-open，只记日志）"""

    class _BrokenSession:
        async def __aenter__(self):
            raise RuntimeError("db down")

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(abuse_service, "AsyncSessionLocal", lambda: _BrokenSession())
    # 不抛异常 = 放行
    await abuse_service.record_and_check_message(TEST_USER_ID, "CODE", "values")
    await abuse_service.record_and_check_thread_delete(TEST_USER_ID, "CODE", "values")


async def test_disabled_config_skips_checks(_setup):
    """enabled=false 时完全不检测"""
    abuse_config.set_config({"enabled": False, "msg_per_minute": 1})
    code = _make_code(_setup["prod_base"])
    for _ in range(5):
        await abuse_service.record_and_check_message(TEST_USER_ID, code, "values")
    state = await _get_state()
    assert state is None


# ─── admin 配置端点 ──────────────────────────────────────────


async def test_admin_config_get_and_set(_setup, monkeypatch):
    """admin 配置端点：GET 返回生效配置+默认+范围；POST 部分更新即时生效；非法值 400"""
    monkeypatch.setattr(settings, "SUPER_ADMIN_USER_IDS", ADMIN_USER["user_id"])
    app.dependency_overrides[get_current_user] = lambda: ADMIN_USER
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/admin/abuse/config")
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["config"]["msg_per_minute"] == abuse_config.DEFAULTS["msg_per_minute"]
            assert data["defaults"]["token_lifetime"] == 5_000_000
            assert data["ranges"]["min"] == 1

            resp = await client.post("/api/v1/admin/abuse/config", json={"msg_per_minute": 5})
            assert resp.status_code == 200
            assert resp.json()["data"]["config"]["msg_per_minute"] == 5
            # 其他键保持默认
            assert resp.json()["data"]["config"]["msg_per_hour"] == 360
            assert abuse_config.get_config()["msg_per_minute"] == 5

            # 非法值 → 400
            resp = await client.post("/api/v1/admin/abuse/config", json={"msg_per_minute": 0})
            assert resp.status_code == 400
            resp = await client.post("/api/v1/admin/abuse/config", json={"unknown_key": 1})
            assert resp.status_code == 400
    finally:
        app.dependency_overrides.clear()


async def test_admin_config_forbidden_for_non_admin(_setup, monkeypatch):
    """非超管访问 admin 端点 → 403"""
    monkeypatch.setattr(settings, "SUPER_ADMIN_USER_IDS", ADMIN_USER["user_id"])
    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/admin/abuse/config")
            assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


# ─── 解冻 ────────────────────────────────────────────────────


async def test_unfreeze_restores_code_and_state(_setup, monkeypatch):
    """解冻：激活码恢复 active、状态行删除、内存清理、用户收到解冻站内信"""
    abuse_config.set_config({"msg_per_minute": 1})
    code = _make_code(_setup["prod_base"])
    await abuse_service.record_and_check_message(TEST_USER_ID, code, "values")
    with pytest.raises(HTTPException):
        await abuse_service.record_and_check_message(TEST_USER_ID, code, "values")
    with pytest.raises(HTTPException):
        await abuse_service.record_and_check_message(TEST_USER_ID, code, "values")
    assert abuse_service.is_frozen(TEST_USER_ID) is not None
    assert _code_status(_setup["prod_base"], code) == "revoked"

    result = await abuse_service.unfreeze_user(TEST_USER_ID, actor_user_id="pytest-abuse-admin")
    assert result["status"] == "normal"
    assert result["restored_code"] == code
    assert _code_status(_setup["prod_base"], code) == "active"
    assert abuse_service.is_frozen(TEST_USER_ID) is None
    assert await _get_state() is None
    notes = await _notifications(TEST_USER_ID)
    assert any(n.type == "abuse_unfrozen" for n in notes)


async def test_admin_unfreeze_endpoint(_setup, monkeypatch):
    """admin 解冻端点：冻结用户经 POST /admin/abuse/users/{user_id}/unfreeze 恢复正常"""
    abuse_config.set_config({"msg_per_minute": 1})
    code = _make_code(_setup["prod_base"])
    await abuse_service.record_and_check_message(TEST_USER_ID, code, "values")
    with pytest.raises(HTTPException):
        await abuse_service.record_and_check_message(TEST_USER_ID, code, "values")
    with pytest.raises(HTTPException):
        await abuse_service.record_and_check_message(TEST_USER_ID, code, "values")

    monkeypatch.setattr(settings, "SUPER_ADMIN_USER_IDS", ADMIN_USER["user_id"])
    app.dependency_overrides[get_current_user] = lambda: ADMIN_USER
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 冻结用户出现在列表里
            resp = await client.get("/api/v1/admin/abuse/users?status=frozen")
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["total"] == 1
            item = data["items"][0]
            assert item["user_id"] == TEST_USER_ID
            assert item["frozen_activation_code"] == code
            assert item["messages_24h"] >= 3

            # 事件流水
            resp = await client.get(f"/api/v1/admin/abuse/users/{TEST_USER_ID}/events")
            assert resp.status_code == 200
            events = resp.json()["data"]
            assert events["total"] >= 3
            assert events["items"][0]["event_type"] == "message"

            # 解冻
            resp = await client.post(f"/api/v1/admin/abuse/users/{TEST_USER_ID}/unfreeze")
            assert resp.status_code == 200
            result = resp.json()["data"]
            assert result["status"] == "normal"
            assert result["restored_code"] == code
    finally:
        app.dependency_overrides.clear()

    assert _code_status(_setup["prod_base"], code) == "active"
    assert abuse_service.is_frozen(TEST_USER_ID) is None


# ─── 事件流水落库 ────────────────────────────────────────────


async def test_events_persisted(_setup):
    """每次消息/删除都会落一条 AbuseEvent（含 phase）"""
    code = _make_code(_setup["prod_base"])
    await abuse_service.record_and_check_message(TEST_USER_ID, code, "values")
    await abuse_service.record_and_check_thread_delete(TEST_USER_ID, code, "strengths")
    async with _TestSessionLocal() as db:
        rows = (
            (await db.execute(select(AbuseEvent).where(AbuseEvent.user_id == TEST_USER_ID)))
            .scalars()
            .all()
        )
    assert len(rows) == 2
    by_type = {r.event_type: r for r in rows}
    assert by_type["message"].phase == "values"
    assert by_type["thread_delete"].phase == "strengths"


async def test_load_frozen_users_from_db(_setup):
    """启动加载：DB 中 frozen 行恢复到内存缓存"""
    abuse_config.set_config({"msg_per_minute": 1})
    code = _make_code(_setup["prod_base"])
    await abuse_service.record_and_check_message(TEST_USER_ID, code, "values")
    with pytest.raises(HTTPException):
        await abuse_service.record_and_check_message(TEST_USER_ID, code, "values")
    with pytest.raises(HTTPException):
        await abuse_service.record_and_check_message(TEST_USER_ID, code, "values")

    # 模拟重启：清内存后从 DB 重载
    abuse_service._frozen_users.clear()
    loaded = await abuse_service.load_frozen_users()
    assert loaded == 1
    info = abuse_service.is_frozen(TEST_USER_ID)
    assert info is not None and info["code"] == code
