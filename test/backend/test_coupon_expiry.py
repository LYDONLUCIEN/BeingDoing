"""
折扣券有效期 + 用户绑定体系测试（020 迁移配套）

测试场景：
1. 默认有效期：create_coupons 默认读运行时配置（90 天），可 ttl_days 覆盖；非法 ttl 拒绝
2. 过期拦截（惰性派生）：过期券 validate/lock 拒绝；_derive_status/list_coupons 派生 expired
3. 锁定免疫：locked 券过期后仍可 redeem；release 后派生 expired
4. 归属：他人券 validate/lock 拒绝；下单锁定认领 owner；release 保留 owner；
   券池排除已绑定/已过期券
5. 软删除/恢复/改期：void 可恢复、used 拒绝恢复、expired 改期复活、void 不可改期
6. 我的券：list_my_coupons 分组 available/used/expired，不含 void/locked
7. 退款退券：return_coupon_on_refund used → unused 保留 owner
8. 运行时配置：get/set/非法回退 90（coupon_config，落盘用 tmp 目录隔离）

使用独立的 in-memory SQLite + monkeypatch 替换 AsyncSessionLocal，避免污染主库。
"""

from datetime import datetime, timedelta, timezone

import pytest
from app.models.database import Base
from app.models.payment import Coupon
from app.models.user import User
from app.services import coupon_config
from app.services import coupon_service as cs_mod
from app.services.coupon_service import CouponService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# ─── 测试专用引擎 + 会话工厂 ──────────────────────────────────

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
_TestSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def _setup_db(monkeypatch, tmp_path):
    """建表 + 插测试用户 + 替换 AsyncSessionLocal + 隔离 coupon_config 落盘目录"""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    monkeypatch.setattr(cs_mod, "AsyncSessionLocal", _TestSessionLocal)
    monkeypatch.setattr(coupon_config, "_config_path", lambda: tmp_path / "coupon_config.json")

    async with _TestSessionLocal() as db:
        now = datetime.now(timezone.utc)
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
                ),
            ]
        )
        await db.commit()

    yield

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _get_coupon(coupon_id: str) -> Coupon:
    async with _TestSessionLocal() as db:
        return (await db.execute(select(Coupon).where(Coupon.id == coupon_id))).scalar_one()


async def _make_expired_coupon(amount: int = 1000) -> Coupon:
    """创建一张已过期的券（expires_at 直接写过去时间）"""
    c = (await CouponService.create_coupons(amount=amount, count=1, ttl_days=1))[0]
    async with _TestSessionLocal() as db:
        coupon = (await db.execute(select(Coupon).where(Coupon.id == c.id))).scalar_one()
        coupon.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        await db.commit()
        await db.refresh(coupon)
        return coupon


# ─── 1. 默认有效期 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_default_ttl_from_config():
    """不传 ttl_days：读运行时默认配置（90 天）；admin 调整配置后新券用新值"""
    c = (await CouponService.create_coupons(amount=1000, count=1))[0]
    delta = (c.expires_at - c.created_at).days
    assert delta == coupon_config.DEFAULT_COUPON_TTL_DAYS == 90

    coupon_config.set_default_ttl_days(30)
    c2 = (await CouponService.create_coupons(amount=1000, count=1))[0]
    assert (c2.expires_at - c2.created_at).days == 30


@pytest.mark.asyncio
async def test_create_ttl_override_and_validation():
    """创建时可覆盖 ttl_days；越界（0/3651）拒绝"""
    c = (await CouponService.create_coupons(amount=1000, count=1, ttl_days=7))[0]
    assert (c.expires_at - c.created_at).days == 7

    with pytest.raises(ValueError):
        await CouponService.create_coupons(amount=1000, count=1, ttl_days=0)
    with pytest.raises(ValueError):
        await CouponService.create_coupons(amount=1000, count=1, ttl_days=3651)


# ─── 2. 过期拦截（惰性派生）────────────────────────────────────


@pytest.mark.asyncio
async def test_expired_coupon_validate_and_lock_rejected():
    """过期券：validate 与 lock 均拒绝，报「已过期」"""
    c = await _make_expired_coupon()

    with pytest.raises(ValueError, match="已过期"):
        await CouponService.validate_coupon(c.code, user_id="u1")
    with pytest.raises(ValueError, match="已过期"):
        await CouponService.lock_coupon(c.code, "order-1", user_id="u1")

    # 存储态仍是 unused（expired 不落库）
    assert (await _get_coupon(c.id)).status == "unused"


@pytest.mark.asyncio
async def test_derived_status_in_list_and_serialize():
    """派生态：list_coupons status=expired/unused 过滤正确，序列化输出派生态"""
    expired_c = await _make_expired_coupon(amount=1000)
    fresh_c = (await CouponService.create_coupons(amount=2000, count=1))[0]

    expired_items, expired_total = await CouponService.list_coupons(status="expired")
    assert expired_total == 1
    assert expired_items[0]["id"] == expired_c.id
    assert expired_items[0]["status"] == "expired"

    unused_items, unused_total = await CouponService.list_coupons(status="unused")
    assert unused_total == 1
    assert unused_items[0]["id"] == fresh_c.id

    all_items, _ = await CouponService.list_coupons()
    by_id = {i["id"]: i for i in all_items}
    assert by_id[expired_c.id]["status"] == "expired"
    assert by_id[fresh_c.id]["status"] == "unused"
    assert by_id[fresh_c.id]["expires_at"] is not None


