"""
支付订单服务测试（P2a 支付宝闭环，mock 渠道层，不打真实支付宝）

测试场景：
1. 金额计算：无券 / 有券 / 券>原价→0 元 / 会员价叠加（先折后券）/ 过期会员
2. 下单锁券 + 渠道下单存 pay_url（page.pay 跳转 URL，存 qr_code 列）
3. 取消订单释放券（尝试渠道关单）
4. 回调幂等：重复通知不重复发码
5. 回调金额不符拒绝交付
6. 0 元单直接 granted（不调渠道、核销券、发邮件）
7. 超时关单释放券
8. 退款守卫：码已被 claim 拒绝
9. 退款成功作废码（渠道退款 + status refunded + 码 revoked）

使用独立 in-memory SQLite + monkeypatch 替换 AsyncSessionLocal；
激活码管理器指向 tmp_path；审计日志与邮件均 mock，避免污染真实数据。
"""

from datetime import datetime, timedelta, timezone
import json
from unittest.mock import AsyncMock

import pytest
from app.config.settings import settings
from app.core.payment.base import NotifyResult
from app.models.database import Base
from app.models.feedback import Notification
from app.models.payment import Coupon, PaymentOrder
from app.models.user import User
from app.services import coupon_service as cs_mod
from app.services import payment_service as ps_mod
from app.services.coupon_service import CouponService
from app.services.payment_service import OrderNotFoundError, PaymentService
from app.utils.simple_activation_manager import SimpleActivationManager
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# ─── 测试专用引擎 + 会话工厂 ──────────────────────────────────

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
_TestSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)


class FakeAlipayChannel:
    """mock 支付宝渠道：记录调用，verify_notify 直接解析 form（不验签）"""

    def __init__(self):
        self.created_orders = []  # (order_no, amount_fen, subject)
        self.closed_orders = []
        self.refunds = []  # (order_no, amount_fen, refund_no)
        self.query_results = {}  # order_no -> NotifyResult | None | Exception

    async def create_order(self, order_no, amount_fen, subject):
        self.created_orders.append((order_no, amount_fen, subject))
        return f"https://openapi.alipay.com/gateway.do?fake-page-pay-{order_no}"

    async def verify_notify(self, form):
        yuan = form.get("total_amount", "0")
        return NotifyResult(
            order_no=form["out_trade_no"],
            channel_transaction_id=form.get("trade_no", ""),
            paid_at=None,
            total_amount_fen=int(round(float(yuan) * 100)),
            trade_status=form.get("trade_status", "TRADE_SUCCESS"),
        )

    async def refund(self, order_no, amount_fen, refund_no):
        self.refunds.append((order_no, amount_fen, refund_no))

    async def close_order(self, order_no):
        self.closed_orders.append(order_no)

    async def query_order(self, order_no):
        """对账查单：query_results 中未配置视为渠道无此单（返回 None）"""
        result = self.query_results.get(order_no)
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def fake_channel():
    return FakeAlipayChannel()


@pytest.fixture(autouse=True)
async def _setup_db(monkeypatch, tmp_path, fake_channel):
    """每个测试前：建表 + 插测试用户 + mock 渠道/激活码管理器/审计/邮件"""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # DB：payment_service 与 coupon_service 各自引用了模块级 AsyncSessionLocal
    monkeypatch.setattr(ps_mod, "AsyncSessionLocal", _TestSessionLocal)
    monkeypatch.setattr(cs_mod, "AsyncSessionLocal", _TestSessionLocal)

    # 渠道层：get_channel → FakeAlipayChannel
    monkeypatch.setattr(ps_mod, "get_channel", lambda name: fake_channel)

    # 激活码管理器：指向 tmp_path（不写真实 data/simple）
    mgr = SimpleActivationManager(base_dir=str(tmp_path / "simple"))
    monkeypatch.setattr(ps_mod, "_activation_manager", lambda: mgr)
    monkeypatch.setattr(
        ps_mod, "get_activation_with_manager", lambda code: (mgr, mgr.get_activation(code))
    )

    # 审计日志：不写文件
    monkeypatch.setattr("app.utils.activation_audit.append_activation_audit", lambda *a, **k: None)

    # 邮件：mock 发送
    monkeypatch.setattr(ps_mod.EmailService, "send_email", AsyncMock(return_value=None))

    # 测试用户：u1 普通；u2 生效会员（lifetime）；u3 过期会员
    now = datetime.now(timezone.utc)
    async with _TestSessionLocal() as db:
        db.add_all(
            [
                User(
                    id="u1",
                    email="alice@test.com",
                    username="alice",
                    password_hash="x",
                    is_active=True,
                    created_at=now,
                ),
                User(
                    id="u2",
                    email="bob@test.com",
                    username="bob",
                    password_hash="x",
                    is_active=True,
                    created_at=now,
                    membership_plan="lifetime",
                    membership_expires_at=now + timedelta(days=365),
                ),
                User(
                    id="u3",
                    email="carol@test.com",
                    username="carol",
                    password_hash="x",
                    is_active=True,
                    created_at=now,
                    membership_plan="monthly",
                    membership_expires_at=now - timedelta(days=1),
                ),
            ]
        )
        await db.commit()

    yield

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _get_user(user_id: str) -> User:
    async with _TestSessionLocal() as db:
        return (await db.execute(select(User).where(User.id == user_id))).scalar_one()


