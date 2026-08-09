# 已消耗激活码去向展示改造计划

> 状态：设计已确认（2026-08-08 grill 会议共识），待开发
> 关联：ADR-0014（套餐全量未绑定码交付 + 消耗升级）

## 1. 背景与问题

消耗升级流程中，一个未绑定付费码被消耗用于升级试用码后（`status=consumed`，`consumed_into=试用码`）：

- 该码出现在 `/dashboard/codes` 的「我购买的激活码」区块，灰色「已消耗」badge；
- 用户点击「去使用」走激活流程，后端拦截返回 400："该激活码已用于升级试用码，不可再次使用"；
- **用户困惑**：以为自己少了一个激活码 / 码被系统吞了。

## 2. 设计共识（决策记录）

| # | 决策点 | 结论 |
|---|--------|------|
| 1 | 被消耗码是否隐藏 | 不全局隐藏。**激活码模块**（owner 视角）本就不显示（无 owner，现状即隐藏）；**订单记录模块**全量展示并标注去向 |
| 2 | 自用 vs 他人消耗 | 不再区分展示策略，统一在订单视图中按"去向"状态展示 |
| 3 | 呈现形态 | **按订单分组**（金额在订单粒度，不做每码分摊），原地替换 PurchasedCodesSection |
| 4 | 升级后试用码的溯源 | **B 方案**：`ActivationRecord` 新增 `upgraded_from_code` 字段，consume 时写入；配一次性回填脚本 |
| 5 | 前端溯源交互 | 卡片加「付费升级」badge，**点击展开**才显示来源付费码完整码值，不直接展示 |
| 6 | Admin 侧 | **扩展现有订单管理**（`/admin/payment/orders` 详情），对订单交付的每个码展示"去向"；码值**不脱敏**；不新建激活码总览页 |
| 7 | 信息完整性 | 替换 PurchasedCodesSection 时**保留现有全部信息**（状态 badge、激活情况、报告状态），只增不减 |

## 3. 改造范围

### 3.1 后端

**a) 数据模型：`upgraded_from_code` 字段**

- `src/backend/app/utils/simple_activation_manager.py`
  - `ActivationRecord` dataclass 新增 `upgraded_from_code: Optional[str] = None`（记录"本试用码是被哪个付费码消耗升级的"）；
  - `_load_all` 兼容：老数据无此字段 setdefault None；
  - `consume_for_trial_upgrade()`：消耗成功后，向目标试用码记录写入 `upgraded_from_code = 被消耗码`。
- **注意两条升级路径都要覆盖**：
  1. `POST /simple-auth/codes/apply-to-trial`（手动消耗升级，simple_auth.py）；
  2. 支付直购升级 `intent=upgrade_trial`（payment_service.py:552-568，支付成功后自动消耗升级）。
  → 写入点收敛在 `consume_for_trial_upgrade` 内部即可自动覆盖两条路径（需确认直购路径是否也走该方法；若直购路径只调 `upgrade_to_full` 而未消耗码，则该路径无"来源码"概念，`upgraded_from_code` 留空，前端 badge 降级显示"付费升级"不展开码值）。

**b) 回填脚本**

- 新增 `scripts/backfill_upgraded_from_code.py`（参考先例 `scripts/migrate_activation_schema.py`）：
  - 扫描全量记录，对每条 `status=consumed && consumed_into` 非空的记录，向对应试用码记录反写 `upgraded_from_code`；
  - 幂等（已有值不覆盖，或强制以 consumed 记录为准——实现时二选一并在脚本注释说明）；
  - 支持 `--dry-run` 预演。

**c) `GET /simple-auth/my-codes`（owner 视角，simple_auth.py）**

- 返回字段新增 `upgraded_from_code`（无则 null）；
- 过滤逻辑不变（consumed 码无 owner，天然不出现）。

**d) `GET /simple-auth/my-purchased-codes`（purchaser 视角，simple_auth.py）**

- 返回字段新增：
  - `source_order_id`（当前未透传）；
  - `consumed_into`（去向备注需要）；
  - 订单联查信息：`order_no/order_id`、`order_created_at`、`product_name`（季度/年度套餐）、`amount_paid`、`amount_discount`（金额单位：分）；
