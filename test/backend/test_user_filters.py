"""用户筛选系统测试（ADR-0023，2026-10-09）：

覆盖：
- validate_filters / strip_empty_filters / get_filter_schema
- filter_users 执行器：SQL 下推过滤器（user_type 多选 OR / account_status /
  profile_completed / paid_status / q / created_range）与内存过滤器
  （code_kind / stage，ctx 注入）的组合语义（过滤器内 OR、过滤器间 AND）、
  含内存过滤器时的全量拉取 + 切片分页（total 为精筛后总数）
- FilterContext 构建器：code_kind 最高档归并（full>trial、consumed/deleted 排除、
  过期计入）、stage 三态归并（多 record 取最前进度、report_unlocked 口径）

使用独立 in-memory SQLite；激活码与 report record 均走 monkeypatch/tmp_path，
不污染真实数据。
"""

from __future__ import annotations

import json
from datetime import datetime
from functools import partial
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.database import Base
from app.models.payment import PaymentOrder
from app.models.user import User, UserProfile
from app.services.user_filters import (
    FILTER_REGISTRY,
    filter_users,
    get_filter_schema,
    strip_empty_filters,
    validate_filters,
)
from app.services.user_filters.service import FilterContext
from app.utils.report_registry import STEP_IDS, ReportRegistry

# ─── 测试专用引擎 + 数据 ──────────────────────────────────────

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
_TestSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)

U1, U2, U3, U4 = "u-alice", "u-bob", "u-carol", "u-dave"


@pytest.fixture(autouse=True)
async def _setup():
    """每个测试前：重建表 + 插 4 个用户（活跃/禁用/注销/管理员）+ profile + 订单"""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with _TestSessionLocal() as db:
        db.add_all(
            [
                # real + 活跃 + 已填 profile + 已付费(granted)
                User(
                    id=U1,
                    email="alice@x.com",
                    username="爱丽丝",
                    password_hash="x",
                    user_type="real",
                    is_active=True,
                    created_at=datetime(2026, 1, 1),
                ),
                # beta + 已禁用 + 未填 profile + 仅 pending 订单（未付费）
                User(
                    id=U2,
                    email="bob@x.com",
                    username="鲍勃",
                    password_hash="x",
                    user_type="beta",
                    is_active=False,
                    created_at=datetime(2026, 2, 1),
                ),
                # real + 已注销 + 无 profile + 无订单
                User(
                    id=U3,
                    email="carol@x.com",
                    username="卡罗尔",
                    password_hash="x",
                    user_type="real",
                    is_active=True,
                    deleted_at=datetime(2026, 3, 15),
                    created_at=datetime(2026, 3, 1),
                ),
                # admin + 活跃 + partially_refunded 订单（按 ADR-0023 不计已付费）
                User(
                    id=U4,
                    email="dave@x.com",
                    username="戴夫",
                    password_hash="x",
                    user_type="admin",
                    is_active=True,
                    created_at=datetime(2026, 4, 1),
                ),
            ]
        )
        db.add_all(
            [
                UserProfile(user_id=U1, profile_completed=True),
                UserProfile(user_id=U2, profile_completed=False),
            ]
        )
        db.add_all(
            [
                PaymentOrder(
                    order_no="O1",
                    user_id=U1,
                    product_type="quarterly_package",
                    amount_original=6900,
                    amount_paid=6900,
                    channel="alipay",
                    status="granted",
                ),
                PaymentOrder(
                    order_no="O2",
                    user_id=U2,
                    product_type="quarterly_package",
                    amount_original=6900,
                    amount_paid=6900,
                    channel="alipay",
                    status="pending",
                ),
                PaymentOrder(
                    order_no="O3",
                    user_id=U4,
                    product_type="quarterly_package",
                    amount_original=6900,
                    amount_paid=6900,
                    channel="alipay",
                    status="partially_refunded",
                ),
            ]
        )
        await db.commit()

    yield


# 内存过滤器注入上下文：U1=full/已出报告，U2=trial/探索中，U4=探索中，U3 无记录
_CTX = FilterContext(
    code_kind_map={U1: "full", U2: "trial"},
    stage_map={U1: "report_unlocked", U2: "exploring", U4: "exploring"},
)


async def _run(filters, page=None, page_size=None, ctx=None):
    async with _TestSessionLocal() as db:
        users, total = await filter_users(
            db, filters, page=page, page_size=page_size, ctx=ctx
        )
        return [u.id for u in users], total


# ─── validate / strip / schema ────────────────────────────────


