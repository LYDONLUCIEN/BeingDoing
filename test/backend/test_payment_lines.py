"""
订单明细行服务测试（P1 退款系统，2026-10-05）

测试场景：
1. allocate_equal：等额分摊、尾差归末行、0 额、单行、非法行数
2. 交付时生成行：年度套餐（3 行）Σ原价/Σ优惠/Σ实付 == 订单总额，状态 available
3. 延期交付：1 行 used（交付即已用），item_ref=目标码
4. 咨询交付：1 行 available，item_ref=booking_id
5. 0 元单（券全覆盖）：行实付为 0
6. 存量回填：老 granted 订单（无行）惰性生成；码已绑定 → used；非 granted 不生成
7. 幂等：重复调用不重复生成
8. line_effective_status：available 行在码被 claim / 预约排期后实时变 used

独立 in-memory SQLite + monkeypatch 替换 AsyncSessionLocal 与激活码管理器，
不打真实渠道与文件数据。
"""

from datetime import datetime, timedelta, timezone
import json
from unittest.mock import AsyncMock

import pytest
from app.models.database import Base
from app.models.payment import ConsultationBooking, PaymentOrder, PaymentOrderLine
from app.models.user import User
from app.services import payment_line_service as pline_mod
from app.services import payment_service as ps_mod
from app.services.payment_line_service import (
    allocate_equal,
    ensure_order_lines,
    line_effective_status,
)
from app.services.payment_service import PaymentService
from app.utils.simple_activation_manager import SimpleActivationManager
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# ─── 测试专用引擎 + 会话工厂 ──────────────────────────────────

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
_TestSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def _setup_db(monkeypatch, tmp_path):
    """每个测试前：建表 + 插测试用户 + mock 激活码管理器/审计/邮件"""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    monkeypatch.setattr(ps_mod, "AsyncSessionLocal", _TestSessionLocal)

    mgr = SimpleActivationManager(base_dir=str(tmp_path / "simple"))
    monkeypatch.setattr(ps_mod, "_activation_manager", lambda: mgr)
    monkeypatch.setattr(
        ps_mod, "get_activation_with_manager", lambda code: (mgr, mgr.get_activation(code))
    )
    monkeypatch.setattr(
        pline_mod, "get_activation_with_manager", lambda code: (mgr, mgr.get_activation(code))
    )
    monkeypatch.setattr("app.utils.activation_audit.append_activation_audit", lambda *a, **k: None)
    monkeypatch.setattr(ps_mod.EmailService, "send_email", AsyncMock(return_value=None))

    now = datetime.now(timezone.utc)
    async with _TestSessionLocal() as db:
        db.add(
            User(
                id="u1",
                email="alice@test.com",
                username="alice",
                password_hash="x",
                is_active=True,
                created_at=now,
            )
        )
        await db.commit()

    yield

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _insert_order(
    product_type: str,
    amount_original: int,
    amount_discount: int,
    amount_paid: int,
    status: str = "pending",
    meta: dict | None = None,
) -> PaymentOrder:
    """直插订单行（测交付/回填用，绕过 create_order 前置校验）"""
    async with _TestSessionLocal() as db:
        order = PaymentOrder(
            order_no=PaymentService._generate_order_no(),
            user_id="u1",
            product_type=product_type,
            channel="alipay",
            amount_original=amount_original,
            amount_discount=amount_discount,
            amount_paid=amount_paid,
            status=status,
            meta=json.dumps(meta, ensure_ascii=False) if meta else None,
        )
        db.add(order)
        await db.commit()
        await db.refresh(order)
        return order


async def _get_lines(order_id: str) -> list[PaymentOrderLine]:
    async with _TestSessionLocal() as db:
        return list(
            (
                await db.execute(
                    select(PaymentOrderLine)
                    .where(PaymentOrderLine.order_id == order_id)
                    .order_by(PaymentOrderLine.line_no)
                )
            )
            .scalars()
            .all()
        )


# ─── allocate_equal：分摊算法 ──────────────────────────────────


def test_allocate_equal_basic():
    assert allocate_equal(10000, 3) == [3333, 3333, 3334]
    assert allocate_equal(100, 3) == [33, 33, 34]
    assert allocate_equal(900, 3) == [300, 300, 300]


