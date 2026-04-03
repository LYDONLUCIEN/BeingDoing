# rumination2.0 改进方案（第 5 步）

## 0. 目标
根据 `uidesign/prompt/new-rumination.md` 与你给出的“Final Decision”截图，重构系统第 5 步 `rumination` 的：
1. 流程细节（表格步骤、每步可编辑列、确认后进入下一步的规则、过滤链路）
2. 对话交互（模块引导语、行点击对话、最终选择 top3 与结束）
3. UI 结构（左右分栏：左表格工作台 + 右侧对话；复用现有彩色渐变背景与对话气泡风格；表格做“白色高级质感磨砂玻璃”）

技术上尽量复用现有后端/表格处理/进度持久化架构：`rumination_progress.json`、`/simple-chat/rumination-xxx` API、`RuminationTableWidget` 的 payload 驱动方式、以及现有提示/LLM 工具链。

---

## 1. 当前实现（v1）梳理（基于仓库现状）

### 1.1 后端：进度与表格 payload
后端核心位置：
- `src/backend/app/api/v1/simple_chat.py`：`/rumination-progress`、`/rumination-get-table`、`/rumination-table-submit`
- `src/backend/app/utils/rumination_progress.py`：`filter_step` 1-9、`filter_table` 持久化
- `src/backend/app/utils/rumination_ops.py`：`gen_table / filter_strength / filter_match / hypotheses_round1-3 / value_filter / passion_filter / reality_filter / similar_filter`
- `src/backend/app/utils/rumination_table_widgets.py`：按 `step` 定义表头列、可编辑列、guideText，并构建 `table_widget` payload
- `src/backend/app/utils/rumination_hypothesis_service.py`：每行生成三条假设（3 条）

当前 `rumination_table_submit` 的主流程是“全量表格确认 + 后端确定性变换”：
1. 前端提交后端：带 `step`、`mode`（`full_step` 或 `single_row`）、以及 `table_data` 或 `row_id+patch`
2. 后端调用 `_rumination_advance_after_step_confirm(step, table, values_list, llm)`：
   - `step=1`：`filter_strength`（删“优势标记=不确定”行） -> `step=2`
   - `step=2`：`structure_hypothesis_round1_table`（删“匹配性=不匹配”行；删“匹配原因”；新增 `假设1-3`、`用户确认的假设`）并用 LLM 填充假设 -> `step=3`
   - `step=3/4/5`：多轮填充空行假设（round2/round3），仍以 `用户确认的假设` 文本输入为核心
   - `step=6`：`value_filter`（删空/待定的行；删 `假设1-3`；新增 `工作目的`）
   - `step=7`：`passion_filter`（删“工作目的=都不符合”；新增 `激情标记`）
   - `step=8`：`reality_filter`（删“激情标记=应该做”；新增 `现实标记`）
   - `step=9`：`similar_filter`（删“现实标记=未来”；仅保留 `id` + `用户确认的假设`）-> 进入 `final_choice`

注意：rumination 的 LLM streaming 系统提示（`simple_chat_system.yaml`）禁止 `pending_ready`，因此“最终结论卡/结束对话”不会像四维维度那样通过 `pending_ready` 自动生成。

### 1.2 前端：表格嵌在聊天流中
关键位置：
- `src/frontend/app/(main)/explore/chat/[phase]/page.tsx`
  - rumination filter 状态下拉取表格：`ruminationApi.getTable(... singleRowMode: true ...)`
  - 表格确认：`handleTableConfirm` -> `ruminationApi.submitTable` -> 用 `next_table_widget` 更新消息流中的 `table_widget`
  - 提交后触发一次 `handleSend()`：目前 follow 文案是：
    - 同步：`"我已确认表格，请继续。"`
    - 最终结果：`"筛选表格已更新为最终结果，请结合列表做最终选择。"`
  - 页面结构仍是通用“侧栏 + 单列对话区”，表格是以聊天消息气泡样式插入
