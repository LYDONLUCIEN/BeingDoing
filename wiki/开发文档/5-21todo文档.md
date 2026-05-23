# 5-21 开发 Todo 文档

> 来源：`wiki/开发文档/5-20新的todo.md`（10 条）  
> 梳理方式：按领域归类 + 代码核查 + grill-me 决策树  
> 状态：**Grill + Triage 对齐完成** — 可拆 Issue / 按 P0→P1 实施

---

## 归类总览

| 分组 | 编号 | 主题 | 优先级 | 类型 |
|------|------|------|--------|------|
| A 数据一致性 | R5-21-01 | 多对话删除异常 / 删后复现 | P0 | Bug 排查 |
| B 阶段体验 | R5-21-02 | 「完成并继续」后祝贺弹窗仍出现 | P1 | 逻辑 / 产品 |
| C 使命阶段 | R5-21-03 | 04 使命：经历匹配价值观重复提问 | P1 | 提示词 / 状态 |
| C 使命阶段 | R5-21-04 | 使命结论卡 keywords 混入价值观+擅长 | P1 | 生成逻辑 |
| D Rumination 引导 | R5-21-05 | 假设步骤引导语顺序（阶段 vs 子步） | P1 | 体验 / 文案 |
| D Rumination 引导 | R5-21-07 | 假设步骤引导语仍是老版本 | P1 | 文案 / 配置 |
| D Rumination 引导 | R5-21-06 | 表格操作后 AI 主动确认（新逻辑） | P1 | 新功能 |
| E Rumination 深度讨论 | R5-21-08 | 匹配阶段深度讨论条数 / 内容不一致 | P1 | neg_gate 机制 |
| F Rumination 假设行逻辑 | R5-21-09 | 第一组未聊完第二组已出现 | P1 | cursor / 提示词 |
| F Rumination 假设行逻辑 | R5-21-10 | step3 说 pass 跳过整组而非逐行 | P1 | 行级解锁 |

**依赖关系（建议实施顺序）**

```
R5-21-01（数据根因） ──► 其余可并行
R5-21-05 / R5-21-07（引导语口径统一） ──► R5-21-06（新主动引导）
R5-21-09 / R5-21-10（step3 行逻辑） ──► 与 R5-21-06 共用 ROW_STATE / cursor 协议
R5-21-08（深度讨论） 独立，但与 step2 表格 id 口径相关
```

---

## A. 数据一致性与删除

### R5-21-01 · 删除单个对话却批量消失，刷新后对话复现

