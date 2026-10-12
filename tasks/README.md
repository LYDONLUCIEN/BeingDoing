# 历史计划与任务材料

本目录保存具体时期的任务方案。它不是当前统一待办，也不会因正文写着“每次会话必须更新”“按顺序执行”而自动成为本轮工作指令。当前目标及约束以用户最新决定、[DECISIONS](../docs/DECISIONS.md)、[产品规则](../docs/PRODUCT_RULES.md)及[ADR状态](../docs/adr/README.md)核对；实现事实仍需源码、提交和验收证据。

| 原计划 | 当前阅读方式 |
| --- | --- |
| [Admin开发总指挥](admin-development-command-center.md) | 3月里程碑、独立子域与step-up目标；混有已做和待办。不要从“安全决策”标题推定所有现行接口都检查step-up，也不强制每次新任务更新旧清单。 |
| [Admin二期功能方案](admin-phase2-feature-plan.md) | 数据归属、报告和后台功能的设计来源；拟议表结构不是实际schema清单。当前筛选及运营标签见ADR-0023。 |
| [Admin子域逐步手册](admin-m1-1panel-step-by-step.md) | 特定旧环境的一次性接入手册；主机、域名与重启步骤不能直接复用。 |
| [Admin E2E清单](admin-e2e-checklist.md) | 可借鉴权限/资源隔离测试意图，先重写为当前接口与环境；未勾选不是本轮必须上线的任务。 |
| [支付模块计划](payment-module-plan.md) | 7月单SKU/永久一次券/回调确认计划已被套餐、主动查单、券期限、多次核销及退款设计替代；官方渠道与金额整数分原则仍须遵守。 |
| [套餐与试用计划](packages-trial-plan.md) | trial/full来源；自动绑定、早期价格、分档延期、审核随机时限和发码时点不能照抄。见ADR-0014/0016/0018与当前产品规则。 |
| [已消耗码去向计划](consumed-code-destination-plan.md) | 记录source/target追溯和展示意图；“按订单金额、不做每码分摊”是当次UI范围，已不能约束10月退款明细行分摊。是否完整实施需逐项核对，不把“设计已确认”当全部完成。 |
| [报告复核计划](report-review-plan.md) | 核心复核/staging/发布流已落地；用户生成失败重试与内容重生成分开，后台受权force明确保留。不要把UI标题扩大成删除运维能力的命令。 |

历史原因及替代提交见 [HISTORY_EVIDENCE](../docs/HISTORY_EVIDENCE.md)，GitHub状态与研究判定的区别见 [ISSUE_HISTORY](../docs/ISSUE_HISTORY.md)。新的执行计划应明确当前目标、依赖与验收，不自动恢复旧文档中已淘汰的v3或尚未开始的数据库/订阅迁移。