- `src/frontend/components/explore/RuminationTableWidget.tsx`
  - 依据后端 payload 渲染列（`select` 或 `input`），并提供一个底部“确认”按钮
  - 目前没有实现“行点击选中态/行点击触发对话线程/逐行聚焦”的 UI 逻辑

### 1.3 表格可编辑列与 guide 文案（v1）
`rumination_table_widgets.py` 中：
- `step=1` 可编辑列：`["优势标记"]`
- `step=2` 可编辑列：`["匹配性"]`（但表头仍包含只读 `匹配原因`）
- `step=3/4/5` 可编辑列：`["用户确认的假设"]`（`假设1-3` 为只读文本列）
- `step=6` 可编辑列：`["工作目的"]`
- `step=7` 可编辑列：`["激情标记"]`
- `step=8` 可编辑列：`["现实标记"]`
- `step=9` 可编辑列：`["用户确认的假设"]`，并在这里完成“相似过滤”后只保留 `id+用户确认的假设`

---

## 2. 目标实现（rumination2.0）期望行为（基于 `new-rumination.md`）

### 2.1 页面结构与核心交互（截图复刻导向）
`uidesign/prompt/new-rumination.md` 强调：
- 页面两大区域：
  - 左侧：可编辑表格工作台（核心数据载体）
  - 右侧：对话框区域（模块引导 + 细节讨论）
- 表格与对话解耦但同屏并行；切换模块时由 AI 给出引导语（Cue）
- 行点击交互：用户可在整个流程中点击某行触发独立的“行级上下文对话”

截图“Final Decision”进一步要求：
- 左右分栏布局（左 table panel / 右 chat panel）
- 表格为白色高级质感磨砂玻璃风格（接近现有毛玻璃卡片，但需要更像截图）
- 行可选中并高亮（蓝色选中态至少在关键步骤可见）
- “确认”按钮在表格工作台区域内，且有明显启用/置灰状态（随步骤规则变化）

### 2.2 过滤弹窗步骤（文档版）
`new-rumination.md`（“方案润色后”）的过滤链路（以 `Confirm` 驱动推进）可概括为 6 个过滤步骤 + 最终选择：
1. （开场）进入准备：表格空、不可编辑，Confirm 禁用或置灰
2. 步骤一：热爱×优势组合展示（表格不可编辑；确认进入下一步）
   - 列：`id / 热爱 / 优势`
   - 该阶段强调“优势已过滤掉不确定优势”，因此不要求用户再编辑优势标记
3. 步骤二：匹配性分析
   - 新增列：`匹配性`（可编辑：匹配/不匹配）
   - 确认后删除“不匹配”行并推进
4. 步骤三：假设生成与选择（与 v1 最大差异之一）
   - 每行生成两个画面感假设：`option1(自由职业导向)`、`option2(公司职业导向)`，并支持 `custom`
   - UI：同一列“假设”下拉选择（`option1/option2/custom`）+ 可按行 regenerate
   - 确认后删除假设为空的行并推进
5. 步骤四：价值过滤
   - 新增列：`工作目的`（可编辑下拉：价值观关键词 + “无”）
   - 删除“无”行并推进
6. 步骤五：激情过滤
   - 新增列：`激情`（可编辑下拉：“应该做/忍不住想做”）
   - 删除“应该做”行并推进
7. 步骤六：现实过滤
   - 新增列：`现实`（可编辑下拉：“现在/未来”）
   - 删除“未来”行并推进
8. 最终选择：从剩余候选中选出 top3，并生成结论卡/结束

同时文档明确：
- 行点击对话要在“当前步骤主题 + 当前行数据”上下文下进行
- 对话结束条件：用户已选出 top3 并确认；然后调用 `end_conversation()` 生成 `conclusion_card`

> 注：`uidesign/prompt/new-rumination.md` 在“主题列表如下：”处似乎内容截断，导致“行点击对话”里的 `{{current_step_topic}}` 主题映射尚不完整。此点在后续落地实现中需要你补齐或我基于已知步骤约定推导。

---

## 3. 差异对比（v1 vs rumination2.0）