async def _get_order(order_id: str) -> PaymentOrder:
    async with _TestSessionLocal() as db:
        return (
            await db.execute(select(PaymentOrder).where(PaymentOrder.id == order_id))
        ).scalar_one()


async def _get_coupon(coupon_id: str) -> Coupon:
    async with _TestSessionLocal() as db:
        return (await db.execute(select(Coupon).where(Coupon.id == coupon_id))).scalar_one()


def _notify_form(order: PaymentOrder, amount_fen: int = None, **overrides) -> dict:
    """构造支付宝通知 form（FakeChannel 直接解析）"""
    fen = order.amount_paid if amount_fen is None else amount_fen
    form = {
        "out_trade_no": order.order_no,
        "trade_no": "2026071922001400000001",
        "trade_status": "TRADE_SUCCESS",
        "total_amount": f"{fen / 100:.2f}",
        "gmt_payment": "2026-07-19 16:00:00",
        "sign": "fake-sign",
        "sign_type": "RSA2",
    }
    form.update(overrides)
    return form


# ─── 金额计算 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_compute_amounts_no_coupon():
    """无券普通用户：原价支付，无抵扣"""
    user = await _get_user("u1")
    original, discount, paid = PaymentService.compute_amounts(user, coupon_amount=0)
    assert (original, discount, paid) == (settings.ANNUAL_PRICE, 0, settings.ANNUAL_PRICE)


@pytest.mark.asyncio
async def test_compute_amounts_with_coupon():
    """有券：实付 = 原价 - 券面额，抵扣 = 券面额"""
    user = await _get_user("u1")
    original, discount, paid = PaymentService.compute_amounts(user, coupon_amount=5000)
    assert (original, discount, paid) == (settings.ANNUAL_PRICE, 5000, settings.ANNUAL_PRICE - 5000)


@pytest.mark.asyncio
async def test_compute_amounts_coupon_exceeds_price():
    """券面额 > 原价：实付下限 0 元，抵扣 = 原价"""
    user = await _get_user("u1")
    original, discount, paid = PaymentService.compute_amounts(user, coupon_amount=20000)
    assert (original, discount, paid) == (
        settings.ANNUAL_PRICE,
        settings.ANNUAL_PRICE,
        0,
    )


@pytest.mark.asyncio
async def test_compute_amounts_member_then_coupon():
    """会员价叠加券：先折（原价×0.85 四舍五入）后券"""
    user = await _get_user("u2")  # 生效会员
    annual = settings.ANNUAL_PRICE
    member_price = round(annual * settings.MEMBER_DISCOUNT_PERCENT / 100)
    _, discount, paid = PaymentService.compute_amounts(user, coupon_amount=0)
    assert paid == member_price
    assert discount == annual - member_price
    # 叠加 5000 券
    _, discount2, paid2 = PaymentService.compute_amounts(user, coupon_amount=5000)
    assert paid2 == member_price - 5000
    assert discount2 == annual - (member_price - 5000)


@pytest.mark.asyncio
async def test_compute_amounts_expired_member_no_discount():
    """过期会员：不享会员价"""
    user = await _get_user("u3")  # 会员已过期
    _, discount, paid = PaymentService.compute_amounts(user, coupon_amount=0)
    assert (discount, paid) == (0, settings.ANNUAL_PRICE)


# ─── 下单 ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_order_locks_coupon(fake_channel):
    """下单锁券：券 unused→locked（locked_order_id=订单）；渠道下单金额正确；pay_url 落库"""
    coupon = (await CouponService.create_coupons(amount=5000, count=1))[0]

    order, payment = await PaymentService.create_order(
        user_id="u1",
        product_type="quarterly_package",
        channel="alipay",
        coupon_code=coupon.code,
    )

    # 券已锁定到该订单
    locked = await _get_coupon(coupon.id)
    assert locked.status == "locked"
    assert locked.locked_order_id == order.id

    # 订单字段
    assert order.status == "pending"
    assert order.amount_paid == 1900
    assert order.amount_discount == 5000
    assert order.coupon_id == coupon.id
    assert len(order.order_no) == 21 and order.order_no.startswith("X")

    # 渠道下单：金额 = 实付，跳转 URL 存 qr_code 列
    assert fake_channel.created_orders == [(order.order_no, 1900, "季度套餐")]
    assert payment == {
        "channel": "alipay",
        "pay_url": f"https://openapi.alipay.com/gateway.do?fake-page-pay-{order.order_no}",
    }
    assert (await _get_order(order.id)).qr_code == payment["pay_url"]


@pytest.mark.asyncio
async def test_create_order_invalid_channel_and_product():
    """不支持的渠道/商品 → ValueError（微信提示即将上线）"""
    with pytest.raises(ValueError, match="即将上线"):
        await PaymentService.create_order("u1", "quarterly_package", "wechat")
    with pytest.raises(ValueError):
        await PaymentService.create_order("u1", "membership_monthly", "alipay")


