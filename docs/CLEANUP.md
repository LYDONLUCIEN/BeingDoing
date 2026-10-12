# clean 分支整理任务与证据

## 需求依据（本次用户请求）

- 从最新 main（用户指定 1.8.0）创建 clean，开展全仓安全评估、旧代码/文档整合、无保留要求且已淘汰项删除，确保稳定性与可审查性。
- 形成清晰开发文档，重点对齐数据字段、关键变量和业务概念；参考 mattpocock/skills。
- 先做代码操作，暂不要求服务器 data/app.db。
- 后续明确：新产品共用账户与交易信息，支持月/年订阅，也可能一次性商品/购物车；激活码/报告可作为历史资源查询，新产品不一定发行它们。

## 基线与工作区

远端 main 与 v1.8.0 同为 e6181d4e8dc34270e6948d2c78695e6855931368。clean 从该提交建立，main 未修改。工作区为独立克隆 BeingDoing；原 openlife 中两个 HTML 文件、另一现有仓库及其本地数据均未改动。

## 整合方式

README 为人类入口；AGENTS/CLAUDE/CONTEXT/claude-开发文档保留短指针，避免外部工具链接失效。规范收敛到 CONTRIBUTING，业务语言/字段/当前规则分开，订阅方向形成 ADR-0024。纠正注册试用发放、有效期、退款、多次券、PDF 引擎等过期口径。

代码统一了会话/回答/管理员授权、导出标识和 Markdown 清洗。删除 analytics 不再调用的磁盘扫描兜底与 chat_optimized 未使用的旧 manager alias。全仓无导入的前端顶层 rehype-raw 6 依赖也已删除，UIW 自带的 7.x 解析器保留并在输出末端清洗。修复渲染器测试的私人绝对路径，以合成数据验证章节/分页不变式。

## 删除依据与保留例外

| 项目 | 证据 / 处理 |
| --- | --- |
| flow/page.tsx.backup | 仅旧 v2.4 文档提及恢复备份，当前探索入口为 `src/frontend/app/(main)/explore/chat/[phase]/page.tsx`；旧流程已替代，无单独保留要求，删除 |
| development-v2.4、TESTING_GUIDE_v2.4 | 已在历史文档目录、指向旧页面/备份恢复操作，现行指南取代；删除旧操作入口 |
| 0812-报告配色配置说明 | 只指导已删除 report_theme.json/WeasyPrint 样式，ADR-0021 与 0923 完成记录明确替代，删除；仍有历史引用处标记失效 |
| BeingDoing-整理文档 | 4 月清理方案与后续保留 .duplicate/原始笔记要求冲突，目录描述也失效，删除并用本台账替代 |
| output 下验证截图/脚本、根 preview PNG | 一次性本地截图/硬编码调试脚本，未被构建或运行代码引用；与 public 正式素材区分，删除并忽略后续 output |
| fixture 的 .json.lock | 25 个空 FileLock 哨兵，内容为零、可运行时重建；保留相邻 JSON 测试输入，删除并精确忽略 *.json.lock |
| .duplicate、data_backup/.bak | 后续 0726/0821 迁移手册明确要求保留历史快照，优先于 4 月删除建议；保留 |
| 会员、团队分析 page.impl | ADR-0006/0007 与当前规则明确保留/未上线，不按无 UI 引用删除 |
| v3 后端 | 第一轮曾按过渡要求保留；本轮维护者明确取消该保留，按 ADR-0025 完成运行链路退役，见下方第二轮台账 |
| 设计/原始资料、PNG 母版、report-renderer/dist | 保留源资料/母版与免构建部署产物；不改只读 report/xunlu |
| Alembic 迁移、运维脚本、历史 ADR | 回滚/存量升级/解释取舍仍有用途；保留并标注已被替代部分 |
| weasyprint 依赖 | ADR-0021 明确说保留给会话导出，但现代码 export_service 实际使用 reportlab；这是一处保留依据与实现冲突。本次遵守明确保留，待单独确认删除，不伪称仍在调用 |

删除前核对 git 跟踪列表、全仓文本引用、Next 路由/构建入口与相应历史记录；删除后跑相同后端基线对照、前端 lint/build、renderer 与安全回归。删除文件仍可由 v1.8.0 的 Git 历史恢复。

## Skills 选型与实际使用