### 3.1 状态机与步数
- v1：`filter_step=1..9`（优势标记→匹配→假设 round1/2/3→价值→激情→现实→相似过滤）
- rumination2.0：过滤弹窗更接近 `step1..6 + final_choice`
  - 优势标记编辑被移除（优势在生成阶段自动过滤）
  - 假设不再用“多轮 round1~3 + 留空进入下一轮”的方式，而是变为“两选一+custom + 按行 regenerate”
  - 相似过滤（v1 step9）不出现在 `new-rumination.md` 最终候选形态中（final table 需要保留 `热爱/优势`）

影响点：
- `rumination_progress.py` 的 `FILTER_STEPS`、`DEFAULT_PROGRESS.filter_step`、以及前端进度展示需要同步调整
- `rumination_table_widgets.py` 的 step->列/可编辑列映射需要全量重做

### 3.2 表格列结构（列名与可编辑列集）
- v1 step1：`优势标记` 可编辑；列里只有 `id/热爱/优势/优势标记`
- rumination2.0：步骤一表格应只有 `id/热爱/优势`（不可编辑）

- v1 step2：列 `匹配性(可编辑)` + `匹配原因(只读，LLM 用于假设生成)`
- rumination2.0：UI 只关心 `匹配性(可编辑)`，匹配原因不一定要显示（但后端若仍需要，可继续保留在 `filter_table` 内不下发）

- v1 step3~5：`假设1/2/3(只读)` + `用户确认的假设(可编辑文本输入)`
- rumination2.0：单列 `假设(下拉：option1/option2/custom + custom 文本)`，并支持按行 regenerate

- v1 step6~8：列名分别为 `工作目的 / 激情标记 / 现实标记`，并在最终 step9 删到只剩 `id+用户确认的假设`
- rumination2.0：现实过滤后输出最终候选表 `id/热爱/优势/假设`，并把 `假设` 重命名为 `事业`，用于最终选择（不再删掉热爱/优势）

### 3.3 假设生成与交互方式
- v1：LLM 生成 3 条假设；用户在“用户确认的假设”里文本选择或留空；留空触发多轮 round2/round3；仍以 step推进代替“按行 regenerate”
- rumination2.0：每行生成 2 个固定类型假设（自由职业导向/公司职业导向），用户通过下拉选择或自定义；并且可以“按行 regenerate”刷新某个假设类型

影响点：
- `rumination_hypothesis_service.py` 需要改为“生成 2 条假设 + 支持指定类型的 regenerate”
- `rumination_ops.py` 的推进逻辑需要从“多步轮询空行”改为“单步生成 + 局部更新”

### 3.4 最终选择与结束对话/结论卡
- v1：filter 完成后只是更新 `main_section=final_choice` 并显示 step9 的 table_widget（`id + 用户确认的假设`）；之后完全依赖 LLM 自然语言问答
- v1：`simple_chat_system.yaml` 明确 rumination 禁止 `pending_ready`，因此不会自动生成 `conclusion_card`
- rumination2.0：要求在最终确认 top3 后调用 `end_conversation()` 生成 `conclusion_card`

影响点：
- 需要补齐“最终 top3 判定 -> 写入 conclusion_card -> 标记线程完成/解锁报告”的完整闭环
- 当前前端 `explore/chat/[phase]/page.tsx` 对 `RuminationSectionProgress` 只做进度展示，没有实现 final_choice/recommend/end 对应的 UI/按钮状态逻辑

### 3.5 行点击对话（row click）
- v1：`RuminationTableWidget` 没有行选择态、也没有 row_id 级别的对话触发能力
- rumination2.0：任何步骤都允许点击某行触发独立行级对话，且提示词需要包含 `current_step_topic + row 数据 + user_query`

影响点：
- 前端需要新增“表格行点击 -> 打开行级对话输入/弹层 -> 发送包含行上下文的消息”
- 后端 rumination streaming 请求模型目前只有 `activation_code/message/phase/thread_id`，不直接支持结构化 `row_context` 参数，因此需要在消息文本中拼装行上下文（或扩展后端请求 schema）

