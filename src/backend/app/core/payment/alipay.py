"""
支付宝渠道适配（官方 alipay-sdk-python）

- 下单：当面付预下单 alipay.trade.precreate → 返回 qr_code 串
- 回调验签：RSA2 + 支付宝公钥（sign/sign_type 不参与签名内容）
- 退款：alipay.trade.refund（同步响应 code=10000 且 fund_change=Y 即成功）
- 关单：alipay.trade.close

配置（settings / .env）：
    ALIPAY_APP_ID / ALIPAY_PRIVATE_KEY_PATH / ALIPAY_PUBLIC_KEY_PATH /
    ALIPAY_NOTIFY_URL / ALIPAY_GATEWAY（默认正式网关，沙箱切 openapi-sandbox）

密钥未配置时构造抛 RuntimeError（路由层转 503），部署可先于密钥到位。
SDK 同步调用一律 asyncio.to_thread 包装。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, Optional
from zoneinfo import ZoneInfo

from app.config.settings import settings
from app.core.payment.base import (
    NotifyResult,
    NotifyVerifyError,
    PaymentChannel,
    PaymentChannelError,
)

logger = logging.getLogger(__name__)

# 支付宝异步通知时间戳时区（gmt_payment 等，东八区）
_ALIPAY_TZ = ZoneInfo("Asia/Shanghai")

# 验签失败 / 必填参数缺失提示
_ERR_VERIFY = "支付宝回调验签失败"


def _fen_to_yuan(amount_fen: int) -> str:
    """分 → 元字符串（两位小数）"""
    return str((Decimal(amount_fen) / Decimal(100)).quantize(Decimal("0.01")))


def _yuan_to_fen(amount_yuan: str) -> int:
    """元字符串 → 分（四舍五入，避免浮点误差）"""
    return int((Decimal(str(amount_yuan)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _read_key(path: str) -> str:
    """读取 PEM 密钥文件内容"""
    return Path(path).read_text(encoding="utf-8").strip()


class AlipayChannel(PaymentChannel):
    """支付宝渠道"""

    def __init__(self) -> None:
        if not settings.ALIPAY_APP_ID:
            raise RuntimeError("支付宝支付未配置：缺少 ALIPAY_APP_ID")
        if not settings.ALIPAY_PRIVATE_KEY_PATH or not settings.ALIPAY_PUBLIC_KEY_PATH:
            raise RuntimeError("支付宝支付未配置：缺少密钥文件路径")
        try:
            self._app_private_key = _read_key(settings.ALIPAY_PRIVATE_KEY_PATH)
            self._alipay_public_key = _read_key(settings.ALIPAY_PUBLIC_KEY_PATH)
        except OSError as e:
            raise RuntimeError(f"支付宝支付未配置：密钥文件读取失败（{e}）")

        self._client = self._build_client()

    def _build_client(self):
        """构建支付宝 SDK 客户端（同步，构造时调用一次）"""
        from alipay.aop.api.AlipayClientConfig import AlipayClientConfig
        from alipay.aop.api.DefaultAlipayClient import DefaultAlipayClient

        config = AlipayClientConfig()
        config.server_url = settings.ALIPAY_GATEWAY
        config.app_id = settings.ALIPAY_APP_ID
        config.app_private_key = self._app_private_key
        config.alipay_public_key = self._alipay_public_key
        config.sign_type = "RSA2"
        return DefaultAlipayClient(config)

    # ─── 下单：当面付 precreate ─────────────────────────────────

    async def create_order(self, order_no: str, amount_fen: int, subject: str) -> str:
        """预下单，返回 qr_code 串

        Raises:
            PaymentChannelError: 下单失败（含网关返回非 10000）
        """
        from alipay.aop.api.request.AlipayTradePrecreateRequest import (
            AlipayTradePrecreateRequest,
        )

        request = AlipayTradePrecreateRequest()
        request.notify_url = settings.ALIPAY_NOTIFY_URL or None
        request.biz_content = {
            "out_trade_no": order_no,
            "total_amount": _fen_to_yuan(amount_fen),
            "subject": subject,
        }
        response = await asyncio.to_thread(self._client.execute, request)
        logger.info("alipay precreate response: %s", response)
        if not response or str(response.get("code")) != "10000":
            sub_msg = (response or {}).get("sub_msg") or (response or {}).get("msg")
            raise PaymentChannelError(f"支付宝下单失败：{sub_msg or response}")
        qr_code = response.get("qr_code")
        if not qr_code:
            raise PaymentChannelError("支付宝下单失败：响应缺少 qr_code")
        return qr_code

    # ─── 回调验签 ───────────────────────────────────────────────

    async def verify_notify(self, form: Dict[str, str]) -> NotifyResult:
        """验签（RSA2 + 支付宝公钥）并解析通知参数

        Raises:
            NotifyVerifyError: 验签失败或必填参数缺失
        """
        from alipay.aop.api.util.SignatureUtils import get_sign_content, verify_with_rsa

        params = {k: v for k, v in (form or {}).items() if k not in ("sign", "sign_type")}
        sign = (form or {}).get("sign", "")
        if not sign:
            raise NotifyVerifyError(f"{_ERR_VERIFY}：缺少 sign")

        content = get_sign_content(params)
        ok = await asyncio.to_thread(
            verify_with_rsa, self._alipay_public_key, content.encode("utf-8"), sign
        )
        if not ok:
            raise NotifyVerifyError(_ERR_VERIFY)

        order_no = params.get("out_trade_no")
        trade_no = params.get("trade_no", "")
        trade_status = params.get("trade_status", "")
        total_amount = params.get("total_amount")
        if not order_no or total_amount is None:
            raise NotifyVerifyError(f"{_ERR_VERIFY}：缺少 out_trade_no/total_amount")

        paid_at: Optional[datetime] = None
        gmt_payment = params.get("gmt_payment")
        if gmt_payment:
            try:
                paid_at = (
                    datetime.strptime(gmt_payment, "%Y-%m-%d %H:%M:%S")
                    .replace(tzinfo=_ALIPAY_TZ)
                    .astimezone(timezone.utc)
                )
            except ValueError:
                logger.warning("alipay notify gmt_payment parse failed: %s", gmt_payment)

        return NotifyResult(
            order_no=order_no,
            channel_transaction_id=trade_no,
            paid_at=paid_at,
            total_amount_fen=_yuan_to_fen(total_amount),
            trade_status=trade_status,
        )

    # ─── 退款 ───────────────────────────────────────────────────

    async def refund(self, order_no: str, amount_fen: int, refund_no: str) -> None:
        """退款（同步响应即成功）

        Raises:
            PaymentChannelError: 退款失败
        """
        from alipay.aop.api.request.AlipayTradeRefundRequest import AlipayTradeRefundRequest

        request = AlipayTradeRefundRequest()
        request.biz_content = {
            "out_trade_no": order_no,
            "refund_amount": _fen_to_yuan(amount_fen),
            "out_request_no": refund_no,
        }
        response = await asyncio.to_thread(self._client.execute, request)
        logger.info("alipay refund response: %s", response)
        if not response or str(response.get("code")) != "10000":
            sub_msg = (response or {}).get("sub_msg") or (response or {}).get("msg")
            raise PaymentChannelError(f"支付宝退款失败：{sub_msg or response}")
        if str(response.get("fund_change", "")).upper() != "Y":
            raise PaymentChannelError(f"支付宝退款失败：fund_change={response.get('fund_change')}")

    # ─── 关单 ───────────────────────────────────────────────────

    async def close_order(self, order_no: str) -> None:
        """关单

        Raises:
            PaymentChannelError: 关单失败
        """
        from alipay.aop.api.request.AlipayTradeCloseRequest import AlipayTradeCloseRequest

        request = AlipayTradeCloseRequest()
        request.biz_content = {"out_trade_no": order_no}
        response = await asyncio.to_thread(self._client.execute, request)
        logger.info("alipay close response: %s", response)
        if not response or str(response.get("code")) != "10000":
            sub_msg = (response or {}).get("sub_msg") or (response or {}).get("msg")
            raise PaymentChannelError(f"支付宝关单失败：{sub_msg or response}")
