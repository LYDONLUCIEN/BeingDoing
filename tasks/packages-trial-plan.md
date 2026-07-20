# 套餐与试用体系实施计划（2026-07-20）

> 来源：2026-07-20 grill-with-docs 会话。术语见 `CONTEXT.md`「支付与商业化」，决策见 ADR-0008/0009/0010。
> 前置：P1 折扣券 ✅、P2a 支付宝闭环 ✅。会员体系保留不上线（ADR-0006/0007）。

## 一、已拍板决策速查

| 主题 | 决策 |
|---|---|
| 会员体系 | 与套餐**并存**，数据库保留，本期不开发不展示，以后上首页 |
| 商品目录 | 季度 ¥69/3月（升级1码）· 年度 ¥99/1年（1升级+2赠品码）· 延期（季度码 ¥23/3月、年度码 ¥33/1年）· 咨询 ¥298/次；旧 ¥99/180 天 SKU 下架 |
| 试用码 | 注册即送自动绑定（每人一个，老用户无码登录补发）；不过期；限 values 10 轮（第 11 条用户消息起拦截；values 内出结论卡推进 strengths 同样拦截）；vip_level=1 |
| 完整码 | 全阶段解锁；vip_level=2（当前 level1/level2 均配置 DeepSeek）；有效期从付款（升级）/首次激活（赠品码）起算 |
| 续期 | 买套餐永远新码/升级，不延旧码；旧码走「延期激活」（原价 1/3），从 max(当前到期,现在) 追加 |
| 报告审核 | 阻塞式：admin 确认后可见；随机 3~24h 超时自动批复（后台如实记录 auto，用户只感知管理员审核通过） |
| 团队分析 | 本期做：选多份报告（自己码的 + 自己订单交付且被一键授权的）生成匹配度/角色投射；激活人一键授权仅对所属人；对话记录永不分享 |
| 咨询 | 状态机：待填问卷→已提交→已预约→已完成；仅未预约前可退款 |
| 退款 | 码类仅未使用可退（退款作废码）；咨询未预约可退；admin 后台发起 |

## 二、数据模型改动

### ActivationRecord（JSON，simple_activation_manager）
新增字段（`_load_all` setdefault 兼容存量）：
- `code_type`: `"trial"|"full"`（存量默认 full）
- `package_type`: `None|"quarterly"|"annual"`（决定延期价格档）
- `source_order_id` / `purchaser_user_id`: 所属人追溯（赠品码归属）
- `report_authorized`: bool（激活人一键授权）
- 赠品码创建时 `expires_at=None`，**claim 时按 package_type 时长落有效期**（claim 三处调用路径需同步，或收敛）
- 试用码 `expires_at=None`（不过期），`vip_level=1`

### payment_orders（SQL，迁移 013）
- 加列 `meta` TEXT（JSON）：product 特定载荷——renewal: {target_code, added_days}；annual: {gift_codes: [...]}；consultation: {booking_id}
- product_type 新取值：`quarterly_package / annual_package / renewal / consultation`

### consultation_bookings（新 SQL 表，迁移 013）
id / order_id FK / user_id / report_id（问卷中选哪份报告）/ topics TEXT / time_slots TEXT(JSON) / contact / note / status(`pending_survey/submitted/scheduled/completed/cancelled`) / scheduled_at / admin_note / created_at / updated_at

### team_analyses（新 SQL 表，迁移 013）
id / user_id / title / code_list TEXT(JSON) / report_ids TEXT(JSON) / status(`generating/done/failed`) / result_markdown TEXT / error / created_at

### 报告审核（走 JSON record.json，跟 report_registry 现有模式）
字段：`review_status`(pending_review/approved) / `review_deadline` / `review_type`(manual/auto) / `reviewed_by` / `reviewed_at`。存量报告无字段视为 approved（祖父豁免）。

## 三、分期实施

### P-A · 试用码体系（✅ 2026-07-20 完成，21+60 测试过，冒烟验证过）
后端：
1. `ActivationRecord` 加 code_type/package_type 等字段 + setdefault 兼容
2. 注册送码：注册端点钩子 → 创建试用码（trial/不过期/vip1/自动 claim 绑定）；老用户无码时在 journeys 接口懒补发
3. 试用门控：`simple_chat_stream` 写端点统计该码 values 线程用户消息数（排除 internal），≥10 拦截返回结构化错误（HTTP 402 + detail.type=trial_limit_reached）；阶段推进（resolve_report_context 写路径）拦非 values；只读端点（history/threads）不拦；`_can_bypass_flow_limits` 豁免
4. journeys 接口返回每 journey 的激活码 + code_type + 有效期