# ─── 3. 锁定免疫 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_locked_coupon_immune_to_expiry():
    """锁定免疫：locked 券过期后仍可 redeem；release 后派生 expired"""
    c = (await CouponService.create_coupons(amount=1000, count=1, ttl_days=1))[0]
    await CouponService.lock_coupon(c.code, "order-1", user_id="u1")

    # 锁定期内过期
    async with _TestSessionLocal() as db:
        coupon = (await db.execute(select(Coupon).where(Coupon.id == c.id))).scalar_one()
        coupon.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        await db.commit()

    # 核销不受过期影响
    redeemed = await CouponService.redeem_coupon(c.id, "u1", "order-1")
    assert redeemed.status == "used"


@pytest.mark.asyncio
async def test_release_after_expiry_derives_expired():
    """关单释放：已过期的券释放回 unused，派生态为 expired，不可再用"""
    c = (await CouponService.create_coupons(amount=1000, count=1, ttl_days=1))[0]
    await CouponService.lock_coupon(c.code, "order-1", user_id="u1")

    async with _TestSessionLocal() as db:
        coupon = (await db.execute(select(Coupon).where(Coupon.id == c.id))).scalar_one()
        coupon.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        await db.commit()

    released = await CouponService.release_coupon(c.id)
    assert released.status == "unused"

    with pytest.raises(ValueError, match="已过期"):
        await CouponService.validate_coupon(c.code, user_id="u1")


# ─── 4. 归属（绑定/认领）──────────────────────────────────────


@pytest.mark.asyncio
async def test_bound_coupon_rejects_other_user():
    """已绑定券：他人 validate/lock 拒绝，归属人正常"""
    c = (await CouponService.create_coupons(amount=1000, count=1, owner_user_id="u1"))[0]

    with pytest.raises(ValueError, match="不属于当前账号"):
        await CouponService.validate_coupon(c.code, user_id="u2")
    with pytest.raises(ValueError, match="不属于当前账号"):
        await CouponService.lock_coupon(c.code, "order-1", user_id="u2")

    got = await CouponService.validate_coupon(c.code, user_id="u1")
    assert got.id == c.id


@pytest.mark.asyncio
async def test_unbound_coupon_claimed_on_lock():
    """未绑定流通券：校验不认领，下单锁定时认领；释放后保留归属"""
    c = (await CouponService.create_coupons(amount=1000, count=1))[0]
    assert c.owner_user_id is None

    # validate 不认领
    await CouponService.validate_coupon(c.code, user_id="u1")
    assert (await _get_coupon(c.id)).owner_user_id is None

    # lock 认领
    await CouponService.lock_coupon(c.code, "order-1", user_id="u1")
    assert (await _get_coupon(c.id)).owner_user_id == "u1"

    # release 保留归属（他人不能再锁）
    await CouponService.release_coupon(c.id)
    assert (await _get_coupon(c.id)).owner_user_id == "u1"
    with pytest.raises(ValueError, match="不属于当前账号"):
        await CouponService.lock_coupon(c.code, "order-2", user_id="u2")


@pytest.mark.asyncio
async def test_draw_from_pool_skips_bound_and_expired():
    """券池：只取未绑定且未过期的 unused；取到即绑定收件人"""
    now = datetime.now(timezone.utc)
    async with _TestSessionLocal() as db:
        bound = Coupon(
            code="BOUNDCPOOL01", amount=1000, status="unused", source="admin",
            created_at=now - timedelta(days=3), owner_user_id="u2",
            expires_at=now + timedelta(days=10),
        )
        expired = Coupon(
            code="EXPIREDPOOL1", amount=1000, status="unused", source="admin",
            created_at=now - timedelta(days=2),
            expires_at=now - timedelta(hours=1),
        )
        free = Coupon(
            code="FREEPOOL0001", amount=1000, status="unused", source="admin",
            created_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=10),
        )
        db.add_all([bound, expired, free])
        await db.commit()
        free_id = free.id

    drawn = await CouponService.draw_from_pool(owner_user_id="u1")
    assert drawn.id == free_id
    assert drawn.owner_user_id == "u1"


# ─── 5. 软删除 / 恢复 / 改期 ───────────────────────────────────