参考 [官方 skills 仓库](https://github.com/mattpocock/skills)，没有全量安装远端脚本。

| Skill | 本次用途 |
| --- | --- |
| [domain-modeling](https://github.com/mattpocock/skills/blob/main/skills/engineering/domain-modeling/SKILL.md) | 纯业务词汇、字段字典分层，记录共享账户真实决定 |
| [codebase-design](https://github.com/mattpocock/skills/blob/main/skills/engineering/codebase-design/SKILL.md) | 将重复权限与文件边界收敛到小接口；未全面重写大路由 |
| [tdd](https://github.com/mattpocock/skills/blob/main/skills/engineering/tdd/SKILL.md) | 先复现越权/注入/令牌问题，再做公开行为回归 |
| [research](https://github.com/mattpocock/skills/blob/main/skills/engineering/research/SKILL.md) | 后台检索官方技能和依赖公告，应用条件与本地证据分开 |
| [writing-for-agents](https://github.com/mattpocock/skills/blob/main/skills/productivity/writing-for-agents/SKILL.md) | 简短根入口，按场景查阅，单一权威定义 |
| [code-review](https://github.com/mattpocock/skills/blob/main/skills/engineering/code-review/SKILL.md) | 对固定 v1.8.0 的差异做规范/需求两个维度独立复审，结果见 [REVIEW.md](REVIEW.md) |

未启动 grill/prototype/全面架构重做：当前已有明确清理授权，先把能由代码和历史自证的部分完成。订阅具体计费、权益、退款及券范围仍需产品定稿。

## 删除文件明细

```text
BeingDoing-整理文档.md
btn-preview.png
docs/历史文档/TESTING_GUIDE_v2.4.md
docs/历史文档/development-v2.4.md
output/login-page.png
output/verify-0922/01-values-default.png
output/verify-0922/02-appearance-panel.png
output/verify-0922/03-values-custom.png
output/verify-0922/04-values-reset.png
output/verify-0922/05-rumination-v4-classic.png
output/verify-0922/06-rumination-guided.png
output/verify-0922/07-rumination-studio-folio.png
output/verify-0922/08-rumination-debug.png
output/verify-0922/08-rumination-matrix-violet-solid.png
output/verify-0922/09-rumination-debug2.png
output/verify-0922/10-toolbar-final.png
output/verify-0922/11-matrix-violet-solid-fixed.png
output/verify-0922/12-guided-3col.png
output/verify-0922/13-guided-locked.png
output/verify-0922/14-confirm-test.png
output/verify-0922/debug-rumination.js
output/verify-0922/debug-rumination2.js
output/verify-0922/debug-zindex.js
output/verify-0922/final-check.js
output/verify-0922/guided-verify.js
output/verify-0922/repro-confirm.js
output/verify-0922/smoke.js
output/verify-1008-2-back-bottom.png
output/verify-1008-2-bottom.png
output/verify-1008-2-scrolled-up.png
output/verify-1008-v4-bottom.png
output/verify-1008-v4-entry.png
output/verify-1008-v4-scrolled-up.png
output/verify-1008-v4-seamless.png
output/verify-1008-v4-width-collapsed.png
output/verify-1008-v4-width-expanded.png
output/verify-1008-values-bottom.png
output/verify-1008-values-scrolled-up.png
output/verify-1008-values.png
output/verify-pay-cancel-close.png
output/verify-pay-confirm-v3.png
output/verify-pay-leave.png
output/verify-pay-mask-1-mask-wide.png
output/verify-pay-mask-2-real-qr.png
output/verify-pay-mask-3-close-confirm.png
output/verify-pay-mask-4-after-cancel.png
output/verify-pay-mask2-1-mask.png
output/verify-pay-mask2-2-real-qr.png
output/verify-pay-mask2-3-close-confirm.png
output/verify-pay-mask2-4-resume.png
src/frontend/app/(main)/explore/flow/page.tsx.backup
test/backend/fixtures/simple_chat_reports/snap_values_20260501_a/values__a9fd7197-640c-48e1-bdc0-59d53bc30761.json.lock
test/backend/fixtures/simple_chat_reports/snap_values_20260501_a/values__t_77363f869cb946bc8f20a7091f525fe4.json.lock
test/backend/fixtures/simple_chat_reports/snap_values_20260501_a/values__t_a83b06586ff444908567c828af5b1082.json.lock
test/backend/fixtures/simple_chat_reports/snap_values_20260501_conclusion_card_error_show/values__a9fd7197-640c-48e1-bdc0-59d53bc30761.json.lock
test/backend/fixtures/simple_chat_reports/snap_values_20260501_conclusion_card_error_show/values__t_551ac7540f484b5bac736e38aaac36f1.json.lock
test/backend/fixtures/simple_chat_reports/snap_values_20260501_conclusion_card_error_show/values__t_551ac7540f484b5bac736e38aaac36f1__note/note.json.lock
test/backend/fixtures/simple_chat_reports/snap_values_20260501_conclusion_card_error_show/values__t_77363f869cb946bc8f20a7091f525fe4.json.lock
test/backend/fixtures/simple_chat_reports/snap_values_20260501_conclusion_card_error_show/values__t_77363f869cb946bc8f20a7091f525fe4__note/note.json.lock
test/backend/fixtures/simple_chat_reports/snap_values_20260501_conclusion_card_error_show/values__t_a83b06586ff444908567c828af5b1082.json.lock
test/backend/fixtures/simple_chat_reports/snap_values_20260501_conclusion_card_repo_right/values__a9fd7197-640c-48e1-bdc0-59d53bc30761.json.lock
test/backend/fixtures/simple_chat_reports/snap_values_20260501_conclusion_card_repo_right/values__t_551ac7540f484b5bac736e38aaac36f1.json.lock
test/backend/fixtures/simple_chat_reports/snap_values_20260501_conclusion_card_repo_right/values__t_551ac7540f484b5bac736e38aaac36f1__note/note.json.lock
test/backend/fixtures/simple_chat_reports/snap_values_20260501_conclusion_card_repo_right/values__t_77363f869cb946bc8f20a7091f525fe4.json.lock
test/backend/fixtures/simple_chat_reports/snap_values_20260501_conclusion_card_repo_right/values__t_77363f869cb946bc8f20a7091f525fe4__note/note.json.lock
test/backend/fixtures/simple_chat_reports/snap_values_20260501_conclusion_card_repo_right/values__t_a83b06586ff444908567c828af5b1082.json.lock
test/backend/fixtures/simple_chat_reports/snap_values_20260501_conclusion_card_show/values__a9fd7197-640c-48e1-bdc0-59d53bc30761.json.lock
test/backend/fixtures/simple_chat_reports/snap_values_20260501_conclusion_card_show/values__t_77363f869cb946bc8f20a7091f525fe4.json.lock
test/backend/fixtures/simple_chat_reports/snap_values_20260501_conclusion_card_show/values__t_77363f869cb946bc8f20a7091f525fe4__note/note.json.lock
test/backend/fixtures/simple_chat_reports/snap_values_20260501_conclusion_card_show/values__t_a83b06586ff444908567c828af5b1082.json.lock
test/backend/fixtures/simple_chat_reports/snap_values_20260501_conclusion_reject/values__a9fd7197-640c-48e1-bdc0-59d53bc30761.json.lock
test/backend/fixtures/simple_chat_reports/snap_values_20260501_conclusion_reject/values__t_551ac7540f484b5bac736e38aaac36f1.json.lock
test/backend/fixtures/simple_chat_reports/snap_values_20260501_conclusion_reject/values__t_551ac7540f484b5bac736e38aaac36f1__note/note.json.lock
test/backend/fixtures/simple_chat_reports/snap_values_20260501_conclusion_reject/values__t_77363f869cb946bc8f20a7091f525fe4.json.lock
test/backend/fixtures/simple_chat_reports/snap_values_20260501_conclusion_reject/values__t_77363f869cb946bc8f20a7091f525fe4__note/note.json.lock
test/backend/fixtures/simple_chat_reports/snap_values_20260501_conclusion_reject/values__t_a83b06586ff444908567c828af5b1082.json.lock
v4card-preview.png
wiki/开发文档/0812-报告配色配置说明.md
```

## 第二轮：v3 运行链路与历史规范分离

维护者指出第一轮仍把 v3 与旧 combo_id 放进当前字段字典；本轮明确取消 v3 保留要求。这是第一轮整理不充分的修正，不能称第一轮已彻底清理。依据为用户明确指令、前端 v4 入口、ADR-0015，以及 [历史研究](HISTORY_EVIDENCE.md) 核对的 Git/issue 替代链。

| 删除/调整 | 核查与处理依据 |
| --- | --- |
| 七步沉淀、组合矩阵、3b/否定闸门、候选生成模块与10类旧接口 | 仅供退役 v3 调用；通用聊天写入口显式拒绝旧阶段。四阶段与 v4 回归分别验证 |
| A/B 分配服务及三项旧配置 | 前端已固定 v4；版本查询固定当前版，历史 ORM、迁移和账户删除仍认识旧表 |
| `rumination_ops` | 旧模块删除；v4 实际用到的四阶段输入提取移到 `rumination_inputs`，行为测试验证优先级 |
| `rumination_export` | 改为明确命名的历史只读导出器；删除自动补 v3 矩阵依赖，不写原数据 |
| scan/fix_combo_id_pollution 脚本 | 修复对象是已退役的旧矩阵索引，保留会误导后续开发继续生产旧结构 |
| 后台跳转、沙箱回退、批量报告生成 | 跳转只进入 v4；上游回退清理快照中下游状态，源数据不改；导出原生 v4，取消矩阵到 v4 的猜测转换 |
| 10个完整 v3 专用测试文件、旧 get-table 源码断言、1个 v3 回放场景 | 随产品能力退役；trial 旧入口测试改为410；新增退役拒绝/只读/原生导出回归。历史失败减少不计为修复 |
| 根规范、字段字典、ADR/历史入口 | v3 不再列为现行契约；历史保留为什么变和替代关系，不作为恢复指令 |

剩余 v3 字样逐类解释：历史证据与测试结果、历史消息读取/导出、既有数据快照、数据库旧表/迁移。当前 v4 同名 `combo_id` 有真实用途，定义为独立组合会话 ID。没有按文字搜索结果批量擦除数据。

本轮不修改 `.env`、`app.db`、真实 data、生产部署配置或历史迁移；代码可以通过 Git 回退，已有历史报告读取权不扩大。