| 字段 | 内容 |
|------|------|
| **问题描述** | 用户反馈：存在多个对话时，删除其中一个会导致侧栏大量对话一并消失；过段时间再回看，被删对话又出现。怀疑与服务器环境、数据未迁移、旧数据结构有关。 |
| **原因猜想** | **代码已核查，存在多条 plausible 路径，不单是「服务器环境问题」：**<br>1. **后端删除本身是单条**：`POST /simple-chat/thread/delete` 只 `unlink` 一个 `{phase}__{thread_id}.json`，并从 `record.json` 的 `session_ids` 移除该 id（`report_registry.remove_session`）。<br>2. **删后复现的高风险路径**：线程列表为空时，前端 init effect 会无 `thread_id` 调 `GET /history`；若磁盘仍残留 `{phase}__{act_sid}.json`（历史迁移遗留），会把旧对话「恢复」为 `__history_fallback__` 线程（`page.tsx` L700–717）。后端 delete 在 `session_ids` 清空时会尝试删 act_sid 残留，但**多线程只删一条时**其他 thread 文件仍在，不应批量删——若用户看到「批量消失」，更可能是 **前端 localStorage 与后端 `remaining_thread_ids` 不同步** 或 **网络失败后回退过期缓存**（`sessionRecovery` L304–308、`page.tsx` L653–667）。<br>3. **未迁移数据**：旧 report 若 `session_ids` 与磁盘文件不一致（重复 id、act_sid 与 t_xxx 混用），删除/同步会出现「删了还在、或一次少很多条」的错觉。<br>4. **沉淀阶段特殊**：rumination 侧栏会 `collapseRuminationThreadsToOne`，多线程在 UI 上本就会折叠成一条，易误解为「删一条没了好多」。 |
| **修复目标** | 1. **删除语义对用户 = 彻底消失**；对系统 = 可审计、可排查（软归档，非裸删）。<br>2. 单删一条时：`record.json`、对话文件、localStorage 三处 **原子一致**；禁止 init fallback 从 act_sid / orphan 恢复。<br>3. 前四阶段 + rumination **统一删除 API 与回归用例**（场景 A 为主，B/C 同测）。<br>4. report 数据体检脚本：对齐 `session_ids` 与磁盘文件；兼容旧格式迁移。<br>5. 删除失败时 UI 明确报错，不回滚成「假成功」。 |
| **决策内容** | ✅ **已定稿（2026-05-21）**<br><br>**场景：** 主反馈来自 **前四阶段多对话侧栏（A）**；用户可能仍携带 **旧 report / 旧 session_ids 格式**，网络或缓存问题会放大症状，但 **当前删除链路本身 UX 不合格**，需整体重做而非仅归因环境。<br>**范围：** 修复与测试覆盖 **A + B（rumination）+ C（旧数据/缓存回退路径）**。<br><br>**删除策略（推荐并已采纳方向）：软归档，非物理抹除**<br>- 用户侧：前端二次确认 → 后端成功后，该 thread **从列表与 history 永久不可见**（等同「彻底清空」体验）。<br>- 后端侧：将 `{phase}__{thread_id}.json`（及 `.lock`）**移动到** `reports/{report_id}/.deleted_threads/{phase}/{thread_id}_{deleted_at}/`，并写 `manifest.json`（操作者、时间、原路径）；同步从 `record.json` 的 `session_ids` 移除。<br>- **不推荐**直接 `unlink` 硬删：误删无法支撑客服/审计；旧格式排查无样本；与「删了又回来」对账困难。<br>- 管理员可选 **90 天后 purge trash**（非 MVP 必须）。<br><br>**同步修复（必做，与归档并行）：**<br>1. 禁止 `session_ids` 为空时无 `thread_id` 的 history fallback 复活已删会话。<br>2. 删除 API 返回 authoritative `remaining_thread_ids`；前端 **仅**以此更新 localStorage。<br>3. 数据体检脚本 + 可选管理端「orphan / 不一致」列表。<br><br>**实现优先级：** P0 — 与 R5-21-02 同属体验硬伤。 |

---

## B. 阶段完成弹窗

### R5-21-02 · 「不再提醒」后进入下一轮仍弹祝贺窗

| 字段 | 内容 |
|------|------|
| **问题描述** | 用户勾选「不再提醒」并完成并继续进入下一阶段后，祝贺弹窗仍然出现。期望：勾选一次后，该激活码内不再出现。 |
| **原因猜想** | **与 4-27 todo #10 一致，当前实现与产品预期不一致：**<br>1. 持久化 key 为 **按阶段**：`bd_phase_complete_dismiss_${activationCode}_${phase}`（`page.tsx` L1813–1815、L1894）。<br>2. 弹窗触发点在 **结论卡确认** `handleConfirmConclusion`，**不是** 顶栏「完成并继续」`handleCompleteAndContinue`（后者直接 `router.push('/explore/transition?from=…')`，不读 dismiss flag）。<br>3. 因此：在 values 勾选不再提醒，进入 strengths 后 **仍会弹**（新 phase 新 key）。<br>4. rumination 阶段 **根本不展示**「不再提醒」勾选（L3810：`dontRemindLabel` 为 undefined）。 |
| **修复目标** | 1. 同一 `activationCode` 勾选一次「不再提醒」，五阶段均不再弹。<br>2. **仅 localStorage** 持久化（`bd_phase_complete_dismiss_${activationCode}`）；接受清缓存后可能再弹。<br>3. rumination 也展示勾选框。 |
| **决策内容** | ✅ **已定稿（2026-05-21；T5 补充）**<br>按激活码全局 dismiss；**不**做后端持久化（用户场景下很少清缓存，实现从简）。 |

