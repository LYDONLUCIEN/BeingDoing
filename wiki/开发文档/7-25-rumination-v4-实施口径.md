# 7-25 Rumination v4 提示词融合 · 实施口径

> 与 `7-25-rumination-v4.md`（产品文档）配套的工程实施契约。2026-07-25 与领域专家逐条 grill 后定案。
> 后端、前端开发以本文档为唯一契约。

> **⚠ 2026-08-06 起部分废止（ADR-0015，用户主导结论卡 + 独立后台平衡点判定）**：
> 本文档中以下内容已被取代——chips 协议（Q6/新1/新2）、出卡双信号与兜底（Q7）、
> tool 调用协议、主对话 LLM 判定 balance（平衡点条目/新5 再评估闸）、AI 落卡。
> 现行口径：主对话纯按原生 md 流程对话；结论卡仅 hypothesis、用户手填；
> 平衡点判定 = 用户点「确认」触发的独立后台 AI（聊/改即作废，需重新确认）。
> 未提及的部分（组合会话骨架/跳过可逆/终选/锁定/变量后置等）仍然有效。
> 详见 `docs/adr/0015-user-driven-card-async-balance-judge.md` 与 CONTEXT.md 三条目。

## 0. 总体原则

- **整体流程不换**：v4 的 combo_session 逐组合深聊 + 结论卡 + 终选骨架保留；融合产品文档的「匹配度确认 → 双方向假设 → 平衡点验证 → 收尾」节奏。
- **平衡点（Balance Point）**：AI 对假设方向的判定——既承载内心渴望（价值观一致、忍不住想做），又能在当下实践（投入可接受、有预期回报）。结果存后台隐藏字段，随对话可翻转，**永不强制终止对话、永不自动跳过卡**。
- **除非用户手动「跳过」，卡永远可选可改**；用户主动跳过的卡不进终选。

## 1. 已定决策清单（逐条对应讨论结论）

| # | 决策 | 内容 |
|---|------|------|
| Q1 | 双方向假设生成 | **先问倾向**：用户倾向明确 → 2 条同方向不同切面；模糊/无想法 → 1 条独立经营向 + 1 条公司岗位向。**恒 2 条**，与优势数量无关 |
| Q2/Q3 | 难平衡话术 | AI 判难平衡时输出**要点式**话术（坦诚顾虑 + 明确不建议 + 给替代路径 + 尊重继续意愿），措辞自由，不终止对话 |
| Q4 | 不匹配分支 | 用户坚持「热爱×优势不匹配」并入难平衡统一机制，reason 记具体原因，不强制终止 |
| Q5 | 上下文载入 | 载入 basic_info + 前四阶段结论卡（全量不截断）；**变量全部后置**（固定指令在前 → 缓存命中）；价值观用**用户真实关键词**，读不到则**整块省略**（禁固定 8 词兜底），提示词含「无价值观关键词则直接问用户」指令 |
| Q6 | chips 定位 | chips 只是**对话内的文字美化提示**：点击 = 把该文本作为用户消息发送，不直接写结论卡；假设经对话完善后由 AI 落卡 |
| Q6b | 多优势 | 1 热爱 + N 优势**组合整体**生成一条字符串假设；dict 形态废弃 |
| Q7 | 出卡双信号 | 隐藏信号 `<<CONCLUSION_READY>>` 不变；可见话术**要点化**（复述总结 + 邀请确认），必须包含锚点短语「**整理成了结论卡**」（后端兜底监测用）；旧句式「现在我为你总结了 N 个假设…」废弃 |
| Q8 | 终选呈现 | ~~绿✓/琥珀⚠/灰？三态徽章~~（2026-07-28 修订，见附录二）：卡片统一紫色主题，不渲染徽章；仅不推荐（`balance_found=false`）卡片底部琥珀 ⚠ 警告条显示 `balance_fail_reason`；顶部不加固定说明 |
| 新1 | chips 三选项 | **[A][B][✏️自己写]**；C 展开内联输入框，提交 = 作为用户消息发送。新一组 chips 生成 → 前端替换选择器；历史消息与用户已发送内容不动；后端只记用户最新确认的假设 |
| 新2 | chips 时机 | 凡「假设要定型」的时刻都弹：首次生成、用户不满意要求重来、用户有想法时（A=用户想法完善版、B=AI 补充另一假设） |
| 新3 | 结论卡极简 | 前端卡面 = **hypothesis + 确认/跳过**；motivation/work_purposes/passion_mark/timing_mark/balance_found/balance_fail_reason 全部后台字段，前端不渲染 |
| 新4 | 跳过行为 | 跳过（abandoned）**不再清空卡**：内容保留，UI 删除线 + 灰色标记；跳过**可逆**（灰色卡上再点「确认」即恢复为 concluded）；终选只出现 concluded 卡 |
| 新5 | 平衡再评估 | hypothesis 变更（新 chips 选定 / 对话中修改 / 用户手动编辑卡）→ 后端立即把 `balance_found` 置 `null`；提示词规则：用已有证据重核四要素，证据被推翻/缺失的维度**只补问一个问题**（不逐条重问），核对后必写 `update_field balance_found` |

