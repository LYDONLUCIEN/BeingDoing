# 支付宝前置模式：页内二维码（2026-10-05）

## 背景

原支付宝「电脑网站支付」（`alipay.trade.page.pay`）为跳转模式：点支付后 `window.open` 新标签页
跳到支付宝收银台整页，用户离开产品页面，体验割裂。

目标：**商品/支付弹窗内直接展示二维码，用户拿支付宝 App 扫一扫，页面原地轮询变「支付成功」**，
全程不跳转。

## 方案

采用支付宝官方支持的前置模式（支持文档：《电脑网站如何在商家页面展示二维码》
https://opendocs.alipay.com/support/01rfuy ）：

- `page.pay` 下单 biz_content 加 `qr_pay_mode=4`（可自定义宽度的**嵌入式二维码**）+ `qrcode_width=220`
- 前端以 **iframe** 加载下单返回的带签名 URL，支付宝页面只渲染一张二维码（官方为 iframe 设计，
  无 X-Frame-Options 拦截）
- **无需新签约任何产品**（复用现有电脑网站支付资质）；异步通知 / sync 查单 / 退款 / 关单全部不变
- SDK 佐证：alipay-sdk-python 3.7.1160 的 `AlipayTradePagePayModel` 自带 `qr_pay_mode` /
  `qrcode_width` 字段，放 biz_content 是正规用法（dict→模型转换后字段存活，测试已覆盖）

支付确认页（商家名+金额）不消失，只是从 PC 收银台网页挪到用户手机支付宝 App 内——监管要求，
任何渠道绕不开。

## 改动

### 后端

1. `src/backend/app/core/payment/alipay.py`
   - 新增常量 `_QR_PAY_MODE = "4"` / `_QRCODE_WIDTH = 220`
   - `create_order` biz_content 增加两参数；其余（验签/查单/退款/关单）不动
   - 切回跳转收银台：删掉这两个参数即可

2. `src/backend/app/services/payment_service.py`
   - 新增 `_CHANNEL_PAY_TYPES = {"alipay": "qr"}`（渠道→展示方式；微信 Native 接入后登记为 qr）
   - `create_order` / `get_user_order` / `get_order_by_no` 返回值统一加 `pay_type`
     （pending 订单才有；未登记渠道兜底 "redirect"）

3. `src/backend/app/api/v1/payment.py`：docstring 同步返回结构

### 前端

4. `src/frontend/lib/api/payment.ts`
   - 新增 `export type PayType = 'qr' | 'redirect'`
   - `CreateOrderResult.payment` / `OrderDetailResult` 加 `pay_type?`（可选，兼容前后端部署时差，
     缺省按 redirect 行为走）

5. `src/frontend/components/payment/PurchaseModal.tsx`
   - 新增 `payType` state；`startWaiting(ord, url, type)`：qr 不再 `window.open`，redirect 保持原行为
   - 等待支付视图：`payType === 'qr' && payUrl` 时渲染 `<iframe src={payUrl} width=248 height=300>`
     （qrcode_width=220 + 支付宝页内边距）；轮询/取消/超时逻辑不动
   - 「重新打开」链接保留为兜底（在新窗口打开同一 URL）

6. `zh.ts` / `en.ts`：`payment.waiting.hint` 改为「请使用支付宝 App 扫一扫上方二维码…」；
   `reopen` 改为「二维码显示不出来？在新窗口打开」

## 测试

- 新增 `test/backend/test_payment_alipay_qr_mode.py`：打桩 SDK client，断言 biz_content 携带
  qr_pay_mode=4/qrcode_width 且经 dict→AlipayTradePagePayModel 转换 + get_params 序列化后不丢失；
  同时核对金额分→元、out_trade_no、notify/return_url 透传
- `test/backend/test_payment_service.py`：下单/订单详情断言补 `pay_type == "qr"`（pending 有、
  支付后为 None）
- 结果：42 passed；`test_deliver_annual_team_analysis_notice` 失败为存量问题（本地 .env 的
  TEAM_ANALYSIS_EMAIL 泄漏进断言，与本次无关，stash 验证过）
- 前端 `next lint` 通过；dev 模式前后端已热加载

## 兼容性与边界

- **旧 pending 订单**：qr_code 列存的是旧收银台 URL，也会按 qr 渲染（iframe 里显示完整收银台，
  略挤但可扫码支付）；影响窗口仅到旧订单超时关单为止
- **前后端部署时差**：前端 `pay_type ?? 'redirect'`，旧后端返回无 pay_type 时退回新窗口跳转，
  行为同旧版
- **移动端**：前置模式二维码给 PC 端用户扫；手机端用户无法扫自己屏幕，后续如需支持要走
  「手机网站支付 wap.pay」，另立任务

## 后续（微信 Native）

微信支付接入后：`_CHANNEL_PAY_TYPES` 登记 `wechat: qr`，渠道返回 `code_url`（weixin://…），
前端用 `react-qr-code` 直接渲染字符串（无需 iframe），轮询闭环复用。

微信侧要办的事（个体工商户资质可用）：

1. **申请商户号**：https://pay.weixin.qq.com 「接入微信支付」（材料：营业执照、经营者身份证、
   银行卡可用经营者个人卡；1~5 工作日）→ 拿 10 位 mchid
2. **绑 AppID**：注册一个免费小程序（https://mp.weixin.qq.com ）拿 appid → 商户平台
   「产品中心 → AppID 账号管理」关联（两边都要确认）
3. **API 安全三件套**（商户平台「账户中心 → API 安全」）：申请 API 证书
   （apiclient_key.pem + 证书序列号）、设置 APIv3 密钥（32 位随机）、复制微信支付公钥 + PubKey_Id
4. **产品中心开通 Native 支付**；回调地址下单时传
   `https://域名/api/v1/payment/notify/wechat`（nginx 已放行该前缀）
5. 代码侧：`core/payment/wechat.py`（wechatpayv3 库，金额单位同为分）+ `/notify/wechat`
   webhook（JSON + 验签 + AES-GCM 解密，注意现有 `verify_notify(form)` 抽象需扩展 headers 入参）
   + `.env` 八个 WECHAT_* 变量；微信无公开沙箱，用 1 分钱订单联调

