"""
报告解读咨询服务测试（P-D，ADR-0008）

测试场景：
1. 购买前置：无报告用户买咨询被拒；有报告（approved/存量无字段）放行
2. 问卷提交：字段校验（缺主题/时间段/联系方式/报告不在名下）+ 成功提交状态流转
3. 问卷守卫：非本人 404；非 pending_survey 重复提交 400
4. Admin 状态机：schedule（仅 submitted，发站内信通知用户）→ complete（仅 scheduled）；非法流转 400
5. 列表/详情：user_email 联查、状态筛选、本人隔离

fixture 风格同 test_payment_service.py；报告注册表 stub 为内存 dict。
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from app.models.database import Base
from app.models.feedback import Notification
from app.models.payment import ConsultationBooking
from app.models.user import User
from app.services import consultation_service as cs_mod
from app.services import payment_service as ps_mod
from app.services.consultation_service import BookingNotFoundError, ConsultationService
from app.services.payment_service import PaymentService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
_TestSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)

# 内存报告注册表：user_id → [record]
_FAKE_REPORTS = [
    {"report_id": "rpt-1", "activation_code": "CODE1", "user_id": "u1",
     "created_at": "2026-07-01T00:00:00", "review_status": "approved"},
    {"report_id": "rpt-2", "activation_code": "CODE2", "user_id": "u1",
     "created_at": "2026-07-02T00:00:00"},  # 无 review_status → 祖父豁免 approved
    {"report_id": "rpt-3", "activation_code": "CODE3", "user_id": "u1",
     "created_at": "2026-07-03T00:00:00", "review_status": "pending_review"},  # 审核中不算
]


class FakeRegistry:
    def list_reports(self):
        return list(_FAKE_REPORTS)


@pytest.fixture(autouse=True)
async def _setup_db(monkeypatch, tmp_path):
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    monkeypatch.setattr(cs_mod, "AsyncSessionLocal", _TestSessionLocal)
    monkeypatch.setattr(ps_mod, "AsyncSessionLocal", _TestSessionLocal)
    monkeypatch.setattr(cs_mod, "_registry", lambda: FakeRegistry())

    # payment_service 的 consultation 前置校验走 ConsultationService → 同一 stub
    from app.utils.simple_activation_manager import SimpleActivationManager

    manager = SimpleActivationManager(base_dir=str(tmp_path / "simple"))
    monkeypatch.setattr(ps_mod, "_activation_manager", lambda: manager)
    monkeypatch.setattr(
        ps_mod, "get_activation_with_manager",
        lambda code: (manager, manager.get_activation(code)),
    )
    monkeypatch.setattr(ps_mod.EmailService, "send_email", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "app.utils.activation_audit.append_activation_audit", lambda *a, **k: None
    )

    now = datetime.now(timezone.utc)
    async with _TestSessionLocal() as db:
        db.add_all(
            [
                User(id="u1", email="alice@test.com", username="alice",
                     password_hash="x", is_active=True, created_at=now),
                User(id="u9", email="nobody@test.com", username="nobody",
                     password_hash="x", is_active=True, created_at=now),
            ]
        )
        await db.commit()

    yield

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _make_booking(user_id: str = "u1", status: str = "pending_survey") -> ConsultationBooking:
    """直接落库造预约单"""
    async with _TestSessionLocal() as db:
        booking = ConsultationBooking(order_id="order-x", user_id=user_id, status=status)
        db.add(booking)
        await db.commit()
        await db.refresh(booking)
        return booking


# ─── 1. 购买前置 ──────────────────────────────────────────────


def test_user_has_completed_report():
    assert ConsultationService.user_has_completed_report("u1") is True
    assert ConsultationService.user_has_completed_report("u9") is False


def test_completed_reports_exclude_pending_review():
    items = ConsultationService.list_user_completed_reports("u1")
    ids = {r["report_id"] for r in items}
    assert ids == {"rpt-1", "rpt-2"}  # rpt-3 审核中被排除


@pytest.mark.asyncio
async def test_consultation_order_rejected_without_report():
    with pytest.raises(ValueError, match="已完成"):
        await PaymentService.create_order(
            user_id="u9", product_type="consultation", channel="alipay"
        )


# ─── 2. 问卷提交 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_survey_success():
    booking = await _make_booking()
    result = await ConsultationService.submit_survey(
        user_id="u1",
        booking_id=booking.id,
        report_id="rpt-1",
        topics="想探讨职业转型方向",
        time_slots=["周三晚 8 点", "周六下午"],
        contact="微信：alice123",
        note="备注",
    )
    assert result["status"] == "submitted"
    assert result["report_id"] == "rpt-1"
    assert result["time_slots"] == ["周三晚 8 点", "周六下午"]

    async with _TestSessionLocal() as db:
        row = (
            await db.execute(
                select(ConsultationBooking).where(ConsultationBooking.id == booking.id)
            )
        ).scalar_one()
    assert row.status == "submitted"
    assert row.contact == "微信：alice123"


@pytest.mark.asyncio
async def test_submit_survey_field_validation():
    booking = await _make_booking()
    with pytest.raises(ValueError, match="主题"):
        await ConsultationService.submit_survey(
            user_id="u1", booking_id=booking.id, report_id="rpt-1",
            topics="", time_slots=["周三"], contact="wx",
        )
    with pytest.raises(ValueError, match="时间段"):
        await ConsultationService.submit_survey(
            user_id="u1", booking_id=booking.id, report_id="rpt-1",
            topics="话题", time_slots=[], contact="wx",
        )
    with pytest.raises(ValueError, match="联系方式"):
        await ConsultationService.submit_survey(
            user_id="u1", booking_id=booking.id, report_id="rpt-1",
            topics="话题", time_slots=["周三"], contact=" ",
        )
    with pytest.raises(ValueError, match="名下"):
        await ConsultationService.submit_survey(
            user_id="u1", booking_id=booking.id, report_id="rpt-other",
            topics="话题", time_slots=["周三"], contact="wx",
        )


@pytest.mark.asyncio
async def test_submit_survey_guards():
    booking = await _make_booking(status="submitted")
    # 非 pending_survey 重复提交
    with pytest.raises(ValueError, match="不可提交"):
        await ConsultationService.submit_survey(
            user_id="u1", booking_id=booking.id, report_id="rpt-1",
            topics="话题", time_slots=["周三"], contact="wx",
        )
    # 非本人
    with pytest.raises(BookingNotFoundError):
        await ConsultationService.submit_survey(
            user_id="u9", booking_id=booking.id, report_id="rpt-1",
            topics="话题", time_slots=["周三"], contact="wx",
        )


# ─── 3. Admin 状态机 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_schedule_and_complete():
    booking = await _make_booking(status="submitted")

    scheduled = await ConsultationService.admin_schedule(
        booking.id, scheduled_at="2026-07-25 20:00", admin_note="已微信确认",
        actor={"user_id": "admin"},
    )
    assert scheduled["status"] == "scheduled"
    assert scheduled["scheduled_at"] is not None
    assert scheduled["admin_note"] == "已微信确认"

    # 站内信通知用户：时间 + 详情页入口；admin_note 为内部备注不透出
    async with _TestSessionLocal() as db:
        notifs = (
            (await db.execute(select(Notification).where(Notification.user_id == "u1")))
            .scalars()
            .all()
        )
    assert len(notifs) == 1
    notif = notifs[0]
    assert notif.type == "consultation_scheduled"
    assert notif.title == "咨询时间已确认"
    assert "2026-07-25 20:00" in notif.content
    assert f"/dashboard/consultation/{booking.id}" in notif.content
    assert "已微信确认" not in notif.content
    assert notif.read_at is None

    completed = await ConsultationService.admin_complete(booking.id, actor={"user_id": "admin"})
    assert completed["status"] == "completed"


@pytest.mark.asyncio
async def test_admin_schedule_invalid_transitions():
    # pending_survey 不能预约
    b1 = await _make_booking(status="pending_survey")
    with pytest.raises(ValueError, match="已提交"):
        await ConsultationService.admin_schedule(b1.id, scheduled_at="2026-07-25 20:00")
    # submitted 不能直接完成
    b2 = await _make_booking(status="submitted")
    with pytest.raises(ValueError, match="已预约"):
        await ConsultationService.admin_complete(b2.id)
    # 时间格式非法
    b3 = await _make_booking(status="submitted")
    with pytest.raises(ValueError, match="格式"):
        await ConsultationService.admin_schedule(b3.id, scheduled_at="下周三吧")


# ─── 4. 列表与详情 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_list_with_email_and_filter():
    await _make_booking(status="submitted")
    await _make_booking(status="pending_survey")

    items, total = await ConsultationService.admin_list_bookings(status="submitted")
    assert total == 1
    assert items[0]["user_email"] == "alice@test.com"

    _, total_all = await ConsultationService.admin_list_bookings()
    assert total_all == 2


@pytest.mark.asyncio
async def test_my_bookings_isolation():
    mine = await _make_booking(user_id="u1")
    await _make_booking(user_id="u9")

    items, total = await ConsultationService.list_my_bookings("u1")
    assert total == 1
    assert items[0]["id"] == mine.id

    with pytest.raises(BookingNotFoundError):
        await ConsultationService.get_my_booking("u9", mine.id)
