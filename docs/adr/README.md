# 决策记录索引

ADR 解释为什么这样做，按决定发生时的范围阅读；当前行为入口为 [产品规则](../PRODUCT_RULES.md)。2026-10-05 退款、10-06 多次券定稿已替代早期对应细则，详见产品规则链接。

| 决策 | 当前阅读提示 |
| --- | --- |
| [ADR-0003: Step3 组合矩阵与深度讨论拆分](0003-step3-combo-matrix.md) | v3 背景，后端兼容保留 |
| [ADR-0004: Rumination v4 页壳刻意偏离 HTML mock](0004-rumination-v4-shell-layout.md) | 历史决定，实施范围请读正文 |
| [ADR-0005: 支付走官方双线接口（微信+支付宝），而非静态收款码人工确认](0005-payment-dual-channel-official-gateway.md) | 历史决定，实施范围请读正文 |
| [ADR-0006: 激活码与会员是两条独立产品线，高级模型权益购买时固化](0006-membership-vs-activation-code-two-product-lines.md) | 会员预留，未上线，要求保留 |
| [ADR-0007: 会员体系按真实代扣设计，本期只交付表与接口、不对外开放](0007-membership-built-but-not-launched.md) | 会员预留，未上线，要求保留 |
| [ADR-0008: 套餐体系取代单一 SKU，激活码分试用/完整双维度](0008-packages-trial-vs-full-codes.md) | 历史决定，实施范围请读正文 |
| [ADR-0009: 报告阻塞式审核 + 随机时限自动批复](0009-report-review-auto-approve.md) | 历史决定，实施范围请读正文 |
| [ADR-0010: 激活码双角色（所属人/激活人）与报告授权边界](0010-code-purchaser-activator-report-auth.md) | 历史决定，实施范围请读正文 |
| [ADR-0011: 存储演进路线——稳定性收敛 → SQLite 全量入库 → 条件触发 PostgreSQL](0011-storage-evolution-sqlite-then-postgres.md) | 演进路线，尚未全量入库 |
| [ADR-0012: 品牌更名——寻路 (xunlu) → 寻路·OpenLife (openlife)](0012-rebrand-xunlu-to-openlife.md) | 历史决定，实施范围请读正文 |
| [ADR-0013: 统计看板——事件时间口径漏斗 + 埋点业务同库（SQLite），不建 Cohort、不提前上 PG](0013-analytics-funnel-event-time-sqlite.md) | 历史决定，实施范围请读正文 |
| [ADR-0014: 套餐交付改为全量未绑定码 + 消耗升级，年度套餐调价 ¥159](0014-unbound-delivery-consume-to-upgrade.md) | 历史决定，实施范围请读正文 |
| [ADR-0015: rumination v4 结论卡改为用户主导填写 + 平衡点判定移交独立后台 AI](0015-user-driven-card-async-balance-judge.md) | 历史决定，实施范围请读正文 |
| [ADR-0016: 延期体系改版 —— 首次过期免费送 7 天 + 付费续期统一 9.9 元/7 天](0016-free-7day-renewal-and-9.9-paid-renewal.md) | 历史决定，实施范围请读正文 |
| [ADR-0017: 报告后处理修正管线 —— 一次生成 + 按章节分步修正](0017-report-post-processing-pipeline.md) | 历史决定，实施范围请读正文 |
| [ADR-0018: 套餐码有效期改为「支付成功起算」+ 团队分析联系邮箱变量化](0018-package-validity-starts-at-purchase.md) | 新套餐有效期从交付起算 |
| [ADR-0019: 报告 PDF 渲染接入 xunlu 精简渲染器（子进程 + 开关共存）](0019-xunlu-pdf-renderer.md) | 双引擎部分被 0021 替代 |
| [ADR-0020: 旧浏览器内核兼容底线——视口高度 vh→dvh 回退与新 CSS 特性静态回退](0020-old-browser-kernel-compat-floor.md) | 历史决定，实施范围请读正文 |
| [ADR-0021: 移除 WeasyPrint 简洁版，xunlu 设计版成为唯一报告渲染引擎](0021-single-xunlu-report-renderer.md) | 历史决定，实施范围请读正文 |
| [ADR-0022: 静态性能皮肤——装饰动画与磨砂玻璃对全员移除](0022-static-performance-skin.md) | 历史决定，实施范围请读正文 |
| [ADR-0023: 通用用户筛选系统（过滤器注册表 + schema 下发）](0023-user-filter-registry.md) | 历史决定，实施范围请读正文 |
| [ADR-0024：跨产品共用账户，交易与产品权益分离](0024-shared-account-product-boundaries.md) | 共享账户边界已接受，实现另行设计 |
