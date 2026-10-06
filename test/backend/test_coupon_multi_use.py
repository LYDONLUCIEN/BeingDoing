"""
优惠券多次核销测试（2026-10-06 设计定稿 §七 关键用例）

覆盖：
1. n=1 新券全链路等价现状 + 双写（coupon_redemptions 行与单槽字段同步）
2. n=3 券：3 个不同用户依次锁→核销，第 4 人报「已被抢完」
3. 每用户每券限 1 次（validate 与 lock 双端报「每个账号限用一次」）
4. 名额守卫：n=2 连续 5 次锁恰好 2 次成功（守卫=单条 UPDATE 原子性，按序验证）
5. 关单释放：名额回补（locked_count-1），释放后可再锁
6. 全额退款：核销行 refunded、used_count-1、名额恢复（n>1 / n=1 双口径）
7. 停用/启用：锁新单被拒、已核销不受影响、启用恢复；部分核销的券不可作废
8. 创建约束：n>1 禁绑归属、n 上限 10000
9. 券池跳过 n>1；「我的折扣券」used 组含共享券核销记录
10. 存量 12 位裸码券（手工插入）validate/lock 原样可用

使用独立的 in-memory SQLite + monkeypatch 替换 AsyncSessionLocal（与 test_coupon_service 同模式）。
"""

from datetime import datetime, timedelta, timezone

import pytest
from app.models.database import Base
from app.models.payment import Coupon, CouponRedemption, PaymentOrder
from app.models.user import User
from app.services import coupon_service as cs_mod
from app.services.coupon_service import CouponService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
_TestSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def _setup_db(monkeypatch):
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(cs_mod, "AsyncSessionLocal", _TestSessionLocal)
    async with _TestSessionLocal() as db:
        now = datetime.now(timezone.utc)
        db.add_all(
            [
                User(id=f"u{i}", email=f"user{i}@test.com", username=f"user{i}",
                     password_hash="x", is_active=True, created_at=now)
                for i in range(1, 7)
            ]
        )
        # 核销行外键关联的订单
        db.add_all(
            [
                PaymentOrder(
                    id=f"order-{i}", order_no=f"NO-{i}", user_id=f"u{i}",
                    product_type="membership_quarterly", amount_original=100,
                    amount_paid=100, channel="alipay", status="granted",
                )
                for i in range(1, 7)
            ]
        )
        await db.commit()
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _get_coupon(coupon_id: str) -> Coupon:
    async with _TestSessionLocal() as db:
        return (
            await db.execute(select(Coupon).where(Coupon.id == coupon_id))
        ).scalar_one()


async def _get_redemption(order_id: str) -> CouponRedemption:
    async with _TestSessionLocal() as db:
        return (
            await db.execute(select(CouponRedemption).where(CouponRedemption.order_id == order_id))
        ).scalar_one()


# ─── 1. n=1 全链路等价 + 双写 ─────────────────────────────────


@pytest.mark.asyncio
async def test_single_use_coupon_dual_write():
    """n=1 新券：锁→核销后单槽字段与核销行、计数器全部一致（旧口径兼容）"""
    c = (await CouponService.create_coupons(amount=1000, count=1))[0]
    await CouponService.lock_coupon(c.code, "order-1", user_id="u1")
    await CouponService.redeem_coupon(c.id, "u1", "order-1")

    final = await _get_coupon(c.id)
    assert final.status == "used"
    assert final.used_by_user_id == "u1"
    assert final.used_order_id == "order-1"
    assert final.used_count == 1 and final.locked_count == 0

    row = await _get_redemption("order-1")
    assert row.status == "used" and row.coupon_id == c.id and row.used_at is not None


# ─── 2/3/4. n>1 名额与限人 ────────────────────────────────────


