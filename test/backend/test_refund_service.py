"""
退款服务测试（2026-10-05 退款系统，mock 渠道层）

测试场景：
1. 全退闭环：申请 → 批准执行 → 订单 refunded / 行 refunded / 码 revoked / 渠道 R001
2. 部分退：年度选 1 码 → 退 1/3 分摊实付、订单 partially_refunded、只作废所选码、券不退
3. admin 下调金额：approve approved_amount < 申请额（必填理由）；超上限拒绝
4. 驳回 / 撤回：状态迁移 + 驳回理由用户可见 + 可重新申请
5. 同订单在途申请互斥
6. 失败重试：渠道抛异常 → failed → retry（同 refund_no 幂等）→ succeeded
7. 0 元单：跳过渠道调用，作废码
8. 并发双批：第二个 approve 拒绝（状态门闩）
9. 咨询协商部分退：admin 代录金额 → 批准执行 → 预约取消
10. 码已使用（申请前已绑定/申请后被激活）不拦截：申请照单全收，admin 可强制批准
    （批准后码强制作废）；金额上限仍不超过实付
11. 全额退款退券（used → unused）；部分退不退券
12. 部分退可勾选已被使用的码（提交后由 admin 审批判断）
"""

from datetime import datetime, timedelta, timezone
import json
from unittest.mock import AsyncMock

import pytest
from app.core.payment.base import NotifyResult, PaymentChannelError
from app.models.database import Base
from app.models.feedback import Notification
from app.models.payment import (
    Coupon,
    CouponRedemption,
    PaymentOrder,
    PaymentOrderLine,
    PaymentRefund,
)
from app.models.user import User
from app.services import coupon_service as cs_mod
from app.services import payment_line_service as pline_mod
from app.services import payment_service as ps_mod
from app.services import refund_service as rs_mod
from app.services.coupon_service import CouponService
from app.services.payment_service import PaymentService
from app.services.refund_service import RefundNotFoundError, RefundService
from app.utils.simple_activation_manager import SimpleActivationManager
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
_TestSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)


class FakeChannel:
    """mock 渠道：记录退款调用，可注入失败；query_order 结果可编程"""

    def __init__(self):
        self.refunds = []
        self.fail_times = 0  # 前 N 次退款抛异常
        self.query_results = {}  # order_no → NotifyResult | None（缺省渠道无此单）
        self.query_calls = []
        self.on_refund = None  # 可选回调：模拟渠道退款期间发生的并发业务动作

    async def query_order(self, order_no):
        self.query_calls.append(order_no)
        return self.query_results.get(order_no)

    async def refund(self, order_no, amount_fen, refund_no):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise PaymentChannelError("模拟渠道超时")
        if self.on_refund is not None:
            await self.on_refund(order_no)
        self.refunds.append((order_no, amount_fen, refund_no))
        return json.dumps({"code": "10000", "fund_change": "Y"})

    async def create_order(self, order_no, amount_fen, subject):
        return f"https://qr.alipay.com/fake-{order_no}"

    async def verify_notify(self, form):
        return NotifyResult(
            order_no=form["out_trade_no"],
            channel_transaction_id=form.get("trade_no", ""),
            paid_at=None,
            total_amount_fen=int(round(float(form.get("total_amount", "0")) * 100)),
            trade_status=form.get("trade_status", "TRADE_SUCCESS"),
        )

    async def close_order(self, order_no):
        pass


@pytest.fixture
def fake_channel():
    return FakeChannel()


@pytest.fixture(autouse=True)
async def _setup_db(monkeypatch, tmp_path, fake_channel):
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    for mod in (ps_mod, cs_mod, rs_mod):
        monkeypatch.setattr(mod, "AsyncSessionLocal", _TestSessionLocal)
    monkeypatch.setattr(ps_mod, "get_channel", lambda name: fake_channel)
    monkeypatch.setattr(rs_mod, "get_channel", lambda name: fake_channel)

    mgr = SimpleActivationManager(base_dir=str(tmp_path / "simple"))
    monkeypatch.setattr(ps_mod, "_activation_manager", lambda: mgr)
    for mod in (ps_mod, rs_mod, pline_mod):
        monkeypatch.setattr(
            mod, "get_activation_with_manager", lambda code: (mgr, mgr.get_activation(code))
        )
    monkeypatch.setattr("app.utils.activation_audit.append_activation_audit", lambda *a, **k: None)
    monkeypatch.setattr(rs_mod.EmailService, "send_email", AsyncMock(return_value=None))
    monkeypatch.setattr(ps_mod.EmailService, "send_email", AsyncMock(return_value=None))

    from app.services.consultation_service import ConsultationService as _CS

    monkeypatch.setattr(_CS, "user_has_completed_report", classmethod(lambda cls, uid: True))

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

    yield mgr

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _get_order(order_id: str) -> PaymentOrder:
    async with _TestSessionLocal() as db:
        return (
            await db.execute(select(PaymentOrder).where(PaymentOrder.id == order_id))
        ).scalar_one()


async def _get_lines(order_id: str) -> list:
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


async def _make_annual_order(mgr, paid: int = 30000, discount: int = 0) -> PaymentOrder:
    """直插已交付年度订单（3 码，金额自定义；走行回填路径）"""
    codes = [mgr.create_activation(mode="combined").code for _ in range(3)]
    order = PaymentOrder(
        order_no=PaymentService._generate_order_no(),
        user_id="u1",
        product_type="annual_package",
        channel="alipay",
        amount_original=paid + discount,
        amount_discount=discount,
        amount_paid=paid,
        status="granted",
        meta=json.dumps({"codes": codes}),
        paid_at=datetime.now(timezone.utc),
    )
    async with _TestSessionLocal() as db:
        db.add(order)
        await db.commit()
        await db.refresh(order)
    return order


