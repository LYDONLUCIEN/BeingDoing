"""
支付宝渠道前置模式测试（不打真实支付宝，SDK client 打桩）

验证 alipay.trade.page.pay 下单请求（官方支持文档「电脑网站如何在商家页面展示二维码」）：
1. biz_content 携带 qr_pay_mode=4 + qrcode_width（前置模式嵌入式二维码，前端 iframe 加载）
2. 金额分→元、out_trade_no、notify_url/return_url 透传正确
3. dict → AlipayTradePagePayModel 转换后参数不丢失（get_params 序列化可见）
"""

import json

import pytest

from app.config.settings import settings
from app.core.payment.alipay import AlipayChannel

_FAKE_PAY_URL = "https://openapi.alipay.com/gateway.do?signed-fake-url"


class _FakeSDKClient:
    """打桩 DefaultAlipayClient：记录 page_execute 收到的请求对象"""

    def __init__(self):
        self.last_request = None

    def page_execute(self, request, http_method="POST"):
        self.last_request = request
        return _FAKE_PAY_URL


@pytest.fixture
def channel(monkeypatch, tmp_path):
    """构造 AlipayChannel：settings 打桩 + 临时密钥文件 + SDK client 替身"""
    priv = tmp_path / "app_private_key.pem"
    pub = tmp_path / "alipay_public_key.pem"
    priv.write_text("fake-private-key", encoding="utf-8")
    pub.write_text("fake-public-key", encoding="utf-8")

    monkeypatch.setattr(settings, "ALIPAY_APP_ID", "2021000000000000")
    monkeypatch.setattr(settings, "ALIPAY_PRIVATE_KEY_PATH", str(priv))
    monkeypatch.setattr(settings, "ALIPAY_PUBLIC_KEY_PATH", str(pub))
    monkeypatch.setattr(settings, "ALIPAY_NOTIFY_URL", "https://example.com/api/v1/payment/notify/alipay")
    monkeypatch.setattr(settings, "ALIPAY_RETURN_URL", "https://example.com/payment/result")

    fake_client = _FakeSDKClient()
    monkeypatch.setattr(AlipayChannel, "_build_client", lambda self: fake_client)
    return AlipayChannel(), fake_client


@pytest.mark.asyncio
async def test_create_order_embeds_qr_pay_mode(channel):
    """前置模式：biz_content 携带 qr_pay_mode=4 + qrcode_width，模型转换后参数仍在"""
    ch, fake_client = channel

    url = await ch.create_order("X202610051234567890123", 19900, "年度套餐")

    assert url == _FAKE_PAY_URL
    request = fake_client.last_request
    assert request.notify_url == settings.ALIPAY_NOTIFY_URL
    assert request.return_url == settings.ALIPAY_RETURN_URL

    # biz_content dict 已被 SDK 转成 AlipayTradePagePayModel，模型字段是参数存活的证明
    assert request.biz_content.qr_pay_mode == "4"
    assert request.biz_content.qrcode_width == 220

    # 完整序列化（page_execute 实际签名的参数）核对
    params = request.get_params()
    biz = json.loads(params["biz_content"])
    assert biz["qr_pay_mode"] == "4"
    assert biz["qrcode_width"] == 220
    assert biz["out_trade_no"] == "X202610051234567890123"
    assert biz["total_amount"] == "199.00"
    assert biz["subject"] == "年度套餐"
    assert biz["product_code"] == "FAST_INSTANT_TRADE_PAY"