@pytest.mark.asyncio
async def test_multi_use_three_users_then_exhausted():
    """n=3 券：3 个不同用户各锁各销；第 4 人 validate/lock 均报「已被抢完」"""
    c = (await CouponService.create_coupons(amount=500, count=1, max_uses=3))[0]
    assert c.max_uses == 3 and c.owner_user_id is None

    for i in (1, 2, 3):
        await CouponService.lock_coupon(c.code, f"order-{i}", user_id=f"u{i}")
        await CouponService.redeem_coupon(c.id, f"u{i}", f"order-{i}")

    final = await _get_coupon(c.id)
    assert final.status == "unused"  # n>1 券级状态不动
    assert final.used_count == 3
    assert CouponService._derive_status(final) == "used"  # 派生：名额耗尽

    with pytest.raises(ValueError, match="已被抢完"):
        await CouponService.validate_coupon(c.code, user_id="u4")
    with pytest.raises(ValueError, match="已被抢完"):
        await CouponService.lock_coupon(c.code, "order-4", user_id="u4")


@pytest.mark.asyncio
async def test_per_user_once():
    """同一用户第二次锁 n>1 券：validate 与 lock 双端报「每个账号限用一次」"""
    c = (await CouponService.create_coupons(amount=500, count=1, max_uses=10))[0]
    await CouponService.lock_coupon(c.code, "order-1", user_id="u1")

    # u1 已有 locked 行：validate 报限一次
    with pytest.raises(ValueError, match="每个账号限用一次"):
        await CouponService.validate_coupon(c.code, user_id="u1")
    # u1 再锁：NOT EXISTS 守卫拒绝
    with pytest.raises(ValueError, match="每个账号限用一次"):
        await CouponService.lock_coupon(c.code, "order-2", user_id="u1")
    # 其他用户不受影响
    await CouponService.lock_coupon(c.code, "order-3", user_id="u2")

    final = await _get_coupon(c.id)
    assert final.locked_count == 2


@pytest.mark.asyncio
async def test_quota_guard_two_of_five():
    """n=2 券连续 5 次锁（不同用户）：恰好 2 次成功 3 次失败（守卫=UPDATE 原子性）"""
    c = (await CouponService.create_coupons(amount=500, count=1, max_uses=2))[0]
    results = []
    for i in (1, 2, 3, 4, 5):
        try:
            await CouponService.lock_coupon(c.code, f"order-{i}", user_id=f"u{i}")
            results.append("ok")
        except ValueError:
            results.append("fail")
    assert results.count("ok") == 2 and results.count("fail") == 3
    final = await _get_coupon(c.id)
    assert final.locked_count == 2


# ─── 5/6. 释放与退款回退 ──────────────────────────────────────


@pytest.mark.asyncio
async def test_release_returns_quota():
    """关单释放：核销行 released、名额回补，释放后可再锁"""
    c = (await CouponService.create_coupons(amount=500, count=1, max_uses=2))[0]
    await CouponService.lock_coupon(c.code, "order-1", user_id="u1")
    await CouponService.lock_coupon(c.code, "order-2", user_id="u2")
    with pytest.raises(ValueError, match="已被抢完"):
        await CouponService.lock_coupon(c.code, "order-3", user_id="u3")

    released = await CouponService.release_coupon(c.id, order_id="order-2")
    assert released.locked_count == 1
    row = await _get_redemption("order-2")
    assert row.status == "released"

    # 名额回补后 u3 可锁
    await CouponService.lock_coupon(c.code, "order-3", user_id="u3")
    final = await _get_coupon(c.id)
    assert final.locked_count == 2