# ─── 0 元单 ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_zero_amount_order_granted_immediately(fake_channel):
    """0 元单：不调渠道，直接 granted；券核销；发码 + 邮件"""
    coupon = (await CouponService.create_coupons(amount=20000, count=1))[0]

    order, payment = await PaymentService.create_order(
        user_id="u1",
        product_type="quarterly_package",
        channel="alipay",
        coupon_code=coupon.code,
    )

    assert payment is None
    assert fake_channel.created_orders == []  # 未调渠道

    final = await _get_order(order.id)
    assert final.status == "granted"
    assert final.amount_paid == 0
    assert final.delivered_code and len(final.delivered_code) == 10
    assert final.paid_at is not None

    # 券已核销
    used = await _get_coupon(coupon.id)
    assert used.status == "used"
    assert used.used_order_id == order.id
    assert used.used_by_user_id == "u1"

    # 邮件已发（mock）
    ps_mod.EmailService.send_email.assert_awaited_once()
    kwargs = ps_mod.EmailService.send_email.await_args.kwargs
    assert kwargs["to_email"] == "alice@test.com"
    assert final.delivered_code in kwargs["body_text"]


# ─── 取消 ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_order_releases_coupon(fake_channel):
    """取消：尝试渠道关单 + 释放券 + status cancelled"""
    coupon = (await CouponService.create_coupons(amount=5000, count=1))[0]
    order, _ = await PaymentService.create_order("u1", "quarterly_package", "alipay", coupon.code)

    cancelled = await PaymentService.cancel_order("u1", order.id)
    assert cancelled.status == "cancelled"

    # 券释放回 unused
    released = await _get_coupon(coupon.id)
    assert released.status == "unused"
    assert released.locked_order_id is None

    # 渠道关单已尝试
    assert fake_channel.closed_orders == [order.order_no]


@pytest.mark.asyncio
async def test_cancel_order_guards():
    """取消守卫：非本人 404；非 pending 400"""
    coupon = (await CouponService.create_coupons(amount=20000, count=1))[0]
    order, _ = await PaymentService.create_order("u1", "quarterly_package", "alipay", coupon.code)

    # 非本人
    with pytest.raises(OrderNotFoundError):
        await PaymentService.cancel_order("u2", order.id)
    # 0 元单已 granted，不可取消
    with pytest.raises(ValueError):
        await PaymentService.cancel_order("u1", order.id)


# ─── 回调 ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_delivers_and_is_idempotent(fake_channel, tmp_path):
    """回调交付 + 幂等：重复通知不重复发码"""
    order, _ = await PaymentService.create_order("u1", "quarterly_package", "alipay", None)

    await PaymentService.handle_alipay_notify(_notify_form(order))
    first = await _get_order(order.id)
    assert first.status == "granted"
    assert first.delivered_code
    assert first.channel_transaction_id == "2026071922001400000001"
    assert first.paid_at is not None

    # 重复通知：同一交付码，激活码管理器里只有一条记录
    await PaymentService.handle_alipay_notify(_notify_form(order))
    second = await _get_order(order.id)
    assert second.status == "granted"
    assert second.delivered_code == first.delivered_code
    mgr = SimpleActivationManager(base_dir=str(tmp_path / "simple"))
    assert len(mgr.list_activations()) == 1


@pytest.mark.asyncio
async def test_notify_trade_finished_also_delivers():
    """TRADE_FINISHED 同样视为支付成功"""
    order, _ = await PaymentService.create_order("u1", "quarterly_package", "alipay", None)
    await PaymentService.handle_alipay_notify(_notify_form(order, trade_status="TRADE_FINISHED"))
    assert (await _get_order(order.id)).status == "granted"


@pytest.mark.asyncio
async def test_notify_amount_mismatch_rejected():
    """回调金额与订单实付不符：拒绝交付（ValueError），订单保持 pending 不发码"""
    order, _ = await PaymentService.create_order("u1", "quarterly_package", "alipay", None)

    with pytest.raises(ValueError, match="金额"):
        await PaymentService.handle_alipay_notify(
            _notify_form(order, amount_fen=order.amount_paid - 1)
        )

    final = await _get_order(order.id)
    assert final.status == "pending"
    assert final.delivered_code is None


@pytest.mark.asyncio
async def test_notify_non_paid_status_ignored():
    """非成功交易状态（如 WAIT_BUYER_PAY）：确认收到但不交付"""
    order, _ = await PaymentService.create_order("u1", "quarterly_package", "alipay", None)
    await PaymentService.handle_alipay_notify(_notify_form(order, trade_status="WAIT_BUYER_PAY"))
    assert (await _get_order(order.id)).status == "pending"


# ─── 主动查单对账（notify 兜底）─────────────────────────────────


async def _backdate_order(order_id: str, minutes: int = 5) -> None:
    """把订单 created_at 拨到指定分钟前（使订单进入对账扫描范围）"""
    async with _TestSessionLocal() as db:
        row = (
            await db.execute(select(PaymentOrder).where(PaymentOrder.id == order_id))
        ).scalar_one()
        row.created_at = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        await db.commit()


@pytest.mark.asyncio
async def test_reconcile_delivers_paid_order(fake_channel):
    """对账：渠道已支付（TRADE_SUCCESS）且金额一致 → 补交付 granted"""
    order, _ = await PaymentService.create_order("u1", "quarterly_package", "alipay", None)
    await _backdate_order(order.id)
    fake_channel.query_results[order.order_no] = NotifyResult(
        order_no=order.order_no,
        channel_transaction_id="2026072500001",
        paid_at=None,
        total_amount_fen=order.amount_paid,
        trade_status="TRADE_SUCCESS",
    )

    delivered = await PaymentService.reconcile_pending_orders()

    assert delivered == 1
    final = await _get_order(order.id)
    assert final.status == "granted"
    assert final.delivered_code
    assert final.channel_transaction_id == "2026072500001"


