"""
订单明细行服务（2026-10-05 退款系统）

设计依据：wiki/开发文档/10-05/订单系统退款设计.md 第 2.2 节。
职责：
1. allocate_equal：等额分摊算法（尾差归最后一行，Σ == 总额）
2. ensure_order_lines：交付（granted）时生成明细行并落库分摊；存量 granted
   订单首次访问退款能力时惰性回填（幂等，已有行直接返回）
3. line_effective_status：行当前有效状态 = DB 持久状态 + 关联实体实时状态
   （码被激活/预约被排期等竞态在查询/审批时实时重验，不回写 DB 列）

分摊口径：同单内各行商品等价 → 原价/优惠/实付均按行数等分、尾差归最后一行；
不变式：Σ price_original_alloc == amount_original，Σ coupon_alloc ==
amount_discount（优惠合计：会员折扣 + 券），Σ amount_paid_alloc == amount_paid。
本平台单一卖家，无平台券/商家券拆分；券面额超折后价时各行实付为 0（不为负）。

行状态（DB 持久，仅退款驱动流转）：
- available 生成时未动，可退
- used     生成时即已被用（码已激活/消耗、咨询已排期、延期交付即已用）
- refunded 已随退款作废
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import (
    ConsultationBooking,
    PaymentOrder,
    PaymentOrderLine,
)
from app.utils.simple_activation_manager import get_activation_with_manager

logger = logging.getLogger(__name__)

# 行商品类型
LINE_ITEM_CODE = "code"
LINE_ITEM_CONSULTATION = "consultation_service"
LINE_ITEM_RENEWAL = "renewal_service"

# 咨询行可退的预约状态（未预约：pending_survey 问卷未填 / submitted 问卷已填未排期）
_CONSULTATION_REFUNDABLE_BOOKING_STATUSES = ("pending_survey", "submitted")

# 订单状态 → 行生成门槛（仅已交付的订单有行；refunded 订单不可再退，不回填）
_LINE_GENERATABLE_STATUSES = ("granted", "partially_refunded")


def allocate_equal(total: int, n: int) -> List[int]:
    """总额等分到 n 行，尾差归最后一行（Σ == total；total 可为 0）"""
    if n <= 0:
        raise ValueError(f"分摊行数必须为正整数：{n}")
    base, rem = divmod(total, n)
    parts = [base] * n
    parts[-1] += rem
    return parts


def _parse_meta(raw: Optional[str]) -> dict:
    """订单 meta JSON → dict（容错，与 PaymentService._parse_meta 同口径）"""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def _order_codes(order: PaymentOrder, meta: dict) -> List[str]:
    """套餐订单交付码列表（新 meta.codes + 兼容旧 gift_codes/delivered_code，去重）

    与 PaymentService._package_order_codes 同口径；本模块独立实现避免
    与 payment_service 顶层互导入（payment_service 顶层 import 本模块）。
    """
    codes: List[str] = []
    for raw in list(meta.get("codes") or []) + list(meta.get("gift_codes") or []):
        code = (raw or "").strip().upper()
        if code and code not in codes:
            codes.append(code)
    delivered = (order.delivered_code or "").strip().upper()
    if delivered and delivered not in codes:
        codes.append(delivered)
    return codes


def _code_initial_status(code: Optional[str]) -> str:
    """生成/回填时码行初始状态：码未绑定且 active → available，否则 used"""
    if not code:
        return "used"
    try:
        _, rec = get_activation_with_manager(code)
    except Exception as e:
        logger.warning("查询激活码状态失败（行置 used，需人工核查）：code=%s err=%s", code, e)
        return "used"
    if rec is None:
        return "used"
    if not rec.owner_user_id and rec.status == "active":
        return "available"
    return "used"


async def _booking_initial_status(db: AsyncSession, booking_id: Optional[str]) -> str:
    """生成/回填时咨询行初始状态：未预约 → available，已排期/已完成/无预约单 → used"""
    if not booking_id:
        return "used"
    booking = (
        await db.execute(
            select(ConsultationBooking).where(ConsultationBooking.id == booking_id)
        )
    ).scalar_one_or_none()
    if booking is None:
        logger.warning("咨询预约单不存在（行置 used，需人工核查）：booking_id=%s", booking_id)
        return "used"
    return "available" if booking.status in _CONSULTATION_REFUNDABLE_BOOKING_STATUSES else "used"


async def ensure_order_lines(
    db: AsyncSession, order: PaymentOrder, source: str = "backfill"
) -> List[PaymentOrderLine]:
    """幂等生成订单明细行（交付时调用；存量 granted 订单惰性回填）

    - 已有行：直接返回（按 line_no 升序）
    - 订单未交付（非 granted/partially_refunded）：返回空列表不生成
    - 行实体：套餐=交付码（季度 1 行 / 年度 3 行）、延期=目标码（used）、
      咨询=预约单、旧 SKU=交付码
    - 分摊：allocate_equal 三连（原价/优惠/实付），尾差归最后一行

    Args:
        source: 生成来源（delivery 交付路径 / backfill 存量回填），仅用于日志审计
    """
    existing = (
        (
            await db.execute(
                select(PaymentOrderLine)
                .where(PaymentOrderLine.order_id == order.id)
                .order_by(PaymentOrderLine.line_no)
            )
        )
        .scalars()
        .all()
    )
    if existing:
        return list(existing)
    if order.status not in _LINE_GENERATABLE_STATUSES:
        return []

    meta = _parse_meta(order.meta)
    # 行定义：(item_type, item_ref, initial_status)
    rows: List[Tuple[str, Optional[str], str]] = []
    if order.product_type in ("quarterly_package", "annual_package"):
        for code in _order_codes(order, meta):
            rows.append((LINE_ITEM_CODE, code, _code_initial_status(code)))
    elif order.product_type == "renewal":
        # 延期交付即已用（不可退），生成即 used，保证行口径完整
        target = (meta.get("target_code") or "").strip().upper() or None
        rows.append((LINE_ITEM_RENEWAL, target, "used"))
    elif order.product_type == "consultation":
        booking_id = (meta.get("booking_id") or None)
        rows.append(
            (LINE_ITEM_CONSULTATION, booking_id, await _booking_initial_status(db, booking_id))
        )
    else:  # 旧 SKU（activation_code，已下架，历史订单兼容）
        code = (order.delivered_code or "").strip().upper() or None
        rows.append((LINE_ITEM_CODE, code, _code_initial_status(code) if code else "used"))

    if not rows:
        logger.warning("订单无可生成的明细行实体（需人工核查）：order_no=%s", order.order_no)
        return []

    n = len(rows)
    originals = allocate_equal(order.amount_original, n)
    discounts = allocate_equal(order.amount_discount, n)  # 优惠合计（会员折扣+券）
    paids = allocate_equal(order.amount_paid, n)

    lines = [
        PaymentOrderLine(
            order_id=order.id,
            line_no=i + 1,
            item_type=item_type,
            item_ref=item_ref,
            price_original_alloc=originals[i],
            coupon_alloc=discounts[i],
            amount_paid_alloc=paids[i],
            status=initial_status,
        )
        for i, (item_type, item_ref, initial_status) in enumerate(rows)
    ]
    db.add_all(lines)
    logger.info(
        "订单明细行已生成：order_no=%s source=%s lines=%d statuses=%s",
        order.order_no,
        source,
        n,
        [s for _, _, s in rows],
    )
    return lines


async def line_effective_status(db: AsyncSession, line: PaymentOrderLine) -> str:
    """行当前有效状态：DB 持久状态 + 关联实体实时状态（查询/审批时重验）

    - DB 已 refunded/used → 原样返回（不可退）
    - code 行：码已绑定/已消耗/已过期/已作废 → used（竞态兜底）
    - 咨询行：预约已排期/已完成/已取消 → used
    - 延期行：恒 used
    """
    if line.status != "available":
        return line.status
    if line.item_type == LINE_ITEM_CODE:
        if not line.item_ref:
            return "used"
        try:
            _, rec = get_activation_with_manager(line.item_ref)
        except Exception as e:
            logger.warning(
                "查询激活码状态失败（行视为 used，需人工核查）：code=%s err=%s",
                line.item_ref,
                e,
            )
            return "used"
        if rec is not None and not rec.owner_user_id and rec.status == "active":
            return "available"
        return "used"
    if line.item_type == LINE_ITEM_CONSULTATION:
        if not line.item_ref:
            return "used"
        booking = (
            await db.execute(
                select(ConsultationBooking).where(ConsultationBooking.id == line.item_ref)
            )
        ).scalar_one_or_none()
        if booking is not None and booking.status in _CONSULTATION_REFUNDABLE_BOOKING_STATUSES:
            return "available"
        return "used"
    return "used"  # renewal_service 恒不可退
