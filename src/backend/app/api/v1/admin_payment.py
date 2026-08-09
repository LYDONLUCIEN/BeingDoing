"""
Admin 支付管理 API（P1：折扣券管理；P2a：订单管理与退款）

接口：
- GET    /admin/coupons          分页列表（status 过滤；used 态联查邮箱/订单号）
- POST   /admin/coupons          单个/批量创建（固定面额，分）
- PATCH  /admin/coupons/{id}     调整面额（仅 unused）
- DELETE /admin/coupons/{id}     作废（仅 unused）
- GET    /admin/payment/orders           订单分页列表（status/channel 筛选，含 user_email + code_refundable）
- GET    /admin/payment/orders/{id}      订单详情（完整字段 + user_email + code_refundable + delivered_codes 去向）
- POST   /admin/payment/orders/{id}/refund  退款（仅 granted 且码未被 claim；成功作废码）

全部 is_super_admin_user 门控，统一响应 {code, message, data}。
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.v1.auth import get_current_user
from app.core.payment.base import PaymentChannelError
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


class CouponUpdateRequest(BaseModel):
    """调整券面额请求"""

    amount: int = Field(..., gt=0, description="新面额（分，>0）")


# ===================== 路由 =====================


@router.get("/coupons")
async def list_coupons(
    status: Optional[str] = Query(None, description="unused | locked | used"),
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
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _ok({"created": [{"id": c.id, "code": c.code, "amount": c.amount} for c in coupons]})


@router.patch("/coupons/{coupon_id}")
async def update_coupon(
    coupon_id: str,
    payload: CouponUpdateRequest,
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """调整券面额（仅 unused）"""
    _require_super_admin(current_user)
    try:
        coupon = await CouponService.update_coupon_amount(coupon_id, payload.amount)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _ok({"id": coupon.id, "code": coupon.code, "amount": coupon.amount})


@router.delete("/coupons/{coupon_id}")
async def delete_coupon(
    coupon_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """作废券（仅 unused）"""
    _require_super_admin(current_user)
    try:
        await CouponService.delete_coupon(coupon_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _ok({"id": coupon_id, "deleted": True})


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