def test_allocate_equal_zero_and_single():
    assert allocate_equal(0, 3) == [0, 0, 0]
    assert allocate_equal(12345, 1) == [12345]


def test_allocate_equal_sum_invariant():
    for total, n in [(999, 7), (1, 5), (123456, 4), (7, 3)]:
        parts = allocate_equal(total, n)
        assert sum(parts) == total
        assert len(parts) == n
        # 尾差只归最后一行：前 n-1 行相等
        assert len(set(parts[:-1])) == 1


def test_allocate_equal_invalid_n():
    with pytest.raises(ValueError):
        allocate_equal(100, 0)
    with pytest.raises(ValueError):
        allocate_equal(100, -1)


# ─── 交付时生成行 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delivery_generates_annual_package_lines():
    """年度套餐交付 → 3 个码行，Σ分摊 == 订单金额，全部 available"""
    order = await _insert_order(
        "annual_package", amount_original=29900, amount_discount=5000, amount_paid=24900
    )
    order = await PaymentService._deliver_order(order.id)

    lines = await _get_lines(order.id)
    assert len(lines) == 3
    assert sum(l.price_original_alloc for l in lines) == 29900
    assert sum(l.coupon_alloc for l in lines) == 5000
    assert sum(l.amount_paid_alloc for l in lines) == 24900
    # 尾差归最后一行
    assert [l.price_original_alloc for l in lines] == [9966, 9966, 9968]
    assert all(l.status == "available" for l in lines)
    assert all(l.item_type == "code" for l in lines)
    # item_ref == meta.codes
    codes = PaymentService._parse_meta(order.meta)["codes"]
    assert [l.item_ref for l in lines] == codes


@pytest.mark.asyncio
async def test_delivery_generates_renewal_line_used():
    """延期交付 → 1 行 used（交付即已用），item_ref=目标码"""
    # 延期交付会校验目标码存在并追加有效期，先造目标码
    rec = ps_mod._activation_manager().create_activation(mode="combined")
    order = await _insert_order(
        "renewal",
        amount_original=9900,
        amount_discount=0,
        amount_paid=9900,
        meta={"target_code": rec.code},
    )
    order = await PaymentService._deliver_order(order.id)
    lines = await _get_lines(order.id)
    assert len(lines) == 1
    assert lines[0].item_type == "renewal_service"
    assert lines[0].item_ref == rec.code
    assert lines[0].status == "used"
    assert lines[0].amount_paid_alloc == 9900


@pytest.mark.asyncio
async def test_delivery_generates_consultation_line():
    """咨询交付 → 1 行 available，item_ref=booking_id"""
    order = await _insert_order("consultation", 29900, 0, 29900)
    order = await PaymentService._deliver_order(order.id)

    lines = await _get_lines(order.id)
    assert len(lines) == 1
    assert lines[0].item_type == "consultation_service"
    assert lines[0].status == "available"
    booking_id = PaymentService._parse_meta(order.meta)["booking_id"]
    assert lines[0].item_ref == booking_id


@pytest.mark.asyncio
async def test_zero_amount_order_lines_paid_zero():
    """0 元单（券全覆盖）：行实付全 0，Σ == 0"""
    order = await _insert_order(
        "quarterly_package", amount_original=9900, amount_discount=9900, amount_paid=0
    )
    order = await PaymentService._deliver_order(order.id)
    lines = await _get_lines(order.id)
    assert len(lines) == 1
    assert lines[0].amount_paid_alloc == 0
    assert lines[0].price_original_alloc == 9900
    assert lines[0].coupon_alloc == 9900


# ─── 存量回填与幂等 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_backfill_legacy_granted_order_with_bound_code():
    """存量 granted 年度订单：码 2 已绑定 → 回填后该行 used，其余 available"""
    mgr = ps_mod._activation_manager()
    codes = [mgr.create_activation(mode="combined").code for _ in range(3)]
    mgr.claim_owner(codes[1], {"user_id": "u1", "email": "alice@test.com"})

    order = await _insert_order(
        "annual_package",
        amount_original=29900,
        amount_discount=200,
        amount_paid=29700,
        status="granted",
        meta={"codes": codes},
    )
    async with _TestSessionLocal() as db:
        row = (
            await db.execute(select(PaymentOrder).where(PaymentOrder.id == order.id))
        ).scalar_one()
        lines = await ensure_order_lines(db, row, source="backfill")
        await db.commit()

    assert [l.status for l in lines] == ["available", "used", "available"]
    assert sum(l.amount_paid_alloc for l in lines) == 29700