## 2. 后端改动

### 2.1 `src/backend/app/domain/rumination_v4_prompt.py`（重写）

**MEGA_PROMPT 结构（缓存友好排版，固定在前、变量在后）**：

1. 角色与核心任务（固定）
2. 咨询流程（固定）：开场（亲切问候+说明目标+匹配度确认并入 motivation 提问「为什么选这个组合/感觉搭吗」）→ 假设生成（先问有无想法 → 无想法/模糊先问倾向 → 2 条候选 chips；硬性标准：角色/对象/动作/目的的画面感、长期可持续、公司岗位真实存在；用户有想法 → A=用户想法完善版、B=AI 补充）→ 平衡点验证（四问：价值观一致/当下可启动/忍不住想做/价值回报；一次一问；顺带收集 work_purposes/passion_mark/timing_mark）→ 收尾出卡
3. 难平衡机制（固定）：判定标准、要点式话术、不终止、可翻转、不匹配并入
4. 假设变更后的平衡再评估三规则（固定，见 1-新5）
5. chips 输出协议（固定）：候选以隐藏块输出（见 2.4）
6. tool 调用协议（固定）：`update_field` / `save_conclusion_card`，VALID_FIELDS 扩展
7. 出卡双信号（固定）：`<<CONCLUSION_READY>>` + 要点式可见话术（必含「整理成了结论卡」）
8. 价值观缺失兜底指令（固定）：背景中无价值观关键词时，验证价值观一致性直接问用户，禁用预设列表
9. 硬约束（固定）：不提系统/prompt/步骤、不用 markdown 标题、中文、300 字内
10. **【当前组合】**（变量）：热爱 + 优势
11. **【用户背景】**（变量）：basic_info + 前四阶段结论卡全量（各阶段 keywords + summary 等，不截断）
12. **【价值观关键词】**（变量，可整块省略）：用户 values 结论卡真实关键词

**CONCLUSION_PROMPT（兜底）更新**：hypothesis 纯字符串（dict 废弃）；输出 JSON 增加 `balance_found`（true/false/null）与 `balance_fail_reason`；价值观参考块可省略。

**SUMMARIZER_PROMPT 更新**：保留字段追加——用户的方向倾向（独立经营/公司/模糊）、当前已确认假设、`balance_found` 状态及原因。

`render_mega_prompt(passion, strengths, user_context, values_keywords=None)`：values_keywords 为 None/空 → 省略价值观块；`render_conclusion_prompt` 同理。

### 2.2 `src/backend/app/services/rumination_v4_service.py`

- `VALID_FIELDS` += `"balance_found"`（bool/null）、`"balance_fail_reason"`（str/null）
- 结论卡结构 += 上述两字段（默认 None）
- **平衡再评估闸**：`update_field`/`save_conclusion_card`/PATCH 导致 hypothesis 内容变化时，`balance_found` 置 None、`balance_fail_reason` 置 None
- `detect_conclusion_signals`：可见锚点改为「整理成了结论卡」（hidden 不变）
- `set_combo_status`：abandoned **不再清空** conclusion_card/hypothesis，改置 `user_skipped=True`；concluded 清除 `user_skipped`
- `build_chat_messages`：mega-prompt 用新签名渲染（user_context + values_keywords 由 routes 装配传入）
- `fallback_generate_conclusion`：走新 CONCLUSION_PROMPT（含 balance 字段）
- chips：流式回复组装完成后解析候选隐藏块、从可见文本剥离（复用 `app.utils.stream_utils.extract_hyp_candidates` 的思路/函数），交给 routes 发 SSE

