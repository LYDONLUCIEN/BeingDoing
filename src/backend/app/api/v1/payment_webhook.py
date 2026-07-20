"""
支付回调 API（无登录鉴权，渠道验签，ADR-0005）

- POST /payment/notify/alipay：支付宝异步通知（form-encoded）
  验签 + 业务处理后按支付宝要求返回纯文本 success / failure
  （failure 会触发支付宝重试，最多约 24h）

幂等：重复回调不重复发码（见 PaymentService._deliver_order）。
部署：nginx 需放行 /api/v1/payment/notify/*（公网可达，HTTPS）。
"""

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from app.services.payment_service import PaymentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payment/notify", tags=["Payment-Webhook"])


@router.post("/alipay")
async def alipay_notify(request: Request) -> Any:
    """支付宝支付结果异步通知

    Returns:
        纯文本 "success"（处理成功或无需处理）/ "failure"（验签失败或处理异常）
    """
    form = {k: v for k, v in (await request.form()).items()}
    try:
        await PaymentService.handle_alipay_notify(form)
    except Exception as e:
        # 验签失败 / 订单不存在 / 金额不符 / 状态异常 / 渠道未配置：返回 failure 触发重试
        logger.warning("alipay notify rejected: %s", e)
        return PlainTextResponse("failure")
    return PlainTextResponse("success")
