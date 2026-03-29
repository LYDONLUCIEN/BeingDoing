# Rumination 过滤机制与表格真源 — 实施计划（2026-03-29）

> 依据：`uidesign/prompt/rumination_prompt.md` 与当前代码 `rumination_progress.py`、`rumination_ops.py`、`simple_chat.py`（rumination 相关路由与流式对话）。  
> **约定**：前四维（values / strengths / interests / purpose）的 `simple_chat_system.yaml` **本次不修改**，由产品/你本地自行维护。本计划只动 **rumination 链路、表格 JSON、相关 API 与前端沉淀页**。

---

## 一、目标摘要

1. **Rumination 不再使用 values 题库**：提问素材来自用户在前四维**已确认的结论/关键词**（与 md「主页面回顾 + 筛选」一致），通过 `prior_context` / 结构化快照注入系统提示，**禁止** `_get_question_bank_phase(rumination) -> values`。
2. **底层维护「全量表格」JSON**：唯一可写的工作副本放在 **rumination 专用存储**（见下文路径约定），**只增改该 JSON**；**绝不回写**各 phase 独立会话文件、结论卡落盘内容或用于生成 `prior_context` 的只读锚点原文。
3. **前端「一次只展示一行」**：每一步内用户逐行确认（或按行聚合 UI），每次「确认」调用后端；后端对**全量表**应用确定性变换 + 持久化，并返回「下一行 / 下一步 / 是否提前结束」。
4. **实装 md 中的过滤链**：在现有一、二步基础上，补齐假设三轮、`value_filter`、`passion_filter`、`reality_filter`、`similar_filter`；**若某步已无行可处理，则跳过或提前进入下一步/结束**，避免空转。
5. **结束前展示「用户筛选后的完整表格」**：主对话或专用 UI 块展示 `filter_table` 最终快照（md 第九步后仅 `id` + `用户确认的假设` 或你们约定的最终列集）。

---

## 二、数据边界（硬约束）

| 数据 | 是否可被 rumination 写入 |
|------|---------------------------|
| `data/.../reports/{report_id}/` 下各 step 对话 JSON、结论卡消息 | **否**（只读，用于回放与 prior） |
| `prior_context` 生成所依赖的锚点/报告摘要（若单独文件） | **否** |
| **`rumination_progress.json`**（及可选 `rumination_table_full.json`） | **是**（唯一工作区） |

**全量表**建议字段扩展（在 `rumination_progress` 内或并列文件二选一）：

- `filter_table`：**当前完整行列表**（所有行、所有当前列），与 md 各步列演进一致。
- `filter_step`：1–9，对应 md 筛选弹窗步骤。
- `filter_row_cursor`（新增）：当前「单行确认」游标（0-based 或 1-based，团队统一即可）；完成一步后可能重置为 0 进入下一步。
- `main_section`：`opening` → `review` → `filter` → `final_choice` → `recommend` → `end`（与现有 `MAIN_SECTIONS` 一致）。
- 可选：`hypothesis_round`（1–3）在 step 3–5 内子状态，避免仅靠 `filter_step` 表达不清。

**原则**：任何 `submit` 只更新 **rumination** 的 progress + 全量表；若需「从全量表删行」，只改 `filter_table` 内存与 JSON，**不**去改 strengths 等 phase 的原始结论。

---

## 三、与 `rumination_prompt.md` 的步骤对齐（实现映射）

| MD 步骤 | 函数（后端） | 用户操作 / 提前结束 |
|--------|--------------|---------------------|
| 1 生成并确认 | 已有 `gen_table` + `filter_strength` | 标记「不确定」行删除；若删后 **0 行** → 提前结束或提示回到回顾补数据 |
| 2 匹配 | 已有 `filter_match`；用户改「匹配性」后提交 | 删除「不匹配」行在进入 step3 时做（见 `generate_hypotheses_round1`） |
| 3 假设第一轮 | **新增** `generate_hypotheses_round1` | 需 **LLM** 为每行生成 `假设1-3`；空「用户确认的假设」进入 round2 |
| 4 假设第二轮 | **新增** `generate_hypotheses_round2` | 仅更新空行假设 |
| 5 假设第三轮 | **新增** `generate_hypotheses_round3` | 仍空则标「待定」 |
| 6 价值过滤 | **新增** `value_filter(table, values)` | 下拉来自 **values 关键词列表**（从 prior 解析，非写回） |
| 7 激情过滤 | **新增** `passion_filter` | 删「都不符合」于 step6；本步填「忍不住/应该」 |
| 8 现实过滤 | **新增** `reality_filter` | 删「应该做」于 step7 |
| 9 相似过滤 | **新增** `similar_filter` | 删「未来」；合并行可由用户编辑后整表提交 |

**提前停止**：每一步提交后计算「剩余行数」；若为 0，则 `filter_step` 跳至 **结束筛选** 或进入 `final_choice`，并在响应里带 `early_terminated: true` 与原因枚举。

---

## 四、假设三轮：确定性 vs LLM

- **结构性变更**（删列、加列、删行）：**纯 Python**，与现有一、二步一致，可单测。
- **假设1/2/3 文案**：md 要求「头脑风暴」，应走 **LLM**（与 `simple_chat` 同 provider 配置），输入：该行 `热爱`、`优势`、（可选）匹配原因、用户价值观摘要；输出：三条短假设，写入该行；失败时降级为模板占位（并打日志），避免卡死流程。

建议新增内部服务模块，例如 `rumination_hypothesis_service.py`，由 `rumination_table_pipeline.py` 调用，**不**放在 `message/stream` 里混写过长逻辑。