async def _notify_and_deliver(order):
    await PaymentService.handle_alipay_notify(
        {
            "out_trade_no": order.order_no,
            "trade_no": "T123",
            "trade_status": "TRADE_SUCCESS",
            "total_amount": f"{order.amount_paid / 100:.2f}",
            "sign": "x",
        }
    )
    return await _get_order(order.id)


# ─── 未交付订单退款辅助（2026-10-18）────────────────────────────


async def _make_undelivered_order(
    status: str = "pending", paid: int = 6900, product_type: str = "quarterly_package"
) -> PaymentOrder:
    """直插未交付订单（pending/paid，无明细行）"""
    order = PaymentOrder(
        order_no=PaymentService._generate_order_no(),
        user_id="u1",
        product_type=product_type,
        channel="alipay",
        amount_original=paid,
        amount_discount=0,
        amount_paid=paid,
        status=status,
    )
    async with _TestSessionLocal() as db:
        db.add(order)
        await db.commit()
        await db.refresh(order)
    return order


def _channel_paid_result(order: PaymentOrder, transaction_id: str = "T999") -> NotifyResult:
    """渠道查单已支付结果（金额与订单一致）"""
    return NotifyResult(
        order_no=order.order_no,
        channel_transaction_id=transaction_id,
        paid_at=datetime.now(timezone.utc),
        total_amount_fen=order.amount_paid,
        trade_status="TRADE_SUCCESS",
    )


async def _lock_coupon_for_order(order: PaymentOrder, amount: int = 1000) -> Coupon:
    """造一张被订单锁定的券（n=1：券级 locked + 核销行 locked）"""
    coupon = (await CouponService.create_coupons(amount=amount, count=1, owner_user_id="u1"))[0]
    async with _TestSessionLocal() as db:
        row = (await db.execute(select(Coupon).where(Coupon.id == coupon.id))).scalar_one()
        row.status = "locked"
        row.locked_order_id = order.id
        o = (
            await db.execute(select(PaymentOrder).where(PaymentOrder.id == order.id))
        ).scalar_one()
        o.coupon_id = coupon.id
        db.add(
            CouponRedemption(
                coupon_id=coupon.id, order_id=order.id, user_id="u1", status="locked"
            )
        )
        await db.commit()
    return coupon


# ─── 1. 全退闭环 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_refund_flow(fake_channel, _setup_db):
    mgr = _setup_db
    order = await _make_annual_order(mgr, paid=30000)

    refund = await RefundService.create_refund_request(
        user_id="u1", order_id=order.id, refund_type="full", reason="不想要了"
    )
    assert refund.status == "pending_review"
    assert refund.requested_amount == 30000
    assert refund.refund_no == order.order_no + "R001"

    executed = await RefundService.approve_refund(
        admin_user={"user_id": "admin"}, refund_id=refund.id
    )
    assert executed.status == "succeeded"
    assert executed.approved_amount == 30000
    assert executed.reviewed_by == "admin"
    assert executed.succeeded_at is not None
    assert fake_channel.refunds == [(order.order_no, 30000, order.order_no + "R001")]

    final = await _get_order(order.id)
    assert final.status == "refunded"
    assert final.amount_refunded == 30000
    assert final.refunded_at is not None
    assert all(l.status == "refunded" for l in await _get_lines(order.id))
    for code in json.loads(final.meta)["codes"]:
        assert mgr.get_activation(code).status == "revoked"


@pytest.mark.asyncio
async def test_full_refund_returns_coupon(fake_channel, _setup_db):
    """整单退完 → 券退回（used → unused 保留归属）"""
    mgr = _setup_db
    order = await _make_annual_order(mgr, paid=30000, discount=1000)
    coupon = (await CouponService.create_coupons(amount=1000, count=1, owner_user_id="u1"))[0]
    async with _TestSessionLocal() as db:
        row = (await db.execute(select(Coupon).where(Coupon.id == coupon.id))).scalar_one()
        row.status = "used"
        row.used_by_user_id = "u1"
        row.used_order_id = order.id
        o = (await db.execute(select(PaymentOrder).where(PaymentOrder.id == order.id))).scalar_one()
        o.coupon_id = coupon.id
        await db.commit()

    refund = await RefundService.create_refund_request(
        user_id="u1", order_id=order.id, refund_type="full", reason="测试"
    )
    await RefundService.approve_refund(admin_user={"user_id": "admin"}, refund_id=refund.id)

    async with _TestSessionLocal() as db:
        final = (await db.execute(select(Coupon).where(Coupon.id == coupon.id))).scalar_one()
    assert final.status == "unused"
    assert final.owner_user_id == "u1"


# ─── 2. 部分退（按码折算）─────────────────────────────────────


