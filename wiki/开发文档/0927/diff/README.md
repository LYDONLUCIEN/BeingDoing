# 提示词 diff 对比（基准：v1.5.1 = 最早版本）

> 基准：v1.5.1（7862b36，2026-07-05）。对比目标：当前 main HEAD（828b3a1，2026-09-23）。
> 说明：v1.6.1（e78062b，2026-09-17）与当前版本提示词**完全相同**，因此「v1.5.1→当前」与「v1.5.1→v1.6.1」的 diff 一致，这里只出一份。
> 标准 unified diff 格式：`-` 行 = 相对 v1.5.1 被删除/被替换掉的旧内容；`+` 行 = 新增/替换后的新内容。

## 文件索引

| 文件 | diff | 变化类型 |
|---|---|---|
| 01 | `simple_chat_system.yaml.diff` | 修改（主聊天系统提示词，核心差异） |
| 02 | `conclusion_card_payload.py.diff` | 修改（新增结论卡状态注入函数） |
| 03 | `prompt_builder.py.diff` | 修改（system prompt 末尾追加状态注入段） |
| 04 | `rumination_prompt_strings.py.diff` | 修改（仅 1 行品牌措辞） |
| 05 | `rumination_v4_prompt.py.新增.diff` | 新增文件（沉淀 v4 全套提示词） |
| 06 | `report_system.yaml.新增.diff` | 新增文件（报告生成系统提示词） |
| 07 | `v1.6.1到当前.空diff证明.diff` | **空文件** —— 证明 v1.6.1→当前提示词零改动 |

## 三版完全相同、无 diff 的提示词文件

- `templates/guide.yaml`、`observation.yaml`、`reasoning.yaml`、`answer_card_summary.yaml`、`pending_conclusion_reply.yaml`、`step_copy.yaml`
- `step_guidance.py`、`rumination_step_guidance.py`

## 增减摘要（只看加了什么 / 减了什么）

### 01 simple_chat_system.yaml（四个阶段同构）

**减少（v1.5.1 有、现在没有）：**
- 结论卡协议旧口径：「用户已确认 5 个关键词及排序**后**，必须……追加隐藏状态块」——只约束确认后必出卡，未约束确认前。
- 优势阶段提问范围中的「未来畅想」一词。

**增加（现在有、v1.5.1 没有）：**
- 结论卡协议新口径：必须等用户对「步骤 N 呈现的最终结果」**明确点头确认**才出卡；**未确认前不输出**；用户提调整意见则补充对话、再次确认后才出卡。
- 每阶段新增「**阶段边界（必须遵守）**」段：用户想跳阶段时——接近完成则立即引导最终确认收束；仍在探索则立即用本阶段问题拉回；禁止顺势展开其它阶段。
- 模板末尾新增「**话题边界（全程适用）**」段：退款/售后/投诉等无关话题 → 引导去「问题反馈」入口 + 拉回当前阶段。

### 02 conclusion_card_payload.py

**增加**：`build_conclusion_state_injection()` 函数（约 70 行）——生成「[结论卡状态·内部参考·严禁向用户复述]」段，含 none/pending/rejected 三态规则 + 当前状态 + 草案摘要/拒绝理由/已补充轮数。无删除。

### 03 prompt_builder.py

**增加**：`conclusion_state_injection` 参数，拼接在 system prompt 最末尾（prefix cache 考虑）。无删除。

### 04 rumination_prompt_strings.py

**修改 1 行**：「隐含寻路产品本身的含义」→「隐含寻路·OpenLife 产品本身的含义」。

### 05 rumination_v4_prompt.py（全新）

**增加**：沉淀 v4 三段 prompt——`MEGA_PROMPT`（主对话引导，无任何隐藏协议）、`BALANCE_JUDGE_PROMPT`（独立后台平衡点判定）、`SUMMARIZER_PROMPT`（30 轮滚动摘要）。

### 06 report_system.yaml（全新）

**增加**：报告生成系统提示词（约 300 行）。
