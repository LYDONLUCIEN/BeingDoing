"""
试用激活码体系（P-A，ADR-0008）测试

覆盖：
- 试用码创建（不过期 / vip_level=1 / code_type=trial）
- 存量 JSON 兼容（无新字段一律 full）
- 注册送码（含送码失败不阻断注册）
- 老用户懒补发（0 码用户调 journeys 自动获得且不重复）
- 10 轮门控（9/10/11 条场景，402 结构与 type 断言，internal 消息不计轮）
- 阶段锁（非 values 写请求 402 trial_phase_locked）
- 只读端点不拦
- 存量 full 码不受任何限制
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException, Response

import app.main  # noqa: F401  先导入 app.main，规避 simple_chat 包循环导入
import app.api.v1.simple_chat_routes as scr
import app.utils.simple_activation_manager as sam
import app.utils.trial_codes as trial_codes
from app.api.v1 import auth as auth_module
from app.api.v1 import simple_auth as simple_auth_module
from app.utils.report_registry import ReportRegistry
from app.utils.simple_activation_manager import SimpleActivationManager
from app.utils.trial_codes import (
    TRIAL_VALUES_USER_MESSAGE_LIMIT,
    count_values_user_messages,
    create_trial_activation_for_user,
    ensure_trial_code_for_user,
    is_trial_code,
)


# ──────────────────────────────────────────────────────────────────
# Fixtures / 工具
# ──────────────────────────────────────────────────────────────────


@pytest.fixture
def prod_base(tmp_path: Path) -> Path:
    base = tmp_path / "simple"
    (base / "reports").mkdir(parents=True)
    return base


@pytest.fixture
def test_base(tmp_path: Path) -> Path:
    base = tmp_path / "test_simple"
    (base / "reports").mkdir(parents=True)
    return base


@pytest.fixture
def patched_roots(prod_base: Path, test_base: Path, monkeypatch):
    """把生产/测试两个 simple 数据根都指向临时目录。"""
    monkeypatch.setattr(sam, "get_simple_base_dir", lambda: prod_base)
    monkeypatch.setattr(sam, "get_simple_test_base_dir", lambda: test_base)
    monkeypatch.setattr(trial_codes, "get_simple_base_dir", lambda: prod_base)
    monkeypatch.setattr(trial_codes, "get_simple_test_base_dir", lambda: test_base)
    return prod_base, test_base


@pytest.fixture
def manager(prod_base: Path) -> SimpleActivationManager:
    return SimpleActivationManager(base_dir=str(prod_base))


USER = {"user_id": "u-trial-1", "email": "trial@example.com"}


def _write_values_thread(
    registry: ReportRegistry, report_id: str, tid: str, n_user: int, n_internal: int = 0
) -> None:
    """构造 values 线程文件：n_user 条真实用户消息 + n_internal 条 internal 协议消息。"""
    registry.bind_session(report_id, "values", tid)
    messages = []
    for i in range(n_user):
        messages.append({"role": "user", "content": f"回答 {i + 1}"})
        messages.append({"role": "assistant", "content": f"追问 {i + 1}"})
    for j in range(n_internal):
        messages.append({"role": "user", "content": "[表格操作]", "internal": True})
    f = registry.get_step_session_file(report_id, "values", tid)
    f.write_text(json.dumps({"messages": messages}, ensure_ascii=False), encoding="utf-8")


def _make_bound_code(
    manager: SimpleActivationManager,
    user: dict,
    code_type: str = "trial",
    n_values_msgs: int = 0,
    n_internal: int = 0,
):
    """创建并绑定激活码，同时建立 report 与 values 线程。返回 (rec, registry, report_id)。"""
    rec = manager.create_activation(mode="combined", code_type=code_type)
    manager.claim_owner(rec.code, user)
    registry = ReportRegistry(base_dir=str(manager.base_dir))
    report = registry.ensure_report(activation_code=rec.code, user_id=user["user_id"])
    rid = report["report_id"]
    if n_values_msgs or n_internal:
        _write_values_thread(registry, rid, "t_1", n_values_msgs, n_internal)
    return rec, registry, rid


def _patch_manager_lookup(monkeypatch, manager: SimpleActivationManager):
    monkeypatch.setattr(scr, "get_activation_manager_for_code", lambda code: manager)


# ──────────────────────────────────────────────────────────────────
# 1. 试用码创建
# ──────────────────────────────────────────────────────────────────


def test_create_trial_code_no_expiry_vip1(manager: SimpleActivationManager):
    rec = manager.create_activation(mode="combined", code_type="trial")
    assert rec.code_type == "trial"
    assert rec.expires_at is None  # 试用码不过期
    assert rec.vip_level == 1
    assert rec.status == "active"
    # 重新加载：不会因为没有 expires_at 被误判 expired
    loaded = manager.get_activation(rec.code)
    assert loaded is not None
    assert loaded.status == "active"
    assert loaded.code_type == "trial"
    assert loaded.expires_at is None


def test_create_full_code_unchanged(manager: SimpleActivationManager):
    rec = manager.create_activation(mode="combined", ttl_minutes=60)
    assert rec.code_type == "full"
    assert rec.expires_at is not None
    assert rec.vip_level == 1  # full 默认档位保持历史行为（P-B 升级时再调）


def test_create_activation_invalid_code_type(manager: SimpleActivationManager):
    with pytest.raises(ValueError):
        manager.create_activation(mode="combined", code_type="bogus")


# ──────────────────────────────────────────────────────────────────
# 2. 存量 JSON 兼容
# ──────────────────────────────────────────────────────────────────


def test_legacy_record_defaults_to_full(manager: SimpleActivationManager, prod_base: Path):
    legacy = {
        "LEGACY01AB": {
            "code": "LEGACY01AB",
            "session_id": "sess-legacy",
            "activation_session_id": "sess-legacy",
            "mode": "combined",
            "created_at": "2026-01-01T00:00:00+00:00",
            "expires_at": "2036-01-01T00:00:00+00:00",
            "last_activity_at": "2026-01-01T00:00:00+00:00",
            "status": "active",
        }
    }
    (prod_base / "activations.json").write_text(json.dumps(legacy), encoding="utf-8")
    rec = manager.get_activation("LEGACY01AB")
    assert rec is not None
    assert rec.code_type == "full"  # 存量一律 full
    assert rec.package_type is None
    assert rec.source_order_id is None
    assert rec.purchaser_user_id is None
    assert rec.report_authorized is False
    assert not is_trial_code(rec)


# ──────────────────────────────────────────────────────────────────
# 3. 注册送码
# ──────────────────────────────────────────────────────────────────


async def test_register_grants_trial_code(patched_roots, prod_base: Path, monkeypatch):
    fake = {
        "user_id": "u-reg-1",
        "email": "reg@example.com",
        "refresh_token": "rt",
        "access_token": "at",
    }

    async def fake_register(**kwargs):
        return dict(fake)

    monkeypatch.setattr(auth_module.AuthService, "register", staticmethod(fake_register))

    req = auth_module.RegisterRequest(email="reg@example.com", password="pw123456")
    out = await auth_module.register(req, Response())
    assert out.code == 200

    mgr = SimpleActivationManager(base_dir=str(prod_base))
    owned = [r for r in mgr.list_activations().values() if r.owner_user_id == "u-reg-1"]
    assert len(owned) == 1
    rec = owned[0]
    assert rec.code_type == "trial"
    assert rec.expires_at is None
    assert rec.vip_level == 1
    assert rec.claimed_at is not None  # 已自动绑定


async def test_register_survives_trial_grant_failure(
    patched_roots, prod_base: Path, monkeypatch
):
    async def fake_register(**kwargs):
        return {"user_id": "u-reg-2", "email": "reg2@example.com", "refresh_token": None}

    def boom(user):
        raise RuntimeError("disk full")

    monkeypatch.setattr(auth_module.AuthService, "register", staticmethod(fake_register))
    monkeypatch.setattr(trial_codes, "create_trial_activation_for_user", boom)

    req = auth_module.RegisterRequest(email="reg2@example.com", password="pw123456")
    out = await auth_module.register(req, Response())
    assert out.code == 200  # 送码失败不阻断注册


# ──────────────────────────────────────────────────────────────────
# 4. 老用户懒补发
# ──────────────────────────────────────────────────────────────────


def test_ensure_trial_code_grants_once(patched_roots, prod_base: Path):
    rec = ensure_trial_code_for_user(USER)
    assert rec is not None
    assert rec.code_type == "trial"
    assert rec.owner_user_id == USER["user_id"]
    # 再次调用不重复发
    assert ensure_trial_code_for_user(USER) is None
    mgr = SimpleActivationManager(base_dir=str(prod_base))
    owned = [r for r in mgr.list_activations().values() if r.owner_user_id == USER["user_id"]]
    assert len(owned) == 1


def test_ensure_trial_code_skipped_when_user_has_code(patched_roots, manager):
    create_trial_activation_for_user(USER, manager=manager)
    assert ensure_trial_code_for_user(USER) is None


async def test_journeys_lazy_grant_and_fields(patched_roots, prod_base: Path):
    # 0 码老用户调 journeys → 自动获得试用码
    out = await simple_auth_module.list_user_journeys(current_user=dict(USER))
    journeys = out.data["journeys"]
    assert len(journeys) == 1
    j = journeys[0]
    assert j["code_type"] == "trial"
    assert j["activation_code"]
    assert j["expires_at"] is None  # 试用码不过期
    # 再次调用不重复发
    out2 = await simple_auth_module.list_user_journeys(current_user=dict(USER))
    assert len(out2.data["journeys"]) == 1
    assert out2.data["journeys"][0]["activation_code"] == j["activation_code"]


# ──────────────────────────────────────────────────────────────────
# 5. my-codes 端点
# ──────────────────────────────────────────────────────────────────


async def test_my_codes_lists_owned_codes(patched_roots, manager, prod_base: Path):
    trial = create_trial_activation_for_user(USER, manager=manager)
    full = manager.create_activation(mode="combined", code_type="full")
    manager.claim_owner(full.code, USER)
    # 其他用户的码不应出现
    other = manager.create_activation(mode="combined", code_type="full")
    manager.claim_owner(other.code, {"user_id": "someone-else", "email": "x@example.com"})
    # 固定 created_at 保证倒序可断言
    data = json.loads((prod_base / "activations.json").read_text(encoding="utf-8"))
    data[trial.code]["created_at"] = "2026-01-01T00:00:00+00:00"
    data[full.code]["created_at"] = "2026-02-01T00:00:00+00:00"
    (prod_base / "activations.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    out = await simple_auth_module.list_my_codes(current_user=dict(USER))
    items = out.data["items"]
    assert [i["code"] for i in items] == [full.code, trial.code]  # 创建时间倒序
    full_item, trial_item = items
    assert full_item["code_type"] == "full"
    assert full_item["source"] == "admin"
    assert full_item["status"] == "active"
    assert full_item["has_report"] is False
    assert full_item["session_id"]
    assert trial_item["code_type"] == "trial"
    assert trial_item["source"] == "试用赠送"
    assert trial_item["expires_at"] is None
    assert all(i["code"] != other.code for i in items)


async def test_my_codes_derives_inactive_for_fresh_package_code(patched_roots, manager):
    """套餐完整码未首次使用（expires_at 为空）→ my-codes 派生 status=inactive；试用码不受影响"""
    full = manager.create_activation(
        mode="combined",
        code_type="full",
        vip_level=2,
        package_type="quarterly",
        no_expiry=True,
    )
    manager.claim_owner(full.code, USER)
    trial = create_trial_activation_for_user(USER, manager=manager)

    out = await simple_auth_module.list_my_codes(current_user=dict(USER))
    items = {i["code"]: i for i in out.data["items"]}
    assert items[full.code]["status"] == "inactive"
    assert items[full.code]["expires_at"] is None
    assert items[trial.code]["status"] == "active"  # 试用码不过期，保持 active


# ──────────────────────────────────────────────────────────────────
# 6. 轮数统计与 10 轮门控
# ──────────────────────────────────────────────────────────────────


def test_count_values_user_messages_excludes_internal(patched_roots, manager):
    rec, registry, rid = _make_bound_code(manager, USER, n_values_msgs=7, n_internal=5)
    assert count_values_user_messages(registry, rid) == 7


async def test_trial_stream_allows_9th_10th_messages(patched_roots, manager, monkeypatch):
    rec, registry, rid = _make_bound_code(manager, USER, n_values_msgs=9)
    _patch_manager_lookup(monkeypatch, manager)
    req = scr.SimpleChatStreamRequest(
        activation_code=rec.code, message="第 10 条回答", phase="values", thread_id="t_1"
    )
    resp = await scr.simple_chat_stream(req, dict(USER))
    assert resp.status_code == 200  # 第 10 条正常进入流式回复


async def test_trial_stream_blocks_11th_message(patched_roots, manager, monkeypatch):
    rec, registry, rid = _make_bound_code(
        manager, USER, n_values_msgs=10, n_internal=3
    )
    _patch_manager_lookup(monkeypatch, manager)
    req = scr.SimpleChatStreamRequest(
        activation_code=rec.code, message="第 11 条回答", phase="values", thread_id="t_1"
    )
    with pytest.raises(HTTPException) as exc:
        await scr.simple_chat_stream(req, dict(USER))
    assert exc.value.status_code == 402
    detail = json.loads(exc.value.detail)
    assert detail["type"] == "trial_limit_reached"
    assert detail["used"] == 10
    assert detail["limit"] == TRIAL_VALUES_USER_MESSAGE_LIMIT


async def test_trial_limit_counts_across_threads(patched_roots, manager, monkeypatch):
    """轮数统计覆盖该 report 全部 values 线程。"""
    rec, registry, rid = _make_bound_code(manager, USER, n_values_msgs=6)
    _write_values_thread(registry, rid, "t_2", 4)
    _patch_manager_lookup(monkeypatch, manager)
    req = scr.SimpleChatStreamRequest(
        activation_code=rec.code, message="又一条", phase="values", thread_id="t_1"
    )
    with pytest.raises(HTTPException) as exc:
        await scr.simple_chat_stream(req, dict(USER))
    assert exc.value.status_code == 402
    assert json.loads(exc.value.detail)["used"] == 10


# ──────────────────────────────────────────────────────────────────
# 7. 阶段锁（非 values 写请求）
# ──────────────────────────────────────────────────────────────────


async def test_trial_phase_lock_on_stream(patched_roots, manager, monkeypatch):
    rec, registry, rid = _make_bound_code(manager, USER, n_values_msgs=3)
    _patch_manager_lookup(monkeypatch, manager)
    req = scr.SimpleChatStreamRequest(
        activation_code=rec.code, message="开始优势阶段", phase="strengths", thread_id="t_9"
    )
    with pytest.raises(HTTPException) as exc:
        await scr.simple_chat_stream(req, dict(USER))
    assert exc.value.status_code == 402
    assert json.loads(exc.value.detail) == {"type": "trial_phase_locked", "has_upgrade_codes": False}


async def test_trial_phase_lock_has_upgrade_codes(patched_roots, manager, monkeypatch):
    """402 detail 带 has_upgrade_codes：有自购未绑定完整码时为 True（前端据此显示升级入口）。"""
    rec, registry, rid = _make_bound_code(manager, USER, n_values_msgs=3)
    paid = manager.create_activation(mode="combined", code_type="full", no_expiry=True)
    manager.set_purchase_source(paid.code, purchaser_user_id=USER["user_id"])
    _patch_manager_lookup(monkeypatch, manager)
    req = scr.SimpleChatStreamRequest(
        activation_code=rec.code, message="开始优势阶段", phase="strengths", thread_id="t_9"
    )
    with pytest.raises(HTTPException) as exc:
        await scr.simple_chat_stream(req, dict(USER))
    assert exc.value.status_code == 402
    assert json.loads(exc.value.detail) == {"type": "trial_phase_locked", "has_upgrade_codes": True}


async def test_trial_phase_lock_on_init(patched_roots, manager, monkeypatch):
    """values 出结论卡后推进 strengths 的入口（/init）同样拦截。"""
    rec, registry, rid = _make_bound_code(manager, USER, n_values_msgs=10)
    registry.select_session(rid, "values", "t_1")  # values 已确认，准备推进
    _patch_manager_lookup(monkeypatch, manager)
    req = scr.SimpleInitRequest(activation_code=rec.code, phase="strengths", thread_id="t_9")
    with pytest.raises(HTTPException) as exc:
        await scr.simple_init(req, dict(USER))
    assert exc.value.status_code == 402
    assert json.loads(exc.value.detail) == {"type": "trial_phase_locked", "has_upgrade_codes": False}


async def test_trial_phase_lock_on_thread_complete(patched_roots, manager, monkeypatch):
    rec, registry, rid = _make_bound_code(manager, USER, n_values_msgs=2)
    _patch_manager_lookup(monkeypatch, manager)
    req = scr.ThreadCompleteRequest(
        activation_code=rec.code, phase="strengths", thread_id="t_9"
    )
    with pytest.raises(HTTPException) as exc:
        await scr.mark_thread_complete(req, dict(USER))
    assert exc.value.status_code == 402
    assert json.loads(exc.value.detail) == {"type": "trial_phase_locked", "has_upgrade_codes": False}


async def test_trial_phase_lock_on_rumination_submit(patched_roots, manager, monkeypatch):
    rec, registry, rid = _make_bound_code(manager, USER, n_values_msgs=2)
    _patch_manager_lookup(monkeypatch, manager)
    req = scr.RuminationTableSubmitRequest(activation_code=rec.code, step=1, table_data=[])
    with pytest.raises(HTTPException) as exc:
        await scr.rumination_table_submit(req, dict(USER))
    assert exc.value.status_code == 402
    assert json.loads(exc.value.detail) == {"type": "trial_phase_locked", "has_upgrade_codes": False}


# ──────────────────────────────────────────────────────────────────
# 8. 只读端点不拦
# ──────────────────────────────────────────────────────────────────


async def test_readonly_threads_not_blocked(patched_roots, manager, monkeypatch):
    """已达 10 轮上限的试用码，只读 GET 端点不受影响。"""
    rec, registry, rid = _make_bound_code(manager, USER, n_values_msgs=10)
    _patch_manager_lookup(monkeypatch, manager)
    out = await scr.list_threads(
        activation_code=rec.code, phase="values", current_user=dict(USER)
    )
    assert out.code == 200
    assert len(out.data["threads"]) == 1


# ──────────────────────────────────────────────────────────────────
# 9. 存量 full 码不受任何限制
# ──────────────────────────────────────────────────────────────────


async def test_full_code_unrestricted_by_round_limit(patched_roots, manager, monkeypatch):
    rec, registry, rid = _make_bound_code(
        manager, USER, code_type="full", n_values_msgs=15
    )
    _patch_manager_lookup(monkeypatch, manager)
    req = scr.SimpleChatStreamRequest(
        activation_code=rec.code, message="第 16 条回答", phase="values", thread_id="t_1"
    )
    resp = await scr.simple_chat_stream(req, dict(USER))
    assert resp.status_code == 200  # full 码无轮数限制


async def test_full_code_unrestricted_by_phase_lock(patched_roots, manager, monkeypatch):
    rec, registry, rid = _make_bound_code(
        manager, USER, code_type="full", n_values_msgs=3
    )
    registry.select_session(rid, "values", "t_1")  # values 已确认，可推进
    _patch_manager_lookup(monkeypatch, manager)
    req = scr.SimpleChatStreamRequest(
        activation_code=rec.code, message="开始优势阶段", phase="strengths", thread_id="t_9"
    )
    resp = await scr.simple_chat_stream(req, dict(USER))
    assert resp.status_code == 200  # full 码无阶段锁


# ──────────────────────────────────────────────────────────────────
# 消耗升级（ADR-0014）
# ──────────────────────────────────────────────────────────────────

from app.utils.trial_codes import (  # noqa: E402
    get_active_trial_code_for_user,
    get_started_trial_code,
)


def test_get_active_trial_code_for_user(patched_roots, manager):
    rec, _, _ = _make_bound_code(manager, USER, code_type="trial")
    found = get_active_trial_code_for_user(USER["user_id"])
    assert found is not None and found.code == rec.code
    assert get_active_trial_code_for_user("nobody") is None


def test_get_active_trial_code_ignores_full_code(patched_roots, manager):
    _make_bound_code(manager, USER, code_type="full")
    assert get_active_trial_code_for_user(USER["user_id"]) is None


def test_get_started_trial_code_requires_messages(patched_roots, manager):
    """已开聊判定：0 条消息 → None；≥1 条 → 返回试用码"""
    rec, registry, rid = _make_bound_code(manager, USER, code_type="trial")
    assert get_started_trial_code(USER["user_id"]) is None

    _write_values_thread(registry, rid, "t_1", 1)
    found = get_started_trial_code(USER["user_id"])
    assert found is not None and found.code == rec.code


def test_consume_for_trial_upgrade_success(patched_roots, manager):
    """消耗成功：码 status=consumed、consumed_into 指向试用码"""
    trial, _, _ = _make_bound_code(manager, USER, code_type="trial")
    full = manager.create_activation(mode="combined", code_type="full", vip_level=2)

    consumed = manager.consume_for_trial_upgrade(full.code, trial.code, actor=USER)
    assert consumed.status == "consumed"
    assert consumed.consumed_into == trial.code

    # 二次消耗拒绝
    import pytest as _pt

    with _pt.raises(ValueError, match="已被消耗"):
        manager.consume_for_trial_upgrade(full.code, trial.code, actor=USER)


def test_consume_for_trial_upgrade_rejects_claimed(patched_roots, manager):
    """已绑定的码不可消耗"""
    import pytest as _pt

    trial, _, _ = _make_bound_code(manager, USER, code_type="trial")
    other, _, _ = _make_bound_code(manager, {"user_id": "u2", "email": "b@x.com"}, code_type="full")
    with _pt.raises(ValueError, match="已绑定"):
        manager.consume_for_trial_upgrade(other.code, trial.code, actor=USER)


def test_consume_for_trial_upgrade_rejects_trial_as_source(patched_roots, manager):
    """试用码不能作为被消耗码"""
    import pytest as _pt

    trial, _, _ = _make_bound_code(manager, USER, code_type="trial")
    another_trial = manager.create_activation(mode="combined", code_type="trial", vip_level=1)
    with _pt.raises(ValueError, match="仅完整码"):
        manager.consume_for_trial_upgrade(another_trial.code, trial.code, actor=USER)


# ──────────────────────────────────────────────────────────────────
# my-codes / my-purchased-codes 溯源字段与订单联查（消耗去向展示改造，ADR-0014）
# ──────────────────────────────────────────────────────────────────

from datetime import datetime, timezone  # noqa: E402

import app.models.database as db_module  # noqa: E402
from app.models.payment import PaymentOrder  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402


@pytest.fixture
async def order_session_local(monkeypatch):
    """内存 SQLite（仅 PaymentOrder 表），替换 simple_auth 内联引用的 AsyncSessionLocal。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(PaymentOrder.__table__.create)
    session_local = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "AsyncSessionLocal", session_local)
    yield session_local
    await engine.dispose()