@pytest.mark.asyncio
async def test_partial_refund_one_code(fake_channel, _setup_db):
    """年度 3 码退 1 个：退 1/3 分摊实付（10000 分），订单 partially_refunded，
    只作废所选码，其余码 active，券不返还"""
    mgr = _setup_db
    order = await _make_annual_order(mgr, paid=30000)

    opts = await RefundService.get_refund_options("u1", order.id)  # 回填行 + 实时状态
    target = opts["lines"][1]  # 选第 2 个码

    refund = await RefundService.create_refund_request(
        user_id="u1",
        order_id=order.id,
        refund_type="partial",
        line_ids=[target["id"]],
        reason="朋友不要了",
    )
    assert refund.requested_amount == 10000
    executed = await RefundService.approve_refund(
        admin_user={"user_id": "admin"}, refund_id=refund.id
    )
    assert executed.status == "succeeded"
    assert fake_channel.refunds == [(order.order_no, 10000, order.order_no + "R001")]

    final = await _get_order(order.id)
    assert final.status == "partially_refunded"
    assert final.amount_refunded == 10000
    assert final.refunded_at is None

    lines_after = await _get_lines(order.id)
    assert [l.status for l in lines_after] == ["available", "refunded", "available"]
    codes = json.loads(final.meta)["codes"]
    assert mgr.get_activation(codes[1]).status == "revoked"
    assert mgr.get_activation(codes[0]).status == "active"
    assert mgr.get_activation(codes[2]).status == "active"

    # 部分退后再全退剩余 → 终态 + 渠道两次退款（不同 refund_no）
    refund2 = await RefundService.create_refund_request(
        user_id="u1", order_id=order.id, refund_type="full", reason="剩下的也退"
    )
    assert refund2.requested_amount == 20000
    executed2 = await RefundService.approve_refund(
        admin_user={"user_id": "admin"}, refund_id=refund2.id
    )
    assert executed2.refund_no == order.order_no + "R002"
    final2 = await _get_order(order.id)
    assert final2.status == "refunded"
    assert final2.amount_refunded == 30000


@pytest.mark.asyncio
async def test_partial_refund_keeps_coupon(fake_channel, _setup_db):
    """部分退不返还券"""
    mgr = _setup_db
    order = await _make_annual_order(mgr, paid=30000, discount=3000)
    coupon = (await CouponService.create_coupons(amount=3000, count=1, owner_user_id="u1"))[0]
    async with _TestSessionLocal() as db:
        row = (await db.execute(select(Coupon).where(Coupon.id == coupon.id))).scalar_one()
        row.status = "used"
        row.used_by_user_id = "u1"
        row.used_order_id = order.id
        o = (await db.execute(select(PaymentOrder).where(PaymentOrder.id == order.id))).scalar_one()
        o.coupon_id = coupon.id
        await db.commit()

    opts = await RefundService.get_refund_options("u1", order.id)  # 回填行
    refund = await RefundService.create_refund_request(
        user_id="u1", order_id=order.id, refund_type="partial", line_ids=[opts["lines"][0]["id"]], reason="x"
    )
    await RefundService.approve_refund(admin_user={"user_id": "admin"}, refund_id=refund.id)

    async with _TestSessionLocal() as db:
        final = (await db.execute(select(Coupon).where(Coupon.id == coupon.id))).scalar_one()
    assert final.status == "used"  # 部分退不退券


# ─── 3. admin 下调金额 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_approve_downgrade_amount_requires_note(fake_channel, _setup_db):
    mgr = _setup_db
    order = await _make_annual_order(mgr, paid=30000)
    refund = await RefundService.create_refund_request(
        user_id="u1", order_id=order.id, refund_type="full", reason="x"
    )
    # 下调无理由 → 拒绝
    with pytest.raises(ValueError, match="调整理由"):
        await RefundService.approve_refund(
            admin_user={"user_id": "admin"}, refund_id=refund.id, approved_amount=25000
        )
    # 带理由下调 → 成功
    executed = await RefundService.approve_refund(
        admin_user={"user_id": "admin"},
        refund_id=refund.id,
        approved_amount=25000,
        note="已使用 10 天，协商退 250",
    )
    assert executed.approved_amount == 25000
    assert "协商" in executed.reason_admin
    final = await _get_order(order.id)
    assert final.amount_refunded == 25000
    assert final.status == "partially_refunded"  # 下调退完所有行，累计 < 实付 → 非终态
    # 渠道按下调金额退款
    assert fake_channel.refunds == [(order.order_no, 25000, order.order_no + "R001")]


@pytest.mark.asyncio
async def test_approve_over_cap_rejected(fake_channel, _setup_db):
    mgr = _setup_db
    order = await _make_annual_order(mgr, paid=30000)
    refund = await RefundService.create_refund_request(
        user_id="u1", order_id=order.id, refund_type="full", reason="x"
    )
    with pytest.raises(ValueError, match="上限"):
        await RefundService.approve_refund(
            admin_user={"user_id": "admin"}, refund_id=refund.id, approved_amount=30001
        )
    assert refund.status == "pending_review"  # 拒批不改变状态


# ─── 4. 驳回 / 撤回 / 重提 ───────────────────────────────────


@pytest.mark.asyncio
async def test_reject_with_reason_then_reapply(fake_channel, _setup_db):
    mgr = _setup_db
    order = await _make_annual_order(mgr)
    refund = await RefundService.create_refund_request(
        user_id="u1", order_id=order.id, refund_type="full", reason="x"
    )
    with pytest.raises(ValueError):
        await RefundService.reject_refund(admin_user={"user_id": "a"}, refund_id=refund.id, note="")
    rejected = await RefundService.reject_refund(
        admin_user={"user_id": "admin"}, refund_id=refund.id, note="码已激活过"
    )
    assert rejected.status == "rejected"
    assert rejected.reason_admin == "码已激活过"
    # 用户详情可见驳回理由
    detail = await RefundService.get_user_refund("u1", refund.id)
    assert detail["reason_admin"] == "码已激活过"
    assert fake_channel.refunds == []

    # 驳回后可重新申请
    refund2 = await RefundService.create_refund_request(
        user_id="u1", order_id=order.id, refund_type="full", reason="再试试"
    )
    assert refund2.status == "pending_review"


@pytest.mark.asyncio
async def test_withdraw_and_reapply(fake_channel, _setup_db):
    mgr = _setup_db
    order = await _make_annual_order(mgr)
    refund = await RefundService.create_refund_request(
        user_id="u1", order_id=order.id, refund_type="full", reason="x"
    )
    withdrawn = await RefundService.withdraw_refund_request("u1", refund.id)
    assert withdrawn.status == "withdrawn"
    # 撤回后可再申请
    refund2 = await RefundService.create_refund_request(
        user_id="u1", order_id=order.id, refund_type="full", reason="y"
    )
    assert refund2.status == "pending_review"
    # 非本人不可操作
    with pytest.raises(RefundNotFoundError):
        await RefundService.withdraw_refund_request("u2", refund2.id)