---

## C. 使命阶段（Purpose）

### R5-21-03 · 04 使命：经历可匹配多个价值观，AI 仍重复问同一问题

| 字段 | 内容 |
|------|------|
| **问题描述** | 某段经历已匹配 1 个或多个价值观时，AI 仍重复追问同一匹配问题。 |
| **原因猜想** | 1. **提示词允许一对多**：`simple_chat_system.yaml` purpose 流程 L171–175 明确「一段经历可以匹配多个价值观」。<br>2. **重复问因**：模型未维护「已处理经历清单」；无结构化 state 记录当前是第几条经历；或 `[STATE_JSON]` / 结论草案协议未携带 `experience_value_rows` 进度，导致每轮仍像「第一条」。<br>3. **「一次一问」与「多价值观确认」张力**：流程要求一次一问，但多价值观需多轮确认，模型可能用同一模板句复述。<br>4. **对话续写约束**（L203）禁止重复开场，但不保证经历索引推进。 |
| **修复目标** | 1. **一行经历 ↔ 多个价值观**：`experience_value_rows` 为 `{ experience, values: string[] }`。<br>2. **`purpose_progress` 持久化**（对话文件 metadata）：已完成 N/10、当前经历序号、已确认 rows；每轮注入 `[内部·使命进度]`。<br>3. 同一段经历一次说清多个 values 并确认后 **不得再问**。 |
| **决策内容** | ✅ **已定稿（2026-05-21；T3 补充）**<br><br>**数据结构：** 一行经历 + `values[]` 数组；展示一行多 tag。<br><br>**进度存储：** 写入 **当前 thread 对话文件 metadata**（字段如 `purpose_progress`），不写入 report 顶层；续聊/刷新从 metadata 恢复后再注入 prompt。<br><br>**提示词：** 已确认经历标记完成 → 直接下一条。 |

---

### R5-21-04 · 使命结论卡 keywords 出现「价值观 + 擅长」混合

| 字段 | 内容 |
|------|------|
| **问题描述** | 使命结论卡上 keywords 标签出现价值观词与擅长词混在一起；预期 keywords 仅为使命核心词 / 用户提及的价值观，不应含擅长。 |
| **原因猜想** | 1. **schema 定义**：purpose 的 `keywords` 应为「使命相关核心词 1~10 个」（`conclusion_card_payload.py` L382）；结构化匹配在 `experience_value_rows[].value`。<br>2. **混入来源**：LLM 生成草案时把 prior_block 四维摘要或 values+strengths 摘进 keywords；或 `final_answer` 回退拼接了错误字段；或用户对话里 mission 表述引用了优势词被原样收录。<br>3. **展示层**：`DimensionConclusionCard` 直接渲染 `data.keywords`，purpose 阶段 **无** 单独过滤 strengths 词。<br>4. **与 rumination 取词不同**：rumination step4 用 `resolve_values_keywords` 严格来源标记；purpose 结论卡无同等校验。 |
| **修复目标** | 1. purpose 结论卡 **keywords = 本阶段实际出现的 values 子集**（不含 strengths）。<br>2. `experience_value_rows` 新写 `{ experience, values[] }`；**读兼容**旧 `{ experience, value }` → `values: [value]`。<br>3. 可选 **迁移脚本**批量规范化历史 purpose 结论卡。 |
| **决策内容** | ✅ **已定稿（2026-05-21；T4 补充 C）**<br><br>**keywords：** values 阶段 5 词之子集，本阶段实际出现才展示。<br><br>**schema 兼容：** 实现层读旧 `value` 自动转 `values[]`（逻辑简单则必做）；另提供 **一次性迁移脚本** 规范化磁盘数据。新写入只用 `values[]`。 |

---

## D. Rumination 引导语

### R5-21-05 · 假设步骤：应先整段 rumination 引导，再 step 引导