前端：
5. dashboard 新增「我的激活码」页：码列表（码值/类型 badge 试用|完整/状态/有效期/来源/「去使用」），layout 导航加项
6. 对话页识别 402 trial_limit_reached → 弹购买引导（先接现有 PurchaseModal，P-B 换套餐版）
7. dashboard 旅程卡显示对应激活码

### P-B · 套餐商品化（✅ 2026-07-20 完成，86 测试全绿，冒烟验证过）
后端：
8. 商品目录改组（下架旧 SKU；季度/年度/延期/咨询价格配置进 settings/.env：QUARTERLY_PRICE=6900、ANNUAL_PRICE=9900、RENEWAL_QUARTERLY_PRICE=2300、RENEWAL_ANNUAL_PRICE=3300、CONSULTATION_PRICE=29800、QUARTERLY_DAYS=90、ANNUAL_DAYS=365）
9. 交付逻辑按 product_type 分支：quarterly=升级试用码（无则发新码，有效期付款起算）；annual=升级+2 赠品码（meta 记录，邮件附全部码）；renewal=校验码归属与 package_type 定价，支付成功追加有效期；consultation 见 P-D
10. 赠品码 claim 时落有效期（三处 claim 路径同步/收敛）
11. 退款守卫适配（升级码已用=已被 claim 过？——规则：升级后的码只要没开始新阶段使用可退？**简化**：升级码交付即视为已用不可退；赠品码未 claim 可退（退赠品部分？暂定整单不可部分退，订单含已用码则整单拒退））
前端：
12. PurchaseModal 泛化：商品选择（季度/年度卡片，年度标「最受欢迎」）、renewal 模式（从激活码页带入 target_code）、成功视图多码展示
13. 我的激活码页加「延期激活」入口（完整码卡片）→ PurchaseModal renewal 模式
14. 落地页定价区块改套餐双卡

### P-C · 报告审核流（✅ 2026-07-20 完成，12+59 测试过，前后端落地）
15. 报告生成钩子：写 review_status=pending_review + 随机 3~24h deadline（record.json）
16. 用户侧报告端点：pending_review → 返回审核中状态（前端报告页显示审核中占位，文案：「报告审核中，预计 24 小时内处理完成，结果将通过站内信通知」）
17. admin：报告列表加审核筛选 + 「确认审核」按钮（manual）；APScheduler 每 10 分钟扫超时 pending → auto 批复
18. 批复后**站内信**通知用户「报告已审核通过」（复用现有 notifications 表/站内信系统，两种批复同一文案；邮件可选）

### P-D · 报告解读咨询（✅ 2026-07-20 完成，96 测试全绿，前后端落地）
19. consultation_bookings 表 + 购买交付（回调生成 booking，meta 关联）
20. 预约问卷页（/dashboard/consultation/[bookingId]）：主题期望/候选时间段/联系方式/备注/选择报告
21. admin 咨询管理页：列表/问卷详情/标记已预约（填时间）/已完成；退款仅限未预约
22. 报告页购买入口弹窗（前置校验：有已完成报告）

### P-E · 团队分析（✅ 2026-07-20 完成，103 测试全绿，前后端落地）
23. 激活人报告页「授权给所属人」开关（report_authorized）
24. 团队分析页（dashboard/team-analysis）：候选报告列表（自己码 + 订单交付已授权码）多选 → 生成
25. LLM 分析服务：汇总报告内容 → 匹配度分析 + 角色投射 → 存 team_analyses，页内查看/历史列表
26. 我的激活码页：所属人视角显示「被谁激活/报告就绪/已授权」状态

## 四、开放问题（实施中遇到再定）

1. 会员折扣（85 折）对套餐是否适用 —— 会员上线前再定
2. 升级码交付后退款边界：暂定「升级码交付即已用不可退；含已用码的订单整单拒退」
3. 团队分析的 LLM 提示词与输出格式 —— P-E 设计时定
4. 赠品码被转送后，激活人看到的「所属人」展示名（邮箱脱敏？）—— P-E 定
5. vip_level 两档模型的 admin 可视化配置（当前走 .env：`LLM_VIP1_PROVIDER/MODEL`、`LLM_VIP2_PROVIDER/MODEL`，开发者可改；接入现有 /admin/model-config 页面做成 admin 可配是后续小任务）