@pytest.mark.asyncio
async def test_in_flight_mutex(fake_channel, _setup_db):
    mgr = _setup_db
    order = await _make_annual_order(mgr)
    await RefundService.create_refund_request(
        user_id="u1", order_id=order.id, refund_type="full", reason="x"
    )
    with pytest.raises(ValueError, match="待处理"):
        await RefundService.create_refund_request(
            user_id="u1", order_id=order.id, refund_type="full", reason="y"
        )


# ─── 5. 失败重试（渠道幂等）─────────────────────────────────


@pytest.mark.asyncio
async def test_channel_failure_and_retry(fake_channel, _setup_db):
    mgr = _setup_db
    order = await _make_annual_order(mgr, paid=30000)
    refund = await RefundService.create_refund_request(
        user_id="u1", order_id=order.id, refund_type="full", reason="x"
    )
    fake_channel.fail_times = 1
    with pytest.raises(PaymentChannelError):
        await RefundService.approve_refund(admin_user={"user_id": "admin"}, refund_id=refund.id)

    failed = await RefundService.admin_get_refund(refund.id)
    assert failed["status"] == "failed"
    assert failed["failed_reason"]

    # 重试：同 refund_no，渠道成功
    executed = await RefundService.retry_refund(admin_user={"user_id": "admin"}, refund_id=refund.id)
    assert executed.status == "succeeded"
    assert fake_channel.refunds == [(order.order_no, 30000, order.order_no + "R001")]
    assert (await _get_order(order.id)).status == "refunded"


@pytest.mark.asyncio
async def test_double_approve_mutex(fake_channel, _setup_db):
    """并发兜底：第二次 approve 因状态已变被拒"""
    mgr = _setup_db
    order = await _make_annual_order(mgr)
    refund = await RefundService.create_refund_request(
        user_id="u1", order_id=order.id, refund_type="full", reason="x"
    )
    await RefundService.approve_refund(admin_user={"user_id": "admin"}, refund_id=refund.id)
    with pytest.raises(ValueError, match="不可审批"):
        await RefundService.approve_refund(admin_user={"user_id": "admin2"}, refund_id=refund.id)
    assert len(fake_channel.refunds) == 1


# ─── 6. 0 元单 / 咨询协商 / 实时重验 ──────────────────────────


@pytest.mark.asyncio
async def test_zero_amount_order_refund(fake_channel, _setup_db):
    """0 元单：跳过渠道，作废码，订单 refunded"""
    mgr = _setup_db
    order = await _make_annual_order(mgr, paid=0, discount=29900)
    refund = await RefundService.create_refund_request(
        user_id="u1", order_id=order.id, refund_type="full", reason="x"
    )
    assert refund.requested_amount == 0
    executed = await RefundService.approve_refund(
        admin_user={"user_id": "admin"}, refund_id=refund.id
    )
    assert executed.status == "succeeded"
    assert fake_channel.refunds == []
    final = await _get_order(order.id)
    assert final.status == "refunded"
    for code in json.loads(final.meta)["codes"]:
        assert mgr.get_activation(code).status == "revoked"


@pytest.mark.asyncio
async def test_consultation_partial_admin_create(fake_channel, _setup_db):
    """咨询协商部分退：admin 代录金额 → 批准执行 → 预约取消"""
    order, _ = await PaymentService.create_order("u1", "consultation", "alipay", None)
    order = await _notify_and_deliver(order)
    assert order.status == "granted"
    from app.config.settings import settings as _settings
    assert order.amount_paid == _settings.CONSULTATION_PRICE

    # 用户自提 partial 需要行选择（咨询只有 1 行）
    opts = await RefundService.get_refund_options("u1", order.id)
    line_id = opts["lines"][0]["id"]

    refund = await RefundService.admin_create_refund_request(
        admin_user={"user_id": "admin"},
        order_id=order.id,
        refund_type="partial",
        amount=15000,
        line_ids=[line_id],
        reason="用户协商退一半",
        note="电话协商一致",
    )
    assert refund.originated == "admin"
    assert refund.created_by_admin == "admin"
    assert refund.requested_amount == 15000

    executed = await RefundService.approve_refund(admin_user={"user_id": "admin"}, refund_id=refund.id)
    assert executed.status == "succeeded"
    assert fake_channel.refunds == [(order.order_no, 15000, order.order_no + "R001")]

    final = await _get_order(order.id)
    assert final.status == "partially_refunded"
    booking_id = json.loads(final.meta)["booking_id"]
    async with _TestSessionLocal() as db:
        from app.models.payment import ConsultationBooking

        booking = (
            await db.execute(
                select(ConsultationBooking).where(ConsultationBooking.id == booking_id)
            )
        ).scalar_one()
    assert booking.status == "cancelled"


@pytest.mark.asyncio
async def test_code_claimed_after_request_admin_can_force_approve(fake_channel, _setup_db):
    """申请后码被激活：admin 为最终裁判，可强制批准；批准后全部码强制作废"""
    mgr = _setup_db
    order = await _make_annual_order(mgr)
    refund = await RefundService.create_refund_request(
        user_id="u1", order_id=order.id, refund_type="full", reason="x"
    )
    # 申请后 1 个码被他人激活（行实时状态变 used）→ 不再拦截批准
    codes = json.loads((await _get_order(order.id)).meta)["codes"]
    mgr.claim_owner(codes[0], {"user_id": "u9", "email": "x@test.com"})
    executed = await RefundService.approve_refund(
        admin_user={"user_id": "admin"}, refund_id=refund.id
    )
    assert executed.status == "succeeded"
    assert executed.approved_amount == 30000
    assert fake_channel.refunds == [(order.order_no, 30000, order.order_no + "R001")]
    assert (await _get_order(order.id)).status == "refunded"
    # 已被他人激活的码也随退款强制作废
    assert mgr.get_activation(codes[0]).status == "revoked"


