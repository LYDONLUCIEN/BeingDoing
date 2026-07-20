# 支付模块实施计划

> 来源：2026-07-19 grill-with-docs 会话。术语以 `CONTEXT.md`「支付与会员」为准，关键决策见 ADR-0005/0006/0007。
> 实施原则：**三期递进，每期独立可交付可验证**。

## 一、已确认决策速查

| 主题 | 决策 |
|---|---|
| 支付确认 | 官方接口自动回调，微信 Native + 支付宝双线（ADR-0005） |
| 权益模型 | 激活码与会员两条独立产品线；会员不免码，享折扣 + 码固化 vip_level=2（ADR-0006） |
| 商品 | 单一 SKU「全程激活码」（五阶段+report，`mode="combined"`），价格/有效期后台可配 |
| 购买数量 | v1 一单限一个码（表预留 quantity） |
| 包月 | 按真实代扣（委托代扣/周期扣款）写，会员本期不开放（ADR-0007） |
| 折扣券 | 通用码、固定金额、无门槛、永久有效、核销一次即作废；下单锁定、关单释放 |
| 邮件发券 | 每收件人独立券码；券池 FIFO，不足按 `DEFAULT_COUPON_AMOUNT` 自动创建 |
| 发码 | 发码自取：成功页展示 + 邮件备份；码不绑定可转送，订单归购买者 |
| 退款 | 官方退款 API（双线）；仅未使用码可退，退款成功即作废码；admin 后台发起 |
| 页面 | 个人空间「我的订单」；购买入口三处（激活页按钮 / dashboard 卡 / 落地页定价）；admin「支付管理」单页 tab（订单 / 折扣券），邮件发券扩展 notifications 页 |

## 二、数据模型（迁移 `011_payment_and_membership`）

新增模型文件 `app/models/payment.py`，并登记 `app/models/__init__.py` + `alembic/env.py` import。金额一律整数**分**。

### payment_orders
| 字段 | 类型 | 说明 |
|---|---|---|
| id | String(36) PK | uuid |
| order_no | String(32) unique index | 商户订单号（生成规则：前缀+时间戳+随机） |
| user_id | String(36) FK users.id | 购买者 |
| product_type | String(32) | `activation_code` / `membership_monthly` / `membership_lifetime` |
| quantity | Integer default 1 | v1 恒为 1，预留 |
| amount_original / amount_discount / amount_paid | Integer | 原价 / 抵扣 / 实付（分） |
| coupon_id | String(36) FK coupons.id nullable | 使用的券 |
| channel | String(16) | `wechat` / `alipay` |
| status | String(16) index | `pending/paid/granted/closed/cancelled/refunding/refunded` |
| channel_transaction_id | String(64) nullable | 渠道交易号 |
| delivered_code | String(16) nullable | 交付的激活码 |
| paid_at / closed_at / refunded_at | DateTime nullable | |
| created_at / updated_at | DateTime | |

### coupons
| 字段 | 类型 | 说明 |
|---|---|---|
| id | String(36) PK | |
| code | String(32) unique index | 券码 |
| amount | Integer | 面额（分） |
| status | String(16) index | `unused/locked/used`（locked=下单锁定中） |
| locked_order_id | String(36) nullable | 锁定它的订单 |
| used_by_user_id / used_order_id / used_at | | 核销信息 |
| source | String(16) | `admin` / `email_auto` |
| created_by / created_at | | |

无 `expires_at`（永久有效，核销即废）。

### subscriptions（P3 用，本期建表）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / user_id FK | | |
| plan_type | String(16) | `monthly` / `lifetime` |
| status | String(16) | `active/cancelled/expired` |
| channel | String(16) | 扣款渠道 |
| agreement_no | String(64) nullable | 代扣签约号 |
| auto_renew | Boolean default true | |
| current_period_start / current_period_end | DateTime | |
| cancelled_at / created_at / updated_at | | |

