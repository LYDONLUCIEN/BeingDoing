"""
支付渠道抽象（ADR-0005：官方接口双线，微信/支付宝插入同一抽象）

各渠道实现 PaymentChannel：
- create_order: 下单生成支付跳转 URL（收银台跳转）
- verify_notify: 异步通知验签 + 解析（验签失败抛 NotifyVerifyError）
- query_order: 主动查询订单支付状态（对账兜底，渠道无此单返回 None）
- refund: 官方退款（同步成功或抛异常）
- close_order: 关单（超时/取消时调用）

SDK 同步调用一律由实现方用 asyncio.to_thread 包装。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional


class PaymentChannelError(Exception):
    """支付渠道调用异常（下单/退款/关单失败）"""


class NotifyVerifyError(PaymentChannelError):
    """异步通知验签失败"""


@dataclass
class NotifyResult:
    """支付成功通知解析结果

    Attributes:
        order_no: 商户订单号（out_trade_no）
        channel_transaction_id: 渠道交易号
        paid_at: 支付完成时间（UTC，可空）
        total_amount_fen: 实付金额（分）
        trade_status: 渠道交易状态（如支付宝 TRADE_SUCCESS / TRADE_FINISHED）
    """

    order_no: str
    channel_transaction_id: str
    paid_at: Optional[datetime]
    total_amount_fen: int
    trade_status: str


class PaymentChannel(ABC):
    """支付渠道抽象接口"""

    @abstractmethod
    async def create_order(self, order_no: str, amount_fen: int, subject: str) -> str:
        """下单，返回支付跳转 URL（pay_url，用户跳转收银台完成支付）

        Raises:
            PaymentChannelError: 下单失败
        """

    @abstractmethod
    async def verify_notify(self, form: Dict[str, str]) -> NotifyResult:
        """异步通知验签并解析

        Raises:
            NotifyVerifyError: 验签失败
        """

    @abstractmethod
    async def query_order(self, order_no: str) -> Optional["NotifyResult"]:
        """主动查询订单支付状态（对账兜底用）。订单在渠道不存在时返回 None

        Returns:
            NotifyResult；渠道无此单时返回 None

        Raises:
            PaymentChannelError: 查询失败
        """

    @abstractmethod
    async def refund(self, order_no: str, amount_fen: int, refund_no: str) -> None:
        """退款（同步响应即成功，否则抛异常）

        Args:
            order_no: 原商户订单号
            amount_fen: 退款金额（分）
            refund_no: 退款请求号（幂等用）

        Raises:
            PaymentChannelError: 退款失败
        """

    @abstractmethod
    async def close_order(self, order_no: str) -> None:
        """关单（未支付订单）

        Raises:
            PaymentChannelError: 关单失败
        """
