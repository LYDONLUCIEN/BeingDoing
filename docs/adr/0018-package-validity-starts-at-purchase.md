# ADR-0018: 套餐码有效期改为「支付成功起算」+ 团队分析联系邮箱变量化

**状态**: accepted
**日期**: 2026-08-16
**决策者**: 产品 + 开发 Grill
**取代**: ADR-0014 中「套餐码未激活语义：交付时 expires_at=None，首次创建对话 session 才起算有效期（maybe_start_validity）」

## 背景

原口径下套餐码「未激活不计时」，用户可以无限期囤码，有效期感知弱；同时交付邮件中的团队分析联系邮箱（xunlu.lab@outlook.com）并非真实可收信的邮箱，且纯文本邮件里邮箱地址与上下文被邮箱客户端一并误识别为可点链接。

## 决策

- **起算点**：套餐码（季度/年度）有效期一律自**支付成功（交付）时刻**起算——`_deliver_package` 创建码时直接落 `expires_at = now + 套餐天数`（90/365）。
- **覆盖范围**：全部交付码（含未绑定/转赠码）交付即倒计时，不再区分「未激活」。
- **消耗升级**：消耗未绑定码升级试用码时，试用码**继承被消耗码的剩余有效期**（`upgrade_to_full` 新增 `expires_at` 参数；两个调用点——`POST /simple-auth/codes/apply-to-trial` 与 intent=upgrade_trial 直购升级——均透传被消耗码的 expires_at）。
- **存量兼容（不溯及既往）**：已售出但 expires_at=None 的存量码保持老口径，`maybe_start_validity` 保留并对这类码继续生效（新码因 expires_at 已落地，该函数对其天然幂等无操作），不做数据迁移。
- **团队分析联系邮箱**：新增环境变量 `TEAM_ANALYSIS_EMAIL`（默认 `soulhappylab@163.com`）统一管理；后端交付邮件/站内信经 `payment_service._team_analysis_notice()` 使用，前端经 `GET /payment/products` 响应新增字段 `team_analysis_email` 下发（前端模块级缓存 + 兜底常量）。
- **交付邮件排版**：团队分析提示段邮箱地址独占一行，降低纯文本邮件客户端把上下文误识别为链接的概率；邮件中「个人空间 - 我的订单」改为「个人空间 - 我的激活码」（侧边栏入口已改版）。

## 实现

- `payment_service._deliver_package`：`create_activation(ttl_minutes=days*24*60)`（不再 `no_expiry=True`）。
- `simple_activation_manager.upgrade_to_full`：新增 keyword 参数 `expires_at`；传入则继承，未传入置 None（老口径兼容）。
- 文案更新：交付邮件「每码有效期：N 天（自购买成功起算）」；`get_products` 套餐 description/features「购买成功起算」；前端 i18n `period`/`giftNote`/`teamNoticeBody`（中英）同步。
- 前端 `lib/api/payment.ts`：`ProductsResult.team_analysis_email` + `getTeamAnalysisEmail()`（缓存 + `TEAM_ANALYSIS_EMAIL_FALLBACK` 兜底）；`TeamAnalysisNoticeModal`/`TeamAnalysisNoticeBox` 经 hook 注入邮箱。

## 后果

- 新购码未绑定/转赠期间也在倒计时，用户感知为「买来即计时」，商品文案已同步明示。
- 免费续期扫描（ADR-0016）与付费续期逻辑不受影响（均依赖 expires_at，新码交付即有值）。
- 测试：`test_packages.py`（交付即起算/claim 不改变/消耗升级继承/存量兼容）、`test_payment_service.py`（直购升级继承、团队邮箱断言改为 settings 变量）。