@pytest.mark.asyncio
async def test_refund_returns_one_slot_multi_use():
    """全额退款（n>1）：核销行 refunded、used_count-1、名额恢复可再核销"""
    c = (await CouponService.create_coupons(amount=500, count=1, max_uses=2))[0]
    for i in (1, 2):
        await CouponService.lock_coupon(c.code, f"order-{i}", user_id=f"u{i}")
        await CouponService.redeem_coupon(c.id, f"u{i}", f"order-{i}")

    returned = await CouponService.return_coupon_on_refund(c.id, "order-1")
    assert returned.used_count == 1
    row = await _get_redemption("order-1")
    assert row.status == "refunded" and row.refunded_at is not None

    # 名额恢复：u3 可锁可销
    await CouponService.lock_coupon(c.code, "order-3", user_id="u3")
    await CouponService.redeem_coupon(c.id, "u3", "order-3")
    final = await _get_coupon(c.id)
    assert final.used_count == 2
    assert CouponService._derive_status(final) == "used"


@pytest.mark.asyncio
async def test_refund_reverts_single_use_coupon():
    """全额退款（n=1）：单槽字段回退 + 核销行 refunded + used_count 归零（现状兼容）"""
    c = (await CouponService.create_coupons(amount=1000, count=1))[0]
    await CouponService.lock_coupon(c.code, "order-1", user_id="u1")
    await CouponService.redeem_coupon(c.id, "u1", "order-1")

    returned = await CouponService.return_coupon_on_refund(c.id, "order-1")
    assert returned.status == "unused"
    assert returned.used_by_user_id is None and returned.used_order_id is None
    assert returned.used_count == 0
    assert returned.owner_user_id == "u1"  # 归属保留
    row = await _get_redemption("order-1")
    assert row.status == "refunded"


# ─── 7. 停用/启用/作废 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_suspend_resume():
    """停用：新锁被拒（validate 同样报错）；已核销不受影响；启用后恢复"""
    c = (await CouponService.create_coupons(amount=500, count=1, max_uses=3))[0]
    await CouponService.lock_coupon(c.code, "order-1", user_id="u1")
    await CouponService.redeem_coupon(c.id, "u1", "order-1")

    suspended = await CouponService.suspend_coupon(c.id)
    assert suspended.suspended_at is not None
    assert CouponService._derive_status(suspended) == "suspended"

    with pytest.raises(ValueError, match="已停止使用"):
        await CouponService.validate_coupon(c.code, user_id="u2")
    with pytest.raises(ValueError, match="已停止使用"):
        await CouponService.lock_coupon(c.code, "order-2", user_id="u2")

    # 已核销不受影响：核销行仍 used、计数不动
    row = await _get_redemption("order-1")
    assert row.status == "used"
    assert (await _get_coupon(c.id)).used_count == 1

    # 部分核销的券不可作废，只可停用
    with pytest.raises(ValueError, match="不可作废"):
        await CouponService.delete_coupon(c.id)

    resumed = await CouponService.resume_coupon(c.id)
    assert resumed.suspended_at is None
    await CouponService.lock_coupon(c.code, "order-2", user_id="u2")  # 恢复可锁


@pytest.mark.asyncio
async def test_resume_requires_suspended():
    """未停用的券不可「启用」；停用幂等拒绝"""
    c = (await CouponService.create_coupons(amount=500, count=1))[0]
    with pytest.raises(ValueError, match="未处于停用状态"):
        await CouponService.resume_coupon(c.id)
    await CouponService.suspend_coupon(c.id)
    with pytest.raises(ValueError, match="已处于停用状态"):
        await CouponService.suspend_coupon(c.id)


# ─── 8. 创建约束 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_constraints():
    """n>1 禁绑归属；n 上限 10000"""
    with pytest.raises(ValueError, match="不可绑定归属用户"):
        await CouponService.create_coupons(amount=500, max_uses=5, owner_user_id="u1")
    with pytest.raises(ValueError, match="总核销次数"):
        await CouponService.create_coupons(amount=500, max_uses=10001)
    with pytest.raises(ValueError, match="总核销次数"):
        await CouponService.create_coupons(amount=500, max_uses=0)
    ok = (await CouponService.create_coupons(amount=500, max_uses=10000))[0]
    assert ok.max_uses == 10000


