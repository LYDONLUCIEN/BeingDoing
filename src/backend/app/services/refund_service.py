"""
退款服务（2026-10-05，设计文档 wiki/开发文档/10-05/订单系统退款设计.md）

统一退款申请单：全退/部分退同走 payment_refunds 状态机
    pending_review →（批准并执行）→ refunding → succeeded / failed（同 refund_no 重试）
    pending_review → withdrawn（用户撤回）/ rejected（admin 驳回，必填理由）

职责：
1. 可退性视图 get_refund_options：行级分摊明细 + 实时状态重验 + 剩余可退
2. 申请（用户自提 / admin 代录）：类型守卫（延期不可退、咨询仅未预约、
   季度/legacy 仅全退、部分退仅年度套餐按码折算或咨询协商）、
   同订单同时仅一个在途申请；partial 申请时把所选行落 line_snapshot
3. 审批 approve：事务内锁定申请 → 实时重验行状态与金额上限（不信任申请时
   快照）→ 批准额只能 ≤ 实时上限、与申请额不一致必填调整理由 → 渠道同步
   退款（0 元单跳过）→ 成功后原子联动订单/行/码/预约/券
4. 驳回 reject / 撤回 withdraw / 失败重试 retry（复用同 refund_no，渠道幂等）
5. 通知：新申请 → admin 站内信+邮件；审批结果与退款成功 → 用户站内信+邮件；
   退款失败 → admin 站内信（人工兜底）

金额一律整数分。业务约束违反抛 ValueError（路由转 400）；
退款单/订单不存在抛 RefundNotFoundError / OrderNotFoundError（路由转 404）。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.core.payment import get_channel
from app.models.database import AsyncSessionLocal
from app.models.feedback import Notification
from app.models.payment import (
    ConsultationBooking,
    PaymentOrder,
    PaymentOrderLine,
    PaymentRefund,
)
from app.models.user import User
from app.services.coupon_service import CouponService
from app.services.email_service import EmailService
from app.services.payment_line_service import (
    LINE_ITEM_CODE,
    LINE_ITEM_CONSULTATION,
    ensure_order_lines,
    line_effective_status,
)
from app.services.payment_service import OrderNotFoundError
from app.utils.simple_activation_manager import get_activation_with_manager

logger = logging.getLogger(__name__)

# ─── 常量 ─────────────────────────────────────────────────────

# 退款单状态
REFUND_PENDING_REVIEW = "pending_review"
REFUND_REFUNDING = "refunding"
REFUND_SUCCEEDED = "succeeded"
REFUND_FAILED = "failed"
REFUND_REJECTED = "rejected"
REFUND_WITHDRAWN = "withdrawn"

# 在途状态（同订单同时最多一个）
_IN_FLIGHT_STATUSES = (REFUND_PENDING_REVIEW, REFUND_REFUNDING)

# 商品类型（与 payment_service 保持一致，避免互导入）
_PRODUCT_QUARTERLY = "quarterly_package"
_PRODUCT_ANNUAL = "annual_package"
_PRODUCT_RENEWAL = "renewal"
_PRODUCT_CONSULTATION = "consultation"

# 站内信类型
NOTIFY_TYPE_ADMIN_REQUEST = "refund_request"
NOTIFY_TYPE_USER_RESULT = "refund_result"

NOTIFY_TITLE_ADMIN_REQUEST = "新退款申请"
NOTIFY_TITLE_APPROVED = "退款申请已批准"
NOTIFY_TITLE_REJECTED = "退款申请已驳回"
NOTIFY_TITLE_SUCCEEDED = "退款已到账"
NOTIFY_TITLE_FAILED_ADMIN = "退款执行失败"

_ERR_RENEWAL = "延期订单交付后即已使用，不可退款（请走线下协商）"


class RefundNotFoundError(Exception):
    """退款单不存在（路由转 404）"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _fen_to_yuan(amount_fen: int) -> str:
    return f"{amount_fen / 100:.2f}"


# ─── 通知 ─────────────────────────────────────────────────────


async def _get_super_admin_ids(db: AsyncSession) -> List[str]:
    """全部 super_admin 的 user_id（与 feedback_service 同口径，避免互导入）"""
    from app.utils.super_admin import get_super_admin_user_ids

    ids = set(get_super_admin_user_ids())
    emails = {
        e.strip().lower()
        for e in (getattr(settings, "SUPER_ADMIN_EMAILS", None) or "").split(",")
        if e.strip()
    }
    if emails:
        result = await db.execute(select(User.id).where(func.lower(User.email).in_(emails)))
        ids.update(result.scalars().all())
    return list(ids)


async def _notify_admins_inapp(
    db: AsyncSession, title: str, content: str, exclude_user_id: Optional[str] = None
) -> None:
    """给全部 super_admin 发站内信（db.add，随调用方 commit）"""
    for admin_id in await _get_super_admin_ids(db):
        if admin_id == exclude_user_id:
            continue
        db.add(
            Notification(
                user_id=admin_id,
                type=NOTIFY_TYPE_ADMIN_REQUEST,
                title=title,
                content=content,
                read_at=None,
                related_feedback_id=None,
            )
        )