@pytest.mark.asyncio
async def test_reconcile_skips_not_exist_and_unpaid(fake_channel):
    """对账：渠道无此单（None）/ 未支付（WAIT_BUYER_PAY）→ 保持 pending"""
    order_none, _ = await PaymentService.create_order("u1", "quarterly_package", "alipay", None)
    order_unpaid, _ = await PaymentService.create_order("u1", "quarterly_package", "alipay", None)
    await _backdate_order(order_none.id)
    await _backdate_order(order_unpaid.id)
    # order_none 不配置 query_results → 返回 None；order_unpaid 返回未支付状态
    fake_channel.query_results[order_unpaid.order_no] = NotifyResult(
        order_no=order_unpaid.order_no,
        channel_transaction_id="",
        paid_at=None,
        total_amount_fen=order_unpaid.amount_paid,
        trade_status="WAIT_BUYER_PAY",
    )

    delivered = await PaymentService.reconcile_pending_orders()

    assert delivered == 0
    assert (await _get_order(order_none.id)).status == "pending"
    assert (await _get_order(order_unpaid.id)).status == "pending"


@pytest.mark.asyncio
async def test_reconcile_amount_mismatch_skipped(fake_channel):
    """对账：渠道已支付但金额不符 → 不交付，保持 pending"""
    order, _ = await PaymentService.create_order("u1", "quarterly_package", "alipay", None)
    await _backdate_order(order.id)
    fake_channel.query_results[order.order_no] = NotifyResult(
        order_no=order.order_no,
        channel_transaction_id="2026072500002",
        paid_at=None,
        total_amount_fen=order.amount_paid - 1,
        trade_status="TRADE_SUCCESS",
    )

    delivered = await PaymentService.reconcile_pending_orders()

    assert delivered == 0
    final = await _get_order(order.id)
    assert final.status == "pending"
    assert final.delivered_code is None


# ─── 即时主动查单（sync 参数）───────────────────────────────────


@pytest.mark.asyncio
async def test_get_order_sync_delivers_paid(fake_channel):
    """sync=True 即时查单：渠道已支付且金额一致 → 返回 granted，不再带 pay_url"""
    ps_mod._ORDER_SYNC_COOLDOWN.clear()
    order, _ = await PaymentService.create_order("u1", "quarterly_package", "alipay", None)
    fake_channel.query_results[order.order_no] = NotifyResult(
        order_no=order.order_no,
        channel_transaction_id="2026072500010",
        paid_at=None,
        total_amount_fen=order.amount_paid,
        trade_status="TRADE_SUCCESS",
    )

    detail = await PaymentService.get_order_by_no("u1", order.order_no, sync=True)

    assert detail["order"]["status"] == "granted"
    assert detail["order"]["delivered_code"]
    assert detail["pay_url"] is None


@pytest.mark.asyncio
async def test_get_order_sync_cooldown(fake_channel):
    """sync 冷却：10 秒内第二次 sync 不再调渠道查单"""
    ps_mod._ORDER_SYNC_COOLDOWN.clear()
    order, _ = await PaymentService.create_order("u1", "quarterly_package", "alipay", None)
    calls = 0

    async def _counting_query(order_no):
        nonlocal calls
        calls += 1
        return None  # 渠道无此单

    fake_channel.query_order = _counting_query

    await PaymentService.get_user_order("u1", order.id, sync=True)
    await PaymentService.get_user_order("u1", order.id, sync=True)

    assert calls == 1
    assert (await _get_order(order.id)).status == "pending"


# ─── 超时关单 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_close_timeout_orders_releases_coupon(fake_channel):
    """超时关单：pending 超 ORDER_TIMEOUT_MINUTES → closed + 释放券 + 尝试渠道关单"""
    coupon = (await CouponService.create_coupons(amount=5000, count=1))[0]
    order, _ = await PaymentService.create_order("u1", "quarterly_package", "alipay", coupon.code)

    # 手工把 created_at 拨到超时前
    async with _TestSessionLocal() as db:
        row = (
            await db.execute(select(PaymentOrder).where(PaymentOrder.id == order.id))
        ).scalar_one()
        row.created_at = datetime.now(timezone.utc) - timedelta(
            minutes=settings.ORDER_TIMEOUT_MINUTES + 1
        )
        await db.commit()

    closed = await PaymentService.close_timeout_orders()
    assert closed == 1

    final = await _get_order(order.id)
    assert final.status == "closed"
    assert final.closed_at is not None
    assert (await _get_coupon(coupon.id)).status == "unused"
    assert fake_channel.closed_orders == [order.order_no]


@pytest.mark.asyncio
async def test_close_timeout_orders_skips_fresh_orders():
    """未超时订单不受影响"""
    order, _ = await PaymentService.create_order("u1", "quarterly_package", "alipay", None)
    closed = await PaymentService.close_timeout_orders()
    assert closed == 0
    assert (await _get_order(order.id)).status == "pending"


# ─── 退款 ──────────────────────────────────────────────────────


