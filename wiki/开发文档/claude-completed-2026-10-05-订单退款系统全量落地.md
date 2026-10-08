# 订单退款系统全量落地（2026-10-05）

> 设计：[10-05/订单系统退款设计.md](./10-05/订单系统退款设计.md)（grill-me 三轮定稿）
> 提交：`8074208`（P1 表结构）→ `3992ec5`（P2 服务+API）→ `017e946`（P3 前端）→ P4 测试收尾
> 回答原始问题的结论：**全款/部分退款均已支持**，统一「用户申请（或 admin 代录）→ admin 审批执行」，金额以实付为上限、原路退回、全链路可审计。

## 一、能力总览

| 能力 | 说明 |
|---|---|
| 全额退款 | 用户申请 / admin 代录 → admin 审批（可下调金额）→ 渠道同步退款 → 作废码/取消预约/退券 |
| 部分退款 | 年度套餐按「码分摊实付」折算（勾选退几个码退几份）；咨询走 admin 协商金额（仅未预约） |
| 不可退 | 延期（交付即已用）；已预约/已完成咨询；码已被激活/消耗的整单；legacy 已升级单 |
| 0 元单 | 同流程，跳过渠道调用，直接作废码 |
| 幂等 | refund_no = order_no+R+3位序号 = 支付宝 out_request_no；失败重试复用同号（fund_change=N 判成功） |
| 治理 | 待审批可撤回；驳回必填理由（用户可见）；驳回后可重提；同订单同时仅一个在途申请 |

## 二、数据库（迁移 023，已应用 dev 库）

- `payment_orders` + `amount_refunded`（累计成功退款）；状态新增 `partially_refunded`
- `payment_order_lines`：订单明细行（原价/优惠/实付分摊，尾差归末行；Σ行=订单额不变式）。交付时生成，存量 granted 订单访问时惰性回填
- `payment_refunds`：退款申请单全留痕（申请额/批准额分列、调整必填理由、审批人/时间、渠道回执、行快照）

## 三、状态机与联动

```
pending_review → refunding → succeeded / failed(可重试)
pending_review → withdrawn / rejected
订单：granted → partially_refunded → refunded（终态纯金额口径：累计退满实付）
```

退款成功原子联动：订单累计与状态 → 行 refunded → 作废码 → 取消预约（咨询）→ 整单退完且券未过期退回券 → 用户站内信+邮件。
渠道失败/联动失败 → failed + admin 站内信告警，人工重试（渠道幂等不多退）。

## 四、API

**用户**：`GET /payment/orders/{id}/refund-options`、`POST .../refund-requests`、`GET /payment/refund-requests(/{id})`、`POST .../{id}/withdraw`
**Admin**（超管门控）：`GET/POST /admin/payment/refunds`、`GET .../{id}`、`POST .../{id}/approve|reject|retry`
旧 `POST /admin/payment/orders/{id}/refund` → **410**（引导新流程）。

## 五、前端

- 用户：「我的订单」卡新增**申请退款**（RefundRequestModal：全退/部分退勾码实时合计、理由必填、待审批可撤回、历史含驳回理由）；部分退款徽标 + 已退金额展示
- admin：支付页新增**退款审批** Tab（列表筛选/详情审计留痕/实时行状态与可退上限/批准可下调/驳回/失败重试/代录）；订单 Tab 旧退款按钮改为代录申请

## 六、测试与验证

- `test_refund_service.py` 16 项：状态机全迁移、按码折算、下调与上限、券规则、互斥、失败重试幂等、双 admin 并发门闩、0 元单、咨询协商、申请后码被激活实时收缩、通知
- `test_refund_api.py` 11 项：路由接线/鉴权/异常映射（410/403/400/404/502/422）
- `test_payment_lines.py` 14 项：分摊算法不变式、交付生成、存量回填、实时行状态
- 存量支付测试全部迁移新流程；全量回归 **893 passed**（基线 878；52 失败均为 rumination/step3 等并行域存量问题，支付域仅剩 2 个环境/文案存量项）
- 全新库引导（init_db）+ dev 库 alembic 022→023 均验证通过；后端已重启，接口在线

## 七、边界与后续

- 发票模块未做（口径已落库可回溯）；手续费线下核算；`refunding` 订单态保留未用（退款状态在退款单上）
- 上线注意：admin 直接退款旧入口已 410，前后端本次同批发布；存量订单首次访问退款能力时自动回填明细行

## 八、逐文件变更清单（2d2b290…6234050，4 提交，29 文件 +4936/−193）

| 文件 | 变更 | 说明 |
|---|---|---|
| `alembic/versions/023_payment_refund_system.py` | 新增 | 迁移 023（dev 已应用） |
| `app/models/payment.py` | +120 | PaymentOrderLine / PaymentRefund 两表 + amount_refunded / partially_refunded |
| `app/models/__init__.py` | +4 | 注册新模型 |
| `app/services/payment_line_service.py` | 新增 | 分摊算法 + 交付生成/存量回填 + 行实时状态 |
| `app/services/refund_service.py` | 新增 | 退款全流程（申请/撤回/驳回/批准执行/重试/通知/联动） |
| `app/services/payment_service.py` | −admin_refund | 交付时生成明细行；移除旧直接退款；序列化加 amount_refunded |
| `app/api/v1/payment.py` | +106 | 用户侧 5 个退款接口 |
| `app/api/v1/admin_payment.py` | +181 | admin 6 个接口 + 旧接口 410 |
| `app/core/payment/base.py` `alipay.py` | +53 | refund 返回回执 str + fund_change=N 幂等重试；alipay.py 同时含并行 qr_pay_mode=4 前置模式 |
| `components/payment/RefundRequestModal.tsx` | 新增 | 用户申请弹窗 |
| `components/admin/RefundApprovalsTab.tsx` | 新增 | admin 审批 Tab |
| `components/dashboard/OrdersSection.tsx` | +37 | 申请退款入口/部分退徽标/已退金额 |
| `components/admin/PaymentOrdersTab.tsx` | ±27 | 旧退款改代录；状态映射补 partially_refunded |
| `app/(main)/admin/payment/page.tsx` | +20 | 退款审批 Tab 挂载 |
| `lib/api/payment.ts` `i18n/zh.ts` `en.ts` | +227 | 退款 API client/类型 + 文案（含并行 PayType 前端段） |
| `app/(main)/explore/survey/page.tsx` | 1 行 | user_id 类型收窄（解除 production build 阻塞） |
| `test_payment_lines.py` `test_refund_service.py` `test_refund_api.py` | 新增 | 14+16+11 项 |
| `test_payment_service.py` `test_packages.py` | 迁移 | 旧退款测试全部改走新流程 |
| `wiki/开发文档/10-05/*` + 本文档 | 新增 | 设计（grill-me 定稿）/需求原文/完成记录 |

> GitHub 存档 issue：[#102](https://github.com/LYDONLUCIEN/BeingDoing/issues/102)（enhancement / ready-for-human，待生产部署勾选）