---

## 4. 改进方案（落地路径）

下面给出“最小风险的实现顺序”，同时确保每一步都能和截图/文档产生明显可见差异。

### 4.1 后端：重塑 rumination 过滤管道（核心）

#### 4.1.1 设计新的 filter_step 与最终表形态
建议保留 `main_section=filter` 与 `filter_table` 这一套持久化思路，但把 `filter_step` 由 1..9 调整为更贴近文档的 1..6（或 1..7 含相似可选）。

建议候选映射（可按你最终确认的版本微调）：
- `filter_step=1`：优势×热爱组合生成并待确认（下发列：`id/热爱/优势`）
- `filter_step=2`：匹配性分析确认（下发列：`id/热爱/优势/匹配性`）
- `filter_step=3`：假设生成与选择确认（下发列：`id/热爱/优势/假设`）
- `filter_step=4`：价值过滤确认（下发列：`id/热爱/优势/假设/工作目的`）
- `filter_step=5`：激情过滤确认（下发列：`id/热爱/优势/假设/激情`）
- `filter_step=6`：现实过滤确认（下发列：`id/热爱/优势/事业(由假设重命名)` 或 `假设` 待 rename）
- `filter_complete -> main_section=final_choice`：下发最终只读表（用于 top3 选择）

#### 4.1.2 引入“标记式过滤”（filtered）与调试友好日志
你提出的关键想法是：`similar_filter`（以及后续过滤链路）不直接删行，而是由后端在 `filter_table` 中为每一行写入“是否被过滤”的标记字段 `filtered`；前端渲染时仅根据 `filtered` 状态决定显示与否，但行的内容依旧保留在 `filter_table` 里以便 debug。

为保证命名与步骤完全可对应，建议统一引入以下行字段（存储在 `rumination_progress.filter_table` 的每个 row 内）：

- `filtered: boolean`：该行是否从当前步的“可见列表”中被排除（默认 `false`）
- `filtered_step: number | null`：本次被过滤的步号（new-rumination 的 1-6；若你在实现阶段额外引入内部 step9 则可扩展），便于追溯
- `filtered_reason: string | null`：过滤原因枚举（如 `match_not`、`hypo_empty`、`value_none`、`passion_should`、`reality_future`）

同时，建议在 `rumination_progress.json` 顶层新增一个 step 日志字段，用于满足“只要记录每次不同 step 过滤了哪些行 id”的要求：

- `filter_step_logs: Array<{ step: number, filtered_row_ids: string[], reason: string }>`

其中：
- `filtered_row_ids` 只包含“本 step 刚刚从 `filtered=false` 变为 `filtered=true` 的行 id”
- `reason` 对应上面的 `filtered_reason` 枚举

工程收益：
- 前端渲染可以稳定复刻“文档的裁剪效果”，同时不丢失任何原始候选（用于 debug）
- 任何一步出现“结果不对”，可以通过 step 日志快速定位具体行 id

#### 4.1.3 调整 `rumination_progress.py`
- 更新 `FILTER_STEPS`、`DEFAULT_PROGRESS.hypothesis_round`（如不再需要可移除或不再使用）
- 保留向后兼容：建议在 `schema_version` 引入新版本号，避免旧 `rumination_progress.json` 解析异常
 - 并补充字段 `filter_step_logs` 以及行级字段初始化（每行默认 `filtered=false`）

#### 4.1.4 调整 `rumination_table_widgets.py`
- 重写 step->columns 与 `EDITABLE_COLS` 映射
- UI payload 的目标列集必须和 `new-rumination.md` 一致（尤其是 step1/step3/最终表）
- 为匹配原因/假设原文等“后端需要但 UI 不展示”的字段，支持在 `filter_table` 内保留，但不下发到 `columns`
 - 在 payload 的 rows 中保留 `filtered` 字段，前端据此隐藏不可见行（但仍能在 debug 模式展开查看）

