"""
Admin 支付管理 API（P1：折扣券管理；P2a：订单管理；2026-10-05 退款审批）

接口：
- GET    /admin/coupons          分页列表（status 过滤含派生态 expired/suspended/void；
                                  used 态联查邮箱/订单号；多次券带 max_uses/used_count/locked_count）
- POST   /admin/coupons          单个/批量创建（固定面额，分；ttl_days 可选，默认读运行时配置；
                                  max_uses 总核销次数 1-10000，>1 为共享促销码，禁绑归属）
- PATCH  /admin/coupons/{id}     调整面额/有效期（仅 unused，含派生 expired——改期即复活）
- DELETE /admin/coupons/{id}     作废（仅 unused 且无核销/锁定记录；软删除置 void，可恢复）
- POST   /admin/coupons/{id}/restore  恢复已作废券（void → unused）
- POST   /admin/coupons/{id}/suspend  停用（剩余名额冻结，已核销保留有效）
- POST   /admin/coupons/{id}/resume   启用（解除停用，剩余名额恢复可用）
- GET    /admin/coupon-config    读折扣券默认有效期（天）
- POST   /admin/coupon-config    调整默认有效期（1-3650 天，即时生效，只影响新券）
- GET    /admin/payment/orders           订单分页列表（status/channel 筛选，含 user_email + code_refundable）
- GET    /admin/payment/orders/{id}      订单详情（完整字段 + user_email + code_refundable + delivered_codes 去向）
- GET    /admin/payment/refunds          退款单分页列表（status/order_no 筛选，含审批留痕）
- GET    /admin/payment/refunds/{id}     退款单详情（行快照 + 实时行状态 + 订单 + 用户邮箱）
- POST   /admin/payment/refunds          代录退款申请（线下协商场景，代录人留痕）
- POST   /admin/payment/refunds/{id}/approve  批准并执行（可下调金额，调整必填理由）
- POST   /admin/payment/refunds/{id}/reject   驳回（必填理由，用户可见）
- POST   /admin/payment/refunds/{id}/retry    失败重试（同 refund_no 渠道幂等）

全部 is_super_admin_user 门控，统一响应 {code, message, data}。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.v1.auth import get_current_user
from app.core.payment.base import PaymentChannelError
from app.services import coupon_config
from app.services.coupon_service import CouponService
from app.services.payment_service import OrderNotFoundError, PaymentService
from app.services.refund_service import RefundNotFoundError, RefundService, refund_to_dict
from app.utils.super_admin import is_super_admin_user

router = APIRouter(prefix="/admin", tags=["Admin-Payment"])


def _ok(data: Any) -> Dict[str, Any]:
    return {"code": 200, "message": "success", "data": data}


def _require_super_admin(current_user: Optional[dict]) -> None:
    if not is_super_admin_user(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")


# ===================== Schemas =====================


class CouponCreateRequest(BaseModel):
    """创建折扣券请求"""

    amount: int = Field(..., gt=0, description="面额（分，>0）")
    count: int = Field(1, ge=1, le=500, description="批量创建数量（1-500）")
    ttl_days: Optional[int] = Field(
        None,
        ge=coupon_config.MIN_TTL_DAYS,
        le=coupon_config.MAX_TTL_DAYS,
        description="有效期天数（可选，默认读运行时配置）",
    )
    max_uses: int = Field(
        1,
        ge=1,
        le=10000,
        description="总核销次数（1-10000；1=单次券，>1=共享促销码：任何用户先到先得，"
        "每账号限用一次，面额×次数=总补贴）",
    )


class CouponUpdateRequest(BaseModel):
    """调整券请求（面额/有效期至少传一个）"""

    amount: Optional[int] = Field(None, gt=0, description="新面额（分，>0）")
    expires_at: Optional[datetime] = Field(None, description="新过期时间（ISO8601，改期即复活）")


class CouponConfigRequest(BaseModel):
    """调整折扣券默认有效期请求"""

    default_ttl_days: int = Field(
        ...,
        ge=coupon_config.MIN_TTL_DAYS,
        le=coupon_config.MAX_TTL_DAYS,
        description="默认有效期天数（1-3650）",
    )


class AdminRefundCreateRequest(BaseModel):
    """代录退款申请请求（线下协商场景）"""

    order_id: str = Field(..., min_length=1, description="订单 ID")
    refund_type: str = Field(..., description="退款类型（full / partial）")
    amount: Optional[int] = Field(
        None, ge=0, description="代录金额（分，可选；不传按规则计算上限）"
    )
    line_ids: Optional[List[str]] = Field(
        None, description="部分退所选行 ID（refund-options.lines[].id）"
    )
    reason: str = Field(..., min_length=1, description="申请事由（必填）")
    note: Optional[str] = Field(None, description="代录备注（写入审批意见栏）")


class AdminRefundApproveRequest(BaseModel):
    """批准退款请求"""

    approved_amount: Optional[int] = Field(
        None, ge=0, description="批准金额（分，不传=申请额；只能 ≤ 实时可退上限）"
    )
    note: Optional[str] = Field(None, description="审批意见 / 金额调整理由（与申请额不一致时必填）")


class AdminRefundRejectRequest(BaseModel):
    """驳回退款请求"""

    note: str = Field(..., min_length=1, description="驳回理由（用户可见）")


# ===================== 路由 =====================


@router.get("/coupons")
async def list_coupons(
    status: Optional[str] = Query(
        None, description="unused | locked | used | expired | suspended | void"
    ),
    source: Optional[str] = Query(None, description="admin | email_auto"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """分页查询折扣券列表"""
    _require_super_admin(current_user)
    items, total = await CouponService.list_coupons(
        status=status, page=page, page_size=page_size, source=source
    )
    return _ok({"items": items, "total": total, "page": page, "page_size": page_size})


@router.post("/coupons")
async def create_coupons(
    payload: CouponCreateRequest,
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """创建折扣券（单个/批量，固定面额；max_uses>1 为共享促销码）"""
    _require_super_admin(current_user)
    try:
        coupons = await CouponService.create_coupons(
            amount=payload.amount,
            count=payload.count,
            source="admin",
            created_by=str(current_user.get("user_id")) if current_user else None,
            ttl_days=payload.ttl_days,
            max_uses=payload.max_uses,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _ok(
        {
            "created": [
                {
                    "id": c.id,
                    "code": c.code,
                    "amount": c.amount,
                    "max_uses": c.max_uses,
                    "expires_at": c.expires_at.isoformat() if c.expires_at else None,
                }
                for c in coupons
            ]
        }
    )


@router.patch("/coupons/{coupon_id}")
async def update_coupon(
    coupon_id: str,
    payload: CouponUpdateRequest,
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """调整券面额/有效期（仅 unused，含派生 expired——改期即复活；至少传一个字段）"""
    _require_super_admin(current_user)
    if payload.amount is None and payload.expires_at is None:
        raise HTTPException(status_code=400, detail="amount 与 expires_at 至少传一个")
    try:
        coupon = None
        if payload.amount is not None:
            coupon = await CouponService.update_coupon_amount(coupon_id, payload.amount)
        if payload.expires_at is not None:
            coupon = await CouponService.update_coupon_expiry(coupon_id, payload.expires_at)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _ok(
        {
            "id": coupon.id,
            "code": coupon.code,
            "amount": coupon.amount,
            "expires_at": coupon.expires_at.isoformat() if coupon.expires_at else None,
        }
    )


@router.delete("/coupons/{coupon_id}")
async def delete_coupon(
    coupon_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """作废券（仅 unused，含派生 expired；软删除置 void，可恢复）"""
    _require_super_admin(current_user)
    try:
        await CouponService.delete_coupon(coupon_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _ok({"id": coupon_id, "voided": True})


@router.post("/coupons/{coupon_id}/restore")
async def restore_coupon(
    coupon_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """恢复已作废券（void → unused；已过有效期的恢复后为 expired 派生态，可再改期）"""
    _require_super_admin(current_user)
    try:
        coupon = await CouponService.restore_coupon(coupon_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _ok({"id": coupon.id, "code": coupon.code, "status": coupon.status})


@router.post("/coupons/{coupon_id}/suspend")
async def suspend_coupon(
    coupon_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """停用券（停机开关）：已核销名额保持有效，剩余名额立即冻结，可 resume 恢复。

    适用：共享促销码面额配错/活动提前结束等运营纠错（作废要求无核销记录，
    部分核销的券只能停用）。
    """
    _require_super_admin(current_user)
    try:
        coupon = await CouponService.suspend_coupon(coupon_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _ok({"id": coupon.id, "code": coupon.code, "suspended": True})


@router.post("/coupons/{coupon_id}/resume")
async def resume_coupon(
    coupon_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """启用券：解除停用，剩余名额恢复可用（已过期则自然派生 expired）"""
    _require_super_admin(current_user)
    try:
        coupon = await CouponService.resume_coupon(coupon_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _ok({"id": coupon.id, "code": coupon.code, "suspended": False})


@router.get("/coupon-config")
async def get_coupon_config(
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """读折扣券默认有效期（天）"""
    _require_super_admin(current_user)
    return _ok(
        {
            "default_ttl_days": coupon_config.get_default_ttl_days(),
            "fallback": coupon_config.DEFAULT_COUPON_TTL_DAYS,
            "min": coupon_config.MIN_TTL_DAYS,
            "max": coupon_config.MAX_TTL_DAYS,
        }
    )


@router.post("/coupon-config")
async def set_coupon_config(
    payload: CouponConfigRequest,
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """调整折扣券默认有效期（即时生效，只影响之后新创建的券）"""
    _require_super_admin(current_user)
    try:
        coupon_config.set_default_ttl_days(payload.default_ttl_days)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _ok({"default_ttl_days": coupon_config.get_default_ttl_days()})


# ===================== 订单管理（P2a）=====================


@router.get("/payment/orders")
async def list_payment_orders(
    status: Optional[str] = Query(
        None, description="pending | paid | granted | closed | cancelled | refunding | refunded"
    ),
    channel: Optional[str] = Query(None, description="alipay | wechat"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """订单分页列表（item = OrderItem + user_email + code_refundable）"""
    _require_super_admin(current_user)
    items, total = await PaymentService.admin_list_orders(
        status=status, channel=channel, page=page, page_size=page_size
    )
    return _ok({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/payment/orders/{order_id}")
async def get_payment_order(
    order_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """订单详情（完整字段 + user_email + code_refundable + delivered_codes 去向）"""
    _require_super_admin(current_user)
    try:
        data = await PaymentService.admin_get_order(order_id)
    except OrderNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _ok(data)


@router.post("/payment/orders/{order_id}/refund")
async def refund_payment_order(
    order_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """【已废弃 2026-10-05】旧直接退款接口：请改用统一退款申请单流程

    兼容期保留此路由但直接拒绝，避免旧客户端静默走非审计路径。
    """
    _require_super_admin(current_user)
    raise HTTPException(
        status_code=410,
        detail="直接退款接口已下线：请用 POST /admin/payment/refunds 代录申请，"
        "再 POST /admin/payment/refunds/{id}/approve 审批执行",
    )


# ===================== 退款审批（2026-10-05）=====================


@router.get("/payment/refunds")
async def list_payment_refunds(
    status: Optional[str] = Query(
        None,
        description="pending_review | refunding | succeeded | failed | rejected | withdrawn",
    ),
    order_no: Optional[str] = Query(None, description="按商户订单号精确筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """退款单分页列表（含用户邮箱与完整审批留痕）"""
    _require_super_admin(current_user)
    items, total = await RefundService.admin_list_refunds(
        status=status, order_no=order_no, page=page, page_size=page_size
    )
    return _ok({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/payment/refunds/{refund_id}")
async def get_payment_refund(
    refund_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """退款单详情（行快照 + 实时行状态 + 订单信息 + 用户邮箱）"""
    _require_super_admin(current_user)
    try:
        data = await RefundService.admin_get_refund(refund_id)
    except RefundNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _ok(data)


@router.post("/payment/refunds")
async def create_payment_refund(
    payload: AdminRefundCreateRequest,
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """代录退款申请（线下协商场景；originated=admin + 代录人留痕）"""
    _require_super_admin(current_user)
    try:
        refund = await RefundService.admin_create_refund_request(
            admin_user=current_user or {},
            order_id=payload.order_id,
            refund_type=payload.refund_type,
            amount=payload.amount,
            line_ids=payload.line_ids,
            reason=payload.reason,
            note=payload.note,
        )
    except (ValueError, OrderNotFoundError, RuntimeError, PaymentChannelError) as e:
        _raise_refund_service_error(e)
    return _ok({"refund": refund_to_dict(refund)})


@router.post("/payment/refunds/{refund_id}/approve")
async def approve_payment_refund(
    refund_id: str,
    payload: AdminRefundApproveRequest,
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """批准并执行退款（可下调金额，与申请额不一致必填理由；同步渠道退款）"""
    _require_super_admin(current_user)
    try:
        refund = await RefundService.approve_refund(
            admin_user=current_user or {},
            refund_id=refund_id,
            approved_amount=payload.approved_amount,
            note=payload.note,
        )
    except (ValueError, RefundNotFoundError, RuntimeError, PaymentChannelError) as e:
        _raise_refund_service_error(e)
    return _ok({"refund": refund_to_dict(refund)})


@router.post("/payment/refunds/{refund_id}/reject")
async def reject_payment_refund(
    refund_id: str,
    payload: AdminRefundRejectRequest,
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """驳回退款申请（必填理由，用户可见；驳回后用户可重新申请）"""
    _require_super_admin(current_user)
    try:
        refund = await RefundService.reject_refund(
            admin_user=current_user or {}, refund_id=refund_id, note=payload.note
        )
    except (ValueError, RefundNotFoundError) as e:
        _raise_refund_service_error(e)
    return _ok({"refund": refund_to_dict(refund)})


@router.post("/payment/refunds/{refund_id}/retry")
async def retry_payment_refund(
    refund_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """失败退款重试（复用同 refund_no，渠道幂等不会重复退款）"""
    _require_super_admin(current_user)
    try:
        refund = await RefundService.retry_refund(
            admin_user=current_user or {}, refund_id=refund_id
        )
    except (ValueError, RefundNotFoundError, RuntimeError, PaymentChannelError) as e:
        _raise_refund_service_error(e)
    return _ok({"refund": refund_to_dict(refund)})


def _raise_refund_service_error(e: Exception) -> None:
    """退款服务异常 → HTTP 状态码映射"""
    if isinstance(e, (OrderNotFoundError, RefundNotFoundError)):
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(e, RuntimeError):
        raise HTTPException(status_code=503, detail=str(e))
    if isinstance(e, PaymentChannelError):
        raise HTTPException(status_code=502, detail=str(e))
    if isinstance(e, ValueError):
        raise HTTPException(status_code=400, detail=str(e))
    raise e
