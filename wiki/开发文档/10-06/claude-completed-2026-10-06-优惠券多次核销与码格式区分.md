# 完成：优惠券多次核销 + 激活码/优惠券码格式区分（2026-10-06）

> 设计定稿：[优惠券多次核销与码格式区分-设计定稿.md](./优惠券多次核销与码格式区分-设计定稿.md)（grill-me 三轮拷问，10 项决策）
> 实施：P1 数据层 → P2 服务层 → P3 API 层 → P4 前端，四段独立提交，随做随测。

## 功能摘要

### 1. 优惠券 n 次核销（促销码模式）

- admin 创建时可设 **可用次数 n**（1-10000）：n=1 为原单次券语义（全兼容）；
  n>1 为共享促销码——任意用户先到先得各抵一次面额，**每账号限用 1 次**，
  面额×n=总补贴负债（表单实时提示）。
- 新表 `coupon_redemptions` 按行记账（coupon/order/user/status/时间戳），
  锁定/核销/关单释放/退款回退全部按行推进；n=1 双写单槽字段保持旧查询兼容。
- 并发守卫：单条 `UPDATE coupons SET locked_count=locked_count+1 WHERE
  used_count+locked_count < max_uses AND 未停用 AND 未过期 AND NOT EXISTS(该用户已有锁定/核销行)`
  ——影响行数判定，并发下恰好 n 个锁成功。
- **停用/启用开关**（运营纠错）：已核销名额保持有效，剩余名额立即冻结，可恢复；
  与作废（仅无核销记录时可用）分开。退款全额成功 → 按行回退 used_count-1，名额恢复。
- 券池（邮件发券）跳过 n>1 共享券；「我的折扣券」used 组含共享券核销记录（不归属）。

### 2. 码格式区分（存量兼容）

| | 新格式 | 例 | 存量 |
|---|---|---|---|
| 优惠券 | `Q-` + 8 位 | `Q-K3M7X9A2` | 12 位裸码永久可用 |
| 激活码 | `OPENLIFE-` + 12 位分 3 组 | `OPENLIFE-9F2K-8M4P-7X1D` | 10 位裸码永久可用 |

- 字符集剔除 `0/O/1/I/L` 防手输混淆；激活码随机源从 `random` 升级 `secrets`。
- 新码含连字符、存量码不含 → **码空间永不相交**，精确匹配即兼容，无迁移。
- 归一化（前后端同规则，`code_format.py` / `lib/codeFormat.ts`）：大小写、
  去所有空白（治邮件折行截断）、全角横杠 `－—–−_` → `-`；
  **裸码按输入框上下文自动补前缀**（券码框裸 8 位→`Q-`，激活码框裸 12 位→
  `OPENLIFE-` 并 4-4-4 重分组；跨框输错退化为清晰的「码不存在」）。
- `POST /payment/coupons/validate` 与 `POST /simple-auth/activate` 增加
  **内存滑动窗口限流 10 次/分/IP**（429），防短码暴力试探。

## 变更清单

### 后端
- 迁移 `024_coupon_multi_redemption.py`：coupons 加 `max_uses/used_count/locked_count/suspended_at`
  （存量 backfill：used 行 used_count=1、locked 行 locked_count=1）；建 `coupon_redemptions`
  （order_id 唯一索引）；`payment_orders.delivered_code` 扩宽 String(16)→String(64)（新激活码 23 字符）。
- `models/payment.py`：Coupon 加列 + 新 CouponRedemption；`models/__init__.py` 导出。
- `services/coupon_service.py`：create(max_uses) / validate / lock（两路守卫）/ release /
  redeem / return_coupon_on_refund(coupon_id, order_id) / suspend / resume /
  draw_from_pool 跳过共享券 / list_my_coupons used 组扩展 / 派生态（used 用满、suspended）。
- `services/payment_service.py`：`_release_coupon_safe(coupon_id, order_id)` 三调用点传订单 ID。
- `services/refund_service.py`：全额退款退券传 `refund.order_id` 按行回退。
- `utils/simple_activation_manager.py`：激活码生成切 `generate_activation_code()`。
- `utils/code_format.py`（新）、`utils/rate_limit.py`（新，单进程内存限流）。
- `api/v1/admin_payment.py`：POST /admin/coupons +max_uses；新增 `/suspend` `/resume`；
  列表 status 支持 suspended，序列化带 max_uses/used_count/locked_count/suspended_at。
- `api/v1/payment.py`：validate 限流。`api/v1/simple_auth.py`：activate 归一化+限流。

### 前端
- `lib/codeFormat.ts`（新）：normalizeCouponCode / normalizeActivationCode。
- `lib/api/payment.ts`：CouponStatus+suspended；CouponItem/CreatedCoupon+max_uses 等字段；
  createCoupons+max_uses；suspendCoupon/resumeCoupon。
- `admin/payment/page.tsx`：创建表单「可用次数」+ 总补贴实时提示；列表「已用/总量」列
  （含锁定数）、停用/启用按钮（橙色系区分作废）、suspended 筛选与徽标、共享券使用信息、
  页头文案更新。
- `PurchaseModal.tsx`：券码输入归一化；placeholder 示例新格式（zh/en i18n）。
- `dashboard/codes/page.tsx`、`explore/activate/page.tsx`：激活码输入归一化。

## 测试

- `test_code_format.py` 16 例：生成规则/归一化矩阵/自动补前缀/存量兼容/跨框输错。
- `test_rate_limit.py` 5 例：限额/隔离/窗口滑动/拒绝不记账/IP 提取。
- `test_coupon_multi_use.py` 15 例：n=1 双写等价、n=3 三人核销+第四人拒、每用户限一次、
  5 锁 2 成、释放回补、退款减名额（n>1/n=1 双口径）、停用/启用/作废守卫、创建约束、
  券池跳过、我的券共享记录、列表派生态过滤、存量 12 位裸码可用。
- `test_coupon_admin_api.py` 8 例：max_uses 透传与 422 边界、suspend/resume 400/403、
  validate/activate 限流 429。
- 既有测试同步：券码格式断言、delivered_code 新格式断言。
- 迁移 024 up/down 在临时 SQLite 精准验证（backfill/列宽/唯一索引/回滚）通过。

## 遗留与说明

- 全量后端套件中存在 **45 个与本次无关的失败**（step3/search/loader 等区域及并行开发中的
  user_type 功能），其中 `test_payment_service.py::test_deliver_annual_team_analysis_notice`
  为存量失败（联系邮箱文案早前变更未同步测试），`test_payment_alipay_qr_mode` 依赖环境缺
  `alipay` 模块。本次改动区域（coupon/payment/refund/code_format/rate_limit）121+ 测试全绿。
- 限流为单进程内存实现：多 worker 部署时需换 Redis（`rate_limit.py` docstring 已注明）。
- validate 响应**不**返回剩余名额（D9 决策：用错时才报「已被抢完/每账号限一次」）。
- 部署顺序：先 `alembic upgrade head`（024），后端代码任意先后（新列有默认值，旧代码写
  新表不冲突）；激活码新格式即刻生效，存量 10 位码不受影响。