| 字段 |  content |
|------|------|
| **问题描述** | 第五轮进入「假设步骤」（filter step 3）时，右侧 AI 应先给出 **整个 rumination 的心理预期/总览**，再给出 **第一个 step 的操作引导**。需确认当前顺序。 |
| **原因猜想** | **当前链路（`rumination_step_guidance.py` 文档化）分三层，互不自动串联：**<br>1. **阶段弹窗**：`step_copy.yaml` → `rumination.intro_zh`（进入 rumination 时一次性）。<br>2. **对话首条**：`POST /init` → `synthesize_rumination_entry_greeting()`（entry_init，含 prior_block）。<br>3. **子步引导**：表格确认后 `playRuminationStepOpeningAfterSubmit` → step opening（step3 为 **fixed** 文案，`STEP_OPENING_FIXED_ZH[3]`）。<br><br>**缺口**：用户从 step2 确认进入 step3 时，**只会播放第 3 层**，不会 replay 第 2 层总览；若用户未细读弹窗/首条，会感觉「直接进假设细节」。 |
| **修复目标** | 1. step2→step3 切换时，右侧 **只出现一条** 合并引导（总览 + 操作，约 200 字内）。<br>2. 更新 `STEP_OPENING_FIXED_ZH[3]`（或等价 fixed 文案），不拆两条、不重复阶段弹窗/entry_init 全文。<br>3. 内容须含：本步在七步中的位置、逐行聊假设、左侧「无/填写假设」、确认后进入下一步。 |
| **决策内容** | ✅ **已定稿（2026-05-21）：方案 C**<br>进入 step3 时 **一条消息** 合并「短版 rumination 上下文 + step3 操作说明」；不采用 A（两条）或 B（仅操作、无过渡）。 |

---

### R5-21-07 · 假设步骤右侧引导语仍是老版本

| 字段 | 内容 |
|------|------|
| **问题描述** | rumination 假设步骤（step3）右侧引导语与当前产品不一致，「不太对」。 |
| **原因猜想** | 1. **step3 opening mode = fixed**（`STEP_OPENING_MODE[3] = "fixed"`），不走 LLM；文案为 `STEP_OPENING_FIXED_ZH[3]`（逐行解锁、选「无」或填假设）。<br>2. **LLM system 模板** `STEP_3_OPENING_SYSTEM_ZH` 仍描述 **「两个推荐假设 + 重新生成按钮 + 自定义」** 旧 UI，fixed 模式下虽不用，但 **主对话 addon**（`RUMINATION_CHAT_STEP_ADDON_ZH`）与 neg_gate 仍可能引用旧口径。<br>3. 与 4-27 todo UI#6 改名（自定义/无）可能未全部同步到 opening 文案。 |
| **修复目标** | 1. **彻底删除**「两个推荐假设」「🔄 重新生成」「自定义二选一」等旧 UI 表述。<br>2. 统一改写：`STEP_OPENING_FIXED_ZH[3]`、`STEP_3_OPENING_SYSTEM_ZH`（备用）、`RUMINATION_CHAT_STEP_ADDON_ZH[3]`、neg_gate step3 相关片段。<br>3. 新口径：逐行解锁；假设列 **「无 / 填写假设」**；右侧对话与当前行联动；填完本行再进下一行。 |
| **决策内容** | ✅ **已定稿（2026-05-21）：方案 A**<br>以 **fixed 文案 + addon 全链路重写** 为准，**不**改 LLM opening；**完全按新流程**，不得残留旧假设生成/ regenerate 描述。与 R5-21-05 合并一条引导文案一并落地。 |

---

### R5-21-06 · 【新功能】表格操作后 AI 主动询问「是否填好」