async def test_my_codes_returns_upgraded_from_code(patched_roots, manager):
    """consume 升级后，my-codes 返回的试用码带正确 upgraded_from_code；未升级码为 None"""
    trial = create_trial_activation_for_user(USER, manager=manager)
    full = manager.create_activation(mode="combined", code_type="full", vip_level=2)
    manager.consume_for_trial_upgrade(full.code, trial.code, actor=USER)
    plain = manager.create_activation(mode="combined", code_type="full")
    manager.claim_owner(plain.code, USER)

    out = await simple_auth_module.list_my_codes(current_user=dict(USER))
    items = {i["code"]: i for i in out.data["items"]}
    assert items[trial.code]["upgraded_from_code"] == full.code
    assert items[plain.code]["upgraded_from_code"] is None
    assert full.code not in items  # 被消耗码无 owner，不出现在 my-codes


async def test_my_purchased_codes_new_fields_and_order_lookup(
    patched_roots, manager, order_session_local
):
    """my-purchased-codes：source_order_id / consumed_into 透传 + 订单金额联查"""
    trial = create_trial_activation_for_user(USER, manager=manager)
    # 已消耗码：带订单来源（季度套餐）
    consumed = manager.create_activation(
        mode="combined",
        code_type="full",
        vip_level=2,
        package_type="quarterly",
        no_expiry=True,
    )
    manager.set_purchase_source(
        consumed.code, source_order_id="order-1", purchaser_user_id=USER["user_id"]
    )
    manager.consume_for_trial_upgrade(consumed.code, trial.code, actor=USER)
    # 未消耗码：无订单来源（存量"其他来源"兜底分组）
    gift = manager.create_activation(
        mode="combined", code_type="full", vip_level=2, package_type="annual", no_expiry=True
    )
    manager.set_purchase_source(gift.code, purchaser_user_id=USER["user_id"])

    async with order_session_local() as db:
        db.add(
            PaymentOrder(
                id="order-1",
                order_no="Q20260801120000ABCD",
                user_id=USER["user_id"],
                product_type="quarterly_package",
                quantity=1,
                amount_original=6900,
                amount_discount=500,
                amount_paid=6400,
                channel="alipay",
                status="granted",
                created_at=datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc),
            )
        )
        await db.commit()

    out = await simple_auth_module.list_my_purchased_codes(current_user=dict(USER))
    items = {i["code"]: i for i in out.data["items"]}

    consumed_item = items[consumed.code]
    assert consumed_item["source_order_id"] == "order-1"
    assert consumed_item["consumed_into"] == trial.code
    assert consumed_item["upgraded_from_code"] is None  # 来源码本身无反向溯源
    assert consumed_item["order_no"] == "Q20260801120000ABCD"
    # sqlite DateTime 读回为 naive datetime，只断言到分钟
    assert consumed_item["order_created_at"].startswith("2026-08-01T12:00")
    assert consumed_item["product_name"] == "季度套餐"
    assert consumed_item["amount_original"] == 6900
    assert consumed_item["amount_discount"] == 500
    assert consumed_item["amount_paid"] == 6400

    gift_item = items[gift.code]
    assert gift_item["source_order_id"] is None
    assert gift_item["consumed_into"] is None
    assert gift_item["order_no"] is None
    assert gift_item["order_created_at"] is None
    assert gift_item["product_name"] is None
    assert gift_item["amount_paid"] is None
    assert gift_item["amount_original"] is None
    assert gift_item["amount_discount"] is None
    # 既有字段保留
    assert gift_item["activated"] is False
    assert "report_authorized" in gift_item