@pytest.mark.asyncio
async def test_request_allowed_when_code_already_used(fake_channel, _setup_db):
    """申请时码已被使用（已绑定他人）：申请不再被拦截，提交后待 admin 审批"""
    mgr = _setup_db
    order = await _make_annual_order(mgr)
    # 申请前 1 个码已被绑定
    codes = json.loads((await _get_order(order.id)).meta)["codes"]
    mgr.claim_owner(codes[0], {"user_id": "u9", "email": "x@test.com"})

    # 能力视图：全退/部分退均允许提交（行状态仍如实展示供 admin 判断）
    opts = await RefundService.get_refund_options("u1", order.id)
    assert opts["full_allowed"] is True
    assert opts["partial_allowed"] is True
    assert [l["effective_status"] for l in opts["lines"]] == ["used", "available", "available"]

    refund = await RefundService.create_refund_request(
        user_id="u1", order_id=order.id, refund_type="full", reason="码未用到，想退"
    )
    assert refund.status == "pending_review"
    assert refund.requested_amount == 30000  # 上限 = min(剩余可退, 未退款行分摊)

    # admin 强制批准 → 全部码作废（含已绑定的码）
    executed = await RefundService.approve_refund(
        admin_user={"user_id": "admin"}, refund_id=refund.id
    )
    assert executed.status == "succeeded"
    for code in codes:
        assert mgr.get_activation(code).status == "revoked"


@pytest.mark.asyncio
async def test_partial_refund_can_select_used_code(fake_channel, _setup_db):
    """部分退可勾选已被使用的码：申请受理 → admin 批准 → 仅所选行退款并作废该码"""
    mgr = _setup_db
    order = await _make_annual_order(mgr, paid=30000)
    codes = json.loads((await _get_order(order.id)).meta)["codes"]
    mgr.claim_owner(codes[1], {"user_id": "u9", "email": "x@test.com"})

    opts = await RefundService.get_refund_options("u1", order.id)
    used_line = opts["lines"][1]
    assert used_line["effective_status"] == "used"

    refund = await RefundService.create_refund_request(
        user_id="u1",
        order_id=order.id,
        refund_type="partial",
        line_ids=[used_line["id"]],
        reason="这个码没用上",
    )
    assert refund.requested_amount == 10000
    executed = await RefundService.approve_refund(
        admin_user={"user_id": "admin"}, refund_id=refund.id
    )
    assert executed.status == "succeeded"
    final = await _get_order(order.id)
    assert final.status == "partially_refunded"
    assert final.amount_refunded == 10000
    lines_after = await _get_lines(order.id)
    assert [l.status for l in lines_after] == ["available", "refunded", "available"]
    assert mgr.get_activation(codes[1]).status == "revoked"
    assert mgr.get_activation(codes[0]).status == "active"


# ─── 7. 可退性视图 / 通知 ─────────────────────────────────────


@pytest.mark.asyncio
async def test_refund_options_view(fake_channel, _setup_db):
    mgr = _setup_db
    order = await _make_annual_order(mgr, paid=30000, discount=3000)
    opts = await RefundService.get_refund_options("u1", order.id)
    assert opts["full_allowed"] is True
    assert opts["partial_allowed"] is True
    assert opts["remaining_refundable"] == 30000
    assert len(opts["lines"]) == 3
    # 分摊校验：Σ = 订单金额
    assert sum(l["amount_paid_alloc"] for l in opts["lines"]) == 30000
    assert opts["pending_request"] is None

    # 非本人 404
    with pytest.raises(Exception):
        await RefundService.get_refund_options("u2", order.id)


