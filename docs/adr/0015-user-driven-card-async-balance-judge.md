# ADR-0015: rumination v4 结论卡改为用户主导填写 + 平衡点判定移交独立后台 AI

**状态**: accepted
**日期**: 2026-08-06
**决策者**: 产品 + 开发 Grill（grill-with-docs 会话收敛）
**取代**: CONTEXT.md「平衡点」「v4 结论卡区」「沉淀 v4 提示词权威来源」中 7-25/7-28 版的工程协议口径（chips、tool 写卡、主对话 LLM 判定 balance）

## 背景

7-25 版 v4 中，结论卡由**主对话 LLM** 通过隐藏 tool 块（`save_conclusion_card`/`update_field`）自动填写，平衡点判定（`balance_found`/`balance_fail_reason`）也由主对话 LLM 在对话过程中「后台」写入；假设候选通过 `[STEP3_HYP_JSON]` chips 协议推送。该模型有两个问题：

1. **用户是结论的旁观者**：探索的终极产出（职业方向结论）由 AI 代笔落卡，用户只点「确认」， ownership 弱，与「引导而非灌输、绝不可代替用户做决定」的咨询准则存在张力。
2. **主对话 LLM 职责过载**：同一个 LLM 既要当咨询师（可见话术），又要当书记员（tool 写卡），还要当裁判（判平衡点）——三重职责互相干扰，tool 协议/双信号/兜底出卡等工程补丁层层叠加，prompt 维护成本高、行为不稳定。

## 决策

- **主对话回归纯咨询**：`rumination_v4_prompt.py` 只保留原生 md 流程 + 少量硬约束；chips 协议、tool 调用协议、出卡双信号、兜底出卡**全部删除**。找到平衡点后，AI 用话术复述总结并**引导用户把结论填入左侧结论卡**。
- **结论卡用户主导**：卡面仅 `hypothesis` 一个字段，用户手写、可修改，确认前为草稿态；motivation/work_purposes/passion_mark/timing_mark 字段废弃。
- **平衡点判定移交独立后台 AI**：用户点「确认」触发异步判定，输入 = 热爱/优势组合 + hypothesis + 该组合完整对话（超长时滚动摘要压缩早期），咨询师视角自由裁量（维持「无机械规则」），输出 `{balance_found, balance_fail_reason}` 落库。
- **判定生命周期**：判定绑定确认时快照——之后任何新对话或改卡，结果即作废，需重新确认重判。分析期间该组合锁卡+锁对话输入（可切换/新建其他组合）；失败自动重试 1-2 次，仍失败则「分析失败，点击重试」，视同未完成。进程重启后 running → failed。
- **状态同步**：确认端点本身即 SSE 流（推 done/failed）；刷新/重进页面见 running 态自动补开订阅 SSE（可降级短轮询）。
- **完成门槛**：「完成并继续」要求所有已确认卡判定完成且结果未作废，否则提示「正在分析中，请稍后」；未确认草稿卡、已跳过卡不参与检查。不推荐不阻断，仅琥珀灯+理由+终选 ⚠ 警告条。

## 后果

- 后端：新增 BALANCE_JUDGE prompt 与异步判定服务（组合级状态机 analyzing/done/failed/stale）；删除 `extract_hyp_candidates`、`parse_tool_blocks`、`apply_tool_call`、`detect_conclusion_signals`、`fallback_generate_conclusion` 及 `hyp_candidates`/`conclusion_card` 等 SSE 事件；确认/重试端点改为 SSE 流式；`rumination_v4_progress.json` 的 combo 增加判定状态字段。
- 前端：删除 `V4HypChipsSelector` 与 store 的 `latestHypCandidates`；结论卡组件重写为三态状态机（草稿/分析中/已判定）+ 绿/琥珀灯；「完成并继续」前检查全部已确认卡的判定状态。
- 主对话不再有任何隐藏块协议，流式 hidden-block 过滤器在 v4 链路可移除。
- 权衡接受：判定结果不再「随对话即时翻转」，用户需显式确认才触发判定（即时性 ↓，可解释性与用户主导权 ↑）；异步判定引入 SSE 重连/失败重试复杂度（换取主对话 LLM 职责单一化）。
- v3 链路（rumination_prompt_strings.py 等）不受影响；AB 分组机制不变。
- 存量 v4 进度数据（含旧 conclusion_card 多字段）需兼容读取：多余字段忽略即可，无需迁移。