async def _make_granted_order(
    user_id: str = "u1", paid: int = 9900, tmp_path=None
) -> PaymentOrder:
    """造一笔旧 SKU（activation_code，已下架）的 granted 历史订单：直接落库。

    交付码在测试激活码管理器目录下创建（未 claim、active）。
    """
    mgr = SimpleActivationManager(base_dir=str(tmp_path / "simple"))
    rec = mgr.create_activation(mode="combined", ttl_minutes=180 * 24 * 60)
    now = datetime.now(timezone.utc)
    order = PaymentOrder(
        order_no=PaymentService._generate_order_no(),
        user_id=user_id,
        product_type="activation_code",
        quantity=1,
        amount_original=9900,
        amount_discount=9900 - paid,
        amount_paid=paid,
        channel="alipay",
        status="granted",
        delivered_code=rec.code,
        paid_at=now,
        created_at=now,
    )
    async with _TestSessionLocal() as db:
        db.add(order)
        await db.commit()
        await db.refresh(order)
    return order


@pytest.mark.asyncio
async def test_refund_guard_claimed_code(fake_channel, tmp_path):
    """退款守卫：交付码已被用户 claim → ValueError 拒绝，不退款不作废"""
    order = await _make_granted_order(tmp_path=tmp_path)

    # 模拟用户 claim 该码
    mgr = SimpleActivationManager(base_dir=str(tmp_path / "simple"))
    mgr.claim_owner(order.delivered_code, {"user_id": "u9", "email": "x@test.com"})

    with pytest.raises(ValueError, match="已被使用"):
        await PaymentService.admin_refund(order.id, actor={"user_id": "admin"})

    final = await _get_order(order.id)
    assert final.status == "granted"
    assert final.refunded_at is None
    assert fake_channel.refunds == []
    # 码未作废
    assert mgr.get_activation(order.delivered_code).status == "active"


@pytest.mark.asyncio
async def test_refund_guard_wrong_status():
    """退款守卫：非 granted 订单拒绝"""
    order, _ = await PaymentService.create_order("u1", "quarterly_package", "alipay", None)
    with pytest.raises(ValueError):
        await PaymentService.admin_refund(order.id, actor={"user_id": "admin"})


@pytest.mark.asyncio
async def test_refund_success_revokes_code(fake_channel, tmp_path):
    """退款成功：渠道退款（refund_no=order_no+R）→ status refunded → 码 revoked"""
    order = await _make_granted_order(tmp_path=tmp_path)

    refunded = await PaymentService.admin_refund(order.id, actor={"user_id": "admin"})
    assert refunded.status == "refunded"
    assert refunded.refunded_at is not None

    # 渠道退款调用正确
    assert fake_channel.refunds == [(order.order_no, order.amount_paid, order.order_no + "R")]

    # 码已作废
    mgr = SimpleActivationManager(base_dir=str(tmp_path / "simple"))
    assert mgr.get_activation(order.delivered_code).status == "revoked"


@pytest.mark.asyncio
async def test_refund_zero_amount_skips_channel(fake_channel, tmp_path):
    """0 元单退款：跳过渠道（无真实支付），直接 refunded + 作废码"""
    order = await _make_granted_order(paid=0, tmp_path=tmp_path)
    assert order.amount_paid == 0

    refunded = await PaymentService.admin_refund(order.id, actor={"user_id": "admin"})
    assert refunded.status == "refunded"
    assert fake_channel.refunds == []

    mgr = SimpleActivationManager(base_dir=str(tmp_path / "simple"))
    assert mgr.get_activation(order.delivered_code).status == "revoked"


# ─── Admin 查询 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_list_and_get_order(tmp_path):
    """admin 列表/详情：含 user_email + code_refundable；状态/渠道筛选"""
    order = await _make_granted_order(tmp_path=tmp_path)

    items, total = await PaymentService.admin_list_orders(status="granted", channel="alipay")
    assert total == 1
    item = items[0]
    assert item["id"] == order.id
    assert item["user_email"] == "alice@test.com"
    assert item["code_refundable"] is True  # 未被 claim

    # claim 后不再可退
    mgr = SimpleActivationManager(base_dir=str(tmp_path / "simple"))
    mgr.claim_owner(order.delivered_code, {"user_id": "u9", "email": "x@test.com"})
    detail = await PaymentService.admin_get_order(order.id)
    assert detail["order"]["code_refundable"] is False

    # 筛选不命中
    items2, total2 = await PaymentService.admin_list_orders(status="pending")
    assert total2 == 0


# ─── 用户侧查询 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_and_get_user_orders():
    """我的订单：仅当前用户；详情 pending 返回 pay_url，非 pending 返回 None"""
    order, payment = await PaymentService.create_order("u1", "quarterly_package", "alipay", None)
    await PaymentService.create_order("u2", "quarterly_package", "alipay", None)

    items, total = await PaymentService.list_user_orders("u1")
    assert total == 1
    assert items[0]["id"] == order.id

    # pending：返回存储的 pay_url
    detail = await PaymentService.get_user_order("u1", order.id)
    assert detail["pay_url"] == payment["pay_url"]

    # 支付后：不再返回 pay_url
    await PaymentService.handle_alipay_notify(_notify_form(order))
    detail2 = await PaymentService.get_user_order("u1", order.id)
    assert detail2["pay_url"] is None

    # 非本人 → 404
    with pytest.raises(OrderNotFoundError):
        await PaymentService.get_user_order("u2", order.id)