### users 加列
`membership_plan String(16) default "none"`（none/monthly/lifetime）、`membership_expires_at DateTime nullable`——订阅变更时维护的缓存字段（P3 使用）。

## 三、配置项（settings.py + .env）

```
# 微信支付 V3
WECHAT_MCH_ID / WECHAT_APP_ID / WECHAT_API_V3_KEY
WECHAT_PRIVATE_KEY_PATH / WECHAT_CERT_SERIAL_NO / WECHAT_NOTIFY_URL
# 支付宝
ALIPAY_APP_ID / ALIPAY_PRIVATE_KEY_PATH / ALIPAY_PUBLIC_KEY_PATH / ALIPAY_NOTIFY_URL
# 商品
ACTIVATION_CODE_PRICE=9900（99 元）  ACTIVATION_CODE_TTL_DAYS=180
# 折扣券
DEFAULT_COUPON_AMOUNT=5000（50 元）
# 订单
ORDER_TIMEOUT_MINUTES=30
# 会员（P3 预留）
MEMBERSHIP_ENABLED=false
MEMBERSHIP_MONTHLY_PRICE=1500（15 元）  MEMBERSHIP_LIFETIME_PRICE=29900（299 元）
MEMBER_DISCOUNT_PERCENT=85（8.5 折）
```

## 四、后端 API

### 用户侧 `app/api/v1/payment.py`
- `GET /payment/products` 商品与价格
- `POST /payment/orders` 下单（product_type, channel, coupon_code?）→ 返回订单 + 支付二维码串；券码在此校验并锁定
- `GET /payment/orders` 我的订单列表（个人空间）
- `GET /payment/orders/{id}` 订单详情（前端轮询支付状态用）
- `POST /payment/orders/{id}/cancel` 主动取消（释放券）

### 回调 `app/api/v1/payment_webhook.py`（无登录鉴权，渠道验签）
- `POST /payment/notify/wechat` 、 `/payment/notify/alipay`（幂等：重复回调直接返回成功）
- `POST /payment/notify/wechat-refund` 、 `/payment/notify/alipay-refund`
- 部署：nginx 放行 `/api/v1/payment/notify/*`（公网可达，HTTPS）

### Admin `app/api/v1/admin_payment.py`（`is_super_admin_user` 门控）
- `GET /admin/payment/orders`（状态/渠道/时间筛选 + 分页）
- `POST /admin/payment/orders/{id}/refund`：校验交付码未使用 → 调渠道退款 API → `refunding`；回调后 `refunded` + 作废码（`SimpleActivationManager` 状态置 revoked + 审计）
- `GET /admin/coupons`（含使用状态）、`POST /admin/coupons`（单个/批量，定金额）、`PATCH /admin/coupons/{id}`（仅 unused 可调金额）、`DELETE /admin/coupons/{id}`（仅 unused）
- 邮件发券：扩展现有 `POST /admin/notifications/email`，加 `attach_coupon: bool`；正文支持 `{{coupon_code}}` 占位符，NotificationService 逐收件人渲染（券池 FIFO 取 + 不足按默认金额创建），与现有进度/限流/退信过滤复用

### 服务层
- `app/services/payment_service.py`：下单、回调处理（验签→改状态→发码→发邮件）、超时关单、退款
- `app/services/coupon_service.py`：校验/锁定/释放/核销/池取券/自动创建
- `app/core/payment/wechat.py` / `alipay.py`：渠道适配（签名、下单、验签、退款）；微信用官方 `wechatpay-python`，支付宝用 `alipay-sdk-python`
- 发码：支付回调成功 → `SimpleActivationManager.create_activation(mode="combined", ttl_days=配置)` → 写 `delivered_code` → 邮件备份（`EmailService.send_email`）
- APScheduler 新 job：每 5 分钟关闭超时 `pending` 订单并释放券（挂法参照 main.py 现有 cron）

## 五、前端页面

