"""
折扣券服务 + 邮件发券扩展测试

测试场景：
1. 创建：单个/批量/唯一性/参数校验（12 位大写字母+数字券码）
2. 后台管理约束：金额修改与删除仅 unused 可用
3. 状态机：validate / lock / release / redeem（含 lock 并发竞争只成功一次）
4. 券池：FIFO 顺序、池空按 DEFAULT_COUPON_AMOUNT 自动创建、exclude_ids 行为
5. 邮件发券：attach_coupon 任务逐收件人取券渲染、券码落库、取券失败不中断整批

使用独立的 in-memory SQLite + monkeypatch 替换 AsyncSessionLocal，避免污染主库。
SMTP 通过 monkeypatch EmailService.send_email 实现 mock。
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from app.config.settings import settings
from app.models.database import Base
from app.models.notification import NotificationRecipient, NotificationTask
from app.models.payment import Coupon
from app.models.user import User, UserProfile
from app.services import coupon_service as cs_mod
from app.services import notification_service as ns_mod
from app.services.coupon_service import CouponService
from app.services.notification_service import NotificationService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# ─── 测试专用引擎 + 会话工厂 ──────────────────────────────────

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
_TestSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def _setup_db(monkeypatch):
    """每个测试前：建表 + 插测试用户 + 替换两个 service 的 AsyncSessionLocal

    autouse 确保所有测试都用测试专用引擎，不碰主库。
    """
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # coupon_service 与 notification_service 各自引用了模块级 AsyncSessionLocal
    monkeypatch.setattr(cs_mod, "AsyncSessionLocal", _TestSessionLocal)
    monkeypatch.setattr(ns_mod, "AsyncSessionLocal", _TestSessionLocal)

    # 插入 3 个测试用户（都有 email，供邮件任务与 used_by_email 联查用）
    async with _TestSessionLocal() as db:
        now = datetime.now(timezone.utc)
        users = [
            User(
                id="u1",
                email="alice@test.com",
                username="alice",
                password_hash="x",
                is_active=True,
                created_at=now - timedelta(days=10),
            ),
            User(
                id="u2",
                email="bob@test.com",
                username="bob",
                password_hash="x",
                is_active=True,
                created_at=now - timedelta(days=5),
            ),
            User(
                id="u3",
                email="carol@test.com",
                username="carol",
                password_hash="x",
                is_active=False,
                created_at=now,
            ),
        ]
        db.add_all(users)
        await db.commit()

    yield

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
def _fast_smtp(monkeypatch):
    """把 SMTP 间隔改成 0，避免测试真的 sleep"""
    monkeypatch.setattr(NotificationService, "SMTP_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(NotificationService, "RETRY_INTERVAL_SECONDS", 0.0)


async def _get_coupon(coupon_id: str) -> Coupon:
    async with _TestSessionLocal() as db:
        return (await db.execute(select(Coupon).where(Coupon.id == coupon_id))).scalar_one()


async def _insert_coupon(code: str, amount: int, created_at: datetime, **kw) -> Coupon:
    """直接插券（可控 created_at，用于 FIFO 测试）"""
    async with _TestSessionLocal() as db:
        coupon = Coupon(
            code=code,
            amount=amount,
            status=kw.get("status", "unused"),
            source=kw.get("source", "admin"),
            created_at=created_at,
        )
        db.add(coupon)
        await db.commit()
        await db.refresh(coupon)
        return coupon


# ─── 创建 ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_single_coupon():
    """单个创建：字段正确、券码 12 位大写字母+数字"""
    coupons = await CouponService.create_coupons(amount=5000, source="admin", created_by="u1")
    assert len(coupons) == 1
    c = coupons[0]
    assert c.amount == 5000
    assert c.status == "unused"
    assert c.source == "admin"
    assert c.created_by == "u1"
    assert len(c.code) == 12
    assert all(ch.isupper() or ch.isdigit() for ch in c.code)


@pytest.mark.asyncio
async def test_create_batch_uniqueness():
    """批量创建 50 张：数量正确、券码全部唯一"""
    coupons = await CouponService.create_coupons(amount=1000, count=50, source="admin")
    assert len(coupons) == 50
    codes = {c.code for c in coupons}
    assert len(codes) == 50

    # 落库后 code 唯一索引生效，总数也是 50
    async with _TestSessionLocal() as db:
        db_codes = (await db.execute(select(Coupon.code))).scalars().all()
    assert len(set(db_codes)) == 50


@pytest.mark.asyncio
async def test_create_invalid_params():
    """非法参数：面额 ≤0 / 数量越界 → ValueError"""
    with pytest.raises(ValueError):
        await CouponService.create_coupons(amount=0, count=1)
    with pytest.raises(ValueError):
        await CouponService.create_coupons(amount=-100, count=1)
    with pytest.raises(ValueError):
        await CouponService.create_coupons(amount=100, count=0)
    with pytest.raises(ValueError):
        await CouponService.create_coupons(amount=100, count=501)


# ─── 后台管理约束（仅 unused 可改/可删）────────────────────────


@pytest.mark.asyncio
async def test_update_amount_only_when_unused():
    """金额修改：unused 可改；locked/used 拒绝"""
    c = (await CouponService.create_coupons(amount=1000, count=1))[0]

    updated = await CouponService.update_coupon_amount(c.id, 2000)
    assert updated.amount == 2000

    # locked 拒绝
    await CouponService.lock_coupon(c.code, "order-1")
    with pytest.raises(ValueError):
        await CouponService.update_coupon_amount(c.id, 3000)

    # used 拒绝
    await CouponService.redeem_coupon(c.id, "u1", "order-1")
    with pytest.raises(ValueError):
        await CouponService.update_coupon_amount(c.id, 3000)


@pytest.mark.asyncio
async def test_update_amount_invalid_value():
    """金额修改：非正面额 / 券不存在 → ValueError"""
    c = (await CouponService.create_coupons(amount=1000, count=1))[0]
    with pytest.raises(ValueError):
        await CouponService.update_coupon_amount(c.id, 0)
    with pytest.raises(ValueError):
        await CouponService.update_coupon_amount("nonexistent-id", 100)


@pytest.mark.asyncio
async def test_delete_only_when_unused():
    """删除：unused 可删；locked/used 拒绝；券不存在拒绝"""
    c1 = (await CouponService.create_coupons(amount=1000, count=1))[0]
    c2 = (await CouponService.create_coupons(amount=1000, count=1))[0]

    # locked 拒绝
    await CouponService.lock_coupon(c1.code, "order-1")
    with pytest.raises(ValueError):
        await CouponService.delete_coupon(c1.id)

    # used 拒绝
    await CouponService.redeem_coupon(c1.id, "u1", "order-1")
    with pytest.raises(ValueError):
        await CouponService.delete_coupon(c1.id)

    # unused 可删
    await CouponService.delete_coupon(c2.id)
    async with _TestSessionLocal() as db:
        gone = (await db.execute(select(Coupon).where(Coupon.id == c2.id))).scalar_one_or_none()
    assert gone is None

    # 不存在拒绝
    with pytest.raises(ValueError):
        await CouponService.delete_coupon("nonexistent-id")


# ─── 状态机：validate / lock / release / redeem ────────────────


@pytest.mark.asyncio
async def test_validate_coupon():
    """validate：unused 返回券；不存在 / 非 unused 拒绝；输入 trim+大写归一"""
    c = (await CouponService.create_coupons(amount=1000, count=1))[0]

    # 小写 + 空格输入也能命中
    got = await CouponService.validate_coupon(f"  {c.code.lower()} ")
    assert got.id == c.id

    with pytest.raises(ValueError):
        await CouponService.validate_coupon("NOTEXIST1234")
    with pytest.raises(ValueError):
        await CouponService.validate_coupon("")

    await CouponService.lock_coupon(c.code, "order-1")
    with pytest.raises(ValueError):
        await CouponService.validate_coupon(c.code)


@pytest.mark.asyncio
async def test_lock_release_redeem_flow():
    """完整状态机：unused → lock → release → lock → redeem"""
    c = (await CouponService.create_coupons(amount=1000, count=1))[0]

    # lock
    locked = await CouponService.lock_coupon(c.code, "order-1")
    assert locked.status == "locked"
    assert locked.locked_order_id == "order-1"

    # release：回到 unused，清空 locked_order_id
    released = await CouponService.release_coupon(c.id)
    assert released.status == "unused"
    assert released.locked_order_id is None

    # 再次 lock + redeem
    await CouponService.lock_coupon(c.code, "order-2")
    redeemed = await CouponService.redeem_coupon(c.id, "u1", "order-2")
    assert redeemed.status == "used"
    assert redeemed.used_by_user_id == "u1"
    assert redeemed.used_order_id == "order-2"
    assert redeemed.used_at is not None


@pytest.mark.asyncio
async def test_state_machine_rejects_wrong_transitions():
    """错误状态迁移全部拒绝"""
    c = (await CouponService.create_coupons(amount=1000, count=1))[0]

    # release / redeem 要求 locked
    with pytest.raises(ValueError):
        await CouponService.release_coupon(c.id)
    with pytest.raises(ValueError):
        await CouponService.redeem_coupon(c.id, "u1", "order-1")

    # lock 不存在的券
    with pytest.raises(ValueError):
        await CouponService.lock_coupon("NOTEXIST1234", "order-x")

    # used 后不可再 lock / release / redeem
    await CouponService.lock_coupon(c.code, "order-1")
    await CouponService.redeem_coupon(c.id, "u1", "order-1")
    with pytest.raises(ValueError):
        await CouponService.lock_coupon(c.code, "order-2")
    with pytest.raises(ValueError):
        await CouponService.release_coupon(c.id)
    with pytest.raises(ValueError):
        await CouponService.redeem_coupon(c.id, "u2", "order-2")


@pytest.mark.asyncio
async def test_lock_concurrent_only_one_wins():
    """lock 并发竞争：两个订单同时锁同一券，只成功一次"""
    c = (await CouponService.create_coupons(amount=1000, count=1))[0]

    results = await asyncio.gather(
        CouponService.lock_coupon(c.code, "order-A"),
        CouponService.lock_coupon(c.code, "order-B"),
        return_exceptions=True,
    )

    successes = [r for r in results if isinstance(r, Coupon)]
    failures = [r for r in results if isinstance(r, ValueError)]
    assert len(successes) == 1
    assert len(failures) == 1

    final = await _get_coupon(c.id)
    assert final.status == "locked"
    assert final.locked_order_id in ("order-A", "order-B")


# ─── 券池：FIFO / 自动创建 / exclude_ids ───────────────────────


@pytest.mark.asyncio
async def test_draw_from_pool_fifo_order():
    """券池 FIFO：取创建最早的 unused；exclude 已取的后取下一张"""
    now = datetime.now(timezone.utc)
    c_old = await _insert_coupon("OLDCOUPON001", 1000, now - timedelta(days=3))
    c_mid = await _insert_coupon("MIDCOUPON001", 2000, now - timedelta(days=2))
    c_new = await _insert_coupon("NEWCOUPON001", 3000, now - timedelta(days=1))

    first = await CouponService.draw_from_pool()
    assert first.id == c_old.id

    second = await CouponService.draw_from_pool(exclude_ids={first.id})
    assert second.id == c_mid.id

    third = await CouponService.draw_from_pool(exclude_ids={first.id, second.id})
    assert third.id == c_new.id

    # 取券不改状态（仍 unused，可下单锁定）
    assert (await _get_coupon(c_old.id)).status == "unused"


@pytest.mark.asyncio
async def test_draw_from_pool_skips_locked_and_used():
    """券池只取 unused：locked / used 不参与 FIFO"""
    now = datetime.now(timezone.utc)
    c_locked = await _insert_coupon("LOCKEDCPN001", 1000, now - timedelta(days=3), status="locked")
    c_used = await _insert_coupon("USEDCPN00001", 1000, now - timedelta(days=2), status="used")
    c_free = await _insert_coupon("FREECPN00001", 1000, now - timedelta(days=1))

    drawn = await CouponService.draw_from_pool()
    assert drawn.id == c_free.id
    assert drawn.id not in (c_locked.id, c_used.id)


@pytest.mark.asyncio
async def test_draw_from_pool_auto_create_when_empty():
    """池空：按 DEFAULT_COUPON_AMOUNT 自动创建（source=email_auto）"""
    drawn = await CouponService.draw_from_pool()
    assert drawn.amount == settings.DEFAULT_COUPON_AMOUNT
    assert drawn.source == "email_auto"
    assert drawn.status == "unused"

    # 全部 exclude 也视同池空 → 再自动创建一张新券
    drawn2 = await CouponService.draw_from_pool(exclude_ids={drawn.id})
    assert drawn2.id != drawn.id
    assert drawn2.amount == settings.DEFAULT_COUPON_AMOUNT
    assert drawn2.source == "email_auto"


# ─── 邮件发券扩展 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_task_attach_coupon_requires_placeholder():
    """attach_coupon=True 但正文无 {{coupon_code}} 占位符 → ValueError"""
    with pytest.raises(ValueError):
        await NotificationService.create_task(
            subject="x",
            body="没有占位符的正文",
            user_filter={},
            attach_coupon=True,
        )


@pytest.mark.asyncio
async def test_run_batch_attach_coupon_renders_per_recipient(monkeypatch):
    """附券任务：逐收件人取券渲染，每封正文含不同券码，券码落 recipient.coupon_code"""
    sent_bodies = {}

    async def fake_send(to_email, subject, body_text):
        sent_bodies[to_email] = body_text

    monkeypatch.setattr(
        "app.services.notification_service.EmailService.send_email",
        AsyncMock(side_effect=fake_send),
    )

    # 池里放 2 张券（u1/u2 是 active，筛选 is_active=True → 2 个收件人）
    c1 = (await CouponService.create_coupons(amount=5000, count=1))[0]
    c2 = (await CouponService.create_coupons(amount=5000, count=1))[0]

    task_id = await NotificationService.create_task(
        subject="专属折扣券",
        body="您的券码：{{coupon_code}}，请尽快使用。",
        user_filter={"is_active": True},
        attach_coupon=True,
    )
    await NotificationService.run_batch(task_id)

    # 两个收件人都发送成功，正文占位符被替换
    assert set(sent_bodies.keys()) == {"alice@test.com", "bob@test.com"}
    for body in sent_bodies.values():
        assert "{{coupon_code}}" not in body

    # 每人拿到的码不同，且来自券池
    codes_sent = {
        body.replace("您的券码：", "").replace("，请尽快使用。", "")
        for body in sent_bodies.values()
    }
    assert codes_sent == {c1.code, c2.code}

    # 券码落库到 recipient.coupon_code；任务详情带出 attach_coupon
    status = await NotificationService.get_status(task_id)
    assert status["attach_coupon"] is True
    assert status["sent"] == 2
    recipient_codes = {r["coupon_code"] for r in status["recipients"]}
    assert recipient_codes == {c1.code, c2.code}


@pytest.mark.asyncio
async def test_run_batch_attach_coupon_auto_create_when_pool_empty(monkeypatch):
    """附券任务池空：自动按默认面额创建券并渲染发送"""
    captured = {}

    async def fake_send(to_email, subject, body_text):
        captured[to_email] = body_text

    monkeypatch.setattr(
        "app.services.notification_service.EmailService.send_email",
        AsyncMock(side_effect=fake_send),
    )

    task_id = await NotificationService.create_task(
        subject="券",
        body="码={{coupon_code}}",
        user_filter={"is_active": False},  # 只有 u3
        attach_coupon=True,
    )
    await NotificationService.run_batch(task_id)

    body = captured["carol@test.com"]
    code = body.replace("码=", "")
    assert code and "{{coupon_code}}" not in body

    # 自动创建的券：默认面额 + email_auto
    async with _TestSessionLocal() as db:
        coupon = (await db.execute(select(Coupon).where(Coupon.code == code))).scalar_one()
    assert coupon.amount == settings.DEFAULT_COUPON_AMOUNT
    assert coupon.source == "email_auto"


@pytest.mark.asyncio
async def test_run_batch_coupon_draw_failure_marks_recipient_failed(monkeypatch):
    """取券失败不中断整批：该收件人 failed（原因含取券失败），其余正常"""
    monkeypatch.setattr(
        "app.services.notification_service.EmailService.send_email",
        AsyncMock(return_value=None),
    )

    # 第一次取券抛错，之后正常
    original_draw = CouponService.draw_from_pool
    calls = {"n": 0}

    async def flaky_draw(exclude_ids=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("pool db error")
        return await original_draw(exclude_ids=exclude_ids)

    monkeypatch.setattr(
        "app.services.notification_service.CouponService.draw_from_pool", flaky_draw
    )

    task_id = await NotificationService.create_task(
        subject="券",
        body="码={{coupon_code}}",
        user_filter={"is_active": True},  # u1 + u2
        attach_coupon=True,
    )
    await NotificationService.run_batch(task_id)

    status = await NotificationService.get_status(task_id)
    assert status["status"] == "completed"
    assert status["sent"] == 1
    assert status["failed"] == 1
    failed = [r for r in status["recipients"] if r["status"] == "failed"]
    assert "取券失败" in failed[0]["error_msg"]