### 2.3 `src/backend/app/api/v1/rumination_v4_routes.py`

- **删除 `_get_values_list()` 固定 8 词**；新增上下文装配函数：
  - basic_info（复用 v3/simple_chat 现有的用户资料拼装，如 prompt_builder 中的实现）
  - 前四阶段结论卡：`load_dimension_conclusions(report_id, reports_root)`，逐阶段取 keywords + summary 等全量内容，不截断
  - values 关键词：复用 `extract_dimension_lists_for_rumination_table` 的 values 结果；为空则传 None（prompt 省略块）
- combo-chat SSE：回复完成后发 `{type:"hyp_candidates", hyp_candidates:[...]}` 事件（无候选不发）；可见文本剥离协议块后入库/推送
- PATCH conclusion-card：前端只需传 `hypothesis`；后端保持兼容（其余字段仍接受但前端不传）；hypothesis 变化触发平衡再评估闸
- state/combo 序列化：combo 增加 `user_skipped`；conclusion_card 含 balance 两字段

### 2.4 chips 隐藏协议（后端解析、前端渲染）

AI 回复末尾输出：
```
[STEP3_HYP_JSON]
{"candidates": ["假设A", "假设B"]}
[/STEP3_HYP_JSON]
```
**复用 v3 同款协议**（前端 MessageContent 已有剥离正则、stream_utils 已有解析）。后端在 v4 SSE 完成时解析并推 `hyp_candidates` 事件；剥离后的文本入库。C 选项纯前端，无协议。

## 3. 前端改动

### 3.1 chips 选择器（`V4ChatPanel.tsx` 或新组件）

- store（`ruminationV4Store.ts`）新增 `latestHypCandidates: string[] | null`；SSE `hyp_candidates` 事件到达即**替换**；发送用户消息后可清空
- 渲染：最新一条 AI 消息下方（或输入区上方）显示选择器：[假设A][假设B][✏️ 自己写]
- 点 A/B → 把该文本作为用户消息发送（走现有 combo-chat 发送链路）
- 点 C → 展开内联输入框 + 提交按钮 → 提交内容作为用户消息发送
- API 类型（`ruminationV4Api.ts`）SSE 事件 += `hyp_candidates`

### 3.2 结论卡极简（`ConclusionCardEditable.tsx` 重写）

- 卡面 = hypothesis（textarea 可编辑）+「确认」/「跳过」按钮
- PATCH 只传 hypothesis
- 跳过态：卡内容保留，**删除线 + 灰色** + 「已跳过」标记；灰色卡上保留「确认」按钮（点击恢复 concluded，可逆）
- 不渲染/不提交 balance 等后台字段

### 3.3 终选弹窗（`V4FinalSelectionModal.tsx`）

- 只列 `status=concluded`（排除 user_skipped/abandoned）的卡
- ~~徽章：`balance_found=true` → 绿 ✓；`false` → 琥珀 ⚠；`null` → 灰 ？~~（2026-07-28 修订，见附录二）：不渲染徽章，卡片统一紫色主题；仅 `balance_found=false` 时卡片底部琥珀 ⚠ 警告条显示 `balance_fail_reason`
- 推荐/不推荐区分不影响可选性

### 3.4 类型

combo/card 类型 += `balance_found: boolean | null`、`balance_fail_reason: string | null`、`user_skipped?: boolean`

## 4. 流程穿越（验收基准）