@pytest.mark.asyncio
async def test_notifications_created(fake_channel, _setup_db, monkeypatch):
    """新申请 → admin 站内信；批准 → 用户站内信（SUPER_ADMIN_USER_IDS 配置 u_admin）"""
    monkeypatch.setattr(rs_mod.settings, "SUPER_ADMIN_USER_IDS", "u_admin", raising=False)
    async with _TestSessionLocal() as db:
        db.add(
            User(
                id="u_admin",
                email="admin@test.com",
                username="admin",
                password_hash="x",
                is_active=True,
                created_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

    mgr = _setup_db
    order = await _make_annual_order(mgr)
    await RefundService.create_refund_request(
        user_id="u1", order_id=order.id, refund_type="full", reason="x"
    )
    async with _TestSessionLocal() as db:
        admin_notifs = (
            (
                await db.execute(
                    select(Notification).where(
                        Notification.type == "refund_request",
                        Notification.user_id == "u_admin",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(admin_notifs) == 1

    refund = (
        await RefundService.list_user_refunds("u1")
    )[0][0]
    await RefundService.approve_refund(admin_user={"user_id": "u_admin"}, refund_id=refund["id"])
    async with _TestSessionLocal() as db:
        user_notifs = (
            (
                await db.execute(
                    select(Notification).where(
                        Notification.type == "refund_result", Notification.user_id == "u1"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(user_notifs) >= 2  # 已批准 + 已到账


# ─── 8. 未交付订单退款（2026-10-18 admin 主动退款）───────────────


@pytest.mark.asyncio
async def test_admin_full_refund_pending_channel_paid(fake_channel, _setup_db):
    """pending 订单渠道确认已支付：admin 全额退款闭环

    创建时与审批时各查单一次（再次确认）；保存 paid_at/channel_transaction_id；
    批准前订单推进 refunding 阻止交付，成功后 refunded；券仍 locked → 释放。
    """
    order = await _make_undelivered_order(status="pending", paid=6900)
    coupon = await _lock_coupon_for_order(order)
    fake_channel.query_results[order.order_no] = _channel_paid_result(order)

    # admin 视图：未交付订单无明细行、仅全退
    opts = await RefundService.admin_get_refund_options(order.order_no)
    assert opts["full_allowed"] is True
    assert opts["partial_allowed"] is False
    assert opts["lines"] == []
    assert opts["remaining_refundable"] == 6900

    # 代录接受商户订单号
    refund = await RefundService.admin_create_refund_request(
        admin_user={"user_id": "admin"},
        order_id=order.order_no,
        refund_type="full",
        reason="渠道已支付但本地未交付",
    )
    assert refund.requested_amount == 6900
    assert refund.originated == "admin"
    # 创建时已查单一次、保存渠道支付信息，并把订单带离 pending 关单池
    assert fake_channel.query_calls == [order.order_no]
    assert (await _get_order(order.id)).status == "paid"

    executed = await RefundService.approve_refund(
        admin_user={"user_id": "admin"}, refund_id=refund.id
    )
    assert executed.status == "succeeded"
    # 审批时再次确认
    assert fake_channel.query_calls == [order.order_no, order.order_no]
    assert fake_channel.refunds == [(order.order_no, 6900, order.order_no + "R001")]

    final = await _get_order(order.id)
    assert final.status == "refunded"
    assert final.amount_refunded == 6900
    assert final.paid_at is not None
    assert final.channel_transaction_id == "T999"
    assert await _get_lines(order.id) == []  # 未交付无明细行

    # 券仍 locked → release_coupon 释放（而非 return_coupon_on_refund）
    async with _TestSessionLocal() as db:
        c = (await db.execute(select(Coupon).where(Coupon.id == coupon.id))).scalar_one()
        redemption = (
            await db.execute(
                select(CouponRedemption).where(CouponRedemption.order_id == order.id)
            )
        ).scalar_one()
    assert c.status == "unused"
    assert redemption.status == "released"


@pytest.mark.asyncio
async def test_admin_pending_channel_unpaid_rejected(fake_channel, _setup_db):
    """pending 订单渠道未支付：创建即拒绝，不落退款单"""
    order = await _make_undelivered_order(status="pending")
    # 渠道无此单
    with pytest.raises(ValueError, match="已支付"):
        await RefundService.admin_create_refund_request(
            admin_user={"user_id": "admin"},
            order_id=order.id,
            refund_type="full",
            reason="x",
        )
    # 渠道有单但未支付
    fake_channel.query_results[order.order_no] = NotifyResult(
        order_no=order.order_no,
        channel_transaction_id="",
        paid_at=None,
        total_amount_fen=order.amount_paid,
        trade_status="WAIT_BUYER_PAY",
    )
    with pytest.raises(ValueError, match="已支付"):
        await RefundService.admin_create_refund_request(
            admin_user={"user_id": "admin"},
            order_id=order.id,
            refund_type="full",
            reason="x",
        )
    # 渠道金额不符
    fake_channel.query_results[order.order_no] = NotifyResult(
        order_no=order.order_no,
        channel_transaction_id="T1",
        paid_at=None,
        total_amount_fen=order.amount_paid - 100,
        trade_status="TRADE_SUCCESS",
    )
    with pytest.raises(ValueError, match="金额"):
        await RefundService.admin_create_refund_request(
            admin_user={"user_id": "admin"},
            order_id=order.id,
            refund_type="full",
            reason="x",
        )
    async with _TestSessionLocal() as db:
        count = (
            await db.execute(
                select(PaymentRefund).where(PaymentRefund.order_id == order.id)
            )
        ).scalars().all()
    assert count == []
    assert (await _get_order(order.id)).status == "pending"
    assert fake_channel.refunds == []


@pytest.mark.asyncio
async def test_admin_full_refund_paid_order(fake_channel, _setup_db):
    """paid 订单（本地已确认支付未交付）：创建与审批仍向渠道核实后全额退款"""
    order = await _make_undelivered_order(status="paid", paid=6900)
    fake_channel.query_results[order.order_no] = _channel_paid_result(order)

    refund = await RefundService.admin_create_refund_request(
        admin_user={"user_id": "admin"},
        order_id=order.id,
        refund_type="full",
        reason="已收款未交付",
    )
    assert refund.requested_amount == 6900
    assert fake_channel.query_calls == [order.order_no]  # 创建时核实渠道已支付

    executed = await RefundService.approve_refund(
        admin_user={"user_id": "admin"}, refund_id=refund.id
    )
    assert executed.status == "succeeded"
    assert fake_channel.query_calls == [order.order_no, order.order_no]  # 审批再次核实
    final = await _get_order(order.id)
    assert final.status == "refunded"
    assert final.amount_refunded == 6900


@pytest.mark.asyncio
async def test_reject_undelivered_refund_returns_order_to_pending(fake_channel, _setup_db):
    """未交付退款被驳回后订单回到 pending，对账仍可补交付，避免已付款订单悬空"""
    order = await _make_undelivered_order(status="pending", paid=6900)
    fake_channel.query_results[order.order_no] = _channel_paid_result(order)
    refund = await RefundService.admin_create_refund_request(
        admin_user={"user_id": "admin"},
        order_id=order.id,
        refund_type="full",
        reason="用户申请后又协商继续交付",
    )
    assert (await _get_order(order.id)).status == "paid"

    rejected = await RefundService.reject_refund(
        admin_user={"user_id": "admin"}, refund_id=refund.id, note="双方确认继续交付"
    )
    assert rejected.status == "rejected"
    async with _TestSessionLocal() as db:
        row = (await db.execute(select(PaymentOrder).where(PaymentOrder.id == order.id))).scalar_one()
        row.qr_code = "https://example.invalid/pay"  # 真实 pending 订单均有渠道预下单凭证
        await db.commit()
    current = await _get_order(order.id)
    assert current.status == "pending"

    await PaymentService._sync_order_from_channel(current, force=True)
    delivered = await _get_order(order.id)
    assert delivered.status == "granted"
    assert delivered.delivered_code


@pytest.mark.asyncio
async def test_user_and_partial_refund_on_undelivered_rejected(fake_channel, _setup_db):
    """用户自提 pending/paid、未交付部分退款均拒绝"""
    pending = await _make_undelivered_order(status="pending")
    paid = await _make_undelivered_order(status="paid")
    fake_channel.query_results[pending.order_no] = _channel_paid_result(pending)

    for order in (pending, paid):
        with pytest.raises(ValueError, match="未交付"):
            await RefundService.create_refund_request(
                user_id="u1", order_id=order.id, refund_type="full", reason="x"
            )
        with pytest.raises(ValueError, match="全额"):
            await RefundService.admin_create_refund_request(
                admin_user={"user_id": "admin"},
                order_id=order.id,
                refund_type="partial",
                reason="x",
            )
    # 用户视图对未交付订单不放开退款
    opts = await RefundService.get_refund_options("u1", paid.id)
    assert opts["full_allowed"] is False
    assert opts["partial_allowed"] is False


# ─── 9. 季度套餐 admin 协商部分退（2026-10-18）────────────────────


@pytest.mark.asyncio
async def test_admin_quarterly_partial_refund(fake_channel, _setup_db):
    """季度套餐：admin 可协商部分退（金额 ≤ 所选行分摊实付，行置 refunded 防重复退）；
    用户侧 partial 规则不放宽"""
    mgr = _setup_db
    order, _ = await PaymentService.create_order("u1", "quarterly_package", "alipay", None)
    order = await _notify_and_deliver(order)
    assert order.status == "granted"

    opts = await RefundService.get_refund_options("u1", order.id)
    line = opts["lines"][0]
    alloc = line["amount_paid_alloc"]
    assert alloc == order.amount_paid  # 季度单码单行

    # 用户侧 partial 不放宽
    assert opts["partial_allowed"] is False
    with pytest.raises(ValueError, match="全额退款"):
        await RefundService.create_refund_request(
            user_id="u1",
            order_id=order.id,
            refund_type="partial",
            line_ids=[line["id"]],
            reason="x",
        )

    # admin 视图 partial_allowed=True
    admin_opts = await RefundService.admin_get_refund_options(order.id)
    assert admin_opts["partial_allowed"] is True

    # 重复选择同一行 → 拒绝，防止分摊金额被重复计算
    with pytest.raises(ValueError, match="重复"):
        await RefundService.admin_create_refund_request(
            admin_user={"user_id": "admin"},
            order_id=order.id,
            refund_type="partial",
            amount=alloc,
            line_ids=[line["id"], line["id"]],
            reason="x",
        )

    # 金额超过该行分摊实付 → 拒绝
    with pytest.raises(ValueError, match="上限"):
        await RefundService.admin_create_refund_request(
            admin_user={"user_id": "admin"},
            order_id=order.id,
            refund_type="partial",
            amount=alloc + 1,
            line_ids=[line["id"]],
            reason="x",
        )

    # 协商金额部分退 → 成功；行置 refunded；订单 partially_refunded；码作废
    refund = await RefundService.admin_create_refund_request(
        admin_user={"user_id": "admin"},
        order_id=order.id,
        refund_type="partial",
        amount=alloc - 1000,
        line_ids=[line["id"]],
        reason="用户使用一段时间后协商退部分",
    )
    assert refund.requested_amount == alloc - 1000
    executed = await RefundService.approve_refund(
        admin_user={"user_id": "admin"}, refund_id=refund.id
    )
    assert executed.status == "succeeded"
    assert fake_channel.refunds == [(order.order_no, alloc - 1000, order.order_no + "R001")]

    final = await _get_order(order.id)
    assert final.status == "partially_refunded"
    assert final.amount_refunded == alloc - 1000
    lines_after = await _get_lines(order.id)
    assert [l.status for l in lines_after] == ["refunded"]
    code = json.loads(final.meta)["codes"][0]
    assert mgr.get_activation(code).status == "revoked"

    # 行已 refunded → 防止重复退
    with pytest.raises(ValueError, match="无可申请项"):
        await RefundService.admin_create_refund_request(
            admin_user={"user_id": "admin"},
            order_id=order.id,
            refund_type="partial",
            amount=1000,
            line_ids=[line["id"]],
            reason="重复退",
        )


# ─── 10. revoke_codes 选择保留码（2026-10-18）─────────────────────


@pytest.mark.asyncio
async def test_revoke_codes_false_keeps_codes(fake_channel, _setup_db):
    """approve revoke_codes=False：退款成功但码保留；落库且 refund_to_dict 输出"""
    mgr = _setup_db
    order = await _make_annual_order(mgr, paid=30000)
    refund = await RefundService.create_refund_request(
        user_id="u1", order_id=order.id, refund_type="full", reason="x"
    )
    executed = await RefundService.approve_refund(
        admin_user={"user_id": "admin"}, refund_id=refund.id, revoke_codes=False
    )
    assert executed.status == "succeeded"
    assert executed.revoke_codes is False

    final = await _get_order(order.id)
    assert final.status == "refunded"
    assert all(l.status == "refunded" for l in await _get_lines(order.id))
    # 码保留不作废
    for code in json.loads(final.meta)["codes"]:
        assert mgr.get_activation(code).status == "active"

    detail = await RefundService.admin_get_refund(refund.id)
    assert detail["revoke_codes"] is False


@pytest.mark.asyncio
async def test_revoke_codes_default_true_and_retry_reuses_choice(fake_channel, _setup_db):
    """默认（不传/NULL）按作废；失败后重试沿用审批时保存的 revoke_codes=False"""
    mgr = _setup_db
    # 默认作废
    order1 = await _make_annual_order(mgr, paid=30000)
    refund1 = await RefundService.create_refund_request(
        user_id="u1", order_id=order1.id, refund_type="full", reason="x"
    )
    await RefundService.approve_refund(admin_user={"user_id": "admin"}, refund_id=refund1.id)
    for code in json.loads((await _get_order(order1.id)).meta)["codes"]:
        assert mgr.get_activation(code).status == "revoked"
    detail1 = await RefundService.admin_get_refund(refund1.id)
    assert detail1["revoke_codes"] is True

    # 审批选保留码 + 渠道失败 → 重试仍保留
    order2 = await _make_annual_order(mgr, paid=30000)
    refund2 = await RefundService.create_refund_request(
        user_id="u1", order_id=order2.id, refund_type="full", reason="x"
    )
    fake_channel.fail_times = 1
    with pytest.raises(PaymentChannelError):
        await RefundService.approve_refund(
            admin_user={"user_id": "admin"}, refund_id=refund2.id, revoke_codes=False
        )
    failed = await RefundService.admin_get_refund(refund2.id)
    assert failed["status"] == "failed"
    assert failed["revoke_codes"] is False  # 审批时选择已落库

    executed = await RefundService.retry_refund(
        admin_user={"user_id": "admin"}, refund_id=refund2.id
    )
    assert executed.status == "succeeded"
    codes2 = json.loads((await _get_order(order2.id)).meta)["codes"]
    for code in codes2:
        assert mgr.get_activation(code).status == "active"  # 重试沿用保留选择


# ─── 11. 未交付退款竞态与金额不变式（2026-10-18 审查补强）────────


@pytest.mark.asyncio
async def test_undelivered_refund_amount_must_be_full(fake_channel, _setup_db):
    """未交付订单创建/审批两侧都禁止下调金额，避免无明细行的部分退款死态"""
    order = await _make_undelivered_order(status="pending", paid=6900)
    fake_channel.query_results[order.order_no] = _channel_paid_result(order)

    with pytest.raises(ValueError, match="全额退款"):
        await RefundService.admin_create_refund_request(
            admin_user={"user_id": "admin"},
            order_id=order.id,
            refund_type="full",
            amount=100,
            reason="试图只退一部分",
        )

    refund = await RefundService.admin_create_refund_request(
        admin_user={"user_id": "admin"},
        order_id=order.id,
        refund_type="full",
        reason="渠道已收款但未交付",
    )
    with pytest.raises(ValueError, match="不允许调整金额|全额退款"):
        await RefundService.approve_refund(
            admin_user={"user_id": "admin"},
            refund_id=refund.id,
            approved_amount=100,
            note="协商",
        )
    assert (await _get_order(order.id)).status == "paid"
    detail = await RefundService.admin_get_refund(refund.id)
    assert detail["status"] == "pending_review"
    assert fake_channel.refunds == []


@pytest.mark.asyncio
async def test_in_flight_refund_blocks_order_close_paths(fake_channel, _setup_db):
    """兼容历史在途单：pending 订单有退款处理中时不得被关单/取消"""
    order = await _make_undelivered_order(status="pending", paid=6900)
    async with _TestSessionLocal() as db:
        row = (await db.execute(select(PaymentOrder).where(PaymentOrder.id == order.id))).scalar_one()
        row.created_at = datetime.now(timezone.utc) - timedelta(days=1)
        db.add(
            PaymentRefund(
                refund_no=order.order_no + "R001",
                order_id=order.id,
                order_no=order.order_no,
                user_id="u1",
                originated="admin",
                refund_type="full",
                requested_amount=6900,
                reason_user="已收款未交付",
                status="pending_review",
            )
        )
        await db.commit()

    assert await PaymentService.close_timeout_orders() == 0
    assert await PaymentService.close_pending_orders_for_user("u1") == 0
    with pytest.raises(ValueError, match="退款申请正在处理中"):
        await PaymentService.cancel_order("u1", order.id)
    assert (await _get_order(order.id)).status == "pending"
    assert fake_channel.refunds == []


@pytest.mark.asyncio
async def test_delivery_is_rejected_while_undelivered_refund_executes(fake_channel, _setup_db):
    """退款审批已认领 refunding 后，迟到 notify/对账交付必须失败且不能生成激活码"""
    order = await _make_undelivered_order(status="pending", paid=6900)
    fake_channel.query_results[order.order_no] = _channel_paid_result(order)
    refund = await RefundService.admin_create_refund_request(
        admin_user={"user_id": "admin"},
        order_id=order.id,
        refund_type="full",
        reason="渠道已收款但未交付",
    )

    delivery_errors = []

    async def late_delivery(_order_no):
        try:
            await PaymentService._deliver_order(order.id)
        except ValueError as e:
            delivery_errors.append(str(e))

    fake_channel.on_refund = late_delivery
    executed = await RefundService.approve_refund(
        admin_user={"user_id": "admin"}, refund_id=refund.id
    )

    assert executed.status == "succeeded"
    assert delivery_errors and "refunding" in delivery_errors[0]
    final = await _get_order(order.id)
    assert final.status == "refunded"
    assert final.delivered_code is None
    assert await _get_lines(order.id) == []