def test_validate_rejects_unknown_key():
    with pytest.raises(ValueError, match="未知筛选字段"):
        validate_filters({"nope": ["x"]})


def test_validate_rejects_bad_enum_value():
    with pytest.raises(ValueError, match="非法值"):
        validate_filters({"user_type": ["real", "bogus"]})
    with pytest.raises(ValueError, match="仅支持"):
        validate_filters({"account_status": "bogus"})


def test_validate_rejects_wrong_shape():
    with pytest.raises(ValueError):
        validate_filters({"paid_status": "paid"})  # multi_enum 需数组
    with pytest.raises(ValueError):
        validate_filters({"created_range": {}})  # date_range 需 after/before 其一
    with pytest.raises(ValueError):
        validate_filters({"q": "   "})  # text 需非空白


def test_validate_passes_legit():
    validate_filters(
        {
            "user_type": ["real", "beta"],
            "stage": ["exploring"],
            "created_range": {"after": "2026-01-01"},
        }
    )


def test_strip_empty_filters():
    assert strip_empty_filters(None) == {}
    assert strip_empty_filters(
        {"q": "", "user_type": [], "created_range": {}, "stage": ["exploring"], "x": None}
    ) == {"stage": ["exploring"]}


def test_get_filter_schema_shape():
    schema = get_filter_schema()
    assert [e["key"] for e in schema] == list(FILTER_REGISTRY.keys())
    by_key = {e["key"]: e for e in schema}
    assert by_key["user_type"]["type"] == "multi_enum"
    assert {o["value"] for o in by_key["user_type"]["options"]} == {
        "real",
        "beta",
        "test",
        "admin",
    }
    assert by_key["stage"]["type"] == "multi_enum"
    assert by_key["created_range"]["options"] is None
    assert by_key["q"]["type"] == "text"


# ─── SQL 下推过滤器 ───────────────────────────────────────────


async def test_user_type_multi_or():
    ids, total = await _run({"user_type": ["real", "admin"]})
    assert sorted(ids) == sorted([U1, U3, U4])
    assert total == 3


async def test_account_status_enum():
    ids, _ = await _run({"account_status": "active"})
    assert sorted(ids) == sorted([U1, U4])  # 活跃且未注销
    ids, _ = await _run({"account_status": "inactive"})
    assert ids == [U2]
    ids, _ = await _run({"account_status": "deleted"})
    assert ids == [U3]


async def test_profile_completed_enum():
    ids, _ = await _run({"profile_completed": "completed"})
    assert ids == [U1]
    ids, _ = await _run({"profile_completed": "incomplete"})
    assert ids == [U2]  # join 语义：无 profile 的用户（U3/U4）不出现，与旧口径一致


async def test_paid_status():
    ids, _ = await _run({"paid_status": ["paid"]})
    assert ids == [U1]  # granted 计入
    ids, _ = await _run({"paid_status": ["unpaid"]})
    assert sorted(ids) == sorted([U2, U3, U4])  # pending 与 partially_refunded 均不计已付费
    ids, total = await _run({"paid_status": ["paid", "unpaid"]})
    assert total == 4  # 两档全选 = 不限


async def test_q_text():
    ids, _ = await _run({"q": "alice"})
    assert ids == [U1]
    ids, _ = await _run({"q": "鲍勃"})
    assert ids == [U2]


async def test_created_range():
    ids, _ = await _run({"created_range": {"after": "2026-02-15"}})
    assert sorted(ids) == sorted([U3, U4])
    ids, _ = await _run({"created_range": {"before": "2026-02-15"}})
    assert sorted(ids) == sorted([U1, U2])
    # 非法日期静默忽略（沿用 UserDB.list_users 口径）
    ids, total = await _run({"created_range": {"after": "not-a-date"}})
    assert total == 4


async def test_sql_filters_pagination():
    ids, total = await _run({"user_type": ["real", "admin"]}, page=1, page_size=2)
    assert total == 3
    assert len(ids) == 2
    ids2, _ = await _run({"user_type": ["real", "admin"]}, page=2, page_size=2)
    assert len(ids2) == 1
    assert not set(ids) & set(ids2)


# ─── 内存过滤器（ctx 注入） ────────────────────────────────────


async def test_code_kind_memory():
    ids, _ = await _run({"code_kind": ["full"]}, ctx=_CTX)
    assert ids == [U1]
    ids, _ = await _run({"code_kind": ["none"]}, ctx=_CTX)
    assert sorted(ids) == sorted([U3, U4])  # 不在 map 即 none
    ids, _ = await _run({"code_kind": ["trial", "full"]}, ctx=_CTX)
    assert sorted(ids) == sorted([U1, U2])