- `lib/api/payment.ts`：apiClient 封装
- `app/(main)/dashboard/orders/page.tsx`「我的订单」：列表（订单号/金额/状态/渠道/时间/激活码）+ 详情 + 未支付订单去支付；`dashboard/layout.tsx` NAV_ITEMS 加一项
- 购买弹窗组件 `components/payment/PurchaseModal.tsx`：选渠道（微信/支付宝 tab）→ 输券码（可选，实时校验抵扣金额）→ 下单 → 展示二维码（qrcode 渲染）+ 30 分钟倒计时 → 轮询订单状态 → 成功页展示激活码（复制按钮）+ 提示邮件已备份
- 三处入口：`/explore/activate` 加「去购买激活码」（过期提示文案改为引导购买）；dashboard 主页购买卡；落地页 `/` 定价区块（未登录点击跳登录后回跳）
- `app/(main)/admin/payment/page.tsx`「支付管理」：tab1 订单（筛选/分页/详情/退款按钮带码状态提示）、tab2 折扣券（创建/批量创建/调金额/作废/使用状态）；`admin/layout.tsx` 导航加一项
- `admin/notifications/page.tsx`：表单加「附折扣券」开关 + 提示默认金额；历史任务显示发券数量
- i18n：用户侧文案补 zh/en key；admin 侧中文硬编码（跟现有约定）

## 六、分期

### P1 · 折扣券先行（✅ 已完成 2026-07-19，17 测试+端到端验证通过）
1. ~~迁移 011：三表 + users 加列（订单/会员表一并建好）~~
2. ~~coupon_service + admin 券管理 API + admin 支付管理页（先只有券 tab）~~
3. ~~邮件发券：notifications 扩展（占位符渲染、FIFO 取券、自动创建、`DEFAULT_COUPON_AMOUNT`）~~
4. ~~测试：券 CRUD / 锁定释放核销 / 邮件发券全链路~~

### P2a · 支付闭环·支付宝（✅ 开发完成 2026-07-19，待真实密钥联调）
1. ~~渠道适配层 `app/core/payment/`（base 抽象 + alipay 实现，微信后续插入同一抽象）+ 配置~~
2. ~~payment_service 下单/回调/关单/发码 + webhook 端点~~（nginx 放行待部署）
3. ~~下单用券核销（锁定→支付成功核销/关单释放）~~
4. ~~PurchaseModal（微信选项置灰「即将上线」）+ 三处入口 + 我的订单页~~
5. ~~admin 订单 tab + 官方退款（仅未使用可退 + 作废码）~~
6. ~~测试：39 全绿；隔离实例冒烟：商品/503/验签拒绝/权限门控全过~~

### P2b · 支付闭环·微信补位
1. `app/core/payment/wechat.py` 实现同一渠道抽象（Native 下单/回调验签/退款/关单）
2. PurchaseModal 启用微信选项
3. 微信侧端到端联调

### P2c · 双渠道联调验收
商户平台真实回调验收、对账抽查、超时/退款异常路径演练

### P3 · 会员（写完，flag 关闭）
1. 会员购买接口（包月含签约参数 / 永久一次性）+ 取消解约 + 扣款回调
2. 会员折扣计算 + 发码固化 vip_level=2 + users 会员缓存字段维护
3. 个人空间会员状态卡（flag 内）
4. 接口级测试 + 沙箱模拟验收（代扣不可端到端，见 ADR-0007）

## 七、已拍板的定价与规则（2026-07-19）

1. 激活码定价 **¥99**，有效期 **180 天**
2. `DEFAULT_COUPON_AMOUNT` = **¥50**
3. 会员月费 **¥15** / 永久 **¥299** / 折扣率 **0.85**（P3 启用）
4. 会员折扣与折扣券**可叠加**：先算会员价（原价×0.85，四舍五入到分），再减券面额，实付下限 0 元
5. 商户号**已有**（微信+支付宝），P2 不阻塞
