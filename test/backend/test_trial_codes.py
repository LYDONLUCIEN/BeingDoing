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
    assert json.loads(exc.value.detail) == {"type": "trial_phase_locked"}


async def test_trial_phase_lock_on_init(patched_roots, manager, monkeypatch):
    """values 出结论卡后推进 strengths 的入口（/init）同样拦截。"""
    rec, registry, rid = _make_bound_code(manager, USER, n_values_msgs=10)
    registry.select_session(rid, "values", "t_1")  # values 已确认，准备推进
    _patch_manager_lookup(monkeypatch, manager)
    req = scr.SimpleInitRequest(activation_code=rec.code, phase="strengths", thread_id="t_9")
    with pytest.raises(HTTPException) as exc:
        await scr.simple_init(req, dict(USER))
    assert exc.value.status_code == 402
    assert json.loads(exc.value.detail) == {"type": "trial_phase_locked"}


async def test_trial_phase_lock_on_thread_complete(patched_roots, manager, monkeypatch):
    rec, registry, rid = _make_bound_code(manager, USER, n_values_msgs=2)
    _patch_manager_lookup(monkeypatch, manager)
    req = scr.ThreadCompleteRequest(
        activation_code=rec.code, phase="strengths", thread_id="t_9"
    )
    with pytest.raises(HTTPException) as exc:
        await scr.mark_thread_complete(req, dict(USER))
    assert exc.value.status_code == 402
    assert json.loads(exc.value.detail) == {"type": "trial_phase_locked"}


async def test_trial_phase_lock_on_rumination_submit(patched_roots, manager, monkeypatch):
    rec, registry, rid = _make_bound_code(manager, USER, n_values_msgs=2)
    _patch_manager_lookup(monkeypatch, manager)
    req = scr.RuminationTableSubmitRequest(activation_code=rec.code, step=1, table_data=[])
    with pytest.raises(HTTPException) as exc:
        await scr.rumination_table_submit(req, dict(USER))
    assert exc.value.status_code == 402
    assert json.loads(exc.value.detail) == {"type": "trial_phase_locked"}


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
