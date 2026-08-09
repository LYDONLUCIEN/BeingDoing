"""
7 天免费续期测试（ADR-0015）

测试场景：
1. 懒过期扫描：active+过期 → expired 并进入待通知列表；试用码/沙箱/无套餐类型不进入
2. 幂等：offered 标记后不再出现在待通知列表（存量补发只发一次）
3. 领取：owner 领取成功 +7 天、status 回 active；重复领取/非 owner/试用码/未发通知 拒绝
4. 扫描服务：站内信落库 + 邮件发送 + offered 标记；二次扫描不重复
5. 付费延期新定价：RENEWAL_PRICE=990 / RENEWAL_DAYS=7 生效

fixture 风格同 test_packages.py：in-memory SQLite + monkeypatch。
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from app.config.settings import settings
from app.models.database import Base
from app.models.feedback import Notification
from app.models.user import User
from app.services import activation_expiry_scan as scan_mod
from app.services.email_service import EmailService
from app.utils.simple_activation_manager import (
    ActivationStatus,
    SimpleActivationManager,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
_TestSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)


@pytest.fixture
async def mgr(monkeypatch, tmp_path):
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    monkeypatch.setattr(scan_mod, "AsyncSessionLocal", _TestSessionLocal)
    monkeypatch.setattr(
        "app.utils.activation_audit.append_activation_audit", lambda *a, **k: None
    )

    manager = SimpleActivationManager(base_dir=str(tmp_path / "simple"))
    # 扫描服务内部自建 manager：把 prod 根指到 tmp
    monkeypatch.setattr(scan_mod, "get_simple_base_dir", lambda: tmp_path / "simple")

    now = datetime.now(timezone.utc)
    async with _TestSessionLocal() as db:
        db.add_all(
            [
                User(
                    id="u1", email="alice@test.com", username="alice",
                    password_hash="x", is_active=True, created_at=now,
                ),
                User(
                    id="u2", email=None, username="bob",
                    password_hash="x", is_active=True, created_at=now,
                ),
            ]
        )
        await db.commit()

    yield manager

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ─── 辅助 ────────────────────────────────────────────────────


def _make_expired_full(mgr, user_id="u1", email="alice@test.com", package_type="quarterly"):
    """造一个昨天过期的完整码"""
    rec = mgr.create_activation(
        mode="combined",
        ttl_minutes=60,
        code_type="full",
        vip_level=2,
        package_type=package_type,
    )
    rec = mgr.claim_owner(rec.code, {"user_id": user_id, "email": email})
    records = mgr._load_all()
    records[rec.code].expires_at = (
        datetime.now(timezone.utc) - timedelta(days=1)
    ).isoformat()
    mgr._save_all(records)
    return mgr.get_activation(rec.code)


# ─── 1. 懒过期扫描 + 待通知列表 ───────────────────────────────


@pytest.mark.asyncio
async def test_scan_marks_expired_and_lists_pending(mgr):
    rec = _make_expired_full(mgr)
    # 懒过期：get_activation 已就地置 expired
    assert rec.status == ActivationStatus.EXPIRED

    pending = mgr.mark_expired_and_list_pending_free_renewal()
    assert [r.code for r in pending] == [rec.code]


@pytest.mark.asyncio
async def test_scan_excludes_trial_and_untyped_and_sandbox(mgr):
    # 试用码：不过期，永不在列表
    trial = mgr.create_activation(mode="combined", code_type="trial")
    mgr.claim_owner(trial.code, {"user_id": "u1", "email": "alice@test.com"})
    # 无套餐类型的存量码：拒延，也不发免费续期
    legacy = _make_expired_full(mgr, package_type=None)
    # 沙箱码：不发
    sbx = _make_expired_full(mgr)
    records = mgr._load_all()
    records[sbx.code].is_sandbox = True
    mgr._save_all(records)

    pending = mgr.mark_expired_and_list_pending_free_renewal()
    codes = {r.code for r in pending}
    assert trial.code not in codes
    assert legacy.code not in codes
    assert sbx.code not in codes


@pytest.mark.asyncio
async def test_offered_marker_makes_scan_idempotent(mgr):
    rec = _make_expired_full(mgr)
    mgr.mark_free_renewal_offered(rec.code)
    assert mgr.mark_expired_and_list_pending_free_renewal() == []


# ─── 2. 领取 ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_claim_success_extends_7_days(mgr):
    rec = _make_expired_full(mgr)
    mgr.mark_free_renewal_offered(rec.code)

    before = datetime.now(timezone.utc)
    claimed = mgr.claim_free_renewal(
        rec.code, user_id="u1", actor={"user_id": "u1", "email": "alice@test.com"}
    )
    assert claimed.status == ActivationStatus.ACTIVE
    assert claimed.free_renewal_claimed_at is not None
    new_expires = datetime.fromisoformat(claimed.expires_at)
    # 已过期码从此刻起 +FREE_RENEWAL_DAYS 天（max(原到期, now) 口径）
    assert new_expires >= before + timedelta(days=settings.FREE_RENEWAL_DAYS)
    assert new_expires <= datetime.now(timezone.utc) + timedelta(
        days=settings.FREE_RENEWAL_DAYS, minutes=1
    )


@pytest.mark.asyncio
async def test_claim_twice_rejected(mgr):
    rec = _make_expired_full(mgr)
    mgr.mark_free_renewal_offered(rec.code)
    mgr.claim_free_renewal(rec.code, user_id="u1")
    with pytest.raises(ValueError, match="已领取"):
        mgr.claim_free_renewal(rec.code, user_id="u1")


@pytest.mark.asyncio
async def test_claim_non_owner_rejected(mgr):
    rec = _make_expired_full(mgr)
    mgr.mark_free_renewal_offered(rec.code)
    with pytest.raises(ValueError, match="激活人"):
        mgr.claim_free_renewal(rec.code, user_id="u2")


@pytest.mark.asyncio
async def test_claim_without_offer_rejected(mgr):
    rec = _make_expired_full(mgr)  # 未发通知
    with pytest.raises(ValueError, match="暂无免费续期"):
        mgr.claim_free_renewal(rec.code, user_id="u1")


@pytest.mark.asyncio
async def test_claim_trial_rejected(mgr):
    trial = mgr.create_activation(mode="combined", code_type="trial")
    mgr.claim_owner(trial.code, {"user_id": "u1", "email": "alice@test.com"})
    with pytest.raises(ValueError, match="完整码"):
        mgr.claim_free_renewal(trial.code, user_id="u1")


# ─── 3. 扫描服务（站内信 + 邮件） ─────────────────────────────


@pytest.mark.asyncio
async def test_scan_service_sends_notification_and_email(mgr, monkeypatch):
    send_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(EmailService, "send_email", send_mock)

    rec = _make_expired_full(mgr)  # owner=u1 有邮箱
    rec2 = _make_expired_full(mgr, user_id="u2", email="")  # owner=u2 无邮箱

    stats = await scan_mod.scan_expired_activations()
    assert stats["notified"] == 2
    assert stats["email_sent"] == 1  # 仅 u1 有邮箱
    send_mock.assert_awaited_once()
    assert "free_renewal=" in send_mock.await_args.kwargs["body_text"]

    async with _TestSessionLocal() as db:
        rows = (
            await db.execute(
                select(Notification).where(Notification.type == "activation_expired")
            )
        ).scalars().all()
    assert len(rows) == 2
    assert {n.user_id for n in rows} == {"u1", "u2"}
    assert all("free_renewal=" in n.content for n in rows)

    # offered 标记已落
    assert mgr.get_activation(rec.code).free_renewal_offered_at is not None
    assert mgr.get_activation(rec2.code).free_renewal_offered_at is not None

    # 二次扫描：不重复通知、不重发邮件
    send_mock.reset_mock()
    stats2 = await scan_mod.scan_expired_activations()
    assert stats2["expired_pending"] == 0
    send_mock.assert_not_awaited()
    async with _TestSessionLocal() as db:
        count = (
            await db.execute(
                select(func.count(Notification.id)).where(
                    Notification.type == "activation_expired"
                )
            )
        ).scalar_one()
    assert int(count) == 2


# ─── 4. 付费延期新定价（ADR-0015：9.9 元 / 7 天） ─────────────


def test_renewal_pricing_settings():
    assert settings.RENEWAL_PRICE == 990
    assert settings.RENEWAL_DAYS == 7
    assert settings.FREE_RENEWAL_DAYS == 7