@pytest.mark.asyncio
async def test_backfill_skips_non_granted_order():
    """非 granted/partially_refunded 订单不生成行"""
    order = await _insert_order("quarterly_package", 9900, 0, 9900, status="pending")
    async with _TestSessionLocal() as db:
        row = (
            await db.execute(select(PaymentOrder).where(PaymentOrder.id == order.id))
        ).scalar_one()
        lines = await ensure_order_lines(db, row)
    assert lines == []


@pytest.mark.asyncio
async def test_ensure_order_lines_idempotent():
    """重复调用不重复生成（已有行直接返回）"""
    mgr = ps_mod._activation_manager()
    codes = [mgr.create_activation(mode="combined").code for _ in range(3)]
    order = await _insert_order(
        "annual_package",
        29900,
        0,
        29900,
        status="granted",
        meta={"codes": codes},
    )
    async with _TestSessionLocal() as db:
        row = (
            await db.execute(select(PaymentOrder).where(PaymentOrder.id == order.id))
        ).scalar_one()
        first = await ensure_order_lines(db, row)
        await db.commit()
    async with _TestSessionLocal() as db:
        row = (
            await db.execute(select(PaymentOrder).where(PaymentOrder.id == order.id))
        ).scalar_one()
        second = await ensure_order_lines(db, row)

    assert [l.id for l in first] == [l.id for l in second]
    assert len(await _get_lines(order.id)) == 3


# ─── line_effective_status：实时重验 ──────────────────────────


@pytest.mark.asyncio
async def test_effective_status_code_claimed_after_generation():
    """生成后码被 claim → effective 变 used（DB 列仍 available）"""
    mgr = ps_mod._activation_manager()
    code = mgr.create_activation(mode="combined").code
    order = await _insert_order(
        "quarterly_package", 9900, 0, 9900, status="granted", meta={"codes": [code]}
    )
    async with _TestSessionLocal() as db:
        row = (
            await db.execute(select(PaymentOrder).where(PaymentOrder.id == order.id))
        ).scalar_one()
        lines = await ensure_order_lines(db, row)
        await db.commit()
        assert await line_effective_status(db, lines[0]) == "available"

        mgr.claim_owner(code, {"user_id": "u1", "email": "alice@test.com"})
        assert await line_effective_status(db, lines[0]) == "used"
        assert lines[0].status == "available"  # DB 持久列不被读路径回写


@pytest.mark.asyncio
async def test_effective_status_consultation_scheduled():
    """咨询行：预约排期后 effective 变 used"""
    order = await _insert_order("consultation", 29900, 0, 29900, status="granted")
    async with _TestSessionLocal() as db:
        booking = ConsultationBooking(order_id=order.id, user_id="u1", status="pending_survey")
        db.add(booking)
        await db.flush()
        order_row = (
            await db.execute(select(PaymentOrder).where(PaymentOrder.id == order.id))
        ).scalar_one()
        order_row.meta = json.dumps({"booking_id": booking.id})
        lines = await ensure_order_lines(db, order_row)
        await db.commit()
        assert await line_effective_status(db, lines[0]) == "available"

        booking.status = "scheduled"
        await db.commit()
        assert await line_effective_status(db, lines[0]) == "used"


@pytest.mark.asyncio
async def test_effective_status_renewal_always_used():
    """延期行恒 used"""
    order = await _insert_order(
        "renewal", 9900, 0, 9900, status="granted", meta={"target_code": "ANYCODE1"}
    )
    async with _TestSessionLocal() as db:
        row = (
            await db.execute(select(PaymentOrder).where(PaymentOrder.id == order.id))
        ).scalar_one()
        lines = await ensure_order_lines(db, row)
        assert await line_effective_status(db, lines[0]) == "used"