#### 4.1.5 调整 `rumination_ops.py` 与 `rumination_hypothesis_service.py`
1. 优势过滤与匹配过滤
在不改变现有 LLM 文案生成逻辑的前提下，把 v1 的“删行函数”改为“标记行函数”：
 - `filter_strength`：当 `优势标记=不确定` 时，把该行 `filtered=true`，并写入 `filtered_step=1` 与 `filtered_reason=strength_uncertain`
 - `filter_match`：当 `匹配性=不匹配` 时，把该行 `filtered=true`，并写入 `filtered_step=2` 与 `filtered_reason=match_not`
 - 其它列字段继续按当前 v1 逻辑补齐（不要删掉，只是标记不可见）

2. 统一“按 step 配置的过滤选项”机制（严格对应 new-rumination 的 1-6）
你提出的点是对的：`filter` 是贯穿每一步的能力，并不只发生在“相似合并”。

因此建议将“过滤判定”抽象成通用入口：`apply_filter_marks_for_step(step, table, config)`，其中 config 由每个 step 的“被视为过滤的选项”配置驱动：
- step2：字段 `匹配性` 命中选项 `不匹配` -> `filtered=true`
- step3：字段 `假设` 为空（用户未选择/未填入）-> `filtered=true`
- step4：字段 `工作目的` 命中选项 `无` -> `filtered=true`
- step5：字段 `激情` 命中选项 `应该做` -> `filtered=true`
- step6：字段 `现实` 命中选项 `未来` -> `filtered=true`

说明：new-rumination 的 step1 是“展示热爱×优势组合”且优势已在上游预过滤为不含“不确定”；因此 step1 不再需要对行进行 filtered 标记（因为不确定优势对应的组合根本不会进入表格）。

这样就不需要用“相似合并”这个概念去解释 step2~6 的筛选语义：它们全部是“选择不合适就排除”的语义；new-rumination 的 1-6 流程里没有独立的 step9。

3. 假设生成与最终表产出（step3/step6）
假设生成逻辑保持：`rumination_hypothesis_service.fill_hypothesis_columns_for_table` 仍负责生成假设文本（对应 UI 的假设 option1/option2/custom），只是下游筛选不再依赖“step9 相似过滤”。

最终产出规则（step6 confirm 后）：
- 后端执行 filtered 标记后，生成 `final_table`：
  - 保留：`id / 热爱 / 优势 / 假设`
  - 并将 `假设` 重命名为 `事业`（供最终选择 top3 使用）

（如果你在实现阶段仍想复用 v1 的 step9 代码结构，可以把它当作内部实现细节：UI 仍只展示 new-rumination 的 final_table，不暴露 step9。）

4. 日志与字段契约保持
`rumination_hypothesis_service.fill_hypothesis_columns_for_table` 仍负责生成 `假设1/假设2/...`（或 rumination2.0 的 option1/option2），只是后续不再靠“删行”来让行消失，而是靠 `filtered` 控制可见性。

4. 状态推进与 next_table_widget
`/rumination-get-table` 在构建 payload 时：
 - columns 不变（仍按 step 决定展示列）
 - rows 返回“全量”，但 UI 侧根据 `filtered` 隐藏
- step6 confirm 后 backend 产出 `final_table`（`假设` -> `事业`），用于进入最终选择 top3；new-rumination 的 1-6 流程不依赖独立 step9。

5. 日志写入
每次 filter step 完成时，把当步新产生的“从 false->true”的行 id 写入 `filter_step_logs`。

----

如果你希望进一步严格对齐 `new-rumination.md` 的“删行语义”，也可以在前端提供一个 admin/debug 开关：
- 默认隐藏 filtered 行
- debug 模式下显示 filtered 行但以灰色、带 reason hover 展示

#### 4.1.6 调整 `simple_chat.py` 的 rumination 接口响应策略
- `/rumination-table-submit` 与 `/rumination-get-table` 的主要契约仍是返回 `progress` 与 `next_table_widget`
- 但需要确保：
  - `next_table_widget.rows` 包含 `filtered` 字段（便于 UI 隐藏）
  - `progress.filter_step_logs` 同步持久化（用于 debug）

