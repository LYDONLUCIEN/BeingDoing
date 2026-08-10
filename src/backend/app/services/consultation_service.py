"""
报告解读咨询服务（P-D，ADR-0008）

状态机：pending_survey → submitted → scheduled → completed（退款走 cancelled，见 payment_service.admin_refund）

规则口径：
- 购买前置：用户须至少持有一份「已完成且审核通过」的报告
- 问卷：pending_survey 时可提交一次（report_id/topics/time_slots/contact/note）→ submitted
- admin：submitted → scheduled（填实际时间+备注，发站内信通知用户）→ completed
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select

from app.models.database import AsyncSessionLocal
from app.models.feedback import Notification
from app.models.payment import ConsultationBooking
from app.models.user import User

logger = logging.getLogger(__name__)

# 咨询状态机
STATUS_PENDING_SURVEY = "pending_survey"
STATUS_SUBMITTED = "submitted"
STATUS_SCHEDULED = "scheduled"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"

# 站内信（notifications 表）
NOTIFY_TYPE_SCHEDULED = "consultation_scheduled"
NOTIFY_TITLE_SCHEDULED = "咨询时间已确认"


def _build_scheduled_notification_content(booking_id: str, scheduled_dt: datetime) -> str:
    """预约确认站内信文案（时间 + 详情页入口；admin_note 为内部备注不透出）。"""
    time_str = scheduled_dt.strftime("%Y-%m-%d %H:%M")
    return (
        f"您的报告解读咨询时间已确认：{time_str}。\n"
        "请提前安排好时间，顾问将通过您预留的联系方式与您沟通。\n"
        f"查看详情：/dashboard/consultation/{booking_id}"
    )


class BookingNotFoundError(Exception):
    """预约单不存在（路由转 404）"""


def _registry():
    """报告注册表（独立成函数便于测试替换）"""
    from app.utils.report_registry import ReportRegistry

    return ReportRegistry()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ConsultationService:
    """报告解读咨询服务"""

    # ─── 报告前置校验 ──────────────────────────────────────────

    @classmethod
    def list_user_completed_reports(cls, user_id: str) -> List[Dict[str, Any]]:
        """用户名下「已完成且审核通过」的报告列表（咨询购买前置 + 问卷选报告）

        存量报告无 review_status 字段视为 approved（祖父豁免，与报告审核流一致）。
        """
        reports: List[Dict[str, Any]] = []
        for record in _registry().list_reports():
            if record.get("user_id") != user_id:
                continue
            review_status = record.get("review_status") or "approved"
            if review_status != "approved":
                continue
            reports.append(
                {
                    "report_id": record.get("report_id"),
                    "activation_code": record.get("activation_code"),
                    "created_at": record.get("created_at"),
                }
            )
        reports.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        return reports

    @classmethod
    def user_has_completed_report(cls, user_id: str) -> bool:
        """是否至少持有一份已完成的有效报告（购买前置条件）"""
        return bool(cls.list_user_completed_reports(user_id))

    # ─── 用户侧：预约单查询与问卷 ──────────────────────────────

    @classmethod
    async def list_my_bookings(
        cls, user_id: str, page: int = 1, page_size: int = 20
    ) -> Tuple[List[Dict[str, Any]], int]:
        """我的咨询预约单列表"""
        async with AsyncSessionLocal() as db:
            base = select(ConsultationBooking).where(ConsultationBooking.user_id == user_id)
            total = (
                await db.execute(
                    select(func.count())
                    .select_from(ConsultationBooking)
                    .where(ConsultationBooking.user_id == user_id)
                )
            ).scalar() or 0
            rows = (
                (
                    await db.execute(
                        base.order_by(ConsultationBooking.created_at.desc())
                        .offset((page - 1) * page_size)
                        .limit(page_size)
                    )
                )
                .scalars()
                .all()
            )
            return [cls._to_dict(b) for b in rows], total

    @classmethod
    async def get_my_booking(cls, user_id: str, booking_id: str) -> Dict[str, Any]:
        """我的预约单详情（仅本人）"""
        async with AsyncSessionLocal() as db:
            booking = await cls._get_or_raise(db, booking_id)
            if booking.user_id != user_id:
                raise BookingNotFoundError("预约单不存在")
            return cls._to_dict(booking)

    @classmethod
    async def submit_survey(
        cls,
        user_id: str,
        booking_id: str,
        *,
        report_id: str,
        topics: str,
        time_slots: List[str],
        contact: str,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """提交预约问卷（pending_survey → submitted）

        Raises:
            BookingNotFoundError: 预约单不存在或非本人
            ValueError: 状态不允许 / 字段非法 / 报告不在名下
        """
        report_id = (report_id or "").strip()
        topics = (topics or "").strip()
        contact = (contact or "").strip()
        slots = [s.strip() for s in (time_slots or []) if (s or "").strip()]
        if not report_id:
            raise ValueError("请选择要解读的报告")
        if not topics:
            raise ValueError("请填写想探讨的主题或期望")
        if not slots:
            raise ValueError("请至少填写一个方便的时间段")
        if len(slots) > 5:
            raise ValueError("候选时间段最多 5 个")
        if not contact:
            raise ValueError("请填写联系方式（微信或电话）")

        # 预约单归属与状态校验（先于报告校验，避免泄露报告存在性）
        async with AsyncSessionLocal() as db:
            booking = await cls._get_or_raise(db, booking_id)
            if booking.user_id != user_id:
                raise BookingNotFoundError("预约单不存在")
            if booking.status != STATUS_PENDING_SURVEY:
                raise ValueError(f"当前状态不可提交问卷（当前状态：{booking.status}）")

        # 报告须在本人名下（防填别人的报告）
        owned_ids = {r["report_id"] for r in cls.list_user_completed_reports(user_id)}
        if report_id not in owned_ids:
            raise ValueError("所选报告不在您的名下或尚未审核通过")

        async with AsyncSessionLocal() as db:
            booking = await cls._get_or_raise(db, booking_id)
            booking.report_id = report_id
            booking.topics = topics
            booking.time_slots = json.dumps(slots, ensure_ascii=False)
            booking.contact = contact
            booking.note = (note or "").strip() or None
            booking.status = STATUS_SUBMITTED
            booking.updated_at = _utcnow()
            await db.commit()
            await db.refresh(booking)
            logger.info("咨询问卷已提交：booking=%s user=%s", booking_id, user_id)
            return cls._to_dict(booking)

    # ─── Admin 侧 ──────────────────────────────────────────────

    @classmethod
    async def admin_list_bookings(
        cls,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Admin 咨询预约单列表（状态筛选 + 分页，含 user_email）"""
        async with AsyncSessionLocal() as db:
            base = select(ConsultationBooking, User.email).join(
                User, ConsultationBooking.user_id == User.id
            )
            count_q = select(func.count()).select_from(ConsultationBooking)
            if status:
                base = base.where(ConsultationBooking.status == status)
                count_q = count_q.where(ConsultationBooking.status == status)
            total = (await db.execute(count_q)).scalar() or 0
            rows = (
                await db.execute(
                    base.order_by(ConsultationBooking.created_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
            items = []
            for booking, email in rows:
                item = cls._to_dict(booking)
                item["user_email"] = email
                items.append(item)
            return items, total

    @classmethod
    async def admin_get_booking(cls, booking_id: str) -> Dict[str, Any]:
        """Admin 预约单详情（含 user_email）"""
        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    select(ConsultationBooking, User.email)
                    .join(User, ConsultationBooking.user_id == User.id)
                    .where(ConsultationBooking.id == booking_id)
                )
            ).first()
            if not row:
                raise BookingNotFoundError("预约单不存在")
            booking, email = row
            item = cls._to_dict(booking)
            item["user_email"] = email
            return item

    @classmethod
    async def admin_schedule(
        cls,
        booking_id: str,
        *,
        scheduled_at: str,
        admin_note: Optional[str] = None,
        actor: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """Admin 标记已预约（submitted → scheduled），填实际时间与备注"""
        scheduled_at = (scheduled_at or "").strip()
        if not scheduled_at:
            raise ValueError("请填写预约时间")
        try:
            scheduled_dt = datetime.fromisoformat(scheduled_at)
        except ValueError:
            raise ValueError("预约时间格式不正确，示例：2026-07-25 20:00")
        async with AsyncSessionLocal() as db:
            booking = await cls._get_or_raise(db, booking_id)
            if booking.status != STATUS_SUBMITTED:
                raise ValueError(f"仅已提交问卷的预约单可标记预约（当前状态：{booking.status}）")
            booking.status = STATUS_SCHEDULED
            booking.scheduled_at = scheduled_dt
            booking.admin_note = (admin_note or "").strip() or None
            booking.updated_at = _utcnow()
            # 站内信通知用户咨询时间已确认
            db.add(
                Notification(
                    user_id=booking.user_id,
                    type=NOTIFY_TYPE_SCHEDULED,
                    title=NOTIFY_TITLE_SCHEDULED,
                    content=_build_scheduled_notification_content(booking_id, scheduled_dt),
                    read_at=None,
                    related_feedback_id=None,
                )
            )
            await db.commit()
            await db.refresh(booking)
            logger.info(
                "咨询已预约：booking=%s scheduled_at=%s actor=%s",
                booking_id,
                scheduled_at,
                (actor or {}).get("user_id"),
            )
            return cls._to_dict(booking)

    @classmethod
    async def admin_complete(cls, booking_id: str, actor: Optional[dict] = None) -> Dict[str, Any]:
        """Admin 标记已完成（scheduled → completed）"""
        async with AsyncSessionLocal() as db:
            booking = await cls._get_or_raise(db, booking_id)
            if booking.status != STATUS_SCHEDULED:
                raise ValueError(f"仅已预约的咨询可标记完成（当前状态：{booking.status}）")
            booking.status = STATUS_COMPLETED
            booking.updated_at = _utcnow()
            await db.commit()
            await db.refresh(booking)
            logger.info(
                "咨询已完成：booking=%s actor=%s", booking_id, (actor or {}).get("user_id")
            )
            return cls._to_dict(booking)

    # ─── 内部 ──────────────────────────────────────────────────

    @staticmethod
    async def _get_or_raise(db, booking_id: str) -> ConsultationBooking:
        booking = (
            await db.execute(
                select(ConsultationBooking).where(ConsultationBooking.id == booking_id)
            )
        ).scalar_one_or_none()
        if not booking:
            raise BookingNotFoundError("预约单不存在")
        return booking

    @staticmethod
    def _to_dict(booking: ConsultationBooking) -> Dict[str, Any]:
        def iso(dt: Optional[datetime]) -> Optional[str]:
            return dt.isoformat() if dt else None

        try:
            slots = json.loads(booking.time_slots) if booking.time_slots else []
        except (ValueError, TypeError):
            slots = []
        return {
            "id": booking.id,
            "order_id": booking.order_id,
            "user_id": booking.user_id,
            "report_id": booking.report_id,
            "topics": booking.topics,
            "time_slots": slots,
            "contact": booking.contact,
            "note": booking.note,
            "status": booking.status,
            "scheduled_at": iso(booking.scheduled_at),
            "admin_note": booking.admin_note,
            "created_at": iso(booking.created_at),
            "updated_at": iso(booking.updated_at),
        }