async def _notify_admins_email(subject: str, body: str) -> None:
    """给 SUPER_ADMIN_EMAILS 逐个发邮件（尽力而为，失败仅记日志）"""
    emails = [
        e.strip()
        for e in (getattr(settings, "SUPER_ADMIN_EMAILS", None) or "").split(",")
        if e.strip()
    ]
    for email in emails:
        try:
            await EmailService.send_email(to_email=email, subject=subject, body_text=body)
        except Exception as e:  # noqa: BLE001
            logger.error("退款通知邮件发送失败（忽略）：to=%s err=%s", email, e)


async def _notify_user_inapp(db: AsyncSession, user_id: str, title: str, content: str) -> None:
    db.add(
        Notification(
            user_id=user_id,
            type=NOTIFY_TYPE_USER_RESULT,
            title=title,
            content=content,
            read_at=None,
            related_feedback_id=None,
        )
    )


async def _notify_user_email(user_id: str, subject: str, body: str) -> None:
    """用户邮件（查邮箱 + 发送均尽力而为，失败仅记日志）"""
    try:
        async with AsyncSessionLocal() as db:
            email = (
                await db.execute(select(User.email).where(User.id == user_id))
            ).scalar_one_or_none()
        if not email:
            return
        await EmailService.send_email(to_email=email, subject=subject, body_text=body)
    except Exception as e:  # noqa: BLE001
        logger.error("退款结果邮件发送失败（忽略）：user=%s err=%s", user_id, e)


async def _get_user_email(db: AsyncSession, user_id: str) -> Optional[str]:
    return (
        await db.execute(select(User.email).where(User.id == user_id))
    ).scalar_one_or_none()


# ─── 内部工具 ─────────────────────────────────────────────────


async def _get_order(db: AsyncSession, order_id: str) -> PaymentOrder:
    order = (
        await db.execute(select(PaymentOrder).where(PaymentOrder.id == order_id))
    ).scalar_one_or_none()
    if not order:
        raise OrderNotFoundError("订单不存在")
    return order


async def _get_refund(
    db: AsyncSession, refund_id: str, for_update: bool = False
) -> PaymentRefund:
    q = select(PaymentRefund).where(PaymentRefund.id == refund_id)
    if for_update:
        q = q.with_for_update()
    refund = (await db.execute(q)).scalar_one_or_none()
    if not refund:
        raise RefundNotFoundError("退款单不存在")
    return refund


async def _order_refundable_lines(
    db: AsyncSession, order: PaymentOrder
) -> List[Tuple[PaymentOrderLine, str]]:
    """订单明细行 + 实时有效状态（ensure 回填 + line_effective_status 重验）"""
    lines = await ensure_order_lines(db, order, source="backfill")
    return [(line, await line_effective_status(db, line)) for line in lines]


def _remaining_refundable(order: PaymentOrder) -> int:
    """订单层面剩余可退（渠道金额口径）"""
    return max(0, order.amount_paid - (order.amount_refunded or 0))


def _supports_partial(order: PaymentOrder, line_count: int) -> bool:
    """部分退支持：年度套餐（多码按码折算）与咨询（协商金额）；其余仅全退"""
    if order.product_type == _PRODUCT_ANNUAL and line_count >= 2:
        return True
    return order.product_type == _PRODUCT_CONSULTATION


def _line_snapshot_json(lines: List[PaymentOrderLine]) -> str:
    """行快照（JSON）：申请时记录所选行 / 批准时记录最终批准行"""
    return json.dumps(
        [
            {
                "line_id": l.id,
                "line_no": l.line_no,
                "item_type": l.item_type,
                "item_ref": l.item_ref,
                "amount_paid_alloc": l.amount_paid_alloc,
            }
            for l in lines
        ],
        ensure_ascii=False,
    )


def _snapshot_line_ids(refund: PaymentRefund) -> List[str]:
    """从 line_snapshot 解析行 id 列表"""
    try:
        rows = json.loads(refund.line_snapshot or "[]")
    except (ValueError, TypeError):
        return []
    if not isinstance(rows, list):
        return []
    return [r["line_id"] for r in rows if isinstance(r, dict) and r.get("line_id")]


async def _assert_no_in_flight(db: AsyncSession, order_id: str) -> None:
    in_flight = (
        await db.execute(
            select(func.count())
            .select_from(PaymentRefund)
            .where(
                PaymentRefund.order_id == order_id,
                PaymentRefund.status.in_(_IN_FLIGHT_STATUSES),
            )
        )
    ).scalar() or 0
    if in_flight:
        raise ValueError("该订单已有待处理的退款申请，请等待处理完成后再提交")


