# 支付二维码自渲染改造：修复不居中/白边，摆脱 iframe 布局漂移

> 完成日期：2026-10-08
> 前置：claude-completed-2026-10-07-支付弹窗收银台化改造.md（iframe 194×210 方案）
> 背景：用户反馈支付宝二维码生成后不居中、有白边，且质疑为何不能提前渲染。

## 根因

1. **不居中/白边**：二维码不是我们渲染的——iframe 内嵌支付宝前置模式页（`qr_pay_mode=4`），
   码的位置由支付宝页面的内边距决定。10-07 校准时页面四周有 ≈12px 内边距，本次实测
   （Playwright + PIL 像素分析）发现**支付宝页面已漂移**：170×170 的码贴死 iframe 左上角，
   右侧 24px、底部 40px 全是空白 → 视觉重心偏左上。iframe 跨域，内部像素完全不可控。
2. **无法提前渲染**：码内容 = 按单 RSA 签名的 URL（含商户单号+金额+时间戳），每单一码，
   物理上无法预生成；签名本身 <100ms，用户感知的慢是 iframe 加载支付宝页的网络耗时。

## 方案：套取 qrCode 文本，前端自渲染（无需签约当面付）

关键发现：前置模式收银台页 HTML 的 `hidden input#J_qrCode` 直接携带二维码内容串
（`https://qr.alipay.com/upx...`，与当面付 precreate 返回同类）——curl 实测 200 可解析。
于是不走 iframe，后端套取该文本，前端用已有依赖 `qrcode.react` 自己画码：
居中/白边/边框/说明文案全自控，永久免疫支付宝页布局漂移。

## 改动清单

**后端**

| 文件 | 改动 |
|---|---|
| `app/core/payment/alipay.py` | 新增 `extract_qr_text(pay_url)`：GET 收银台页（gb18030 解码）→ 正则提取 `input#J_qrCode` 的 value → 校验 `https://qr.alipay.com/` 前缀；任何失败返回 None |
| `app/services/payment_service.py` | ① `create_order` 下单后顺带套取，`payment` 响应新增 `qr_text`；② `get_user_order`/`get_order_by_no` 仅 **sync=false** 时返回 `qr_text`（sync=true 是 2s 轮询热路径，不套取）；③ 新增 `refresh_qr_text`（仅本人 pending 单，10s 冷却防刷，`_QR_REFRESH_COOLDOWN`） |
| `app/api/v1/payment.py` | 新增 `POST /payment/orders/{order_id}/refresh-qr` |

**前端**

| 文件 | 改动 |
|---|---|
| `lib/api/payment.ts` | `CreateOrderResult.payment` / `OrderDetailResult` 增加 `qr_text?: string \| null`；新增 `refreshQrCode(id)` |
| `components/payment/PurchaseModal.tsx` | ① `QrStage` 优先自渲染（QRCodeSVG 164px + 支 badge + 「打开支付宝，扫一扫完成支付」说明），`qrText=null` 回退 iframe；三形态同尺寸 194×210 零跳动；② 窄弹窗等待视图同样自渲染/回退；③ 状态行/窄视图新增「刷新二维码」按钮（`RefreshCw` 图标，点击换新码） |
| `lib/i18n/locales/zh.ts` / `en.ts` | 新增 `payment.wide.qrScanTip`、`payment.qr.refresh`、`payment.qr.refreshFailed` |

**测试**：`test_payment_alipay_qr_mode.py` 修正 qrcode_width 220→170 的历史陈旧断言；
新增 `extract_qr_text` 正常提取 + 四类失败回退（HTTP 非 200 / 无 J_qrCode / value 非法 / 网络异常）用例；
`test_payment_service.py` 下单响应断言补 `qr_text: None`（fake 渠道无提取方法）。

## 回退与降级

- 提取失败（支付宝改页面结构/网络异常）→ `qr_text=None` → 前端自动回退 iframe 嵌入，支付链路不受影响；
- 状态行保留「二维码显示不出来？在新窗口打开」（`pay_url` 直开收银台页）兜底；
- 码会轮换（实测每次套取都是新 upx 码）→ 用户可点「刷新二维码」换新码。

## 验证

- 后端单测：43 passed（仅 `test_deliver_annual_team_analysis_notice` 失败，为环境变量依赖的存量问题，与本改动无关）
- API 实测：下单 812ms 返回 `qr_text`；refresh-qr 正常返回新码、10s 内重复 400 冷却；sync=1 轮询不带 qr_text 且 <50ms
- Playwright E2E（本机 127.0.0.1:3000）：自渲染二维码居中（像素复核左右边距 26/30）；OpenCV 解码内容 = `https://qr.alipay.com/upx...`；点「刷新二维码」SVG 变化
- `npm run build` 通过；`tsc --noEmit` 无错
- 测试订单已全部取消，压测账号已 teardown

## 部署提醒

涉及前端 + 后端，生产机 `./deploy.sh`（或 `./start.sh prod`）后生效；无数据库迁移、无新依赖
（qrcode.react 已在 package.json，httpx 已在 requirements）。
若未来想要完全自定义收银台（金额/倒计时/品牌页），可评估签约「当面付」（precreate 直接返回
qr_code 文本，连套取都省掉）——但当前方案已满足视觉诉求，非必需。
