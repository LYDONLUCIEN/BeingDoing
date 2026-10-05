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
10. 申请后码被激活：approve 实时重验，上限收缩/拒批
11. 全额退款退券（used → unused）；部分退不退券
"""

from datetime import datetime, timedelta, timezone
import json
from unittest.mock import AsyncMock

import pytest
from app.core.payment.base import PaymentChannelError
from app.models.database import Base
from app.models.feedback import Notification
from app.models.payment import Coupon, PaymentOrder, PaymentOrderLine, PaymentRefund
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
    """mock 渠道：记录退款调用，可注入失败"""

    def __init__(self):
        self.refunds = []
        self.fail_times = 0  # 前 N 次退款抛异常

    async def refund(self, order_no, amount_fen, refund_no):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise PaymentChannelError("模拟渠道超时")
        self.refunds.append((order_no, amount_fen, refund_no))
        return json.dumps({"code": "10000", "fund_change": "Y"})

    async def create_order(self, order_no, amount_fen, subject):
        return f"https://qr.alipay.com/fake-{order_no}"

    async def verify_notify(self, form):
        from app.core.payment.base import NotifyResult

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
async def test_code_claimed_after_request_blocks_approve(fake_channel, _setup_db):
    """申请后码被激活：approve 实时重验 → 拒批（请驳回）"""
    mgr = _setup_db
    order = await _make_annual_order(mgr)
    refund = await RefundService.create_refund_request(
        user_id="u1", order_id=order.id, refund_type="full", reason="x"
    )
    # 申请后 1 个码被他人激活
    codes = json.loads((await _get_order(order.id)).meta)["codes"]
    mgr.claim_owner(codes[0], {"user_id": "u9", "email": "x@test.com"})
    # 上限实时收缩：3 码只剩 2 码可退（20000 < 申请 30000）→ 拒批并提示收缩后上限
    with pytest.raises(ValueError, match="超出实时可退上限"):
        await RefundService.approve_refund(admin_user={"user_id": "admin"}, refund_id=refund.id)
    assert fake_channel.refunds == []
    assert (await _get_order(order.id)).status == "granted"


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
