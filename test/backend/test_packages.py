"""
套餐商品化测试（P-B，ADR-0008；mock 渠道层，不打真实支付宝）

测试场景：
1. 商品目录：新目录（季度套餐/年度套餐/咨询），旧 SKU 下架拒绝
2. 季度套餐交付（ADR-0014）：一律发 1 个未绑定码，不自动升级试用码、不自动绑定
3. 年度套餐交付（ADR-0014）：3 个未绑定码（字段/所属人追溯）
4. 有效期口径（ADR-0018）：支付成功（交付）即起算 90/365 天；
   消耗升级继承被消耗码剩余有效期；存量未激活码仍由 maybe_start_validity 首用落地
5. 延期激活：校验（非本人/试用码/无套餐类型拒绝）+ 延期数学（未过期累加/已过期从此刻）
6. 咨询交付：生成 pending_survey 预约单 + meta.booking_id
7. 退款守卫：套餐码全未动可退、任一动用拒退（ADR-0014）；延期拒退；咨询未预约可退、已预约拒退

fixture 风格同 test_payment_service.py：in-memory SQLite + monkeypatch。
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from app.config.settings import settings
from app.models.database import Base
from app.models.payment import ConsultationBooking
from app.models.user import User
from app.services import coupon_service as cs_mod
from app.services import payment_service as ps_mod
from app.services.coupon_service import CouponService
from app.services.payment_service import PaymentService
from app.utils.simple_activation_manager import SimpleActivationManager
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
_TestSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)


class FakeAlipayChannel:
    def __init__(self):
        self.created_orders = []
        self.refunds = []
        self.closed_orders = []

    async def create_order(self, order_no, amount_fen, subject):
        self.created_orders.append((order_no, amount_fen, subject))
        return f"https://qr.alipay.com/fake-{order_no}"

    async def refund(self, order_no, amount_fen, refund_no):
        self.refunds.append((order_no, amount_fen, refund_no))

    async def close_order(self, order_no):
        self.closed_orders.append(order_no)


@pytest.fixture
def fake_channel():
    return FakeAlipayChannel()


@pytest.fixture
def mgr():
    return None


@pytest.fixture(autouse=True)
async def _setup_db(monkeypatch, tmp_path, fake_channel):
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    monkeypatch.setattr(ps_mod, "AsyncSessionLocal", _TestSessionLocal)
    monkeypatch.setattr(cs_mod, "AsyncSessionLocal", _TestSessionLocal)
    monkeypatch.setattr(ps_mod, "get_channel", lambda name: fake_channel)

    manager = SimpleActivationManager(base_dir=str(tmp_path / "simple"))
    monkeypatch.setattr(ps_mod, "_activation_manager", lambda: manager)
    monkeypatch.setattr(
        ps_mod,
        "get_activation_with_manager",
        lambda code: (manager, manager.get_activation(code)),
    )
    monkeypatch.setattr(
        "app.utils.activation_audit.append_activation_audit", lambda *a, **k: None
    )
    monkeypatch.setattr(ps_mod.EmailService, "send_email", AsyncMock(return_value=None))

    # 咨询购买前置（报告持有校验）：P-B 测试不涉及报告注册表，一律 stub 为有报告
    from app.services.consultation_service import ConsultationService as _CS

    monkeypatch.setattr(
        _CS, "user_has_completed_report", classmethod(lambda cls, uid: True)
    )

    now = datetime.now(timezone.utc)
    async with _TestSessionLocal() as db:
        db.add_all(
            [
                User(
                    id="u1", email="alice@test.com", username="alice",
                    password_hash="x", is_active=True, created_at=now,
                ),
                User(
                    id="u2", email="bob@test.com", username="bob",
                    password_hash="x", is_active=True, created_at=now,
                ),
            ]
        )
        await db.commit()

    yield manager

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ─── 辅助 ────────────────────────────────────────────────────


async def _big_coupon(amount: int = 999999) -> str:
    """造一张足够覆盖任何商品的大额券"""
    coupons = await CouponService.create_coupons(amount=amount, count=1, source="admin")
    return coupons[0].code


def _make_trial(mgr, user_id="u1", email="alice@test.com"):
    rec = mgr.create_activation(mode="combined", code_type="trial")
    return mgr.claim_owner(rec.code, {"user_id": user_id, "email": email})


def _make_full(mgr, package_type="quarterly", user_id="u1", email="alice@test.com", days=30):
    rec = mgr.create_activation(
        mode="combined",
        ttl_minutes=days * 24 * 60,
        code_type="full",
        vip_level=2,
        package_type=package_type,
    )
    return mgr.claim_owner(rec.code, {"user_id": user_id, "email": email})


# ─── 1. 商品目录 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_products_catalog():
    data = PaymentService.get_products()
    types = {item["product_type"] for item in data["items"]}
    assert types == {"quarterly_package", "annual_package", "consultation"}
    quarterly = next(i for i in data["items"] if i["product_type"] == "quarterly_package")
    assert quarterly["popular"] is True  # 「最受欢迎」标在季度套餐（2026-08-24 起）
    annual = next(i for i in data["items"] if i["product_type"] == "annual_package")
    assert "popular" not in annual
    assert annual["price"] == settings.ANNUAL_PRICE
    consultation = next(i for i in data["items"] if i["product_type"] == "consultation")
    assert consultation["requires_report"] is True
    # 团队分析联系邮箱经目录下发前端（TEAM_ANALYSIS_EMAIL 统一变量）
    assert data["team_analysis_email"] == settings.TEAM_ANALYSIS_EMAIL


@pytest.mark.asyncio
async def test_legacy_sku_rejected():
    with pytest.raises(ValueError, match="已下架"):
        await PaymentService.create_order(
            user_id="u1", product_type="activation_code", channel="alipay"
        )


# ─── 2. 季度套餐交付 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_quarterly_delivers_unbound_code(_setup_db):
    """季度套餐交付（ADR-0014）：发 1 个未绑定码，不自动升级试用码"""
    mgr = _setup_db
    trial = _make_trial(mgr)
    coupon = await _big_coupon()

    order, payment = await PaymentService.create_order(
        user_id="u1",
        product_type="quarterly_package",
        channel="alipay",
        coupon_code=coupon,
    )

    assert payment is None  # 0 元单直接交付
    assert order.status == "granted"
    meta = PaymentService._parse_meta(order.meta)
    codes = meta.get("codes") or []
    assert len(codes) == 1
    assert order.delivered_code == codes[0]
    assert "upgraded" not in meta

    rec = mgr.get_activation(codes[0])
    assert rec.code_type == "full"
    assert rec.package_type == "quarterly"
    assert rec.vip_level == 2
    assert rec.owner_user_id is None  # 未绑定，不自动绑购买者
    assert rec.purchaser_user_id == "u1"
    assert rec.source_order_id == order.id
    # ADR-0018：支付成功（交付）即起算，有效期 ≈ now + 90 天
    expires = datetime.fromisoformat(rec.expires_at)
    expected = datetime.now(timezone.utc) + timedelta(days=settings.QUARTERLY_DAYS)
    assert abs((expires - expected).total_seconds()) < 120

    # 试用码不被自动升级
    trial_rec = mgr.get_activation(trial.code)
    assert trial_rec.code_type == "trial"
    assert trial_rec.vip_level == 1

    # 已有有效期的码：maybe_start_validity 幂等不动（仅存量未激活码由它落地）
    mgr.maybe_start_validity(codes[0])
    assert mgr.get_activation(codes[0]).expires_at == rec.expires_at


@pytest.mark.asyncio
async def test_quarterly_issues_unbound_code_without_trial(_setup_db):
    """无试用码时同样发 1 个未绑定码（ADR-0014）"""
    mgr = _setup_db
    coupon = await _big_coupon()

    order, _ = await PaymentService.create_order(
        user_id="u1",
        product_type="quarterly_package",
        channel="alipay",
        coupon_code=coupon,
    )

    assert order.delivered_code
    rec = mgr.get_activation(order.delivered_code)
    assert rec.code_type == "full"
    assert rec.package_type == "quarterly"
    assert rec.owner_user_id is None  # 未绑定
    assert rec.purchaser_user_id == "u1"
    assert rec.vip_level == 2
    # ADR-0018：支付成功（交付）即起算
    expires = datetime.fromisoformat(rec.expires_at)
    expected = datetime.now(timezone.utc) + timedelta(days=settings.QUARTERLY_DAYS)
    assert abs((expires - expected).total_seconds()) < 120
    meta = PaymentService._parse_meta(order.meta)
    assert meta.get("codes") == [order.delivered_code]


# ─── 3. 年度套餐交付（3 个未绑定码，ADR-0014）──────────────────────


@pytest.mark.asyncio
async def test_annual_delivers_three_unbound_codes(_setup_db):
    mgr = _setup_db
    trial = _make_trial(mgr)
    coupon = await _big_coupon()

    order, _ = await PaymentService.create_order(
        user_id="u1",
        product_type="annual_package",
        channel="alipay",
        coupon_code=coupon,
    )

    assert order.status == "granted"
    meta = PaymentService._parse_meta(order.meta)
    codes = meta.get("codes")
    assert codes and len(codes) == 3
    assert len(set(codes)) == 3
    assert order.delivered_code == codes[0]

    # 试用码不被自动升级
    assert mgr.get_activation(trial.code).code_type == "trial"

    for code in codes:
        rec = mgr.get_activation(code)
        assert rec.code_type == "full"
        assert rec.package_type == "annual"
        assert rec.vip_level == 2
        # ADR-0018：交付即起算，有效期 ≈ now + 365 天
        expires = datetime.fromisoformat(rec.expires_at)
        expected = datetime.now(timezone.utc) + timedelta(days=settings.ANNUAL_DAYS)
        assert abs((expires - expected).total_seconds()) < 120
        assert rec.owner_user_id is None  # 未绑定，可转送/自用/消耗升级
        assert rec.purchaser_user_id == "u1"  # 所属人追溯
        assert rec.source_order_id == order.id


@pytest.mark.asyncio
async def test_gift_code_expiry_starts_at_delivery(_setup_db):
    """ADR-0018：赠品码交付即起算；claim/首次使用均不改变有效期"""
    mgr = _setup_db
    coupon = await _big_coupon()
    order, _ = await PaymentService.create_order(
        user_id="u1",
        product_type="annual_package",
        channel="alipay",
        coupon_code=coupon,
    )
    gift = PaymentService._parse_meta(order.meta)["codes"][0]

    # 交付时已有有效期 ≈ now + 365 天
    rec0 = mgr.get_activation(gift)
    expires = datetime.fromisoformat(rec0.expires_at)
    expected = datetime.now(timezone.utc) + timedelta(days=settings.ANNUAL_DAYS)
    assert abs((expires - expected).total_seconds()) < 120

    # 另一个人绑定赠品码 → 有效期不变（购买起算，claim 不起算）
    claimed = mgr.claim_owner(gift, {"user_id": "u2", "email": "bob@test.com"})
    assert claimed.expires_at == rec0.expires_at
    assert claimed.owner_user_id == "u2"
    assert claimed.purchaser_user_id == "u1"  # 所属人不变

    # 首次开始探索 → maybe_start_validity 幂等不动
    mgr.maybe_start_validity(gift)
    assert mgr.get_activation(gift).expires_at == rec0.expires_at


@pytest.mark.asyncio
async def test_maybe_start_validity_ignores_trial_and_started(_setup_db):
    """maybe_start_validity：试用码/无套餐类型/已有有效期的码一律不动"""
    mgr = _setup_db
    trial = _make_trial(mgr)
    full = _make_full(mgr, package_type="quarterly", days=30)  # 已有有效期
    legacy = mgr.create_activation(mode="combined", ttl_minutes=30 * 24 * 60)  # 无套餐类型

    mgr.maybe_start_validity(trial.code)
    mgr.maybe_start_validity(full.code)
    mgr.maybe_start_validity(legacy.code)

    assert mgr.get_activation(trial.code).expires_at is None  # 试用码不过期
    assert mgr.get_activation(full.code).expires_at == full.expires_at  # 不变
    assert mgr.get_activation(legacy.code).expires_at == legacy.expires_at  # 不变


@pytest.mark.asyncio
async def test_consume_upgrade_inherits_remaining_validity(_setup_db):
    """ADR-0018：消耗升级时试用码继承被消耗码的剩余有效期；存量未激活码保持老口径"""
    mgr = _setup_db
    trial = _make_trial(mgr)
    coupon = await _big_coupon()
    order, _ = await PaymentService.create_order(
        user_id="u1",
        product_type="quarterly_package",
        channel="alipay",
        coupon_code=coupon,
    )
    code = PaymentService._parse_meta(order.meta)["codes"][0]

    # 新口径码（交付已有 expires_at）：升级后试用码继承同一到期时刻
    consumed = mgr.consume_for_trial_upgrade(code, trial.code, actor={"user_id": "u1"})
    upgraded = mgr.upgrade_to_full(
        trial.code,
        "quarterly",
        settings.QUARTERLY_DAYS,
        expires_at=consumed.expires_at,
        actor={"user_id": "u1"},
    )
    assert upgraded.expires_at == consumed.expires_at
    assert upgraded.code_type == "full"
    # 继承后 maybe_start_validity 不再动它
    mgr.maybe_start_validity(trial.code)
    assert mgr.get_activation(trial.code).expires_at == consumed.expires_at

    # 存量未激活码（expires_at=None）升级：保持 None，首次使用起算老口径兼容
    legacy = mgr.create_activation(
        mode="combined", code_type="full", vip_level=2,
        package_type="quarterly", no_expiry=True,
    )
    trial2 = _make_trial(mgr, user_id="u2", email="bob@test.com")
    consumed2 = mgr.consume_for_trial_upgrade(legacy.code, trial2.code, actor={"user_id": "u2"})
    upgraded2 = mgr.upgrade_to_full(
        trial2.code,
        "quarterly",
        settings.QUARTERLY_DAYS,
        expires_at=consumed2.expires_at,
        actor={"user_id": "u2"},
    )
    assert upgraded2.expires_at is None
    mgr.maybe_start_validity(trial2.code)
    expires2 = datetime.fromisoformat(mgr.get_activation(trial2.code).expires_at)
    expected2 = datetime.now(timezone.utc) + timedelta(days=settings.QUARTERLY_DAYS)
    assert abs((expires2 - expected2).total_seconds()) < 120


# ─── 4. 延期激活 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_renewal_rejects_invalid_targets(_setup_db):
    mgr = _setup_db
    trial = _make_trial(mgr)
    full = _make_full(mgr)
    legacy = mgr.create_activation(mode="combined", ttl_minutes=30 * 24 * 60)  # 无套餐类型
    mgr.claim_owner(legacy.code, {"user_id": "u1", "email": "alice@test.com"})

    with pytest.raises(ValueError, match="试用码"):
        await PaymentService.create_order(
            user_id="u1", product_type="renewal", channel="alipay", target_code=trial.code
        )
    with pytest.raises(ValueError, match="无套餐类型"):
        await PaymentService.create_order(
            user_id="u1", product_type="renewal", channel="alipay", target_code=legacy.code
        )
    with pytest.raises(ValueError, match="激活人或所属人"):
        await PaymentService.create_order(
            user_id="u2", product_type="renewal", channel="alipay", target_code=full.code
        )
    with pytest.raises(ValueError, match="target_code"):
        await PaymentService.create_order(
            user_id="u1", product_type="renewal", channel="alipay"
        )


@pytest.mark.asyncio
async def test_renewal_extends_active_code(_setup_db):
    """未过期：新有效期 = 原到期 + 时长（累加）"""
    mgr = _setup_db
    full = _make_full(mgr, package_type="quarterly", days=30)
    old_expires = datetime.fromisoformat(full.expires_at)
    coupon = await _big_coupon()

    order, payment = await PaymentService.create_order(
        user_id="u1",
        product_type="renewal",
        channel="alipay",
        coupon_code=coupon,
        target_code=full.code,
    )

    assert payment is None
    assert order.amount_original == settings.RENEWAL_PRICE
    meta = PaymentService._parse_meta(order.meta)
    assert meta["added_days"] == settings.RENEWAL_DAYS

    rec = mgr.get_activation(full.code)
    new_expires = datetime.fromisoformat(rec.expires_at)
    expected = old_expires + timedelta(days=settings.RENEWAL_DAYS)
    assert abs((new_expires - expected).total_seconds()) < 120


@pytest.mark.asyncio
async def test_renewal_extends_expired_code_from_now(_setup_db):
    """已过期：新有效期 = now + 时长（从此刻重算）"""
    mgr = _setup_db
    full = _make_full(mgr, package_type="annual", days=1)
    # 手工把有效期改到过去
    records = mgr._load_all()
    records[full.code].expires_at = (
        datetime.now(timezone.utc) - timedelta(days=10)
    ).isoformat()
    mgr._save_all(records)

    coupon = await _big_coupon()
    order, _ = await PaymentService.create_order(
        user_id="u1",
        product_type="renewal",
        channel="alipay",
        coupon_code=coupon,
        target_code=full.code,
    )

    assert order.amount_original == settings.RENEWAL_PRICE
    rec = mgr.get_activation(full.code)
    new_expires = datetime.fromisoformat(rec.expires_at)
    expected = datetime.now(timezone.utc) + timedelta(days=settings.RENEWAL_DAYS)
    assert abs((new_expires - expected).total_seconds()) < 120
    assert rec.status == "active"


# ─── 5. 咨询交付 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_consultation_creates_booking(_setup_db):
    coupon = await _big_coupon()
    order, payment = await PaymentService.create_order(
        user_id="u1",
        product_type="consultation",
        channel="alipay",
        coupon_code=coupon,
    )

    assert payment is None
    assert order.status == "granted"
    assert order.delivered_code is None
    meta = PaymentService._parse_meta(order.meta)
    booking_id = meta.get("booking_id")
    assert booking_id

    async with _TestSessionLocal() as db:
        booking = (
            await db.execute(
                select(ConsultationBooking).where(ConsultationBooking.id == booking_id)
            )
        ).scalar_one()
    assert booking.order_id == order.id
    assert booking.user_id == "u1"
    assert booking.status == "pending_survey"


# ─── 6. 退款守卫 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refund_allowed_when_package_codes_untouched(_setup_db, fake_channel):
    """套餐退款（ADR-0014）：全部码未动 → 可退，全部码作废；任一动用 → 拒退"""
    mgr = _setup_db
    for product_type in ("quarterly_package", "annual_package"):
        coupon = await _big_coupon()
        order, _ = await PaymentService.create_order(
            user_id="u1",
            product_type=product_type,
            channel="alipay",
            coupon_code=coupon,
        )
        refunded = await PaymentService.admin_refund(order.id)
        assert refunded.status == "refunded"
        for code in PaymentService._parse_meta(refunded.meta)["codes"]:
            assert mgr.get_activation(code).status == "revoked"

    # 任一码被 claim → 整单拒退
    coupon = await _big_coupon()
    order, _ = await PaymentService.create_order(
        user_id="u1",
        product_type="annual_package",
        channel="alipay",
        coupon_code=coupon,
    )
    codes = PaymentService._parse_meta(order.meta)["codes"]
    mgr.claim_owner(codes[0], {"user_id": "u2", "email": "bob@test.com"})
    with pytest.raises(ValueError, match="不可退款"):
        await PaymentService.admin_refund(order.id)


@pytest.mark.asyncio
async def test_refund_rejected_for_renewal(_setup_db):
    mgr = _setup_db
    full = _make_full(mgr)
    coupon = await _big_coupon()
    order, _ = await PaymentService.create_order(
        user_id="u1",
        product_type="renewal",
        channel="alipay",
        coupon_code=coupon,
        target_code=full.code,
    )
    with pytest.raises(ValueError, match="不可退款"):
        await PaymentService.admin_refund(order.id)


@pytest.mark.asyncio
async def test_refund_consultation_before_scheduled(fake_channel):
    coupon = await _big_coupon()
    order, _ = await PaymentService.create_order(
        user_id="u1",
        product_type="consultation",
        channel="alipay",
        coupon_code=coupon,
    )
    # 0 元单调包退款渠道逻辑——补一个真实支付金额验证渠道调用
    async with _TestSessionLocal() as db:
        row = (
            await db.execute(
                select(ps_mod.PaymentOrder).where(ps_mod.PaymentOrder.id == order.id)
            )
        ).scalar_one()
        row.amount_paid = 100
        await db.commit()

    refunded = await PaymentService.admin_refund(order.id)
    assert refunded.status == "refunded"
    assert fake_channel.refunds, "应调用渠道退款"

    meta = PaymentService._parse_meta(order.meta)
    async with _TestSessionLocal() as db:
        booking = (
            await db.execute(
                select(ConsultationBooking).where(
                    ConsultationBooking.id == meta["booking_id"]
                )
            )
        ).scalar_one()
    assert booking.status == "cancelled"


@pytest.mark.asyncio
async def test_refund_consultation_rejected_when_scheduled():
    coupon = await _big_coupon()
    order, _ = await PaymentService.create_order(
        user_id="u1",
        product_type="consultation",
        channel="alipay",
        coupon_code=coupon,
    )
    meta = PaymentService._parse_meta(order.meta)
    async with _TestSessionLocal() as db:
        booking = (
            await db.execute(
                select(ConsultationBooking).where(
                    ConsultationBooking.id == meta["booking_id"]
                )
            )
        ).scalar_one()
        booking.status = "scheduled"
        await db.commit()

    with pytest.raises(ValueError, match="已预约"):
        await PaymentService.admin_refund(order.id)
