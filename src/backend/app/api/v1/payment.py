"""
支付 API（用户侧，P2a：支付宝闭环；2026-10-05 退款申请）

接口（全部 get_current_user 登录鉴权，统一响应 {code, message, data}）：
- GET  /payment/products             商品目录 + 会员折扣信息
- POST /payment/coupons/validate     校验券码（返回面额 + 有效期）
- GET  /payment/my-coupons           我的折扣券（按派生态分组 available/used/expired）
- POST /payment/orders               下单（锁券 + 渠道下单；0 元单直接交付）
- GET  /payment/orders               我的订单列表（分页，仅当前用户）
- GET  /payment/orders/by-no/{order_no}  按商户订单号查详情（支付回跳页用）
- GET  /payment/orders/{id}          订单详情（pending 返回 pay_url 供继续支付）
- POST /payment/orders/{id}/cancel   取消订单（仅 pending，释放券）
- GET  /payment/orders/{id}/refund-options  退款能力视图（行级分摊 + 可退性）
- POST /payment/orders/{id}/refund-requests 提交退款申请（全退/部分退）
- GET  /payment/refund-requests      我的退款申请列表
- GET  /payment/refund-requests/{id} 退款申请详情（含审批留痕）
- POST /payment/refund-requests/{id}/withdraw 撤回（仅待审批）

异常映射：ValueError → 400；OrderNotFoundError → 404；渠道未配置 RuntimeError → 503。
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.v1.auth import get_current_user
from app.core.payment.base import PaymentChannelError
from app.services.coupon_service import CouponService
from app.services.payment_service import OrderNotFoundError, PaymentService
from app.services.refund_service import RefundNotFoundError, RefundService, refund_to_dict

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
    intent: Optional[str] = Field(
        None, description="订单意图（可选；upgrade_trial=试用拦截点直购升级，仅套餐）"
    )


class RefundRequestCreate(BaseModel):
    """退款申请提交请求"""

    refund_type: str = Field(..., description="退款类型（full 全退 / partial 部分退）")
    line_ids: Optional[List[str]] = Field(
        None, description="部分退所选行 ID（refund-options.lines[].id；套餐按码折算必传）"
    )
    reason: str = Field(..., min_length=1, description="申请理由")


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
    """校验券码，返回面额与有效期（无效/过期/非本人券 400；校验不认领归属）"""
    try:
        coupon = await CouponService.validate_coupon(
            payload.code, user_id=str(current_user["user_id"])
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _ok(
        {
            "code": coupon.code,
            "amount": coupon.amount,
            "expires_at": coupon.expires_at.isoformat() if coupon.expires_at else None,
        }
    )


@router.get("/my-coupons")
async def list_my_coupons(
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """我的折扣券（按派生态分组 available/used/expired；不含已作废）"""
    return _ok(await CouponService.list_my_coupons(str(current_user["user_id"])))


@router.post("/orders")
async def create_order(
    payload: OrderCreateRequest,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """创建支付订单

    返回 {order, payment}：payment = {channel, pay_type, pay_url}；
    pay_type=qr 时前端 iframe 嵌入展示二维码（支付宝前置模式）；0 元单 payment=null（已直接交付）。
    """
    try:
        order, payment = await PaymentService.create_order(
            user_id=str(current_user["user_id"]),
            product_type=payload.product_type,
            channel=payload.channel,
            coupon_code=payload.coupon_code,
            target_code=payload.target_code,
            intent=payload.intent,
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


@router.get("/orders/by-no/{order_no}")
async def get_order_by_no(
    order_no: str,
    sync: bool = Query(False),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """按商户订单号查订单详情（仅本人）

    ⚠️ 必须声明在 GET /orders/{order_id} 之前，避免被路径参数路由抢走。
    用于支付宝 page.pay 同步回跳后的支付结果页查询。
    sync=true 时先向渠道即时查单补交付（10 秒冷却防刷），秒级确认支付结果。
    """
    try:
        data = await PaymentService.get_order_by_no(
            user_id=str(current_user["user_id"]), order_no=order_no, sync=sync
        )
    except OrderNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _ok(data)


@router.get("/orders/{order_id}")
async def get_order(
    order_id: str,
    sync: bool = Query(False),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """订单详情（仅本人）；pending 时返回存储的 pay_url 供继续支付

    sync=true 时先向渠道即时查单补交付（10 秒冷却防刷），秒级确认支付结果。
    """
    try:
        data = await PaymentService.get_user_order(
            user_id=str(current_user["user_id"]), order_id=order_id, sync=sync
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


# ===================== 退款申请（2026-10-05）=====================


@router.get("/orders/{order_id}/refund-options")
async def get_refund_options(
    order_id: str,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """订单退款能力视图（仅本人）：行级分摊明细 + 实时可退性 + 剩余可退"""
    try:
        data = await RefundService.get_refund_options(
            user_id=str(current_user["user_id"]), order_id=order_id
        )
    except OrderNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _ok(data)


@router.post("/orders/{order_id}/refund-requests")
async def create_refund_request(
    order_id: str,
    payload: RefundRequestCreate,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """提交退款申请（全退/部分退；金额按规则计算，admin 审批后执行）"""
    try:
        refund = await RefundService.create_refund_request(
            user_id=str(current_user["user_id"]),
            order_id=order_id,
            refund_type=payload.refund_type,
            line_ids=payload.line_ids,
            reason=payload.reason,
        )
    except (ValueError, OrderNotFoundError) as e:
        _raise_for_service_error(e)
    return _ok({"refund": refund_to_dict(refund)})


@router.get("/refund-requests")
async def list_refund_requests(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """我的退款申请列表（含状态与驳回理由）"""
    items, total = await RefundService.list_user_refunds(
        user_id=str(current_user["user_id"]), page=page, page_size=page_size
    )
    return _ok({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/refund-requests/{refund_id}")
async def get_refund_request(
    refund_id: str,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """退款申请详情（仅本人；含审批留痕与驳回理由）"""
    try:
        data = await RefundService.get_user_refund(
            user_id=str(current_user["user_id"]), refund_id=refund_id
        )
    except RefundNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _ok(data)


@router.post("/refund-requests/{refund_id}/withdraw")
async def withdraw_refund_request(
    refund_id: str,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """撤回退款申请（仅本人 + 待审批；撤回后可再次申请）"""
    try:
        refund = await RefundService.withdraw_refund_request(
            user_id=str(current_user["user_id"]), refund_id=refund_id
        )
    except (ValueError, RefundNotFoundError) as e:
        if isinstance(e, RefundNotFoundError):
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    return _ok({"refund": refund_to_dict(refund)})