---

## 五、API 设计（建议）

在现有基础上演进（路径可保持 `/simple-chat/` 前缀）：

1. **`GET /rumination-progress`**  
   返回扩展字段：`filter_table`、`filter_step`、`filter_row_cursor`、`main_section`、（可选）`pending_row` — 仅一行给前端展示。

2. **`POST /rumination-table-submit`（重构语义）**  
   请求体建议扩展为：
   - `activation_code`, `thread_id`
   - `filter_step`（当前 md 步骤 1–9）
   - `mode`: `single_row` | `full_step`（兼容以后整表确认）
   - `row_id` + `patch`（单行模式：只改该行的可编辑列）
   - 或 `table_data`（整表模式：与现行为兼容）

   响应：
   - `progress`（更新后）
   - `next_action`: `same_step_next_row` | `advance_step` | `show_full_table` | `enter_final_choice`
   - `display_row`（下一行快照，单行模式）
   - `full_table_preview`（可选，用于最后展示）
   - `next_table_widget`（与现前端 `RuminationTableWidget` 对齐的 payload）

3. **`GET /rumination-get-table`**  
   与 `progress` 一致：优先读已持久化的 `filter_table`；无则 `gen_table(prior strengths, passions)` 初始化并 **写回** progress（仅 rumination JSON）。

4. **（可选）`GET /rumination-final-table`**  
   只读返回筛选结束后的完整表，供报告页 / 对话内嵌展示。

**流式对话 `/message/stream`（rumination）**：  
- 系统提示改为 md 主流程 + **禁止**注入 values 题库块；注入「四维关键词摘要」段落。  
- `STATE_JSON` 保持仅 `continue`（或后续若要做「主流程阶段机」可扩展专用字段，但与表格提交解耦，避免与结论卡协议混淆）。

---

## 六、前端改造要点（`chat/[phase]/page.tsx` 等）

1. **进入 `rumination` 且 `main_section == filter`**：拉 `GET rumination-progress` 或 `getTable`，拿到 `display_row` 或自行用 `cursor` 切片 `filter_table[0]`。
2. **`RuminationTableWidget`**：  
   - 单行模式：只渲染一行 + 当前步可编辑列（与 md「每次弹窗只编辑指定列」一致）。  
   - 确认 → `submitTable` 带 `row_id` + `patch`；根据响应更新本地状态或拉新 progress。
3. **筛选结束后**：在对话区或独立卡片 **渲染完整最终表**（`full_table_preview` 或 `filter_table` 最终列）。
4. **`RuminationSectionProgress`**：`main_section` / `filter_step` / `filter_row_cursor` 展示需与后端同步更新（提交成功后 `ruminationApi.get` 或直接用 submit 返回）。

---

## 七、后端文件级修改清单（实施顺序建议）

| 顺序 | 文件 / 目录 | 内容 |
|------|-------------|------|
| 1 | `rumination_progress.py` | 扩展默认结构与 `save/load` 字段；版本号或 `schema_version` 便于迁移 |
| 2 | `rumination_ops.py` | 实现 `generate_hypotheses_round1/2/3`、`value_filter`、`passion_filter`、`reality_filter`、`similar_filter`；补全单测 |
| 3 | 新建 `rumination_hypothesis_service.py`（或 `rumination_pipeline.py`） | 编排步骤、调用 LLM、提前终止判断 |
| 4 | `simple_chat.py` | 重写 `rumination_table_submit` / `rumination_get-table`；`_get_question_bank_phase` 对 rumination 返回空或专用占位；`_build_system_prompt` rumination 分支注入四维关键词、去掉题库 |
| 5 | `simple_chat_system.yaml`（仅 `rumination` 段） | 对齐 `rumination_prompt.md` 主流程文案（开场、回顾顺序、筛选与最终选择）；**不动**其它 phase |
| 6 | 前端 `rumination.ts` + `page.tsx` + `RuminationTableWidget` | 单行提交与最终全表展示 |
| 7 | `docs/`（可选） | API 与状态机说明（若你希望文档同步） |

---

## 八、测试与验收

1. **单元测试**：每个 `rumination_ops` 函数：输入表 JSON → 期望行数、列集合、边界（空表、全「不确定」、全「不匹配」）。
2. **集成测试**：伪造 `prior_context` + 初始化表 → 模拟多次 `submit` 贯穿 1–9 或提前终止。
3. **回归**：确认 values/strengths/interests/purpose 的对话文件与结论卡在多次 rumination 操作后 **字节级不变**（或哈希对比抽样）。
4. **验收**：用户可见「逐行确认 → 全表最终结果」；网络失败时 progress 不丢（锁与现有 `ConversationFileManager` 模式一致）。

---

## 九、风险与备注

- **LLM 假设生成延迟**：需超时与降级文案，避免阻塞单行提交。  
- **prior 解析**：`extract_from_prior_context` 仍为启发式；若关键词提取失败，应有明确 UI 提示「请在前序阶段完成确认」而非静默用占位词。  
- **与 Admin Fork / 双根数据**：`reports_root` 继续用 `get_effective_simple_root(rec)`，计划不变。  

---

## 十、本次不做的范围（明确排除）

- 修改 **values / strengths / interests / purpose** 的 `simple_chat_system.yaml` 正文（由你自行编辑）。  
- 在 rumination 中 **写回** 各 phase 结论卡或锚点原文。  
- 将表格状态写入 **数据库**（除非后续产品要求；当前仍以 report 目录 JSON 为准）。

---

*文档结束。实施时可在本文件勾选阶段并记录 PR 链接。*