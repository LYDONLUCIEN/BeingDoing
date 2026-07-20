"""
支付渠道工厂

get_channel(name) 按渠道名返回实现实例（进程内缓存）。
密钥未配置时抛 RuntimeError（路由层转 503「支付宝支付未配置」），
部署可先于密钥到位。
"""

from typing import Dict

from app.core.payment.base import PaymentChannel

_CHANNELS: Dict[str, PaymentChannel] = {}


def get_channel(name: str) -> PaymentChannel:
    """获取支付渠道实例

    Args:
        name: 渠道名（alipay；wechat 后续插入同一抽象）

    Returns:
        PaymentChannel 实例

    Raises:
        ValueError: 未知渠道
        RuntimeError: 渠道密钥未配置
    """
    normalized = (name or "").strip().lower()
    if normalized in _CHANNELS:
        return _CHANNELS[normalized]

    if normalized == "alipay":
        from app.core.payment.alipay import AlipayChannel

        channel: PaymentChannel = AlipayChannel()
    else:
        raise ValueError(f"不支持的支付渠道：{name}")

    _CHANNELS[normalized] = channel
    return channel