# ─── 序列化 ───────────────────────────────────────────────────


def refund_to_dict(refund: PaymentRefund) -> Dict[str, Any]:
    """ORM → 退款单契约字段（用户/admin 共用；审批留痕全量可见）"""
    snapshot = None
    if refund.line_snapshot:
        try:
            parsed = json.loads(refund.line_snapshot)
            snapshot = parsed if isinstance(parsed, list) else None
        except (ValueError, TypeError):
            snapshot = None
    return {
        "id": refund.id,
        "refund_no": refund.refund_no,
        "order_id": refund.order_id,
        "order_no": refund.order_no,
        "user_id": refund.user_id,
        "originated": refund.originated,
        "created_by_admin": refund.created_by_admin,
        "refund_type": refund.refund_type,
        "requested_amount": refund.requested_amount,
        "approved_amount": refund.approved_amount,
        "reason_user": refund.reason_user,
        "reason_admin": refund.reason_admin,
        "status": refund.status,
        "reviewed_by": refund.reviewed_by,
        "reviewed_at": _iso(refund.reviewed_at),
        "executed_at": _iso(refund.executed_at),
        "succeeded_at": _iso(refund.succeeded_at),
        "failed_reason": refund.failed_reason,
        "line_snapshot": snapshot,
        "created_at": _iso(refund.created_at),
        "updated_at": _iso(refund.updated_at),
    }


# ─── 服务 ─────────────────────────────────────────────────────