# ──────────────────────────────────────────────────────────────────
# 11. 邮箱验证门控（403 email_not_verified）
# ──────────────────────────────────────────────────────────────────

UNVERIFIED_USER = {
    "user_id": "u-unverified-1",
    "email": "unv@example.com",
    "email_verified": False,
}
VERIFIED_USER = {
    "user_id": "u-verified-1",
    "email": "v@example.com",
    "email_verified": True,
}
PHONE_ONLY_USER = {"user_id": "u-phone-1", "phone": "13800000000"}  # 无邮箱


async def test_unverified_email_blocked_on_stream(patched_roots, manager, monkeypatch):
    """邮箱未验证：试用码 values 阶段发消息也被 403 拦截（优先于试用门控）。"""
    rec, registry, rid = _make_bound_code(manager, UNVERIFIED_USER, n_values_msgs=1)
    _patch_manager_lookup(monkeypatch, manager)
    req = scr.SimpleChatStreamRequest(
        activation_code=rec.code, message="你好", phase="values", thread_id="t_1"
    )
    with pytest.raises(HTTPException) as exc:
        await scr.simple_chat_stream(req, dict(UNVERIFIED_USER))
    assert exc.value.status_code == 403
    assert json.loads(exc.value.detail) == {"type": "email_not_verified"}