---

#### 4.1.7 命名-步骤对照（严格对应 new-rumination 的 1-6）
为了避免实现时出现命名歧义，建议明确以下对应（只覆盖 1-6）：

- step2（匹配性过滤“删除不匹配”）
  - `filtered_reason = match_not`
- step3（假设选择后“假设为空的行被过滤”）
  - `filtered_reason = hypo_empty`
- step4（价值过滤“选择无 -> 删除无”）
  - `filtered_reason = value_none`
- step5（激情过滤“删除应该做”）
  - `filtered_reason = passion_should`
- step6（现实过滤“删除未来”）
  - `filtered_reason = reality_future`

这样前端通过 `filtered` 就能复现 new-rumination 的“看见的集合变化”，同时后端保留完整数据用于 debug。

---

#### 4.1.8 调整 `rumination_table_widgets` 中的列与可见性规则
由于 rows 保留全量，建议前端表格渲染增加：
- `hideFilteredRows=true` 默认启用
- `showFilteredInDebug`（可选）当开启时，显示 filtered=true 的行，但在样式上降低可见性并展示 reason

---

至此你提出的“similar_filter 为后端标记能力 + LLM 整理 + 前端 filtered 渲染 + 保留内容 + 日志只记 filtered ids”的要求都已形成一套可落地的数据契约。

#### 4.1.9（兼容性说明）原有 v1 ops 的替换策略
实现上不建议一次性大改所有 filter_* 名字，避免大规模 diff 风险。你可以：
- 保留现有函数名作为入口，但在内部从“删除/裁剪”改为“标记/保留”
- 在新代码里新增显式函数名（如 `mark_strength_filter`、`mark_reality_filter`、`similar_merge_marking`），逐步迁移

---

#### 4.1.10 调整 `rumination_ops.py` 与 `rumination_hypothesis_service.py`（旧条目补充，保留为参考）
1. 优势过滤：
   - 如果你坚持文档“优势列表已过滤掉不确定优势”：
     - 需要增强 `extract_from_prior_context()`，从 strengths 的 prior 文本中提取“标签=不确定”的优势并排除
     - 否则将无法自动完成过滤，仍只能回退到 v1 的“用户在 rumination 内再标记不确定”的方式
2. 假设生成：
   - 改成“一次生成两条假设（option1/option2）”
   - 新增 regenerate 能力：
     - `regenerate_hypothesis(row_id, hypo_type)`（其中 hypo_type 对应自由职业/公司职业）
3. 状态推进：
   - 去掉 v1 的 `hypothesis_round=1..3` 多轮机制，改为：
   - `filter_step=3` 一次生成并允许用户选择/自定义
   - confirm 后对“假设为空”行写入 `filtered=true` 并推进（保留内容用于 debug）

> 工程建议：为了复用现有表格“整表 submit”流程，`regenerate` 可以作为扩展 endpoint，或作为 `rumination-table-submit` 的一种 `mode=single_row` + patch 语义实现（但需要明确后端 patch 字段契约）。

#### 4.1.11 调整 `simple_chat.py` rumination 接口响应策略
- `/rumination-table-submit` 的 response 中 `next_table_widget` 仍使用 payload 驱动前端渲染
- `next_action` 需要扩展：
  - 在文档模式下，确认后的 follow 文案要与当前模块强绑定（比如进入假设选择模块、进入价值过滤模块等），避免现在的通用 `"我已确认表格，请继续。"`
- 对于最终 top3 结束，需要提供一种“后端生成 conclusion_card / 标记 thread 完成”的机制（目前不存在）

### 4.2 前端：重构 rumination 页面布局与表格交互（强制对齐截图）

#### 4.2.1 新增 rumination2.0 布局组件（左右分栏）
改动点：
- `src/frontend/app/(main)/explore/chat/[phase]/page.tsx`
  - 在 `phase === 'rumination'` 时，分支渲染一个自定义布局，隐藏通用的 `ChatPhaseSidebar`
  - 页面主体区域使用 flex row：
    - 左：表格工作台（glass panel）
    - 右：对话框区域（沿用现有气泡/输入框组件与流式消息渲染）