# ─── 9. 券池 / 我的折扣券 / 列表 ──────────────────────────────


@pytest.mark.asyncio
async def test_draw_from_pool_skips_multi_use():
    """券池 FIFO 跳过 n>1 共享券（券池语义=每人一张不同的券）"""
    now = datetime.now(timezone.utc)
    async with _TestSessionLocal() as db:
        multi = Coupon(
            id="cm", code="Q-POOLSKIP1", amount=100, max_uses=99, status="unused",
            expires_at=now + timedelta(days=30), created_at=now - timedelta(days=2),
        )
        single = Coupon(
            id="cs", code="Q-POOLTAKEN", amount=200, max_uses=1, status="unused",
            expires_at=now + timedelta(days=30), created_at=now - timedelta(days=1),
        )
        db.add_all([multi, single])
        await db.commit()

    drawn = await CouponService.draw_from_pool(owner_user_id="u1")
    assert drawn.id == "cs"  # 取到 n=1 的，跳过 n=99 的（尽管它更早创建）


@pytest.mark.asyncio
async def test_my_coupons_includes_shared_redemptions():
    """「我的折扣券」used 组含共享券核销记录（券不归属，按行取）"""
    c = (await CouponService.create_coupons(amount=500, count=1, max_uses=5))[0]
    await CouponService.lock_coupon(c.code, "order-1", user_id="u1")
    await CouponService.redeem_coupon(c.id, "u1", "order-1")

    groups = await CouponService.list_my_coupons("u1")
    assert groups["available"] == []  # 共享券不归属，不进 available
    assert len(groups["used"]) == 1
    assert groups["used"][0]["code"] == c.code
    assert groups["used"][0]["used_order_no"] == "NO-1"


@pytest.mark.asyncio
async def test_list_coupons_suspended_filter():
    """列表派生态过滤：停用券出现在 suspended 过滤、不出现在 unused"""
    c = (await CouponService.create_coupons(amount=500, count=1, max_uses=5))[0]
    await CouponService.suspend_coupon(c.id)

    items, total = await CouponService.list_coupons(status="suspended")
    assert total == 1 and items[0]["id"] == c.id
    assert items[0]["status"] == "suspended"
    assert items[0]["max_uses"] == 5

    _, total_unused = await CouponService.list_coupons(status="unused")
    assert total_unused == 0


@pytest.mark.asyncio
async def test_list_coupons_exhausted_shows_used():
    """n>1 用满的券出现在 used 过滤（派生态），序列化带 max_uses/used_count"""
    await CouponService.create_coupons(amount=500, count=1, max_uses=1)
    multi = (await CouponService.create_coupons(amount=300, count=1, max_uses=2))[0]

    for i in (1, 2):
        await CouponService.lock_coupon(multi.code, f"order-{i}", user_id=f"u{i}")
        await CouponService.redeem_coupon(multi.id, f"u{i}", f"order-{i}")

    items, total = await CouponService.list_coupons(status="used")
    assert total == 1
    assert items[0]["id"] == multi.id
    assert items[0]["status"] == "used"
    assert items[0]["used_count"] == 2 and items[0]["max_uses"] == 2


# ─── 10. 存量裸码兼容 ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_legacy_bare_code_still_works():
    """存量 12 位裸码券（无前缀无连字符）validate/lock 原样可用"""
    now = datetime.now(timezone.utc)
    async with _TestSessionLocal() as db:
        db.add(
            Coupon(
                id="legacy1", code="AB12CD34EF56", amount=1000, max_uses=1,
                status="unused", expires_at=now + timedelta(days=30), created_at=now,
            )
        )
        await db.commit()

    coupon = await CouponService.validate_coupon("ab12cd34ef56")  # 小写也能命中（归一化大写）
    assert coupon.id == "legacy1"
    locked = await CouponService.lock_coupon("AB12CD34EF56", "order-1", user_id="u1")
    assert locked.status == "locked"