async def test_unverified_email_blocked_on_init(patched_roots, manager, monkeypatch):
    rec, registry, rid = _make_bound_code(manager, UNVERIFIED_USER, n_values_msgs=1)
    _patch_manager_lookup(monkeypatch, manager)
    req = scr.SimpleInitRequest(activation_code=rec.code, phase="values", thread_id="t_9")
    with pytest.raises(HTTPException) as exc:
        await scr.simple_init(req, dict(UNVERIFIED_USER))
    assert exc.value.status_code == 403
    assert json.loads(exc.value.detail) == {"type": "email_not_verified"}


async def test_unverified_email_blocked_on_full_code(patched_roots, manager, monkeypatch):
    """门控与码类型无关：full 码用户邮箱未验证同样拦截。"""
    rec, registry, rid = _make_bound_code(manager, UNVERIFIED_USER, code_type="full", n_values_msgs=1)
    _patch_manager_lookup(monkeypatch, manager)
    req = scr.SimpleChatStreamRequest(
        activation_code=rec.code, message="你好", phase="values", thread_id="t_1"
    )
    with pytest.raises(HTTPException) as exc:
        await scr.simple_chat_stream(req, dict(UNVERIFIED_USER))
    assert exc.value.status_code == 403
    assert json.loads(exc.value.detail) == {"type": "email_not_verified"}


