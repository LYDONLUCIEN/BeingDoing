"""
Admin 支付管理 API（P1：折扣券管理；P2a：订单管理与退款）

接口：
- GET    /admin/coupons          分页列表（status 过滤含派生态 expired/void；used 态联查邮箱/订单号）
- POST   /admin/coupons          单个/批量创建（固定面额，分；ttl_days 可选，默认读运行时配置）
- PATCH  /admin/coupons/{id}     调整面额/有效期（仅 unused，含派生 expired——改期即复活）
- DELETE /admin/coupons/{id}     作废（仅 unused；软删除置 void，可恢复）
- POST   /admin/coupons/{id}/restore  恢复已作废券（void → unused）
- GET    /admin/coupon-config    读折扣券默认有效期（天）
- POST   /admin/coupon-config    调整默认有效期（1-3650 天，即时生效，只影响新券）
- GET    /admin/payment/orders           订单分页列表（status/channel 筛选，含 user_email + code_refundable）
- GET    /admin/payment/orders/{id}      订单详情（完整字段 + user_email + code_refundable + delivered_codes 去向）
- POST   /admin/payment/orders/{id}/refund  退款（仅 granted 且码未被 claim；成功作废码）

全部 is_super_admin_user 门控，统一响应 {code, message, data}。
"""

from typing import Any, Dict, Optional

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.v1.auth import get_current_user
from app.core.payment.base import PaymentChannelError
from app.services import coupon_config
from app.services.coupon_service import CouponService
from app.services.payment_service import OrderNotFoundError, PaymentService
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


# ===================== 路由 =====================


@router.get("/coupons")
async def list_coupons(
    status: Optional[str] = Query(None, description="unused | locked | used | expired | void"),
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
    """创建折扣券（单个/批量，固定面额）"""
    _require_super_admin(current_user)
    try:
        coupons = await CouponService.create_coupons(
            amount=payload.amount,
            count=payload.count,
            source="admin",
            created_by=str(current_user.get("user_id")) if current_user else None,
            ttl_days=payload.ttl_days,
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
    """发起退款：仅 granted 且交付码未被任何用户 claim；成功即 refunded 并作废码"""
    _require_super_admin(current_user)
    try:
        order = await PaymentService.admin_refund(order_id, actor=current_user)
    except OrderNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except PaymentChannelError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return _ok({"order": PaymentService._order_to_dict(order)})
