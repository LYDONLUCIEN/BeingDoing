# 提示词微调指南

本文档说明各提示词所在位置，便于进行微调。

## 1. 结论卡待展示时的动态注入（pending_conclusion 模式）

**文件**：`src/backend/app/domain/prompts/templates/pending_conclusion_reply.yaml`

**结构**：`system_prompt` + 对话消息（最多 40 轮）+ `prior_conclusion` + `conclusion_rules_and_goals` + 输出格式说明（放最后）

**用途**：当 `metadata.pending_conclusion` 存在时，将本内容作为**最后一条 user 消息**追加，要求主 LLM 先回应用户，再输出 `[REPLY]` 和 `[CONCLUSION_JSON]`。

**模板变量**：`prior_summary`、`prior_keywords`、`conclusion_rules_and_goals`

**如何查看动态加载的注入内容（测试用）**：
1. 在 `.env` 中设置 `DEBUG=True`
2. 启动后端，触发一次「结论卡待展示」的对话（需先有 `metadata.pending_conclusion`）
3. 在 tmux backend 窗口或日志中查看 `[pending_conclusion] 动态注入内容长度=...` 及完整内容
4. 或在 `simple_chat.py` 约 1692 行处加 `print(injection)` 或断点

**如何触发 pending_conclusion 流程**：`pending_conclusion` 由后台任务 `_background_completion_check` 在检测到「对话已完成但本轮未展示结论卡」时写入。一般需满足：用户消息 ≥5 轮或距上次展示 ≥3 轮，且 `check_dimension_complete` 返回结论。下一轮用户发消息时即进入本流程。

---

## 2. 各阶段结论卡重要原则（conclusion_rules）

**文件**：`src/backend/app/domain/conclusion_card_goals.py`

**变量**：`CONCLUSION_RULES` 字典

**用途**：每个 step（values/strengths/interests/purpose/rumination）的结论卡生成规则，会注入到：
- `pending_conclusion_reply.yaml` 中的 `conclusion_rules`
- `dimension_completion_checker.py` 的 `summary_prompt`

**可调内容**：按阶段修改 `CONCLUSION_RULES["values"]` 等键对应的字符串。

---

## 3. 结论卡生成提示词（check_dimension_complete）

**文件**：`src/backend/app/core/dimension_completion_checker.py`

**函数**：`check_dimension_complete` 内的 `check_prompt` 与 `summary_prompt`

**用途**：
- `check_prompt`：判断对话是否已完成该维度探索
- `summary_prompt`：生成结论卡的 `keywords` 和 `summary`

**可调内容**：
- 完成判断的 criteria 文案
- 汇总生成的 `summary_hint`、`goal_hint`
- 严禁杜撰的 `anti_fabrication` 段（约 290 行附近）
- `conclusion_rules` 通过 `get_conclusion_rules(phase)` 动态注入

---

## 4. 主对话 System Prompt（各阶段引导）

**文件**：`src/backend/app/api/v1/simple_chat.py`

**函数**：`_build_system_prompt`（约 770–993 行）

**用途**：values/strengths/interests/purpose/rumination 各阶段的主引导提示词。

**可调内容**：各阶段的大段咨询流程与重要准则。

---

## 5. 显式完成检测提示词

**文件**：`src/backend/app/core/dimension_completion_checker.py`

**函数**：`detect_explicit_completion` 内的 `prompt`（约 162–174 行）

**用途**：判断用户是否明确表示「就这样」「可以了」等，以提前弹出结论卡。