async def test_verified_email_passes_gate(patched_roots, manager, monkeypatch):
    rec, registry, rid = _make_bound_code(manager, VERIFIED_USER, n_values_msgs=1)
    _patch_manager_lookup(monkeypatch, manager)
    req = scr.SimpleChatStreamRequest(
        activation_code=rec.code, message="你好", phase="values", thread_id="t_1"
    )
    resp = await scr.simple_chat_stream(req, dict(VERIFIED_USER))
    assert resp.status_code == 200


async def test_phone_only_user_passes_gate(patched_roots, manager, monkeypatch):
    """手机号注册（无邮箱）用户不受邮箱门控影响。"""
    rec, registry, rid = _make_bound_code(manager, PHONE_ONLY_USER, n_values_msgs=1)
    _patch_manager_lookup(monkeypatch, manager)
    req = scr.SimpleChatStreamRequest(
        activation_code=rec.code, message="你好", phase="values", thread_id="t_1"
    )
    resp = await scr.simple_chat_stream(req, dict(PHONE_ONLY_USER))
    assert resp.status_code == 200


# ──────────────────────────────────────────────────────────────────
# 12. 问卷昵称默认回填注册 username
# ──────────────────────────────────────────────────────────────────


class _FakeSurveyRequest:
    def __init__(self, survey_data):
        self.survey_data = survey_data


def test_survey_nickname_default_from_username():
    req = _FakeSurveyRequest({"age": "25"})
    out = scr._survey_data_with_nickname_default(req, {"username": " 小明 "})
    assert out["nickname"] == "小明"
    assert out["age"] == "25"


def test_survey_nickname_explicit_wins():
    req = _FakeSurveyRequest({"nickname": "自定义昵称"})
    out = scr._survey_data_with_nickname_default(req, {"username": "小明"})
    assert out["nickname"] == "自定义昵称"


def test_survey_nickname_no_username_no_fill():
    req = _FakeSurveyRequest({})
    out = scr._survey_data_with_nickname_default(req, {"user_id": "u1"})
    assert "nickname" not in out