- 联查方式：按 `source_order_id` 批量查 `PaymentOrder`（`meta.codes` 已有码↔订单关系可交叉校验）；
- 无 `source_order_id` 的存量码：订单字段返回 null，前端归入"其他来源"兜底分组；
- 现有字段（`activated / activated_by / activated_by_self / has_report / report_status / report_authorized`）全部保留。

**e) Admin 订单接口（admin_payment.py）**

- 订单详情响应对交付码列表（`_package_order_codes`）中每个码附 `destination` 信息：
  ```json
  {
    "code": "XXXX",
    "destination_type": "unbound | bound_self | bound_other | consumed_for_upgrade | revoked",
    "destination_detail": "脱敏邮箱或试用码码值（admin 不脱敏）"
  }
  ```
- `bound_self/bound_other` 判断：owner_user_id == purchaser_user_id。

### 3.2 前端

**a) `/dashboard/codes` 页面（app/(main)/dashboard/codes/page.tsx）**

- **激活码模块（上半）**：
  - 升级来的码卡片加「付费升级」badge；
  - 点击展开显示来源付费码完整码值（默认折叠）；
  - i18n：`zh.ts` / 英文 locale 新增文案。
- **订单记录模块（下半，原地替换 PurchasedCodesSection）**：
  - 按订单分组渲染：订单头（订单号、日期、商品名、实付金额、券抵扣）+ 订单下码列表；
  - 每个码一行/卡：**保留**现有状态 badge、激活情况、报告状态，**新增**"去向"备注列；
  - 去向 5 态文案：
    | 状态 | 文案 |
    |------|------|
    | unbound | 未绑定（可使用/可转赠） |
    | bound_self | 已绑定给自己 |
    | bound_other | 已绑定给 {脱敏邮箱} |
    | consumed_for_upgrade | 已用于升级试用码 {完整码值} |
    | revoked | 已作废（退款） |
  - `source_order_id` 为空的归入"其他来源"分组（分组头不显示金额）；
  - **移除**该区块的「去使用」误引导向：consumed/revoked 状态的码不再渲染「去使用」按钮（未绑定码保留，可复制码值）。

**b) Admin 订单详情页**

- 交付码列表新增"去向"列，展示 `destination_type` + `destination_detail`（不脱敏）。

**c) 类型定义**

- `src/frontend/lib/api/teamAnalysis.ts` 中 `PurchasedCodeItem` 类型同步新增字段；my-codes 的 item 类型新增 `upgraded_from_code`。

### 3.3 测试

- `test/backend/test_trial_codes.py` / `test_payment_service.py` 追加：
  - consume 后试用码记录 `upgraded_from_code` 正确写入（手动 + 直购两条路径）；
  - my-codes 返回 `upgraded_from_code`；
  - my-purchased-codes 返回订单联查字段 + `consumed_into`；
  - admin 订单详情 destination 5 态正确；
  - 回填脚本幂等性。
- 前端手动验证清单：自用升级后 codes 页两模块展示正确；他人消耗后订单视图去向正确。

### 3.4 文档更新

- `AGENTS.md` 试用激活码体系章节：补 `upgraded_from_code` 字段与订单分组视图说明；
- 视情况更新 `CONTEXT.md` 术语（去向 / destination）。

## 4. 不做的事（明确排除）

- 不改退款口径（退款只依赖 `status` / `owner_user_id`，本改造纯展示层 + 一个冗余溯源字段）；
- 不做每码金额分摊（金额保持订单粒度展示）；
- 不新建 admin 激活码总览页（后续需要再议）；
- 不对 admin 视图脱敏。

## 5. 实施顺序建议

1. 后端字段 + consume 写入 + 回填脚本（含 dry-run 验证）；
2. my-codes / my-purchased-codes 接口扩展 + 后端测试；
3. 前端 codes 页两模块改造 + i18n；
4. Admin 订单详情去向列 + 测试；
5. 文档更新（AGENTS.md 等）。