async def test_stage_memory():
    ids, _ = await _run({"stage": ["report_unlocked"]}, ctx=_CTX)
    assert ids == [U1]
    ids, _ = await _run({"stage": ["not_started"]}, ctx=_CTX)
    assert ids == [U3]
    ids, _ = await _run({"stage": ["exploring", "report_unlocked"]}, ctx=_CTX)
    assert sorted(ids) == sorted([U1, U2, U4])  # 等价旧 has_report=true


async def test_and_across_filters_or_within():
    # user_type ∈ {real, admin}（OR）AND stage = exploring（AND）
    ids, _ = await _run({"user_type": ["real", "admin"], "stage": ["exploring"]}, ctx=_CTX)
    assert ids == [U4]  # U1 是 real 但已出报告；U3 是 real 但未开始


async def test_memory_filter_pagination_total_is_post_filter():
    ids, total = await _run({"stage": ["exploring", "report_unlocked"]}, page=1, page_size=2, ctx=_CTX)
    assert total == 3  # 精筛后总数
    assert len(ids) == 2
    ids2, _ = await _run({"stage": ["exploring", "report_unlocked"]}, page=2, page_size=2, ctx=_CTX)
    assert len(ids2) == 1


# ─── FilterContext 构建器 ─────────────────────────────────────


def _fake_code(code: str, owner: str | None, status: str, code_type: str):
    return SimpleNamespace(
        owner_user_id=owner, status=status, code_type=code_type, code=code
    )


def test_code_kind_map_priority_and_exclusions(monkeypatch):
    from app.utils.simple_activation_manager import SimpleActivationManager

    fake = {
        # U1：trial + 过期 full → full（过期计入、full 优先）
        "T1": _fake_code("T1", U1, "active", "trial"),
        "F1": _fake_code("F1", U1, "expired", "full"),
        # U2：仅 trial
        "T2": _fake_code("T2", U2, "active", "trial"),
        # U3：full 但已 consumed（消耗进他人升级）→ 不计入
        "F3": _fake_code("F3", U3, "consumed", "full"),
        # U4：full 但已 deleted → 不计入
        "F4": _fake_code("F4", U4, "deleted", "full"),
        # 无 owner → 跳过
        "F9": _fake_code("F9", None, "active", "full"),
    }
    monkeypatch.setattr(
        SimpleActivationManager, "list_activations", lambda self: fake
    )

    ctx = FilterContext()
    assert ctx.code_kind_of(U1) == "full"
    assert ctx.code_kind_of(U2) == "trial"
    assert ctx.code_kind_of(U3) == "none"
    assert ctx.code_kind_of(U4) == "none"


def _write_record(base, report_id: str, user_id: str, unlocked: bool) -> None:
    d = base / "reports" / report_id
    d.mkdir(parents=True, exist_ok=True)
    steps = {}
    for sid in STEP_IDS:
        steps[sid] = {
            "step_id": sid,
            # 全解锁：values 等四步给 selected_session_id；rumination 给 locked（v4 特例口径）
            "selected_session_id": ("sess-1" if (unlocked and sid != "rumination") else None),
            "locked": bool(unlocked),
            "session_ids": [],
        }
    if not unlocked:
        # 进行中：仅 values 完成
        steps["values"]["selected_session_id"] = "sess-1"
        steps["values"]["locked"] = True
        steps["values"]["session_ids"] = ["sess-1"]
    record = {
        "report_id": report_id,
        "activation_code": "CODE1",
        "user_id": user_id,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "status": "in_progress",
        "final_conclusion": None,
        "steps": steps,
    }
    (d / "record.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def test_stage_map_most_advanced_wins(monkeypatch, tmp_path):
    base = tmp_path / "simple"
    # U1：一条探索中 + 一条已出报告 → 取最前 = report_unlocked
    _write_record(base, "rpt-a", U1, unlocked=False)
    _write_record(base, "rpt-b", U1, unlocked=True)
    # U2：仅探索中
    _write_record(base, "rpt-c", U2, unlocked=False)

    monkeypatch.setattr(
        "app.utils.report_registry.ReportRegistry",
        partial(ReportRegistry, base_dir=str(base)),
    )

    ctx = FilterContext()
    assert ctx.stage_of(U1) == "report_unlocked"
    assert ctx.stage_of(U2) == "exploring"
    assert ctx.stage_of(U3) == "not_started"