| 字段 | 内容 |
|------|------|
| **问题描述** | step3 假设：用户在表格操作后（选「无」、假设框回车、编辑后失焦、自拟内容确认），右侧 AI 应 **主动** 问是否填好；用户确认后继续下一假设。 |
| **原因猜想** | **当前无此主动触发**：行解锁依赖用户 **发消息** 或 AI 输出 `[ROW_STATE_JSON]` / `_try_rumination_step3_auto_unlock`（假设字段完整则 cursor+1）。表格 UI 变更 **不会** 自动发 chat 或 opening。 |
| **修复目标** | 1. **仅 step3**：表格变更 → 右侧 AI 主动追问（填假设场景）。<br>2. **填假设路径：** 用户 **文字回复**确认 → ROW_STATE / cursor+1。<br>3. **选「无」/ pass 路径：** 表格选「无」→ **逐行**解锁下一行，**无需**文字确认（见 R5-21-10）。<br>4. **不加**「本行完成」按钮。 |
| **决策内容** | ✅ **已定稿（2026-05-21，T1 补充）**<br>- **范围：** 仅 step3。<br>- **填假设：** 文字回复确认后进下一行。<br>- **选「无」/跳过：** 逐行 +1，免文字确认；**固定短句**提示换行（非 LLM）。<br>- **不加按钮。** |

---

## E. Rumination 深度讨论（neg_gate）

### R5-21-08 · 匹配阶段：仅 1 条需深度讨论，AI 却聊 2 条且编造选项

| 字段 | 内容 |
|------|------|
| **问题描述** | filter step 2（匹配性）：用户认为只有 1 条「不匹配」需深度讨论，进入后 AI 聊了两条，且其中一条与用户表格选项不符。需弄清传入深度讨论的行内容、index 是显示索引还是原始索引。 |
| **原因猜想** | **机制梳理（代码）：**<br>1. **采集**：`collect_step2_mismatches` 遍历 **filter_table 全表**，凡 `匹配性 == "不匹配"` 的行进入 `items`（含 `id`、`热爱`、`优势`、`label`）。<br>2. **索引**：使用 row 的 **`id` 字段**（字符串，通常为生成表时的稳定 id），**不是** UI 显示序号；UI 行号与 `id` 可能不一致。<br>3. **传入深度讨论**：`rumination_neg_state.items` 最多 20 条；`build_injection_zh` 注入 **编号列表**；**无 `current_item_index` 程序字段**，靠提示词要求「逐条、不跳过」。<br>4. **聊 2 条**：可能实际有 2 行「不匹配」（含用户未注意到的一行）；或 LLM 违反「一次一条」合并/编造第二条。<br>5. **选项不一致**：注入的是提交时 `pending_table_submit.table_data` 快照；若用户弹窗后改表未同步，或 AI  hallucinate 了「匹配性」取值，会出现偏差。 |
| **修复目标** | 1. `rumination_neg_state` 增加 **`current_index`**（0-based），深度讨论 **一次只注入当前条**。<br>2. UI 显示「第 i / N 条」+ 当前条字段，与表格 row id 绑定。<br>3. **进下一条（双通道）：** ① 用户文字「这条聊完了 / 下一条」；② AI 回复末尾 `[NEG_ITEM_DONE]`（对用户不可见）— 任一触发 `current_index+1`。<br>4. 全部聊完 →「结束讨论」；禁止 AI 聊列表外条目。step 2/3/5/6 同机制。 |
| **决策内容** | ✅ **已定稿（2026-05-21；T2 补充 A+C）**<br>程序逐条推进；index+1 由 **用户口头** 或 **AI 隐藏标记** 触发，不加「下一条」按钮。 |

---

## F. Rumination 假设步骤行级逻辑（Step 3）

### R5-21-09 · 第一组未讨论完，第二组已出现