class RefundService:
    """退款申请单服务"""

    # ─── 用户侧：可退性视图 / 申请 / 撤回 / 查询 ───────────────

    @classmethod
    async def get_refund_options(cls, user_id: str, order_id: str) -> Dict[str, Any]:
        """订单退款能力视图（用户申请弹窗数据源）

        - 行级分摊明细（含实时有效状态；不回写 DB）
        - full/partial 可用性（守卫规则）+ 剩余可退
        - 在途申请与历史申请摘要

        Raises:
            OrderNotFoundError: 订单不存在或非本人
        """
        async with AsyncSessionLocal() as db:
            order = await _get_order(db, order_id)
            if order.user_id != user_id:
                raise OrderNotFoundError("订单不存在")

            lines = await _order_refundable_lines(db, order)
            await db.commit()  # 惰性回填的明细行落库（ensure 只 add+flush）
            available_count = sum(1 for _, s in lines if s == "available")
            remaining = _remaining_refundable(order)

            in_flight = (
                (
                    await db.execute(
                        select(PaymentRefund)
                        .where(
                            PaymentRefund.order_id == order.id,
                            PaymentRefund.status.in_(_IN_FLIGHT_STATUSES),
                        )
                        .order_by(PaymentRefund.created_at.desc())
                    )
                )
                .scalars()
                .first()
            )
            history = (
                (
                    await db.execute(
                        select(PaymentRefund)
                        .where(PaymentRefund.order_id == order.id)
                        .order_by(PaymentRefund.created_at.desc())
                        .limit(10)
                    )
                )
                .scalars()
                .all()
            )

            deliverable = order.status in ("granted", "partially_refunded")
            full_allowed = (
                deliverable
                and order.product_type != _PRODUCT_RENEWAL
                and len(lines) > 0
                and available_count == len(lines)
            )
            partial_allowed = (
                deliverable
                and _supports_partial(order, len(lines))
                and available_count > 0
            )

            return {
                "order": {
                    "id": order.id,
                    "order_no": order.order_no,
                    "product_type": order.product_type,
                    "amount_paid": order.amount_paid,
                    "amount_refunded": order.amount_refunded or 0,
                    "status": order.status,
                },
                "full_allowed": full_allowed,
                "partial_allowed": partial_allowed,
                # 套餐部分退按所选码分摊实付；咨询部分退走 admin 协商金额
                "partial_by_lines": order.product_type
                in (_PRODUCT_QUARTERLY, _PRODUCT_ANNUAL),
                "remaining_refundable": remaining,
                "lines": [
                    {
                        "id": line.id,
                        "line_no": line.line_no,
                        "item_type": line.item_type,
                        "item_ref": line.item_ref,
                        "amount_paid_alloc": line.amount_paid_alloc,
                        "effective_status": status,
                    }
                    for line, status in lines
                ],
                "pending_request": refund_to_dict(in_flight) if in_flight else None,
                "history": [refund_to_dict(r) for r in history],
            }

    @classmethod
    async def create_refund_request(
        cls,
        user_id: str,
        order_id: str,
        refund_type: str,
        line_ids: Optional[List[str]] = None,
        reason: Optional[str] = None,
    ) -> PaymentRefund:
        """用户提交退款申请（金额按规则计算，不手输）

        Raises:
            OrderNotFoundError / ValueError（守卫规则）
        """
        reason = (reason or "").strip()
        if not reason:
            raise ValueError("请填写退款申请理由")
        return await cls._create_request(
            order_id=order_id,
            refund_type=refund_type,
            line_ids=line_ids,
            requested_amount=None,
            reason=reason,
            originated="user",
            created_by_admin=None,
            require_owner=user_id,
            note=None,
        )

    @classmethod
    async def admin_create_refund_request(
        cls,
        admin_user: dict,
        order_id: str,
        refund_type: str,
        amount: Optional[int] = None,
        line_ids: Optional[List[str]] = None,
        reason: Optional[str] = None,
        note: Optional[str] = None,
    ) -> PaymentRefund:
        """Admin 代录退款申请（线下协商场景；代录人留痕，可手输协商金额）

        Raises:
            OrderNotFoundError / ValueError
        """
        reason = (reason or "").strip()
        if not reason:
            raise ValueError("代录退款必须填写申请事由")
        return await cls._create_request(
            order_id=order_id,
            refund_type=refund_type,
            line_ids=line_ids,
            requested_amount=amount,
            reason=reason,
            originated="admin",
            created_by_admin=str(admin_user.get("user_id")) if admin_user else None,
            require_owner=None,
            note=note,
        )

    @classmethod
    async def _create_request(
        cls,
        order_id: str,
        refund_type: str,
        line_ids: Optional[List[str]],
        requested_amount: Optional[int],
        reason: str,
        originated: str,
        created_by_admin: Optional[str],
        require_owner: Optional[str],
        note: Optional[str] = None,
    ) -> PaymentRefund:
        """申请落库共用路径（用户自提 / admin 代录）"""
        if refund_type not in ("full", "partial"):
            raise ValueError("退款类型仅支持 full / partial")

        async with AsyncSessionLocal() as db:
            order = await _get_order(db, order_id)
            if require_owner is not None and order.user_id != require_owner:
                raise OrderNotFoundError("订单不存在")
            applicant_id = order.user_id

            if order.status not in ("granted", "partially_refunded"):
                raise ValueError(f"订单当前状态不可申请退款（{order.status}）")
            if order.product_type == _PRODUCT_RENEWAL:
                raise ValueError(_ERR_RENEWAL)
            await _assert_no_in_flight(db, order.id)

            lines = await _order_refundable_lines(db, order)
            if not lines:
                raise ValueError("订单缺少可退明细，需人工核查")
            available = {line.id: line for line, s in lines if s == "available"}
            cap = sum(l.amount_paid_alloc for l in available.values())
            selected_lines: List[PaymentOrderLine] = []

            if refund_type == "full":
                # 全退：无可退项被使用（码已激活/消耗、咨询已预约 → 整单不可退）；
                # 已退过部分后全退剩余允许（行 refunded 不算被使用）。
                # 金额 = min(订单剩余可退, 可用行分摊实付)——历史审批曾下调
                # 金额时二者会偏离，取小者保证不超退
                if any(s == "used" for _, s in lines):
                    raise ValueError(
                        "订单内激活码已被使用或咨询已预约，不可整单退款（请走线下协商）"
                    )
                computed = min(_remaining_refundable(order), cap)
            else:
                # 部分退：仅年度套餐（按码折算）/ 咨询（协商金额）
                if not _supports_partial(order, len(lines)):
                    raise ValueError("该商品仅支持全额退款")
                if not line_ids:
                    raise ValueError("部分退款必须选择退款项")
                all_ids = {line.id for line, _ in lines}
                unknown = [i for i in line_ids if i not in all_ids]
                if unknown:
                    raise ValueError("退款项不存在")
                selected_lines = [available[i] for i in line_ids if i in available]
                if len(selected_lines) != len(line_ids):
                    raise ValueError("所选退款项已被使用，请刷新后重试")
                computed = sum(l.amount_paid_alloc for l in selected_lines)

            final_amount = requested_amount if requested_amount is not None else computed
            if originated != "admin" and final_amount != computed:
                raise ValueError("申请金额不合法")
            if final_amount < 0 or final_amount > cap:
                raise ValueError(f"申请金额超出可退上限（上限 ¥{_fen_to_yuan(cap)} 元）")
            if final_amount == 0 and cap > 0:
                raise ValueError("申请金额必须大于 0")

            refund = PaymentRefund(
                refund_no=await _next_refund_no(db, order.order_no),
                order_id=order.id,
                order_no=order.order_no,
                user_id=applicant_id,
                originated=originated,
                created_by_admin=created_by_admin,
                refund_type=refund_type,
                requested_amount=final_amount,
                reason_user=reason,
                reason_admin=(note or "").strip() or None,
                # partial：申请时即落所选行快照（批准时据此重验）
                line_snapshot=_line_snapshot_json(selected_lines) if selected_lines else None,
                status=REFUND_PENDING_REVIEW,
            )
            db.add(refund)
            await db.flush()

            user_email = await _get_user_email(db, applicant_id)
            await _notify_admins_inapp(
                db,
                title=NOTIFY_TITLE_ADMIN_REQUEST,
                content=(
                    f"订单 {order.order_no} 的用户（{user_email or applicant_id}）"
                    f"提交了{'全额' if refund_type == 'full' else '部分'}退款申请"
                    f"（¥{_fen_to_yuan(final_amount)}）：\n\n{reason[:200]}\n\n"
                    f"请在 admin 后台「退款审批」中处理。"
                ),
                exclude_user_id=applicant_id,
            )
            await db.commit()
            await db.refresh(refund)

        await _notify_admins_email(
            subject="【寻路·OpenLife】新退款申请待审批",
            body=(
                f"订单 {refund.order_no} 有新的退款申请（{refund.refund_no}）：\n"
                f"类型：{'全额' if refund.refund_type == 'full' else '部分'}退款\n"
                f"金额：¥{_fen_to_yuan(refund.requested_amount)}\n"
                f"理由：{reason[:500]}\n\n请登录 admin 后台处理。"
            ),
        )
        return refund

    @classmethod
    async def withdraw_refund_request(cls, user_id: str, refund_id: str) -> PaymentRefund:
        """用户撤回申请（仅本人 + 待审批）

        Raises:
            RefundNotFoundError / ValueError
        """
        async with AsyncSessionLocal() as db:
            refund = await _get_refund(db, refund_id)
            if refund.user_id != user_id:
                raise RefundNotFoundError("退款单不存在")
            if refund.status != REFUND_PENDING_REVIEW:
                raise ValueError(f"仅待审批的申请可撤回（当前状态：{refund.status}）")
            refund.status = REFUND_WITHDRAWN
            await db.commit()
            await db.refresh(refund)
            return refund

    @classmethod
    async def list_user_refunds(
        cls, user_id: str, page: int = 1, page_size: int = 20
    ) -> Tuple[List[Dict[str, Any]], int]:
        """我的退款申请列表（按申请时间倒序）"""
        async with AsyncSessionLocal() as db:
            count_q = select(func.count()).select_from(PaymentRefund).where(
                PaymentRefund.user_id == user_id
            )
            total = (await db.execute(count_q)).scalar() or 0
            rows = (
                await db.execute(
                    select(PaymentRefund)
                    .where(PaymentRefund.user_id == user_id)
                    .order_by(PaymentRefund.created_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).scalars().all()
            return [refund_to_dict(r) for r in rows], total

    @classmethod
    async def get_user_refund(cls, user_id: str, refund_id: str) -> Dict[str, Any]:
        """退款单详情（仅本人）"""
        async with AsyncSessionLocal() as db:
            refund = await _get_refund(db, refund_id)
            if refund.user_id != user_id:
                raise RefundNotFoundError("退款单不存在")
            return refund_to_dict(refund)

    # ─── Admin：列表 / 详情 / 审批 / 驳回 / 重试 ───────────────

    @classmethod
    async def admin_list_refunds(
        cls,
        status: Optional[str] = None,
        order_no: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Admin 退款单列表（状态/订单号筛选 + 分页，含用户邮箱）"""
        async with AsyncSessionLocal() as db:
            q = select(PaymentRefund, User.email).join(User, PaymentRefund.user_id == User.id)
            count_q = select(func.count()).select_from(PaymentRefund)
            if status:
                q = q.where(PaymentRefund.status == status)
                count_q = count_q.where(PaymentRefund.status == status)
            if order_no:
                q = q.where(PaymentRefund.order_no == order_no)
                count_q = count_q.where(PaymentRefund.order_no == order_no)
            total = (await db.execute(count_q)).scalar() or 0
            rows = (
                await db.execute(
                    q.order_by(PaymentRefund.created_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
            items = []
            for refund, user_email in rows:
                item = refund_to_dict(refund)
                item["user_email"] = user_email
                items.append(item)
            return items, total

    @classmethod
    async def admin_get_refund(cls, refund_id: str) -> Dict[str, Any]:
        """Admin 退款单详情（完整审批留痕 + 订单 + 用户邮箱 + 实时行状态）"""
        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    select(PaymentRefund, User.email, PaymentOrder)
                    .join(User, PaymentRefund.user_id == User.id)
                    .join(PaymentOrder, PaymentRefund.order_id == PaymentOrder.id)
                    .where(PaymentRefund.id == refund_id)
                )
            ).first()
            if not row:
                raise RefundNotFoundError("退款单不存在")
            refund, user_email, order = row
            item = refund_to_dict(refund)
            item["user_email"] = user_email
            item["order"] = {
                "id": order.id,
                "order_no": order.order_no,
                "product_type": order.product_type,
                "amount_paid": order.amount_paid,
                "amount_refunded": order.amount_refunded or 0,
                "status": order.status,
                "coupon_id": order.coupon_id,
            }
            # 实时行状态（审批参考：申请后码可能已被用）
            lines = await _order_refundable_lines(db, order)
            await db.commit()  # 惰性回填的明细行落库
            item["order_lines"] = [
                {
                    "id": line.id,
                    "line_no": line.line_no,
                    "item_type": line.item_type,
                    "item_ref": line.item_ref,
                    "amount_paid_alloc": line.amount_paid_alloc,
                    "db_status": line.status,
                    "effective_status": eff,
                }
                for line, eff in lines
            ]
            return item

    @classmethod
    async def approve_refund(
        cls,
        admin_user: dict,
        refund_id: str,
        approved_amount: Optional[int] = None,
        note: Optional[str] = None,
    ) -> PaymentRefund:
        """批准并执行退款（一个动作：批准 → 同步渠道 → 状态联动）

        Args:
            approved_amount: 批准金额（分，不传 = 申请额；只能 ≤ 实时上限，
                与申请额不一致必填 note 金额调整理由）
            note: 审批意见 / 金额调整理由

        Raises:
            RefundNotFoundError / ValueError（状态或守卫不符）
            PaymentChannelError: 渠道退款失败（单据置 failed，可重试）
        """
        admin_id = str(admin_user.get("user_id")) if admin_user else None
        note = (note or "").strip() or None

        # 事务 A：锁定申请 + 实时重验（不信任申请时快照）
        async with AsyncSessionLocal() as db:
            refund = await _get_refund(db, refund_id, for_update=True)
            if refund.status != REFUND_PENDING_REVIEW:
                raise ValueError(f"退款单当前状态不可审批（{refund.status}）")
            order = await _get_order(db, refund.order_id)
            if order.status not in ("granted", "partially_refunded"):
                raise ValueError(f"订单当前状态不可退款（{order.status}）")

            lines = await _order_refundable_lines(db, order)
            available = {line.id: line for line, s in lines if s == "available"}
            has_remaining = _remaining_refundable(order) > 0

            # 批准行集合：partial = 申请所选行 ∩ 仍可用；full = 当前全部可用行
            if refund.refund_type == "full":
                approved_lines = list(available.values())
                if has_remaining and not approved_lines:
                    raise ValueError("订单内可退项已全部被使用，不可退款（请驳回并走线下协商）")
            else:
                requested_ids = _snapshot_line_ids(refund)
                approved_lines = [available[i] for i in requested_ids if i in available]
                if has_remaining and not approved_lines:
                    raise ValueError("所选退款项已被使用，不可退款（请驳回并走线下协商）")

            cap = min(
                sum(l.amount_paid_alloc for l in approved_lines),
                _remaining_refundable(order),
            )
            final_amount = (
                approved_amount if approved_amount is not None else refund.requested_amount
            )
            if final_amount < 0 or final_amount > cap:
                raise ValueError(
                    f"批准金额超出实时可退上限（上限 ¥{_fen_to_yuan(cap)}；"
                    "所选退款项可能已被使用）"
                )
            if final_amount != refund.requested_amount and not note:
                raise ValueError("批准金额与申请金额不一致，必须填写调整理由")
            if final_amount == 0 and cap > 0:
                raise ValueError("批准金额必须大于 0（如不退款请驳回）")

            refund.status = REFUND_REFUNDING
            refund.approved_amount = final_amount
            refund.reason_admin = note or refund.reason_admin
            refund.reviewed_by = admin_id
            refund.reviewed_at = _utcnow()
            # 批准时重落快照 = 最终批准行集合（审计：批准时点的行选择）
            refund.line_snapshot = _line_snapshot_json(approved_lines)
            await db.commit()

        executed = await cls._execute_refund(refund_id)

        # 用户站内信/邮件：审批结果（批准金额 + 到账说明）
        async with AsyncSessionLocal() as db:
            order = await _get_order(db, executed.order_id)
            await _notify_user_inapp(
                db,
                executed.user_id,
                NOTIFY_TITLE_APPROVED,
                content=(
                    f"您的退款申请（{executed.refund_no}，订单 {order.order_no}）已批准，"
                    f"金额 ¥{_fen_to_yuan(executed.approved_amount or 0)}，"
                    "将原路退回支付账户。"
                ),
            )
            await db.commit()
        await _notify_user_email(
            executed.user_id,
            subject="【寻路·OpenLife】退款申请已批准",
            body=(
                f"您好，\n\n您的退款申请已批准：\n\n"
                f"订单号：{executed.order_no}\n退款单号：{executed.refund_no}\n"
                f"批准金额：¥{_fen_to_yuan(executed.approved_amount or 0)}\n"
                f"审批意见：{executed.reason_admin or '—'}\n\n"
                f"款项将原路退回，到账时间以支付渠道为准。\n\n—— 寻路·OpenLife"
            ),
        )
        return executed

    @classmethod
    async def retry_refund(cls, admin_user: dict, refund_id: str) -> PaymentRefund:
        """失败重试（复用同 refund_no，渠道幂等不会重复退）

        Raises:
            RefundNotFoundError / ValueError / PaymentChannelError
        """
        async with AsyncSessionLocal() as db:
            refund = await _get_refund(db, refund_id, for_update=True)
            if refund.status != REFUND_FAILED:
                raise ValueError(f"仅失败状态可重试（当前状态：{refund.status}）")
            refund.status = REFUND_REFUNDING
            refund.failed_reason = None
            await db.commit()
        return await cls._execute_refund(refund_id)

    @classmethod
    async def reject_refund(cls, admin_user: dict, refund_id: str, note: str) -> PaymentRefund:
        """驳回申请（必填理由，用户可见）

        Raises:
            RefundNotFoundError / ValueError
        """
        note = (note or "").strip()
        if not note:
            raise ValueError("驳回必须填写理由")
        async with AsyncSessionLocal() as db:
            refund = await _get_refund(db, refund_id, for_update=True)
            if refund.status != REFUND_PENDING_REVIEW:
                raise ValueError(f"退款单当前状态不可驳回（{refund.status}）")
            refund.status = REFUND_REJECTED
            refund.reason_admin = note
            refund.reviewed_by = str(admin_user.get("user_id")) if admin_user else None
            refund.reviewed_at = _utcnow()
            user_id = refund.user_id
            refund_no = refund.refund_no
            order_no = refund.order_no
            await _notify_user_inapp(
                db,
                user_id,
                NOTIFY_TITLE_REJECTED,
                content=f"您的退款申请（{refund_no}，订单 {order_no}）已被驳回：{note}",
            )
            await db.commit()
            await db.refresh(refund)

        await _notify_user_email(
            user_id,
            subject="【寻路·OpenLife】退款申请已驳回",
            body=(
                f"您好，\n\n您的退款申请（{refund_no}，订单 {order_no}）已被驳回：\n"
                f"{note}\n\n如有疑问请通过反馈渠道与我们联系。\n\n—— 寻路·OpenLife"
            ),
        )
        return refund

    # ─── 执行与状态联动 ────────────────────────────────────────

    @classmethod
    async def _execute_refund(cls, refund_id: str) -> PaymentRefund:
        """执行渠道退款 + 成功联动（approve / retry 共用）

        渠道调用在 DB 事务外（refunding 已先行落库，并发执行有状态门闩）；
        成功后事务 B 原子联动：退款单 succeeded → 订单 amount_refunded/
        status/refunded_at → 行 refunded → 用户站内信；事务外作废码、
        （整单退完）退回券、发送到账邮件。
        渠道或联动失败：单据置 failed + admin 站内信告警，异常上抛（路由转 502），
        重试复用同 refund_no（渠道幂等不会多退）。
        """
        # 预读执行参数（渠道调用不占 DB 事务）
        async with AsyncSessionLocal() as db:
            refund = await _get_refund(db, refund_id)
            if refund.status != REFUND_REFUNDING:
                raise ValueError(f"退款单当前状态不可执行（{refund.status}）")
            order = await _get_order(db, refund.order_id)
            amount = refund.approved_amount or 0
            refund_no = refund.refund_no
            order_no = order.order_no
            channel_name = order.channel
            user_id = refund.user_id

        # 渠道退款（0 元单无真实支付，跳过渠道调用）
        channel_response: Optional[str] = None
        executed_at = _utcnow()
        if amount > 0:
            channel = get_channel(channel_name)
            try:
                channel_response = await channel.refund(
                    order_no=order_no, amount_fen=amount, refund_no=refund_no
                )
            except Exception as e:
                # 渠道失败：置 failed + admin 告警，异常上抛（路由转 502）
                logger.error("渠道退款失败：refund_no=%s err=%s", refund_no, e)
                await cls._mark_failed_and_notify(refund_id, f"渠道退款失败：{e}")
                raise

        try:
            # 事务 B：成功联动（原子）
            async with AsyncSessionLocal() as db:
                refund = await _get_refund(db, refund_id, for_update=True)
                if refund.status != REFUND_REFUNDING:
                    logger.warning(
                        "退款执行跳过（状态已被并发处理）：refund_no=%s status=%s",
                        refund_no,
                        refund.status,
                    )
                    await db.rollback()
                    return refund

                order = await _get_order(db, refund.order_id)
                snapshot_ids = set(_snapshot_line_ids(refund))

                refund.status = REFUND_SUCCEEDED
                refund.executed_at = executed_at
                refund.succeeded_at = _utcnow()
                refund.channel_response = channel_response

                # 订单联动：累计退款 + 状态迁移
                # 终态（refunded）判定：累计退满实付（金额口径不变式：
                # refunded ⇔ amount_refunded == amount_paid；协商下调退完所有行
                # 但累计 < 实付时维持 partially_refunded——如实反映"退过部分"）
                order.amount_refunded = (order.amount_refunded or 0) + amount

                # 行联动：批准行集合 → refunded；收集作废码 / 预约单
                lines = (
                    (
                        await db.execute(
                            select(PaymentOrderLine).where(PaymentOrderLine.order_id == order.id)
                        )
                    )
                    .scalars()
                    .all()
                )
                revoked_codes: List[str] = []
                booking_ids: List[str] = []
                now = _utcnow()
                for line in lines:
                    if line.id in snapshot_ids:
                        line.status = "refunded"
                        line.refunded_at = now
                        if line.item_type == LINE_ITEM_CODE and line.item_ref:
                            revoked_codes.append(line.item_ref)
                        if line.item_type == LINE_ITEM_CONSULTATION and line.item_ref:
                            booking_ids.append(line.item_ref)

                fully_refunded = order.amount_refunded >= order.amount_paid
                if fully_refunded:
                    order.status = "refunded"
                    order.refunded_at = _utcnow()
                else:
                    order.status = "partially_refunded"

                # 咨询退款（全额或协商部分）：预约单取消
                for booking_id in booking_ids:
                    booking = (
                        await db.execute(
                            select(ConsultationBooking).where(
                                ConsultationBooking.id == booking_id
                            )
                        )
                    ).scalar_one_or_none()
                    if booking is not None:
                        booking.status = "cancelled"

                await _notify_user_inapp(
                    db,
                    user_id,
                    NOTIFY_TITLE_SUCCEEDED,
                    content=(
                        f"您的退款（{refund_no}，订单 {order_no}，"
                        f"¥{_fen_to_yuan(amount)}）已原路退回，请留意到账。"
                    ),
                )
                coupon_id = order.coupon_id
                await db.commit()

            # 作废码（渠道已退款，失败仅记日志人工兜底）
            for code in revoked_codes:
                try:
                    mgr, _rec = get_activation_with_manager(code)
                    if mgr:
                        mgr.update_status([code], "revoked", actor={"user_id": "system:refund"})
                except Exception as e:  # noqa: BLE001
                    logger.error(
                        "退款作废码失败（需人工核查）：refund_no=%s code=%s err=%s",
                        refund_no,
                        code,
                        e,
                    )
            if revoked_codes:
                logger.info(
                    "退款完成，交付码已作废：refund_no=%s codes=%s", refund_no, revoked_codes
                )

            # 整单退完 → 退回券（按订单核销行回退，多次券减名额；失败不阻断）
            if coupon_id and fully_refunded:
                try:
                    await CouponService.return_coupon_on_refund(coupon_id, refund.order_id)
                except ValueError as e:
                    logger.error(
                        "退款退券失败（订单已退款，需人工核查）：order=%s coupon=%s err=%s",
                        refund.order_id,
                        coupon_id,
                        e,
                    )

            await _notify_user_email(
                user_id,
                subject="【寻路·OpenLife】退款已到账",
                body=(
                    f"您好，\n\n您的退款已成功原路退回：\n\n"
                    f"订单号：{order_no}\n退款单号：{refund_no}\n"
                    f"退款金额：¥{_fen_to_yuan(amount)}\n\n"
                    f"到账时间以支付渠道为准（通常 1~7 个工作日）。\n\n—— 寻路·OpenLife"
                ),
            )
            async with AsyncSessionLocal() as db:
                return await _get_refund(db, refund_id)

        except Exception as e:
            # 渠道已退但联动失败（极端）：置 failed 供重试（同 refund_no 幂等不会多退）
            logger.error("退款联动失败（置 failed 供重试）：refund_no=%s err=%s", refund_no, e)
            await cls._mark_failed_and_notify(
                refund_id, f"退款后处理失败（渠道侧以 refund_no 幂等，可安全重试）：{e}"
            )
            raise

    @classmethod
    async def _mark_failed_and_notify(cls, refund_id: str, reason: str) -> None:
        """退款单置 failed + admin 站内信告警（仅 refunding 态才迁移）"""
        async with AsyncSessionLocal() as db:
            refund = await _get_refund(db, refund_id, for_update=True)
            if refund.status != REFUND_REFUNDING:
                return
            refund.status = REFUND_FAILED
            refund.failed_reason = reason
            await _notify_admins_inapp(
                db,
                title=NOTIFY_TITLE_FAILED_ADMIN,
                content=(
                    f"退款单 {refund.refund_no}（订单 {refund.order_no}）执行失败：{reason}\n"
                    f"请核查后重试（渠道幂等，不会重复退款）。"
                ),
            )
            await db.commit()


async def _next_refund_no(db: AsyncSession, order_no: str) -> str:
    """退款单号 = order_no + "R" + 3 位序号（渠道幂等号，事务内取号）"""
    count = (
        await db.execute(
            select(func.count())
            .select_from(PaymentRefund)
            .where(PaymentRefund.order_no == order_no)
        )
    ).scalar() or 0
    return f"{order_no}R{count + 1:03d}"