| 场景 | 关键表现 |
|------|----------|
| A 标准路径 | 开场问动机/匹配度 → 问想法 → 模糊 → 问倾向 → 2 chips（独立+公司）→ 点击发送 → 细化 → 四问验证 → `<<CONCLUSION_READY>>`+「整理成了结论卡」→ 卡出现 → 确认 → 终选绿徽章 |
| B 倾向明确 | 2 chips 同方向两切面 |
| C 用户有想法 | A=想法完善版、B=AI 补充；仍弹 chips 供确定性选择；不满意可 C 自输 |
| D 难平衡 | `balance_found=false`+reason → 要点式话术不出卡 → 继续聊翻转 → 正常出卡；聊不动 → 带 false 出卡 → 终选琥珀徽章悬停原因 |
| E 不匹配 | 并入 D，reason=不匹配原因 |
| F 忘打标记 | 可见锚点「整理成了结论卡」触发 → 后端 fallback 出卡 |
| G 出卡后修改 | hypothesis 变 → balance 置 null → AI 按再评估三规则补问/直写 → 更新 |
| H 手动跳过 | 卡保留+删除线灰色+可逆；不进终选 |

## 5. 文档同步

- CONTEXT.md：更新「v4 结论卡区」定义（跳过保留卡、可逆）、「平衡点」（补 null 态与再评估闸）、chips 选择器定义
- 本文件即实施口径；产品文档 `7-25-rumination-v4.md` 保持原文不动

---

## 附:2026-07-27 交互口径修订(出卡不锁 / 确认才锁 / 再聊聊)

> 与领域专家 grill 后定案,优先级高于上文冲突条目。

1. **出卡 = 草案,不锁定**:`apply_tool_call(save_conclusion_card)` 与 `patch_conclusion_card` 均**不再强制 `status=concluded`**;草案期对话继续,AI 每轮可迭代覆盖卡内容。确认动作统一走 `set_combo_status(concluded)`。
2. **草案卡注入上下文**:`build_chat_messages` 在草案期(有卡且非 concluded)每轮注入【当前结论草案(用户尚未确认)】system 消息;concluded 后不注入(对话已锁定)。
3. **「再聊聊」**:`concluded → discussing` 时 `set_combo_status` 写入 `reopen_feedback`(用户对当前结论不满意,先问哪里不合适),随草案一起注入 LLM 上下文;AI 下次 `save_conclusion_card` 或用户再确认时自动清除。
4. **前端三态卡底**:草案卡常显「跳过/确认」;已确认卡显示「✓ 已确认」+「再聊聊」;跳过卡维持删除线灰标、编辑态「确认(恢复)」。点击文本进编辑态不变。
5. **终选口径不变**:只认 `concluded` 且未跳过的卡;「再聊聊」的组合掉出终选池,重新确认后回池。
6. 顺手修复:`set_combo_status(discussing)` 现在也清除 `user_skipped`(原 abandoned→discussing 会残留跳过标记)。
7. **空可见回复兜底(空气泡修复)**:prompt 硬约束"每次回复必须含可见正文,隐藏块禁止单独成条";routes 在 `visible_text` 为空时按情境补兜底话术(出卡/chips/一般追问)并 `logger.warning` 记录原始回复;`build_chat_messages` 跳过空内容消息;前端 store `done` 空文本不追加、`V4ChatPanel` 不渲染空消息。前端 store 收到 `conclusion_card` 事件不再强制本地 `status='concluded'`(与"出卡不锁"对齐)。

---

## 附录二:2026-07-28 终选 UI 简化(统一紫色主题)

> 用户反馈终选弹窗颜色过多,与领域专家确认后定案,优先级高于 Q8 / §3.3 冲突条目。

1. **卡片全统一紫色主题**:删除 6 色循环 THEMES,数字标签(01/02…)、选中边框/阴影/标题、优势 tags 统一用紫色系(主色 `#553df2`,tag 底 `#f4f1ff` / 字 `#5d49ef`,与 V4ComboMatrixSelector 主按钮同族)。
2. **移除三态徽章(BalanceBadge)**:绿 ✓ 推荐 / 琥珀 ⚠ / 灰 ? 未评估徽章全部不再渲染。
3. **推荐 vs 不推荐唯一差异**:不推荐(`balance_found=false`)卡片底部保留琥珀 ⚠ 警告条(`balance_fail_reason`);推荐卡片无任何标记。
4. **弹窗其余杂色一并紫化**:确认按钮渐变 `#826aff→#553df2`、已选 x/3 pill、装饰光斑、右上角勾选标记均为紫色系。