| 字段 | 内容 |
|------|------|
| **问题描述** | 假设步骤中，第一组（行）尚未讨论完，第二组已在表格或对话中出现。希望完整了解提示词与解锁机制。 |
| **原因猜想** | **机制梳理：**<br>1. **行解锁**：`filter_row_cursor`（0-based）；仅 `cursor` 行可编辑；`redact_step3_rows_for_widget` 脱敏后续行。<br>2. **推进条件**：AI 输出 `[ROW_STATE_JSON]{row, state:confirmed}[/ROW_STATE_JSON]` 且 row==cursor 且假设列完整（「无」或自填）→ cursor+1；或 **auto_unlock** 在 AI 回复后检测当前行假设完整则 cursor+1（可能 **抢跑**）。<br>3. **对话侧**：`format_step3_row_context_block` 注入当前行；filterStep 消息隔离；若 cursor 被误增，右侧会切到下一「热爱×优势」组合。<br>4. **「组」语义**：若指同一「热爱」下多行优势，cursor 逐行推进；若 AI 提前输出下一 row 的 ROW_STATE 或 auto_unlock 误判「无」为完整，会 **跳组**。 |
| **修复目标** | 1. **关闭 auto_unlock（默认）**，cursor+1 由明确规则驱动；保留 **单变量/feature flag** 可重新开启（`RUMINATION_STEP3_AUTO_UNLOCK_ENABLED`，默认 `false`）。<br>2. **「一组」= 同一「热爱」下的多行**；禁止 pass 一次跳过整组，必须 **逐行** cursor+1。<br>3. 选「无」：cursor+1 + **固定短句**换行（非 LLM）+ context 同步刷新。<br>4. 填假设：R5-21-06 主动问 + 文字确认。 |
| **决策内容** | ✅ **已定稿（2026-05-21；T1/T6 补充）**<br><br>**auto_unlock：** 现阶段 **关**；单变量可重开。<br><br>**「一组」：** 同一热爱下多行；pass **逐行**，禁止跳组。<br><br>**pass / 选「无」：** 固定短句换行（非 LLM），免文字确认。<br><br>**换行/对话 context：** **不**额外强调「仍在同一热爱」；只报 **第 N 行** + 标准字段格式（如「热爱：xx / 优势：xx」），与现有 step3 提示词、`format_step3_row_context_block` 口径一致。<br><br>**填假设：** AI 问 + 用户文字确认。 |

---

### R5-21-10 · step3 用户说 pass，跳过整组热爱；表格进下一行但对话进下一组合

| 字段 | 内容 |
|------|------|
| **问题描述** | step3 用户对某行说 pass/跳过：期望 **逐行** 跳过；实际跳过 **整组热爱**；表格 cursor 进下一行，但右侧对话 **直接进入下一个热爱组合**（行与对话不同步）。 |
| **原因猜想** | 1. **「无」= 行级跳过**：`is_rumination_step3_row_hypothesis_complete("无")` 为 true，应只解锁 **当前行**。<br>2. **pass 口语**：模型可能理解为「跳过整个热爱维度」，在 ROW_STATE 或回复中带 **错误 row index**，或一次 cursor += 多步（未见代码有多步，但 AI 可输出 row=cursor+1）。<br>3. **表格 vs 对话不同步**：表格 widget 跟 `filter_row_cursor`；对话 context 跟 `[内部·子步3当前行]`；若 chat 未 reload context 而 cursor 已变，会出现 **表进一行、对话跳组合**。<br>4. **neg_gate step3**：若用户未填假设就点确认，pending_rows 会进深度讨论，与「pass」路径交叉。 |
| **修复目标** | 1. pass / 「无」：仅 cursor+1，禁止按热爱批量 skip。<br>2. 选「无」后：固定短句换行 + context 与表格同步。<br>3. 口语 pass → 引导表格选「无」。 |
| **决策内容** | ✅ **已定稿（2026-05-21）**<br>与 R5-21-09 合并实现。核心：**逐行跳过，不跳组**；「无」路径免文字确认；填假设路径仍要文字确认。 |

---

## 附录 A · Rumination 引导语三层（现状）

```
进入 Rumination 阶段
  ├─ [1] 阶段弹窗：step_copy.yaml / rumination.intro_zh
  ├─ [2] 对话首条：entry_init（LLM + prior_block）
  └─ 每子步表格「确认」后
        └─ [3] 子步 opening：step 1–7（step3=fixed，其余 mostly llm）
              └─ 主对话持续：RUMINATION_CHAT_STEP_ADDON_ZH[step]
```

## 附录 B · Step3 行解锁（定稿后目标）

