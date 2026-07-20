"""
支付 API（用户侧，P2a：支付宝闭环）

接口（全部 get_current_user 登录鉴权，统一响应 {code, message, data}）：
- GET  /payment/products             商品目录 + 会员折扣信息
- POST /payment/coupons/validate     校验券码（返回面额）
- POST /payment/orders               下单（锁券 + 渠道预下单；0 元单直接交付）
- GET  /payment/orders               我的订单列表（分页，仅当前用户）
- GET  /payment/orders/{id}          订单详情（pending 返回 qr_code 供继续支付）
- POST /payment/orders/{id}/cancel   取消订单（仅 pending，释放券）

异常映射：ValueError → 400；OrderNotFoundError → 404；渠道未配置 RuntimeError → 503。
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.v1.auth import get_current_user
from app.core.payment.base import PaymentChannelError
from app.services.coupon_service import CouponService
from app.services.payment_service import OrderNotFoundError, PaymentService

router = APIRouter(prefix="/payment", tags=["Payment"])


def _ok(data: Any) -> Dict[str, Any]:
    return {"code": 200, "message": "success", "data": data}


def _raise_for_service_error(e: Exception) -> None:
    """服务层异常 → HTTP 状态码映射"""
    if isinstance(e, OrderNotFoundError):
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(e, RuntimeError):
        # 渠道密钥未配置（部署可先于密钥到位）
        raise HTTPException(status_code=503, detail=str(e))
    if isinstance(e, PaymentChannelError):
        raise HTTPException(status_code=502, detail=str(e))
    if isinstance(e, ValueError):
        raise HTTPException(status_code=400, detail=str(e))
    raise e


# ===================== Schemas =====================


class CouponValidateRequest(BaseModel):
    """券码校验请求"""

    code: str = Field(..., min_length=1, description="券码")


class OrderCreateRequest(BaseModel):
    """下单请求"""

    product_type: str = Field(
        ..., description="商品类型（quarterly_package/annual_package/renewal/consultation）"
    )
    channel: str = Field(..., description="支付渠道（alipay；wechat 即将上线）")
    coupon_code: Optional[str] = Field(None, description="折扣券码（可选）")
    target_code: Optional[str] = Field(None, description="延期激活目标码（renewal 必传）")


# ===================== 路由 =====================


@router.get("/products")
async def get_products(
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """商品目录 + 会员折扣信息"""
    return _ok(PaymentService.get_products())


@router.post("/coupons/validate")
async def validate_coupon(
    payload: CouponValidateRequest,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """校验券码，返回面额（无效 400）"""
    try:
        coupon = await CouponService.validate_coupon(payload.code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _ok({"code": coupon.code, "amount": coupon.amount})


@router.post("/orders")
async def create_order(
    payload: OrderCreateRequest,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """创建支付订单

    返回 {order, payment}：payment = {channel, qr_code}；0 元单 payment=null（已直接交付）。
    """
    try:
        order, payment = await PaymentService.create_order(
            user_id=str(current_user["user_id"]),
            product_type=payload.product_type,
            channel=payload.channel,
            coupon_code=payload.coupon_code,
            target_code=payload.target_code,
        )
    except (ValueError, RuntimeError, PaymentChannelError) as e:
        _raise_for_service_error(e)

    # create_order 内部已落库并 join 不到券码（券在锁定时已知），此处补 coupon_code 展示
    order_dict = PaymentService._order_to_dict(
        order, coupon_code=(payload.coupon_code or "").strip().upper() or None
    )
    return _ok({"order": order_dict, "payment": payment})


@router.get("/orders")
async def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """我的订单列表（仅当前用户）"""
    items, total = await PaymentService.list_user_orders(
        user_id=str(current_user["user_id"]), page=page, page_size=page_size
    )
    return _ok({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/orders/{order_id}")
async def get_order(
    order_id: str,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """订单详情（仅本人）；pending 时返回存储的 qr_code 供继续支付"""
    try:
        data = await PaymentService.get_user_order(
            user_id=str(current_user["user_id"]), order_id=order_id
        )
    except OrderNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _ok(data)


@router.post("/orders/{order_id}/cancel")
async def cancel_order(
    order_id: str,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """取消订单（仅本人 pending；释放券）"""
    try:
        order = await PaymentService.cancel_order(
            user_id=str(current_user["user_id"]), order_id=order_id
        )
    except (ValueError, OrderNotFoundError) as e:
        _raise_for_service_error(e)
    return _ok({"order": PaymentService._order_to_dict(order)})
