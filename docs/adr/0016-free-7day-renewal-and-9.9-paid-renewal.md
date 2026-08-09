# ADR-0016: 延期体系改版 —— 首次过期免费送 7 天 + 付费续期统一 9.9 元/7 天

**状态**: accepted
**日期**: 2026-08-08
**决策者**: 产品 + 开发 Grill
**取代**: 「延期激活统一 20 元 / 90 天」（2026-07-28 口径，settings.RENEWAL_PRICE=2000 / RENEWAL_DAYS=90）

## 背景

旧延期 SKU（20 元 / 90 天）对「只是想再多用几天收尾」的用户门槛偏高，且码过期后没有任何召回触点——用户悄悄流失。新体系用「首次过期免费送 7 天」做召回钩子，再用低单价（9.9 元 / 7 天）做持续续费。

## 决策

- **免费续期（每码一次）**：完整码（code_type=full 且 package_type∈{quarterly,annual}）首次过期时，给**激活人（owner）**发邮件+站内信（无邮箱只发站内信；不给购买者发），内含领取链接 `{FRONTEND_URL}/dashboard/codes?free_renewal=<code>`。
  - **手动领取**：链接进「我的激活码」页自动弹确认弹窗，用户点击才生效；链接**不限时**，领取后从当天起 +7 天（沿用 `extend_validity` 的 `max(原到期, now) + days` 口径）。
  - **粒度**：每个码一次（非每个用户）；`ActivationRecord` 新增 `free_renewal_offered_at`（幂等标记）/ `free_renewal_claimed_at`。
  - **存量补发**：所有已 expired 且未发过通知的完整码，首次扫描全量补发。
- **付费续期**：SKU 直接替换为 **9.9 元 / 7 天**（`RENEWAL_PRICE=990`、`RENEWAL_DAYS=7`），旧 20 元/90 天下线（仅历史订单展示）。与免费解耦：不强制先领免费、随时可买、不限次、active/expired 均可买。延期订单维持**不可退**口径。
- **试用码**（expires_at=None，不过期）不涉及。

## 实现

- **检测**：新增 APScheduler 每日 job `activation_expiry_scan`（`ACTIVATION_EXPIRY_SCAN_CRON`，默认每日 10:00）→ `app/services/activation_expiry_scan.py`。激活码过期此前纯懒判定（`get_activation`），扫描时先统一转正再通知。
- **幂等**：以 `free_renewal_offered_at` 为准，每码只发一次；发送顺序先邮件后站内信，失败整体下次重试，避免重复站内信。
- **领取 API**：`POST /simple-auth/codes/free-renewal/claim`（仅 owner 可领）；`GET /simple-auth/my-codes` 每项新增 `free_renewal_available` 供卡片直显领取按钮。
- **审计**：`activation_audit` 新增事件 `free_renewal_claimed`；延期本身沿用 `EVENT_EXTENDED`。
- **前端**：新组件 `FreeRenewalClaimModal`（领取确认/成功态）；codes 页支持 `?free_renewal=` 参数自动弹窗；付费延期文案改 ¥9.9 / 7 天。

## 后果

- 每日 10:00 扫描会给「今天起新过期 + 存量全部已过期」的完整码激活人发信；上线首日存在一波存量补发邮件。
- 无 owner / owner 账号已删的过期码直接打 offered 标记跳过（永不再有通知对象）。
- 旧延期价格配置（`RENEWAL_QUARTERLY_PRICE`/`RENEWAL_ANNUAL_PRICE`）维持弃用状态不变。
- 测试：`test/backend/test_free_renewal.py`（扫描/幂等/领取/定价 10 例）。