```
filter_row_cursor = k（逐行；「一组」= 同一热爱下多行，但 cursor 仍每次 +1）

选「无」/ pass：
  → 表格选「无」→ cursor = k+1（免文字确认，禁止按热爱批量 skip）
  → 右侧插入 **固定短句**（非 LLM）：「好的，这条我们先跳过。请看左侧第 N 行…」
  → 对话 context 随 cursor 同步刷新

填假设：
  → AI 主动问 → 用户文字确认 → ROW_STATE → cursor = k+1

auto_unlock：默认关（RUMINATION_STEP3_AUTO_UNLOCK_ENABLED=false），单变量可开作验证
```

## 附录 C · 深度讨论 neg_gate（定稿后目标）

```
表格确认（step 2/3/5/6）→ collect_* → 弹窗
  → deep_start：neg_state.status=exploring，items[] + current_index=0
  → 仅注入 items[current_index] 进 system
  → 聊完当前条 → index+1 触发（双通道）：
       ① 用户文字：「这条聊完了 / 下一条」
       ② AI 末尾 [NEG_ITEM_DONE]（不可见）
  → index >= len(items) 或用户「结束讨论」→ deep_end / continue → submit
```

---

## Grill-me 进度

| 条目 | 状态 |
|------|------|
| R5-21-02 祝贺弹窗「不再提醒」 | ✅ 方案 A（按激活码，全阶段生效） |
| R5-21-01 删除对话异常 | ✅ 场景 A 为主 + B/C 同测；**软归档** + 同步/fallback 修复 |
| R5-21-03 使命重复提问 | ✅ 一行经历多价值观 + A′ 进度块 |
| R5-21-04 使命结论卡 keywords | ✅ 方案 B：本阶段实际出现的 values 子集 |
| R5-21-05 假设步骤引导语顺序 | ✅ 方案 C：一条合并引导 |
| R5-21-07 假设步骤引导语老版本 | ✅ 方案 A：去掉旧 UI，fixed+addon 全链路重写 |
| R5-21-06 表格操作后 AI 主动确认 | ✅ 仅 step3；填假设=文字确认；选「无」=逐行免确认 |
| R5-21-08 匹配阶段深度讨论 | ✅ 方案 A：current_index 程序逐条 |
| R5-21-09 / R5-21-10 step3 行解锁 | ✅ auto_unlock 关（可配置）；一组=同热爱多行；无=逐行免确认 |

**Grill-me：10/10 条均已定稿。** 见下方实施优先级摘要。

---

## 实施优先级摘要（定稿后）

| 优先级 | 编号 | 概要 |
|--------|------|------|
| P0 | R5-21-01 | 软归档删除 + fallback/同步修复 + 四阶段+rumination 回归 |
| P0 | R5-21-02 | 按激活码全局「不再提醒」 |
| P1 | R5-21-03 / 04 | 使命：一行多 values + 进度块；keywords=本阶段 values 子集 |
| P1 | R5-21-05 / 07 | step3 合并引导 + 去旧文案 |
| P1 | R5-21-06 / 09 / 10 | step3 行解锁：填假设需文字确认；选「无」逐行免确认；auto_unlock 关（flag） |
| P1 | R5-21-08 | neg_gate `current_index` 逐条深度讨论 |

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-05-21 | 初稿：自 5-20 todo 归类 + 代码核查 + 决策树 |
| 2026-05-21 | R5-21-02 定稿：方案 A（按激活码全阶段不再提醒） |
| 2026-05-21 | R5-21-01 定稿：前四阶段为主；软归档 + fallback/同步/体检脚本 |
| 2026-05-21 | R5-21-03 定稿：一行经历多价值观 + A′ 进度块 |
| 2026-05-21 | R5-21-04 定稿：keywords = 本阶段实际出现的 values 子集 |
| 2026-05-21 | R5-21-05 定稿：方案 C，step3 一条合并引导 |
| 2026-05-21 | R5-21-07 定稿：方案 A，去掉旧假设/regenerate 文案 |
| 2026-05-21 | R5-21-06 定稿：仅 step3；填假设文字确认；选「无」免确认 |
| 2026-05-21 | R5-21-08 定稿：方案 A，neg_gate current_index 逐条 |
| 2026-05-21 | R5-21-09/10 定稿：auto_unlock 关+flag；一组=同热爱多行；逐行 pass |
| 2026-05-21 | **全部 10 条 grill 定稿完成** |
| 2026-05-21 | Triage：追加「待对齐清单」与第二轮 grill 会话 |
| 2026-05-21 | T1 定稿：step3 选「无」→ 固定短句换行（非 LLM） |
| 2026-05-21 | T2 定稿：neg_gate index+1 = 用户文字 + AI `[NEG_ITEM_DONE]` 双通道 |
| 2026-05-21 | T3 定稿：使命进度存对话 metadata `purpose_progress` |
| 2026-05-21 | T4 定稿：values[] 读兼容 + 迁移脚本（C） |
| 2026-05-21 | T5 定稿：「不再提醒」仅 localStorage |
| 2026-05-21 | T6 定稿：换行仅第 N 行 + 热爱/优势标准字段，不强调同热爱组 |
| 2026-05-21 | T8 定稿：GitHub Issue 拆 2 P0 + 3 P1；**第二轮 grill 全部完成** |

