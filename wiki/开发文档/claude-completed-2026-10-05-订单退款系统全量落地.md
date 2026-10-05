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