复用点：
- `ChatPhaseBackground`：用于截图的彩色渐变背景（rumination 主题色已存在）
- `flow-chat-light.css`：用户白泡、AI 气泡、输入框的样式可以直接复用（只需要重新排版位置）

#### 4.2.2 升级 `RuminationTableWidget`（v2）
当前 `RuminationTableWidget` 存在三类缺口：
1. 没有行点击选中态
2. 没有行点击触发对话的回调
3. 不支持“假设下拉 + custom 文本 + regenerate 图标”的复合单元格交互

建议改为：
- 新增 `RuminationTableWidgetV2` 或在现有组件上扩展 payload schema：
  - 列类型支持：`select` / `text` / `hypothesis_select`（或 `composite`）
  - 行支持：`onRowClick(row)`、`selectedRowId`
  - 支持“按行操作列”或把 regenerate 图标渲染在假设单元格右侧

Confirm 逻辑：
- `disabled` 不再只与 `sending` 绑定，而要与 `editableCols`/`step` 规则绑定
- 用户点 confirm 后：
  - 立即冻结表格输入（disabled=true）
  - 等待后端返回 `next_table_widget` 后再解冻并替换表格

#### 4.2.3 行点击对话（row click）
建议在前端实现为：
1. 用户点击表格某行 -> 记录 `selectedRow`
2. 右侧聊天区域弹出“行级对话输入/小弹层”
3. 用户输入后，前端把消息组装成带上下文的文本（因为后端 streaming schema 目前不支持结构化 row_context）
   - 消息内容包含：
     - 当前模块主题（由前端根据 `filter_step` 映射得到）
     - 被点击行 `row` 的关键字段
     - 用户本次 `user_query`

---

## 5. 验收清单（对照截图与文档）
建议你在实现后按下面检查：
1. rumination 页面呈现左右分栏：左表格面板 + 右对话面板，且背景/气泡/输入框风格与现有一致
2. 表格：
   - step1：只有 `id/热爱/优势`，不可编辑但 Confirm 可点击（符合文档）
   - step2：仅 `匹配性` 可编辑，下拉选项匹配/不匹配
   - step3：`假设` 为 option1/option2/custom 下拉 + custom 输入；每行可 regenerate
   - step4/5/6：`工作目的/激情/现实` 分别为下拉并标记过滤对应不符合的行（`filtered=true`，内容保留）
   - reality 之后最终表仅用于 final choice，并把 `假设` 重命名为 `事业`（代表行保留、其余行 `filtered=true`）
3. 行点击对话：
   - 点击某行后，右侧能开启并引导“针对该行”的对话（至少 UI 上能看出上下文变更）
4. 最终 top3：
   - 用户完成 top3 选择并确认后：出现 `conclusion_card`，并能解锁进入下一步/报告（闭环可达）

---

## 6. 关键风险与待确认点
1. `uidesign/prompt/new-rumination.md` 在“主题列表如下：”处截断，导致行点击对话的 `current_step_topic` 映射规则不完整
2. “结束对话并生成 conclusion_card”目前 v1 并未在 rumination 流程里实现（rumination 禁止 `pending_ready`，所以需要新增结束闭环机制）
3. 若要做到“优势列表已过滤掉不确定优势”，必须增强 strengths prior 的解析能力；否则只能回退到 v1 那种 rumination 内用户再标记

--- 

## 7. 建议的实现顺序（从可见差异到闭环）
1. UI 层：先做 rumination 左表+右聊布局（不改后端逻辑也能先复刻截图结构）
2. 后端表格列集与流程：把 step1~step6 的列和可编辑列集改成文档版本
3. 假设交互：实现“两选一+custom+按行 regenerate”
4. 行点击对话：实现行级对话输入弹层与消息组装
5. 最终 top3 闭环：补齐 conclusion_card 生成与线程完成/解锁报告

