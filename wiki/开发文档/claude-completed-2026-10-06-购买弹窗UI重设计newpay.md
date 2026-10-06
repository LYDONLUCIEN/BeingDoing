# 购买弹窗 UI 重设计（对齐 newpay.html 设计稿）

**日期**：2026-10-06
**设计稿**：`wiki/开发文档/10-05/newpay.html`
**改动文件**：`src/frontend/components/payment/PurchaseModal.tsx`、`src/frontend/lib/i18n/locales/zh.ts`、`src/frontend/lib/i18n/locales/en.ts`

## 定稿决策（grill-me 确认）

1. **二维码保留 iframe 方案**：后端 `page.pay` 前置模式（`qr_pay_mode=4, qrcode_width=220`）返回签名 URL，前端 iframe 嵌入支付宝二维码页。后端零改动、零支付风险。QR 舞台自适应：占位 176×176（四角标 + 支 logo）→ 激活 248×300 iframe。
2. **套餐改名**：quarterly_package → **启程版**、annual_package → **同行版**（`productName.*` 同步改，订单列表一致）。
3. **免费版信息卡**：三列布局含免费版卡，仅展示不可选（无 CTA，本弹窗无免费流程），标记「免费体验」。

## 新布局（宽视图：套餐下单 + 等待支付）

- 弹窗头：eyebrow「寻路 · OPENLIFE 探索方案」+ 大标题「选择适合你的探索方式」
- 三列方案卡：01 免费版（绿）/ 02 启程版（蓝，推荐标）/ 03 同行版（紫），每卡 = 特性卡（编号/定位/承诺/✓ 特性）+ 价格选择条（sr-only radio + value）
- 折叠三列功能对比（8 行，免费/启程/同行，选中列高亮）
- 结算面板：左 QR 列（占位 → 支付宝 iframe）+ 右三行（应付金额+生成付款码 / 优惠码 / 支付方式：支付宝 + 微信即将上线禁用态）
- 状态行（role=status）：错误红 / 订单已创建+扫码提示+重开+取消订单 / 券码反馈绿
- 信任行：安全支付
- 删除：权益 2×2 矩阵、渐变背景、固定底栏；成功视图与窄模式（延期/咨询）不变

## 行为接线（唯一逻辑变化）

- `wideMode = !renewalMode && !consultationMode && view !== 'success'`（等待支付并入宽壳）
- 等待期金额/套餐以服务端订单为准（`order.product_type` / `order.amount_paid`）——resume 单可能不是当前选中套餐
- `startWaiting` 后结算面板 `scrollIntoView`（防二维码在折叠线下方）
- 金额行按钮：下单「生成付款码」/ ≤0 元「免费领取」/ 等待轮询禁用「等待支付…」/ 关闭过期「重新下单」
- 等待期方案卡/券码/渠道置灰禁用

## 验证（Playwright DOM 断言 26/26 PASS + 真实下单）

- 结构/交互断言全过：三列卡、价格切换（¥159↔¥69）、对比表、券码错误状态行、响应式（1100/800/640/375）、英文 locale 无裸 key
- 真实下单端到端：点「生成付款码」→ 订单创建（状态行显示单号）→ **支付宝签名 URL iframe 渲染在二维码区**（qr_pay_mode=4）→ 按钮「等待支付…」→ 取消订单回下单视图
- Resume 路径：订单中心「继续支付」→ 宽弹窗直接进等待视图（iframe + 服务端金额）
- 截图：`wiki/开发文档/10-05/newpay-截图/`
- tsc + next lint 零错误；生产已重新 build 部署（tmux frontend，FRONTEND_MODE=production）

## 已知说明

- headless Chromium 装跨域支付宝 OOPIF 后合成输入会失效（Playwright 真实点击无效、JS click 正常）——测试环境问题，非应用缺陷；线上真实浏览器不受影响
- 测试账号 pw-newpay@test.com 的测试订单已全部取消

## 2026-10-06 晚 追加修复

1. **三卡等高**：`WidePlanCard` 根节点加 `flex-1`（原为自然高度，启程版因「推荐」标签多一行导致三卡不等高）。修复后实测 297/297/297。
2. **「二维码没渲染」排查**：根因是前端构建损坏（另一会话重 build 后 `next start` 未随之重启，页面静态 chunk 400、整页无水合，任何点击无效）。`./start.sh restart frontend` 重建后验证：iframe 内支付宝二维码正常渲染（像素分析黑像素占比 32.9%、中心区 39.7%，典型二维码特征）。截图 `50-cards-equal.png` / `51-qr-rendered.png`。