---

## 待对齐清单（Triage · 实施前必须拍板）

| # | 关联条目 | _gap_ | 风险 |
|---|----------|------|------|
| T1 | R5-21-06 / 09 / 10 | 选「无」逐行跳过后，右侧 **AI 要不要说话**？ | ✅ **B 固定短句** |
| T2 | R5-21-08 | `current_index+1` **触发条件** | ✅ **A+C 双通道** |
| T3 | R5-21-03 | 使命进度块 **存哪** | ✅ **B 对话 metadata** |
| T4 | R5-21-03 / 04 | schema `value`→`values[]` **旧结论卡兼容** | ✅ **C 读兼容 + 迁移脚本** |
| T5 | R5-21-02 | 「不再提醒」仅 localStorage vs 后端 | ✅ **仅 localStorage** |
| T6 | R5-21-09 | 同热爱多行是否点明「仍在同一热爱」 | ✅ **B 仅第 N 行 + 标准字段** |
| T7 | 全文 | 文档优先级/附录一致性 | ✅ 已修（R5-21-06→P1；附录 C 已更新） |
| T8 | 流程 | GitHub Issue 拆分 | ✅ **A：2 P0 + 3 P1 切片** |

**Triage 建议（类别 / 状态）：**

| 编号 | category | 建议 state | 说明 |
|------|----------|------------|------|
| R5-21-01 | bug | ready-for-agent | 可复现路径清晰，P0 |
| R5-21-02 | bug | ready-for-agent | 定稿完整，P0 |
| R5-21-03~04 | bug | ready-for-agent | T3/T4 已对齐 |
| R5-21-05~07 | enhancement | ready-for-agent | 文案为主 |
| R5-21-06~10 | enhancement | ready-for-agent | T1/T2/T6 已对齐 |
| R5-21-08 | bug | ready-for-agent | T2 已对齐 |

---

## GitHub Issue 拆分方案（T8 · 已定稿 A）

| Issue | 优先级 | 覆盖条目 | 标题建议 |
|-------|--------|----------|----------|
| **#1** | P0 | R5-21-01 | fix: 对话 thread 软归档删除 + fallback/同步/体检脚本 |
| **#2** | P0 | R5-21-02 | fix: 阶段完成弹窗「不再提醒」按激活码 global（localStorage） |
| **#3** | P1 | R5-21-06, 09, 10, 05, 07 | feat: rumination step3 行解锁协议 + 引导文案 |
| **#4** | P1 | R5-21-08 | fix: neg_gate current_index 逐条深度讨论 |
| **#5** | P1 | R5-21-03, 04 | fix: purpose 使命进度 + values[] schema + keywords 子集 |

**实施顺序：** #1 → #2 → #3 → #4 → #5（#3/#4 可并行）

**第二轮 Grill 对齐摘要（T1–T8）：** 选「无」→固定短句；neg_gate A+C；使命进度 metadata；values[] 读兼容+脚本；dismiss 仅 localStorage；换行仅 N 行+字段；Issue 5 片。

---