@pytest.mark.asyncio
async def test_get_order_by_no():
    """按商户订单号查详情：本人 pending 返回 pay_url；非本人/不存在 → 404"""
    order, payment = await PaymentService.create_order("u1", "quarterly_package", "alipay", None)

    detail = await PaymentService.get_order_by_no("u1", order.order_no)
    assert detail["order"]["id"] == order.id
    assert detail["pay_url"] == payment["pay_url"]

    # 非本人 → 404
    with pytest.raises(OrderNotFoundError):
        await PaymentService.get_order_by_no("u2", order.order_no)
    # 不存在的订单号 → 404
    with pytest.raises(OrderNotFoundError):
        await PaymentService.get_order_by_no("u1", "X_NOT_EXIST")


# ─── 套餐交付（ADR-0014：全量未绑定码 + 消耗升级）───────────────


@pytest.mark.asyncio
async def test_deliver_quarterly_one_unbound_code(fake_channel, tmp_path):
    """季度套餐交付：1 个未绑定码，不自动绑定、不升级试用码"""
    order, _ = await PaymentService.create_order("u1", "quarterly_package", "alipay", None)
    await PaymentService.handle_alipay_notify(_notify_form(order))

    final = await _get_order(order.id)
    assert final.status == "granted"
    meta = ps_mod.PaymentService._parse_meta(final.meta)
    codes = meta.get("codes") or []
    assert len(codes) == 1
    assert final.delivered_code == codes[0]
    assert "upgraded" not in meta

    mgr = SimpleActivationManager(base_dir=str(tmp_path / "simple"))
    rec = mgr.get_activation(codes[0])
    assert rec is not None
    assert rec.owner_user_id is None  # 未绑定
    assert rec.status == "active"
    assert rec.code_type == "full"
    assert rec.package_type == "quarterly"
    assert rec.purchaser_user_id == "u1"
    assert rec.source_order_id == order.id


@pytest.mark.asyncio
async def test_deliver_annual_three_unbound_codes(fake_channel, tmp_path):
    """年度套餐交付：3 个未绑定码，全部可自用/转赠"""
    order, _ = await PaymentService.create_order("u1", "annual_package", "alipay", None)
    await PaymentService.handle_alipay_notify(_notify_form(order))

    final = await _get_order(order.id)
    meta = ps_mod.PaymentService._parse_meta(final.meta)
    codes = meta.get("codes") or []
    assert len(codes) == 3
    assert len(set(codes)) == 3  # 码不重复

    mgr = SimpleActivationManager(base_dir=str(tmp_path / "simple"))
    for code in codes:
        rec = mgr.get_activation(code)
        assert rec is not None and rec.owner_user_id is None
        assert rec.package_type == "annual"
        assert rec.purchaser_user_id == "u1"