@pytest.mark.asyncio
async def test_void_restore_and_expiry_update():
    """作废=软删除可恢复；恢复后若过期为派生 expired，可改期复活；used 不可恢复"""
    c = (await CouponService.create_coupons(amount=1000, count=1))[0]

    await CouponService.delete_coupon(c.id)
    assert (await _get_coupon(c.id)).status == "void"

    # void 不可 validate / 不可再作废 / 不可改期
    with pytest.raises(ValueError):
        await CouponService.validate_coupon(c.code, user_id="u1")
    with pytest.raises(ValueError):
        await CouponService.delete_coupon(c.id)
    with pytest.raises(ValueError):
        await CouponService.update_coupon_expiry(c.id, datetime.now(timezone.utc))

    # 恢复 → unused
    restored = await CouponService.restore_coupon(c.id)
    assert restored.status == "unused"
    assert restored.voided_at is None

    # 改期：先改到过去 → 派生 expired；再改到未来 → 复活可用
    await CouponService.update_coupon_expiry(
        c.id, datetime.now(timezone.utc) - timedelta(hours=1)
    )
    with pytest.raises(ValueError, match="已过期"):
        await CouponService.validate_coupon(c.code, user_id="u1")
    await CouponService.update_coupon_expiry(
        c.id, datetime.now(timezone.utc) + timedelta(days=10)
    )
    got = await CouponService.validate_coupon(c.code, user_id="u1")
    assert got.id == c.id

    # used 不可恢复
    await CouponService.lock_coupon(c.code, "order-1", user_id="u1")
    await CouponService.redeem_coupon(c.id, "u1", "order-1")
    with pytest.raises(ValueError):
        await CouponService.restore_coupon(c.id)


# ─── 6. 我的券 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_my_coupons_grouped():
    """list_my_coupons：按派生态分组 available/used/expired；不含 void 与 locked"""
    available = (await CouponService.create_coupons(amount=1000, count=1, owner_user_id="u1"))[0]
    to_use = (await CouponService.create_coupons(amount=2000, count=1, owner_user_id="u1"))[0]
    expired = (await CouponService.create_coupons(amount=3000, count=1, owner_user_id="u1"))[0]
    voided = (await CouponService.create_coupons(amount=4000, count=1, owner_user_id="u1"))[0]
    locked = (await CouponService.create_coupons(amount=5000, count=1, owner_user_id="u1"))[0]
    other_user = (await CouponService.create_coupons(amount=6000, count=1, owner_user_id="u2"))[0]

    # used
    await CouponService.lock_coupon(to_use.code, "order-1", user_id="u1")
    await CouponService.redeem_coupon(to_use.id, "u1", "order-1")
    # expired
    async with _TestSessionLocal() as db:
        row = (await db.execute(select(Coupon).where(Coupon.id == expired.id))).scalar_one()
        row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        await db.commit()
    # void
    await CouponService.delete_coupon(voided.id)
    # locked
    await CouponService.lock_coupon(locked.code, "order-2", user_id="u1")

    groups = await CouponService.list_my_coupons("u1")
    assert [i["code"] for i in groups["available"]] == [available.code]
    assert [i["code"] for i in groups["used"]] == [to_use.code]
    assert [i["code"] for i in groups["expired"]] == [expired.code]
    all_codes = {i["code"] for g in groups.values() for i in g}
    assert voided.code not in all_codes
    assert locked.code not in all_codes
    assert other_user.code not in all_codes
    assert groups["available"][0]["expires_at"] is not None


# ─── 7. 退款退券 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_return_coupon_on_refund():
    """退款退券：used → unused，清核销字段，保留归属；非 used 拒绝"""
    c = (await CouponService.create_coupons(amount=1000, count=1))[0]
    await CouponService.lock_coupon(c.code, "order-1", user_id="u1")
    await CouponService.redeem_coupon(c.id, "u1", "order-1")

    returned = await CouponService.return_coupon_on_refund(c.id)
    assert returned.status == "unused"
    assert returned.used_by_user_id is None
    assert returned.used_order_id is None
    assert returned.used_at is None
    assert returned.owner_user_id == "u1"  # 保留归属

    # 退回后归属人可再次使用
    got = await CouponService.validate_coupon(c.code, user_id="u1")
    assert got.id == c.id

    # 非 used 拒绝
    with pytest.raises(ValueError):
        await CouponService.return_coupon_on_refund(c.id)


# ─── 8. 运行时配置 ────────────────────────────────────────────


def test_coupon_config_get_set(tmp_path, monkeypatch):
    """coupon_config：默认 90；set 后生效；非法值回退 90；越界 set 拒绝"""
    monkeypatch.setattr(coupon_config, "_config_path", lambda: tmp_path / "coupon_config.json")

    def _clear_cache():
        # 直接写盘绕过了 set，需清 mtime 缓存模拟文件变更（快速连续写 mtime 可能不变）
        monkeypatch.setattr(coupon_config, "_cache_days", None)
        monkeypatch.setattr(coupon_config, "_cache_mtime", None)

    assert coupon_config.get_default_ttl_days() == 90

    coupon_config.set_default_ttl_days(45)
    assert coupon_config.get_default_ttl_days() == 45

    # 非法文件内容 → 回退默认
    (tmp_path / "coupon_config.json").write_text('{"default_ttl_days": -5}', encoding="utf-8")
    _clear_cache()
    assert coupon_config.get_default_ttl_days() == 90
    (tmp_path / "coupon_config.json").write_text("not json", encoding="utf-8")
    _clear_cache()
    assert coupon_config.get_default_ttl_days() == 90

    with pytest.raises(ValueError):
        coupon_config.set_default_ttl_days(0)
    with pytest.raises(ValueError):
        coupon_config.set_default_ttl_days(3651)
