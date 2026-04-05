# Simple Chat 模块深度审查报告

> 审查日期：2026-04-04
> 范围：`simple_chat.py` 全流程 + 前端对接 + 所有依赖模块
> 文件行数：后端 `simple_chat.py` 2825 行 | 前端 `page.tsx` 1788 行

---

## 一、架构总览

### 1.1 Simple Chat 在系统中的定位

Simple Chat 是 BeingDoing 的**核心对话引擎**，区别于 LangGraph Agent 模式：
- 不使用 LangGraph 图结构
- 通过 **system_prompt + 历史消息** 直接调用 LLM
- 会话由「激活码」标识，对话历史保存在文件系统（`data/simple/` 或 `data/test/simple/sandboxes/`）
- 支持 5 个阶段：values → strengths → interests → purpose → rumination

### 1.2 模块依赖关系图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        前端 (Next.js)                                │
│  page.tsx ──→ threads.ts / session.ts / rumination.ts / survey.ts   │
│      │                                                               │
│      │  SSE Stream / REST API                                        │
└──────┼───────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   simple_chat.py (2825行, API 路由层)                 │
│                                                                      │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌──────────────────┐   │
│  │ /init    │  │ /message │  │ /message  │  │ /thread/*        │   │
│  │ (初始化) │  │ (同步)   │  │ /stream   │  │ (complete/reopen │   │
│  │          │  │          │  │ (流式)    │  │  /delete)        │   │
│  └────┬─────┘  └────┬─────┘  └─────┬─────┘  └────────┬─────────┘   │
│       │             │              │                  │              │
│       ▼             ▼              ▼                  ▼              │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │              _resolve_report_context()                       │    │
│  │  激活码校验 → 报告初始化 → 线程解析 → 存储上下文构建         │    │
│  └──────────────────────────┬──────────────────────────────────┘    │
│                             │                                       │
│  ┌──────────────────────────▼──────────────────────────────────┐    │
│  │              _build_system_prompt()                          │    │
│  │  YAML模板渲染 + 题库注入 + 基本信息 + 前序结论 + 输出协议   │    │
│  └──────────────────────────┬──────────────────────────────────┘    │
│                             │                                       │
│  ┌──────────────────────────▼──────────────────────────────────┐    │
│  │              LLM 调用 (chat / chat_stream)                  │    │
│  │  对话模型(deepseek-chat) / 推理模型(deepseek-reasoner)      │    │
│  └──────────────────────────┬──────────────────────────────────┘    │
│                             │                                       │
│  ┌──────────────────────────▼──────────────────────────────────┐    │
│  │              结论状态机 (pending → confirmed/rejected)       │    │
│  │  STATE_JSON解析 → pending判定 → 结论卡生成 → 锚点写入       │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        依赖模块层                                     │
│                                                                      │
│  ┌─────────────────┐  ┌──────────────────┐  ┌───────────────────┐   │
│  │ SimpleActivation │  │ ReportRegistry   │  │ ConversationFile  │   │
│  │ Manager (631行)  │  │ (481行)          │  │ Manager (316行)   │   │
│  │ 激活码生命周期   │  │ 报告/步骤/会话   │  │ 对话文件读写      │   │
│  └─────────────────┘  └──────────────────┘  └───────────────────┘   │
│                                                                      │
│  ┌─────────────────┐  ┌──────────────────┐  ┌───────────────────┐   │
│  │ context_refiner  │  │ survey_storage   │  │ dimension_        │   │
│  │ (175行)          │  │ (355行)          │  │ completion_       │   │
│  │ 锚点摘要提炼    │  │ 问卷/前序上下文  │  │ checker (394行)   │   │
│  └─────────────────┘  └──────────────────┘  └───────────────────┘   │
│                                                                      │
│  ┌─────────────────┐  ┌──────────────────┐  ┌───────────────────┐   │
│  │ rumination_ops   │  │ rumination_      │  │ rumination_       │   │
│  │ (377行)          │  │ table_widgets    │  │ progress (118行)  │   │
│  │ 表格生成/筛选   │  │ (183行)          │  │ 进度持久化        │   │
│  └─────────────────┘  └──────────────────┘  └───────────────────┘   │
│                                                                      │
│  ┌─────────────────┐  ┌──────────────────┐  ┌───────────────────┐   │
│  │ conclusion_card  │  │ dimension_       │  │ admin_prompt_lab  │   │
│  │ _goals (159行)   │  │ completion (44行)│  │ (332行)           │   │
│  │ 结论卡规则定义   │  │ 维度完成配置     │  │ 提示词实验室      │   │
│  └─────────────────┘  └──────────────────┘  └───────────────────┘   │
│                                                                      │
│  ┌─────────────────┐  ┌──────────────────┐                          │
│  │ sandbox_fork     │  │ admin_policy     │                          │
│  │ (386行)          │  │ (29行)           │                          │
│  │ 沙箱生命周期    │  │ 管理员策略开关   │                          │
│  └─────────────────┘  └──────────────────┘                          │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 二、核心对话流程详解

### 2.1 流式对话主流程 (`/message/stream`)

这是系统最核心的端点，处理用户每一轮消息。完整流程如下：

```
用户发送消息
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ 1. 请求预处理 (simple_chat.py:2223-2259)                │
│    ├─ 解析 activation_code → 获取激活码记录              │
│    ├─ _resolve_report_context() 统一解析存储上下文        │
│    │   ├─ 校验激活码归属 (owner 绑定)                    │
│    │   ├─ 校验沙箱过期                                   │
│    │   ├─ 初始化/获取 report                             │
│    │   ├─ 解析 phase_step (normalize_step_id)            │
│    │   ├─ 解析 logical_session_id (线程选择策略)         │
│    │   ├─ 锁定上一阶段 (非管理员)                        │
│    │   └─ 绑定当前会话到 step 会话池                     │
│    ├─ 校验阶段可编辑 (_assert_step_editable)             │
│    └─ 返回 StreamingResponse                             │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ 2. event_stream() 生成器启动 (2261-)                     │
│    ├─ 获取对话/推理 LLM provider                         │
│    ├─ 读取当前线程历史消息                               │
│    ├─ 首条消息时触发上一阶段锚点摘要 (2278-2289)         │
│    ├─ 加载题库 (线程级固定, 首次随机抽取)                │
│    ├─ 加载基本信息 + 前序上下文                          │
│    ├─ 构建 system_prompt                                 │
│    ├─ 注入锚点摘要 [此前对话要点]                        │
│    ├─ 裁剪历史到最近 30 轮                               │
│    ├─ 追加当前用户消息                                   │
│    └─ 保存用户消息到文件                                 │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ 3. Pending 结论草案处理 (2362-2598)                      │
│    │                                                     │
│    ├─ 读取 metadata 中的 conclusion_state                │
│    │                                                     │
│    ├─ 若存在 pending_conclusion (草案待确认):            │
│    │   ├─ 调用推理模型判定用户态度                       │
│    │   │   _decide_pending_action_by_llm_streaming()     │
│    │   │   ├─ 流式透传 think_start/chunk/end             │
│    │   │   ├─ 超时 20s 降级为 continue                   │
│    │   │   └─ 解析 <STATE>/<CONTENT> 或 JSON             │
│    │   │                                                 │
│    │   ├─ confirmed → 生成最终结论卡                     │
│    │   │   ├─ check_dimension_complete() 综合生成         │
│    │   │   ├─ 超时 25s 降级用草案                        │
│    │   │   ├─ 更新 metadata → CONFIRMED                  │
│    │   │   ├─ 发送 dimension_conclusion SSE 事件          │
│    │   │   ├─ 写入 conclusion_card 消息                  │
│    │   │   ├─ 写入 note.json 审计记录                    │
│    │   │   ├─ 写入锚点 + 触发异步锚点提炼               │
│    │   │   └─ return (结束本轮)                          │
│    │   │                                                 │
│    │   ├─ rejected → 清除 pending, 记录反馈              │
│    │   │   ├─ 更新 metadata → REJECTED                   │
│    │   │   ├─ 写入 note.json                             │
│    │   │   └─ 继续进入正常对话流                         │
│    │   │                                                 │
│    │   └─ continue → 保持现状, 继续对话                  │
│    │                                                     │
│    └─ 若无 pending 但有 rejected_feedback:               │
│        └─ 注入 "[上一版结论未获认可]" 上下文             │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ 4. 主对话 LLM 流式调用 (2603-2656)                       │
│    ├─ 获取并发信号量 (可选)                              │
│    ├─ llm.chat_stream() 流式调用                         │
│    ├─ 逐 chunk 处理:                                     │
│    │   ├─ dict 类型 → think_start/chunk/end 事件         │
│    │   └─ str 类型 → 累积 full_reply                     │
│    │       └─ _build_stream_hidden_block_filter()        │
│    │           过滤 [STATE_JSON]...[/STATE_JSON] 块      │
│    │           只输出用户可见增量                         │
│    ├─ 获取 token 使用量 (_last_stream_usage)             │
│    └─ 记录 DeepSeek Context Cache 命中率                 │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ 5. 后处理 (2657-2756)                                    │
│    ├─ _split_visible_reply_and_state() 拆分可见文本      │
│    │   和 STATE_JSON                                     │
│    ├─ 保存 assistant 回复到文件                          │
│    ├─ rumination 阶段: 检测 markdown 表格并额外保存      │
│    ├─ 解析 STATE_JSON:                                   │
│    │   ├─ pending_ready → 更新 metadata 为 PENDING       │
│    │   │   写入 note.json 记录草案创建                   │
│    │   └─ continue → 无状态迁移                          │
│    ├─ 每 20 轮触发后台锚点摘要提炼                       │
│    ├─ 记录 Analytics 埋点                                │
│    └─ 发送 done 事件 (含完整回复 + token 使用量)         │
└─────────────────────────────────────────────────────────┘
```

### 2.2 结论状态机

结论卡的生命周期由一个四状态机驱动：

```
                    ┌──────────────────────────────────────┐
                    │                                      │
                    ▼                                      │
              ┌──────────┐    LLM输出STATE_JSON     ┌─────┴────┐
  开始 ──────→│   none   │ ──── pending_ready ────→ │ pending  │
              └──────────┘                          └────┬─────┘
                    ▲                                    │
                    │                          用户回复后LLM判定
                    │                         ┌─────────┼─────────┐
                    │                         │         │         │
                    │                    confirmed  rejected  continue
                    │                         │         │         │
                    │                         ▼         ▼         │
                    │                   ┌──────────┐ ┌────────┐   │
                    │                   │confirmed │ │rejected│   │
                    │                   │(生成结论 │ │(清除草 │   │
                    │                   │ 卡并锁定)│ │ 案继续)│   │
                    │                   └──────────┘ └───┬────┘   │
                    │                                    │        │
                    │         用户选择"再聊聊"            │        │
                    │  ┌─────────────────────────────────┘        │
                    │  │                                          │
                    │  ▼                                          │
                    └──── 继续对话 ←───────────────────────────────┘
```

**状态存储位置**：对话文件的 `metadata` 字段中，通过 `_read_conclusion_meta()` / `_build_conclusion_meta_update()` 统一读写。

**新旧字段兼容**（`simple_chat.py:307-355`）：
| 新字段 | 旧字段（兼容） | 说明 |
|--------|---------------|------|
| `conclusion_state` | `pending_status` | 状态名 |
| `conclusion_draft` | `pending_conclusion` | 待确认草案 |
| `conclusion_final` | `dimension_conclusion` | 最终结论 |
| `conclusion_feedback` | `pending_last_rejected.feedback` | 否定反馈 |

### 2.3 初始化流程 (`/init`)

```
前端进入阶段页面
    │
    ▼
POST /simple-chat/init
    │
    ├─ _resolve_report_context() (同上)
    │
    ├─ 读取历史消息
    │   ├─ 有历史 → 直接返回 messages (不重复生成)
    │   └─ 无历史 → 生成首轮引导问题
    │       ├─ 构建 system_prompt
    │       ├─ 发送固定 user 消息: "我是来访者...请给出第一轮引导问题"
    │       ├─ LLM 生成回复
    │       ├─ 失败时降级到本地兜底问题 (_build_fallback_opening_question)
    │       └─ 只写入 assistant 消息 (不写入那条固定 user 消息)
    │
    └─ 返回 messages + activation info + report_id
```

---

## 三、提示词体系详解

### 3.1 System Prompt 构建流程

`_build_system_prompt()` (simple_chat.py:1479-1517) 是提示词的核心组装点：

```
_build_system_prompt(phase, question_bank, basic_info, prior_context, template_override, extra_goal_hint)
    │
    ├─ 1. 构建 prior_block (前序阶段结论)
    │     若 prior_context 非空: "\n\n以下是该来访者在上一轮咨询中的谈话结果...\n{prior_context}"
    │
    ├─ 2. 渲染模板
    │     ├─ 有 template_override (管理员调试) → Jinja2 直接渲染
    │     └─ 无 override → get_simple_chat_system_prompt(context)
    │         └─ 加载 templates/simple_chat_system.yaml
    │             └─ Jinja2 渲染 {% if phase == "values" %} ... {% endif %}
    │
    ├─ 3. 追加管理员调试目标 (可选)
    │     "[管理员调试目标补充]\n{extra_goal_hint}"
    │
    └─ 4. 追加输出协议 (固定)
          "[输出协议 - 必须遵守]
           在你的自然语言回复末尾，追加如下块（严格 JSON）：
           [STATE_JSON]
           {"state":"continue|pending_ready","draft":{"summary":"...","keywords":["..."]}}
           [/STATE_JSON]"
```

### 3.2 各阶段提示词内容

所有阶段提示词定义在 `templates/simple_chat_system.yaml`，通过 Jinja2 `{% if phase %}` 分支：

#### Values 阶段（价值观）— 最详细，约 50 行

**目标**：帮助用户发现并确认 5 个价值观关键词

**流程指令**：
1. 开场直接询问 5 个价值观关键词
2. 记录初始答案（标记"用户自述"）
3. 深度提问探索（一次一问，标记"探索发现"）
4. 整合与确认（对比初始 vs 探索，权重+1）
5. 收敛判断（无新词 或 累计 10 个独立问题）
6. 排序与整合（合并到 5 个，用户排序）
7. 最终确认
8. 结束

**关键约束**：
- 一次一问
- 完整收敛（不能凑够 5 个就停）
- 结论卡协议（必须输出 `pending_ready` + STATE_JSON）
- 严禁提前透露下一阶段
- 对话续写（不重复开场）
- 命名约束（单一概念词，禁止 `/、或、&` 并列）

**动态注入**：
- `{{ question_bank }}` — 随机抽取 6 道题（线程级固定）
- `{{ basic_info }}` — 用户问卷信息
- `{{ prior_block }}` — 前序阶段结论（values 阶段为空）

#### Strengths 阶段（优势）— 约 35 行

**目标**：发现并确认 10 个优势

**差异**：
- 需要 10 个（而非 5 个）
- 增加标记体系（用户对每个优势标记分类）
- 提问差异化要求

#### Interests 阶段（热爱）— 约 20 行

**目标**：发现 3 个核心热爱方向

**差异**：
- 更精简的流程描述
- 目标至少 6 个候选，筛选 TOP3

#### Purpose 阶段（使命）— 约 20 行

**目标**：表达工作使命感

**差异**：
- 结合前序信息回顾
- 梳理价值经历
- 总结使命表达

#### Rumination 阶段（沉淀）— 约 15 行

**目标**：综合前序结果，形成可执行方向

**差异**：
- 不使用固定题库（`{{ question_bank }}` 不注入）
- 基于 prior_block 中四阶段结论推进
- 明确标注"本轮即最后阶段"

### 3.3 Pending 判定提示词

当用户回复待确认结论时，使用独立提示词判定态度（`simple_chat.py:737-772`）：

```
你是职业咨询系统中的"确认状态判定器"。

当前阶段：{phase}
待确认总结摘要：{summary}
待确认关键词：{kw_text}
用户最新回复：{user_reply}

请严格输出以下两行，不要输出任何其他内容：
<STATE>confirmed|rejected|continue</STATE>
<CONTENT>给用户展示的一句话（20-80字）</CONTENT>

判定要求：
1) 只有当用户明确同意当前总结内容时，state 才能是 confirmed。
2) 当用户表达不认可、希望调整、继续讨论时，state 为 rejected。
3) 无法明确同意或否定时，state 为 continue。
4) 像"嗯/好/行"等口头语，若缺乏明确语义，优先判为 continue。
```

**双格式降级策略**：
1. 先尝试 JSON mode (`response_format: json_object`)
2. JSON mode 失败 → 纯文本 `<STATE>/<CONTENT>` token 格式
3. 推理模型空 content → 降级到对话模型重试
4. 全部失败 → 硬编码兜底文案

### 3.4 结论卡生成提示词

`check_dimension_complete()` (dimension_completion_checker.py:224-393) 分两步：

**第一步：完成判定**（跳过条件：有 prior_conclusion）
```
你是一位职业咨询师。请判断以下对话是否已经完成「{label}」维度的探索。
该维度的目标：{goal}
完成标准：{criteria}
请用 JSON 回复：{"complete": true 或 false, "reason": "简短理由"}
```

**第二步：结论生成**
```
基于以下对话，生成「{label}」维度的探索结论汇总。
{prior_hint}          ← 若有上一轮结论，要求综合更新
{values_extra}        ← values 阶段特别要求 5 个核心词
该维度的目标：{goal}
{summary_hint}
{goal_hint}           ← 来自 conclusion_card_goals.py
{conclusion_rules}    ← 来自 conclusion_card_goals.py
{anti_fabrication}    ← 严禁杜撰约束

请只输出一个 JSON 对象：
{"keywords": ["词1", "词2", ...], "summary": "汇总文案：用 **关键词** 标出核心词。"}
```

### 3.5 Pending 结论注入提示词

当 metadata 中存在 pending_conclusion 时，通过 `pending_conclusion_reply.yaml` 追加在对话末尾：

```
【系统指令 - 结论卡模式】检测到需要输出结论卡，请完成以下任务：

---
【上一轮结论（供综合更新）】
摘要：{{ prior_summary }}
关键词：{{ prior_keywords }}
---

【本阶段结论卡规则与目标】
{{ conclusion_rules_and_goals }}

【输出格式 - 必须严格遵守】
先回应用户消息，再输出结论 JSON。按以下格式输出：

[REPLY]
（你对用户消息的自然语言回复，1-3句话）

[CONCLUSION_JSON]
{"keywords": ["词1", "词2", ...], "summary": "汇总文案"}

【硬性约束】keywords 仅来自用户对话中亲口提到的词汇，严禁杜撰。
【硬性约束】每个 keywords 必须是单一概念词。
【硬性约束】严禁提及下一阶段。
```

### 3.6 锚点摘要提示词

`context_refiner.py` 中的 `refine_and_save_anchor()` 每 20 轮或结论确认时触发：

```
你是一位职业规划咨询师的助手。请从以下对话中提取结构化摘要。

对话内容（最近部分）：
{conv_text[:2000]}

请输出 JSON：
{
  "goals": "用户在本阶段的核心发现/目标（1-3句话）",
  "personality": "用户展现的性格特征",
  "style": "用户的沟通风格偏好",
  "conflicts": "用户表达的矛盾或犹豫"
}
```

### 3.7 提示词注入完整顺序

一次流式对话中，LLM 收到的消息序列：

```
[0] system: _build_system_prompt() 输出
    ├─ 阶段模板 (simple_chat_system.yaml 渲染)
    │   ├─ 咨询流程指令
    │   ├─ 重要准则
    │   ├─ {{ question_bank }} (6道随机题)
    │   ├─ {{ basic_info }} (用户问卷)
    │   └─ {{ prior_block }} (前序阶段结论)
    ├─ [管理员调试目标补充] (可选)
    └─ [输出协议] STATE_JSON 格式要求

[1] assistant: "[此前对话要点]\n{anchor_text}" (若有锚点摘要)

[2..N] 历史消息 (最近 30 轮 user/assistant)

[N+1] assistant: "[上一版结论未获认可] 用户反馈：..." (若有 rejected_feedback)

[N+2] user: 当前用户输入
```

---

## 四、前端对接流程

### 4.1 前端核心文件

| 文件 | 行数 | 职责 |
|------|------|------|
| `app/(main)/explore/chat/[phase]/page.tsx` | 1788 | 主聊天页面，所有 API 调用和 SSE 流处理 |
| `lib/explore/threads.ts` | 192 | 线程管理（localStorage 持久化） |
| `lib/explore/session.ts` | 118 | 会话状态（阶段进度、激活码） |
| `lib/api/rumination.ts` | 150 | Rumination API 客户端 |
| `lib/api/survey.ts` | 73 | 问卷和前序上下文 API |
| `components/explore/FlowAiMessage.tsx` | 216 | AI 消息展示组件 |
| `lib/explore/ruminationStepBoundaries.ts` | 97 | Rumination 步骤消息切片 |

### 4.2 前端 SSE 流处理

`page.tsx` 中 `handleSend()` (line 816-1057) 的流式处理：

```typescript
// 1. 构建请求
const response = await fetch('/api/v1/simple-chat/message/stream', {
  method: 'POST',
  headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
  body: JSON.stringify({ activation_code, message, phase, thread_id }),
  signal: abortController.signal,
});

// 2. 逐行读取 SSE
const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = '';

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });

  // 按行解析 "data: {...}\n\n"
  const lines = buffer.split('\n');
  for (const line of lines) {
    if (!line.startsWith('data: ')) continue;
    const json = JSON.parse(line.slice(6));

    if (json.think_start)        → 开始思考动画
    if (json.think_chunk)        → 追加思考内容
    if (json.think_end)          → 结束思考动画
    if (json.chunk)              → 追加可见回复文本
    if (json.dimension_conclusion) → 显示结论卡
    if (json.table_widget)       → 显示表格组件
    if (json.done)               → 流结束，更新最终状态
    if (json.error)              → 显示错误
    if (json.heartbeat)          → 保持连接（pending 判定中）
  }
}
```

### 4.3 前端线程管理

线程数据同时存在于 localStorage 和后端：

```
前端 localStorage                    后端 report record.json
┌─────────────────────┐              ┌──────────────────────┐
│ explore_threads_{code}│              │ steps.{phase}        │
│ {                    │              │   .session_ids: []   │
│   values: [          │  ◄── 同步 ──│   .selected_session_id│
│     {id, title,      │              │   .locked: bool      │
│      status, msgs}   │              │                      │
│   ]                  │              └──────────────────────┘
│ }                    │
└─────────────────────┘
```

**同步策略**：
- 进入阶段时 `GET /threads` 从后端拉取线程列表
- 每个线程 `GET /history` 加载消息
- 创建/删除线程时同时更新前后端
- Rumination 阶段强制折叠为单线程

---

## 五、所有 API 端点清单

| 端点 | 方法 | 行号 | 用途 | 是否流式 |
|------|------|------|------|----------|
| `/simple-chat/init` | POST | 1763 | 初始化阶段对话 | 否 |
| `/simple-chat/message` | POST | 1600 | 同步单轮对话 | 否 |
| `/simple-chat/message/stream` | POST | 2223 | 流式对话（主入口） | SSE |
| `/simple-chat/history` | GET | 2156 | 获取历史消息 | 否 |
| `/simple-chat/threads` | GET | 2075 | 获取线程列表 | 否 |
| `/simple-chat/thread/complete` | POST | 1977 | 标记线程完成 | 否 |
| `/simple-chat/thread/reopen` | POST | 1917 | 重新打开线程 | 否 |
| `/simple-chat/thread/delete` | POST | 2769 | 删除线程 | 否 |
| `/simple-chat/survey` | GET | 1079 | 获取问卷数据 | 否 |
| `/simple-chat/survey` | POST | 1141 | 保存问卷数据 | 否 |
| `/simple-chat/prior-context` | GET | 1098 | 获取前序上下文 | 否 |
| `/simple-chat/prior-context` | POST | 1115 | 保存前序上下文 | 否 |
| `/simple-chat/rumination-progress` | GET | 1183 | 获取 rumination 进度 | 否 |
| `/simple-chat/rumination-progress` | POST | 1217 | 保存 rumination 进度 | 否 |
| `/simple-chat/rumination-get-table` | GET | 1373 | 获取筛选表格 | 否 |
| `/simple-chat/rumination-table-submit` | POST | 1289 | 提交筛选表格 | 否 |

---

## 六、已不再使用的逻辑（死代码）

### 6.1 后端死代码

| 代码 | 位置 | 说明 | 建议 |
|------|------|------|------|
| `detect_explicit_completion()` | dimension_completion_checker.py:141-195 | 显式完成检测函数，simple_chat.py 未导入 | 删除或标记 deprecated |
| `_should_run_completion_check()` | dimension_completion_checker.py:198-221 | 完成检测触发条件，simple_chat.py 未调用 | 删除或标记 deprecated |
| `/message` 同步端点 | simple_chat.py:1600-1760 | 前端已全部使用 `/message/stream`，同步端点无调用方 | 保留为降级方案但标记 |
| `save_basic_info()` (session 级) | survey_storage.py | 从未被调用，所有保存走 `save_basic_info_by_user()` | 删除 |
| `merge_basic_info_sources()` | survey_storage.py | 定义但从未被导入 | 删除 |
| `answer_card_summary.yaml` | domain/prompts/templates/ | 仅被 LangGraph agent 的 question_flow.py 使用，与 simple_chat 无关 | 不影响，但应标注归属 |
| `get_answer_card_prompt()` | domain/prompts/loader.py:74 | 同上，仅 LangGraph 使用 | 标注归属 |
| `ConversationCategory` 枚举 | conversation_file_manager.py:19-24 | 定义了 MAIN_FLOW/GUIDANCE/CLARIFICATION/OTHER，但 simple_chat 使用自定义 category 字符串 | 删除枚举或统一使用 |
| `merge_row_by_id()` | rumination_ops.py | 定义但未在 simple_chat.py 中使用 | 确认是否有其他调用方 |

### 6.2 前端死代码/冗余

| 代码 | 位置 | 说明 |
|------|------|------|
| `sessionIdByThread` 对象 | page.tsx:363 | 构建后未使用 |
| 重复的 `/simple-chat/init` 调用 | page.tsx:534, 579, 1093 | 三处调用逻辑相似，可提取 |
| 重复的 `/simple-chat/threads` 调用 | page.tsx:341, 465 | 两处调用逻辑相似 |

### 6.3 旧字段兼容层

`_read_conclusion_meta()` 和 `_build_conclusion_meta_update()` 维护了新旧字段的双写兼容。以下旧字段可在确认无旧数据后移除：

| 旧字段 | 新字段 | 位置 |
|--------|--------|------|
| `pending_status` | `conclusion_state` | metadata |
| `pending_conclusion` | `conclusion_draft` | metadata |
| `dimension_conclusion` | `conclusion_final` | metadata |
| `pending_last_rejected` | `conclusion_feedback` | metadata |

---

## 七、问题与风险评估

### 7.1 架构级问题

#### P0: simple_chat.py 2825 行，严重违反单一职责

**现状**：一个文件包含了：
- 16 个 API 端点
- LLM provider 选择逻辑
- 结论状态机
- 提示词构建
- SSE 流处理
- Rumination 表格管理
- 文件存储操作
- 管理员权限检查

**影响**：
- 无法独立测试任何子功能
- 修改一处容易影响其他功能
- 多人协作困难

**建议拆分方案**：
```
simple_chat.py (路由层, ~300行)
    ├─ simple_chat_stream.py (流式对话核心, ~500行)
    ├─ simple_chat_conclusion.py (结论状态机, ~400行)
    ├─ simple_chat_threads.py (线程管理端点, ~300行)
    ├─ simple_chat_rumination.py (rumination 端点, ~400行)
    ├─ simple_chat_prompt.py (提示词构建, ~200行)
    └─ simple_chat_context.py (上下文解析, ~200行)
```

#### P0: 前端 page.tsx 1788 行，同样严重

**建议拆分**：
```
page.tsx (容器组件, ~200行)
    ├─ hooks/useSimpleChat.ts (对话逻辑 + SSE, ~400行)
    ├─ hooks/useThreads.ts (线程管理, ~200行)
    ├─ hooks/useRumination.ts (rumination 逻辑, ~200行)
    ├─ components/ChatMessages.tsx (消息列表, ~200行)
    ├─ components/ChatInput.tsx (输入框, ~150行)
    └─ components/ThreadSidebar.tsx (线程侧边栏, ~150行)
```

### 7.2 LLM 调用风险

| 问题 | 位置 | 影响 | 建议 |
|------|------|------|------|
| 无超时控制 | `llm.chat_stream()` 调用处 | 流式请求可能无限挂起 | 添加 `asyncio.timeout(60)` |
| 无重试机制 | 所有 LLM 调用 | 单次失败 = 用户请求失败 | 添加指数退避重试 (3次) |
| `_last_stream_usage` 并发竞态 | simple_chat.py:2647 | 两个并发流互相覆盖 token 统计 | 改为请求级变量 |
| Pending 判定超时仅 20s | PENDING_JUDGE_TIMEOUT_SECONDS | 推理模型可能需要更长时间 | 可配置化 |
| 结论生成超时仅 25s | CONCLUSION_GEN_TIMEOUT_SECONDS | 复杂对话的结论生成可能超时 | 可配置化 |

### 7.3 数据一致性风险

| 问题 | 位置 | 影响 | 建议 |
|------|------|------|------|
| 前后端线程状态可能不一致 | threads.ts vs report record.json | 前端 localStorage 和后端文件可能分叉 | 以后端为准，前端仅缓存 |
| 结论确认后 thread_completed=False | simple_chat.py:2477 | confirmed 时 thread_completed 设为 False，需要用户再点"确认没有问题" | 考虑合并为一步 |
| 并发写入对话文件 | ConversationFileManager | FileLock 超时 30s，高并发下可能排队 | 监控锁等待时间 |
| 锚点摘要异步写入 | _trigger_anchor_refiner | fire-and-forget，失败静默 | 添加失败告警 |

### 7.4 提示词风险

| 问题 | 位置 | 影响 | 建议 |
|------|------|------|------|
| 用户输入直接拼入 system prompt | prior_block, basic_info | 用户可通过问卷注入指令 | 对 basic_info 做 sanitize |
| STATE_JSON 协议可能被用户触发 | 输出协议 | 用户发送含 `[STATE_JSON]` 的消息可能干扰解析 | 在用户消息中转义该标记 |
| 题库每线程固定但跨线程不同 | _get_or_create_thread_question_bank | 同一阶段不同线程的题库不同，可能导致体验不一致 | 可接受，但应文档化 |
| Rumination 阶段无题库 | simple_chat_system.yaml | `{{ question_bank }}` 在 rumination 分支中未使用 | 正确设计，但模板中应显式说明 |
| 历史裁剪到 30 轮可能丢失关键上下文 | MAX_HISTORY_TURNS=30 | 长对话中早期关键信息被截断 | 锚点摘要机制已部分缓解 |

### 7.5 前端风险

| 问题 | 位置 | 影响 | 建议 |
|------|------|------|------|
| SSE 手动解析而非 EventSource | page.tsx:859-1025 | 更易出错，缺少自动重连 | 考虑使用 EventSource 或 eventsource-parser 库 |
| JSON 解析错误静默吞掉 | page.tsx:1023 | 畸形响应被忽略 | 至少 console.warn |
| 无请求去重 | handleSend | 快速双击可发送重复消息 | 添加 debounce 或 loading 锁 |
| 无流超时检测 | SSE 处理 | 流挂起时用户无感知 | 添加心跳超时检测 |
| Token 刷新竞态 | page.tsx:882-894 | 多个并发 401 可能触发多次刷新 | 使用刷新锁 |

---

## 八、模块合并与复用建议

### 8.1 可合并的配置模块

**现状**：步骤定义分散在 3 个文件中

```
conclusion_card_goals.py  → 结论卡规则 + 目标 + 验证配置
dimension_completion.py   → 维度完成标准 + 目标
rumination_table_widgets.py → 引导文案 + 可编辑列定义
```

**建议**：合并为 `domain/step_definitions.py`

```python
STEP_DEFINITIONS = {
    "values": {
        "label": "价值观",
        "goal": "帮助用户发现并确认 5 个价值观关键词",
        "completion_criteria": "用户已明确确认 5 个关键词及排序",
        "conclusion_rules": "...",
        "conclusion_validation": {"min_keywords": 5, "max_keywords": 5, "strict_match": True},
        "prompt_hint": "...",
        "rumination_guide_text": None,  # 非 rumination 阶段
    },
    # ...
}
```

### 8.2 可合并的存储 API

**现状**：survey_storage.py 有两套并行 API

```
用户级: save_basic_info_by_user() / load_basic_info_by_user()  ← 当前使用
会话级: save_basic_info() / load_basic_info()                   ← 仅 load 被降级使用
```

**建议**：
1. 删除 `save_basic_info()`（从未调用）
2. 将 `load_basic_info()` 标记为 `@deprecated`，仅作迁移兼容
3. 删除 `merge_basic_info_sources()`（从未调用）

### 8.3 可合并的激活码查找

**现状**：两个入口函数

```
get_activation_manager_for_code(code)  → 按前缀选择 manager
get_activation_with_manager(code)      → 带跨 root 降级查找
```

**建议**：合并为单一入口

```python
def get_activation(code: str, *, fallback: bool = True) -> Tuple[SimpleActivationManager, Optional[ActivationRecord]]:
    """统一激活码查找入口。fallback=True 时跨 root 降级查找。"""
```

### 8.4 可提取的公共逻辑

#### 时间戳解析
`sandbox_fork.py` 和 `simple_activation_manager.py` 各自实现了过期时间解析，应提取到 `utils/time_utils.py`。

#### JSON 提取
`_extract_json_object()` 在 simple_chat.py 和 dimension_completion_checker.py 中各有一份，应提取到 `utils/json_utils.py`。

#### 激活码校验 + 报告上下文解析
`_resolve_report_context()` 被 6 个端点调用，每个端点还各自做了额外的过期检查和权限检查。应提取为装饰器或中间件。

### 8.5 `/message` 同步端点的处置

`/message` (simple_chat.py:1600-1760) 是流式端点的同步版本，逻辑高度重复但缺少：
- Pending 结论处理
- 锚点摘要触发
- 思考过程透传
- 结论卡生成

**建议**：
- 若确认前端不再调用，标记 `@deprecated` 并在下个版本删除
- 若需保留为降级方案，应复用流式端点的核心逻辑而非独立实现

---

## 九、Rumination 子流程详解

Rumination 是最复杂的子流程，涉及 9 步筛选表格：

```
Step 1: 热爱 × 优势 交叉表 (gen_table)
    用户标记每个优势是否"确定"
    │
    ▼
Step 2: 匹配性分析 (filter_strength → filter_match)
    过滤"不确定"优势，AI 标记热爱-优势匹配性
    用户可修改匹配标记
    │
    ▼
Step 3-5: 假设生成 (structure_hypothesis → round2 → round3)
    基于匹配结果生成职业假设
    用户逐步确认/修改
    │
    ▼
Step 6: 价值观筛选 (value_filter)
    添加"工作目的"列，关联价值观
    │
    ▼
Step 7: 激情标记 (passion_filter)
    标记哪些假设让用户有激情
    │
    ▼
Step 8: 现实标记 (reality_filter)
    标记哪些假设现实可行
    │
    ▼
Step 9: 最终筛选 (similar_filter)
    保留确认的假设，输出最终方向
```

**数据流**：
- 每步的表格数据存储在 `rumination_progress.json` 的 `filter_step_snapshots` 中
- 每步保存 `initial`（初始表）和 `submitted`（用户提交后的表）
- 支持 `reset_initial` 回退到该步初始状态

**问题**：
- Step 3-9 的表格生成函数（`structure_hypothesis_round1_table` 等）在 `rumination_ops.py` 中定义，但 `simple_chat.py` 仅直接使用了 Step 1-2 的函数
- Step 3+ 的逻辑可能在前端或其他端点中触发，需要确认完整调用链

---

## 十、性能瓶颈分析

### 10.1 每次请求的 I/O 操作

一次 `/message/stream` 请求涉及的文件 I/O：

```
读操作 (请求开始):
  1. activations.json (激活码查找)
  2. record.json (报告状态)
  3. {category}.json (对话历史)
  4. {category}.json (metadata 读取, 重复读)
  5. basic_info.json (用户问卷)
  6. prior_context_{phase}.txt (前序上下文)
  7. record.json (锚点摘要, 重复读)

写操作 (请求过程中):
  8. {category}.json (保存用户消息, 带文件锁)
  9. {category}.json (保存助手回复, 带文件锁)
  10. {category}.json (更新 metadata, 带文件锁)
  11. {category}__note/note.json (审计记录, 可选)
  12. record.json (锚点写入, 可选)

异步操作 (后台):
  13. record.json (锚点摘要提炼, 每 20 轮)
```

**优化建议**：
- 合并步骤 3 和 4 的重复读取（`get_messages` 和 `get_conversation_data` 读同一文件）
- 合并步骤 8、9、10 的三次写入为单次批量写入
- 缓存 `activations.json` 和 `record.json`（热数据）

### 10.2 LLM 调用次数

| 场景 | LLM 调用次数 | 模型 |
|------|-------------|------|
| 普通对话 | 1 次 | 对话模型 |
| Pending 判定 | 1-3 次 | 推理模型 (可能降级到对话模型) |
| 结论确认 | 1-2 次 | 推理模型 |
| 锚点摘要 | 1 次 | 对话模型 (后台) |

**最坏情况**：一次用户消息可能触发 1(判定) + 1(降级) + 1(结论生成) + 1(主对话) + 1(锚点) = **5 次 LLM 调用**。

---

## 十一、改进路线图

### Phase 1: 紧急修复（1 周）

- [ ] 用户消息中转义 `[STATE_JSON]` 标记，防止协议注入
- [ ] 对 `basic_info` 做 sanitize，防止提示词注入
- [ ] 前端 SSE JSON 解析错误添加 console.warn
- [ ] 前端 handleSend 添加 loading 锁防重复提交
- [ ] LLM 调用添加 `asyncio.timeout(60)`

### Phase 2: 代码治理（2 周）

- [ ] 拆分 `simple_chat.py` 为 6 个子模块
- [ ] 拆分前端 `page.tsx` 为 hooks + 子组件
- [ ] 删除已确认的死代码（`detect_explicit_completion`、`save_basic_info`、`merge_basic_info_sources`）
- [ ] 合并 `conclusion_card_goals.py` + `dimension_completion.py` 为 `step_definitions.py`
- [ ] 提取公共 JSON 提取函数到 `utils/json_utils.py`
- [ ] 标记 `/message` 同步端点为 deprecated

### Phase 3: 稳定性提升（2 周）

- [ ] LLM 调用添加指数退避重试
- [ ] 合并对话文件的重复读写操作
- [ ] 前端使用 eventsource-parser 替代手动 SSE 解析
- [ ] 添加流超时检测（前端 30s 无数据则提示）
- [ ] 超时常量（PENDING_JUDGE_TIMEOUT_SECONDS 等）迁移到 settings.py
- [ ] 添加 simple_chat 核心流程的集成测试

### Phase 4: 架构优化（按需）

- [ ] 评估 `/message` 同步端点是否可删除
- [ ] 旧 metadata 字段兼容层清理（确认无旧数据后）
- [ ] 会话级 survey_storage API 清理
- [ ] 考虑将对话存储从文件系统迁移到数据库（支持并发和查询）