@pytest.mark.asyncio
async def test_deliver_annual_team_analysis_notice(fake_channel, tmp_path):
    """年度套餐（3 人团队码）交付：发团队分析报告站内信 + 交付邮件附文案；重复回调不重复发"""
    order, _ = await PaymentService.create_order("u1", "annual_package", "alipay", None)
    await PaymentService.handle_alipay_notify(_notify_form(order))

    # 站内信：团队分析报告申请方式
    async with _TestSessionLocal() as db:
        rows = (
            (await db.execute(select(Notification).where(Notification.user_id == "u1")))
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert rows[0].type == "team_analysis_notice"
    assert rows[0].read_at is None
    assert settings.TEAM_ANALYSIS_EMAIL in rows[0].content
    assert "xunlu.lab@outlook.com" not in rows[0].content

    # 交付邮件附同一文案（邮箱独占一行）
    kwargs = ps_mod.EmailService.send_email.await_args.kwargs
    assert settings.TEAM_ANALYSIS_EMAIL in kwargs["body_text"]
    assert "xunlu.lab@outlook.com" not in kwargs["body_text"]

    # 重复回调幂等：不重复发站内信
    await PaymentService.handle_alipay_notify(_notify_form(order))
    async with _TestSessionLocal() as db:
        cnt = (
            await db.execute(
                select(func.count()).select_from(Notification).where(Notification.user_id == "u1")
            )
        ).scalar_one()
    assert cnt == 1


@pytest.mark.asyncio
async def test_deliver_quarterly_no_team_analysis_notice(fake_channel, tmp_path):
    """季度套餐交付：不发团队分析报告站内信，邮件也不含该文案"""
    order, _ = await PaymentService.create_order("u1", "quarterly_package", "alipay", None)
    await PaymentService.handle_alipay_notify(_notify_form(order))

    async with _TestSessionLocal() as db:
        cnt = (
            await db.execute(
                select(func.count()).select_from(Notification).where(Notification.user_id == "u1")
            )
        ).scalar_one()
    assert cnt == 0

    kwargs = ps_mod.EmailService.send_email.await_args.kwargs
    assert settings.TEAM_ANALYSIS_EMAIL not in kwargs["body_text"]


@pytest.mark.asyncio
async def test_intent_upgrade_trial_auto_consumes(fake_channel, tmp_path, monkeypatch):
    """直购升级（intent=upgrade_trial）：发码后自动消耗 1 码升级试用码"""
    mgr = SimpleActivationManager(base_dir=str(tmp_path / "simple"))
    trial = mgr.create_activation(mode="combined", code_type="trial", vip_level=1)
    mgr.claim_owner(trial.code, {"user_id": "u1", "email": "alice@test.com"})
    monkeypatch.setattr(
        "app.utils.trial_codes.get_active_trial_code_for_user",
        lambda user_id: mgr.get_activation(trial.code),
    )

    order, _ = await PaymentService.create_order(
        "u1", "quarterly_package", "alipay", None, None, "upgrade_trial"
    )
    await PaymentService.handle_alipay_notify(_notify_form(order))

    final = await _get_order(order.id)
    meta = ps_mod.PaymentService._parse_meta(final.meta)
    assert meta.get("auto_upgraded") is True
    codes = meta.get("codes") or []
    assert len(codes) == 1

    # 购买码已消耗，指向试用码
    consumed = mgr.get_activation(codes[0])
    assert consumed.status == "consumed"
    assert consumed.consumed_into == trial.code

    # 试用码原地升级（同码字符串）
    upgraded = mgr.get_activation(trial.code)
    assert upgraded.code_type == "full"
    assert upgraded.vip_level == 2
    assert upgraded.package_type == "quarterly"
    assert upgraded.purchaser_user_id == "u1"
    # ADR-0018：升级后试用码继承被消耗码的剩余有效期（购买起算口径）
    assert upgraded.expires_at == consumed.expires_at


@pytest.mark.asyncio
async def test_intent_upgrade_trial_without_trial_falls_back(fake_channel, tmp_path, monkeypatch):
    """直购升级但用户无试用码：退化为普通未绑定交付"""
    monkeypatch.setattr(
        "app.utils.trial_codes.get_active_trial_code_for_user", lambda user_id: None
    )
    order, _ = await PaymentService.create_order(
        "u1", "quarterly_package", "alipay", None, None, "upgrade_trial"
    )
    await PaymentService.handle_alipay_notify(_notify_form(order))

    final = await _get_order(order.id)
    meta = ps_mod.PaymentService._parse_meta(final.meta)
    assert meta.get("auto_upgraded") is not True
    mgr = SimpleActivationManager(base_dir=str(tmp_path / "simple"))
    rec = mgr.get_activation((meta.get("codes") or [""])[0])
    assert rec is not None and rec.status == "active" and rec.owner_user_id is None


@pytest.mark.asyncio
async def test_create_order_rejects_invalid_intent():
    """非法 intent / 非套餐商品带 intent → 400"""
    with pytest.raises(ValueError, match="不支持的订单意图"):
        await PaymentService.create_order("u1", "quarterly_package", "alipay", None, None, "xxx")
    with pytest.raises(ValueError, match="仅套餐订单支持"):
        await PaymentService.create_order(
            "u1", "consultation", "alipay", None, None, "upgrade_trial"
        )


async def _make_granted_annual_order(tmp_path) -> PaymentOrder:
    """造一笔已交付的年度套餐订单（3 个未绑定码）"""
    order, _ = await PaymentService.create_order("u1", "annual_package", "alipay", None)
    await PaymentService.handle_alipay_notify(_notify_form(order))
    return await _get_order(order.id)


@pytest.mark.asyncio
async def test_refund_package_untouched_success(fake_channel, tmp_path):
    """套餐退款：全部码未动 → 可退，退款成功全部码作废"""
    order = await _make_granted_annual_order(tmp_path)
    meta = ps_mod.PaymentService._parse_meta(order.meta)
    codes = meta["codes"]

    refunded = await PaymentService.admin_refund(order.id, actor={"user_id": "admin"})
    assert refunded.status == "refunded"
    assert fake_channel.refunds == [(order.order_no, order.amount_paid, order.order_no + "R")]

    mgr = SimpleActivationManager(base_dir=str(tmp_path / "simple"))
    for code in codes:
        assert mgr.get_activation(code).status == "revoked"


@pytest.mark.asyncio
async def test_refund_package_rejected_when_code_claimed(fake_channel, tmp_path):
    """套餐退款：任一码被 claim → 整单不可退"""
    order = await _make_granted_annual_order(tmp_path)
    meta = ps_mod.PaymentService._parse_meta(order.meta)
    mgr = SimpleActivationManager(base_dir=str(tmp_path / "simple"))
    mgr.claim_owner(meta["codes"][1], {"user_id": "u9", "email": "x@test.com"})

    with pytest.raises(ValueError, match="不可退款"):
        await PaymentService.admin_refund(order.id, actor={"user_id": "admin"})
    assert fake_channel.refunds == []
    assert (await _get_order(order.id)).status == "granted"


@pytest.mark.asyncio
async def test_refund_package_rejected_when_code_consumed(fake_channel, tmp_path):
    """套餐退款：任一码被消耗升级 → 整单不可退"""
    order = await _make_granted_annual_order(tmp_path)
    meta = ps_mod.PaymentService._parse_meta(order.meta)
    mgr = SimpleActivationManager(base_dir=str(tmp_path / "simple"))
    trial = mgr.create_activation(mode="combined", code_type="trial", vip_level=1)
    mgr.claim_owner(trial.code, {"user_id": "u1", "email": "alice@test.com"})
    mgr.consume_for_trial_upgrade(meta["codes"][0], trial.code, actor={"user_id": "u1"})

    with pytest.raises(ValueError, match="不可退款"):
        await PaymentService.admin_refund(order.id, actor={"user_id": "admin"})
    assert fake_channel.refunds == []


@pytest.mark.asyncio
async def test_refund_package_rejected_legacy_upgraded(fake_channel, tmp_path):
    """旧订单（meta.upgraded=True，已自动升级试用码）→ 不可退"""
    order = await _make_granted_annual_order(tmp_path)
    async with _TestSessionLocal() as db:
        row = await cls_get(db, order.id)
        meta = ps_mod.PaymentService._parse_meta(row.meta)
        meta["upgraded"] = True
        row.meta = json.dumps(meta, ensure_ascii=False)
        await db.commit()

    with pytest.raises(ValueError, match="不可退款"):
        await PaymentService.admin_refund(order.id, actor={"user_id": "admin"})


async def cls_get(db, order_id):
    return (
        await db.execute(select(PaymentOrder).where(PaymentOrder.id == order_id))
    ).scalar_one()


# ─── Admin 订单详情：交付码去向（ADR-0014 消耗去向展示）──────────


@pytest.mark.asyncio
async def test_admin_order_detail_delivered_codes_destinations(fake_channel, tmp_path):
    """详情 delivered_codes：unbound / bound_self / bound_other 三态与 detail"""
    order, _ = await PaymentService.create_order("u1", "annual_package", "alipay", None)
    await PaymentService.handle_alipay_notify(_notify_form(order))

    mgr = SimpleActivationManager(base_dir=str(tmp_path / "simple"))
    meta = ps_mod.PaymentService._parse_meta((await _get_order(order.id)).meta)
    codes = meta["codes"]
    assert len(codes) == 3
    # codes[0] 保持未绑定；codes[1] 本人绑定；codes[2] 他人绑定
    mgr.claim_owner(codes[1], {"user_id": "u1", "email": "alice@test.com"})
    mgr.claim_owner(codes[2], {"user_id": "u9", "email": "other@test.com"})

    detail = await PaymentService.admin_get_order(order.id)
    delivered = {d["code"]: d for d in detail["order"]["delivered_codes"]}
    assert set(delivered) == set(codes)

    d0 = delivered[codes[0]]
    assert d0["destination_type"] == "unbound"
    assert d0["destination_detail"] is None
    assert d0["status"] == "active"
    assert d0["upgraded_from_code"] is None

    d1 = delivered[codes[1]]
    assert d1["destination_type"] == "bound_self"
    assert d1["destination_detail"] == "alice@test.com"  # admin 不脱敏

    d2 = delivered[codes[2]]
    assert d2["destination_type"] == "bound_other"
    assert d2["destination_detail"] == "other@test.com"


@pytest.mark.asyncio
async def test_admin_order_detail_destination_consumed_revoked_unknown(fake_channel, tmp_path):
    """详情 delivered_codes：consumed_for_upgrade / revoked / unknown 三态"""
    mgr = SimpleActivationManager(base_dir=str(tmp_path / "simple"))

    # consumed_for_upgrade：季度单交付码被消耗升级试用码
    order_a, _ = await PaymentService.create_order("u1", "quarterly_package", "alipay", None)
    await PaymentService.handle_alipay_notify(_notify_form(order_a))
    meta_a = ps_mod.PaymentService._parse_meta((await _get_order(order_a.id)).meta)
    consumed_code = meta_a["codes"][0]
    trial = mgr.create_activation(mode="combined", code_type="trial", vip_level=1)
    mgr.claim_owner(trial.code, {"user_id": "u2", "email": "bob@test.com"})
    mgr.consume_for_trial_upgrade(consumed_code, trial.code, actor={"user_id": "u2"})

    # revoked：另一季度单全部码未动 → 退款成功作废码
    order_b, _ = await PaymentService.create_order("u1", "quarterly_package", "alipay", None)
    await PaymentService.handle_alipay_notify(_notify_form(order_b))
    meta_b = ps_mod.PaymentService._parse_meta((await _get_order(order_b.id)).meta)
    revoked_code = meta_b["codes"][0]
    refunded = await PaymentService.admin_refund(order_b.id, actor={"user_id": "admin"})
    assert refunded.status == "refunded"

    detail_a = await PaymentService.admin_get_order(order_a.id)
    d = detail_a["order"]["delivered_codes"][0]
    assert d["code"] == consumed_code
    assert d["destination_type"] == "consumed_for_upgrade"
    assert d["destination_detail"] == trial.code  # 受益试用码完整码值
    assert d["status"] == "consumed"
    assert d["upgraded_from_code"] is None  # 来源码本身无反向溯源
    # 试用码记录上的反向溯源已写入（顺带验证）
    assert mgr.get_activation(trial.code).upgraded_from_code == consumed_code

    detail_b = await PaymentService.admin_get_order(order_b.id)
    d_b = detail_b["order"]["delivered_codes"][0]
    assert d_b["code"] == revoked_code
    assert d_b["destination_type"] == "revoked"
    assert d_b["destination_detail"] is None

    # unknown：meta.codes 里的码在索引中不存在
    async with _TestSessionLocal() as db:
        row = (
            await db.execute(select(PaymentOrder).where(PaymentOrder.id == order_b.id))
        ).scalar_one()
        meta = ps_mod.PaymentService._parse_meta(row.meta)
        meta["codes"] = list(meta["codes"]) + ["ZZZUNKNOWN1"]
        row.meta = json.dumps(meta, ensure_ascii=False)
        await db.commit()
    detail_b2 = await PaymentService.admin_get_order(order_b.id)
    d_unknown = detail_b2["order"]["delivered_codes"][1]
    assert d_unknown["code"] == "ZZZUNKNOWN1"
    assert d_unknown["destination_type"] == "unknown"
    assert d_unknown["status"] is None
