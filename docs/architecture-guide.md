# BeingDoing 架构指南 - 前后端调用链路

> 帮助开发者快速理解系统核心链路，方便逐步调试。

## 目录
- [整体架构图](#整体架构图)
- [前端 Stores（全局状态）](#前端-stores)
- [前端 API 模块 → 后端路由对照表](#前后端对照表)
- [核心链路：对话流程](#核心链路对话流程)
- [Agent 节点链与关键状态](#agent-节点链)
- [SSE 流式协议](#sse-流式协议)
- [数据持久化路径](#数据持久化路径)
- [探索步骤定义](#探索步骤定义)

---

## 整体架构图

```
用户浏览器
    │
    ├── Next.js Pages ─── Zustand Stores (auth/session/progress/authModal)
    │                         │
    │                    lib/api/*.ts (Axios)
    │                         │
    │              ┌──────────┴──────────┐
    │         POST /chat-optimized/     其他 REST API
    │         messages/stream            (auth, sessions, answers...)
    │              │                         │
    ├──────── FastAPI (port 8000) ───────────┤
    │              │                         │
    │      chat_optimized.py            auth.py / sessions.py / ...
    │              │
    │      LangGraph Agent
    │      ┌───────────────────────────────────┐
    │      │ reasoning → action → observation  │ ← 循环
    │      │         ↓                         │
    │      │   user_agent_node → END           │
    │      └───────────────────────────────────┘
    │              │
    │      OpenAI LLM / Knowledge Base (CSV)
    │
    └── 数据存储
         ├── data/conversations/{session_id}/  (对话文件)
         ├── data/question_progress/           (题目进度)
         ├── logs/{user_id}/{session_id}/      (调试日志)
         └── SQLite / PostgreSQL               (用户、会话、答案)
```

---

## 前端 Stores

| Store | 文件 | 关键状态 | 持久化 |
|-------|------|---------|--------|
| `useAuthStore` | `stores/authStore.ts` | `user`, `token`, `isAuthenticated` | localStorage `auth-storage` |
| `useSessionStore` | `stores/sessionStore.ts` | `currentSession` (session_id, current_step) | localStorage `session-storage` |
| `useProgressStore` | `stores/progressStore.ts` | `progresses` (每步骤完成数/总数) | localStorage `progress-storage` |
| `useAuthModalStore` | `stores/authModalStore.ts` | `isOpen`, `redirectTo` | 无(内存) |

---

## 前后端对照表

### 认证 (`lib/api/auth.ts` → `api/v1/auth.py`)

| 前端触发 | 前端函数 | HTTP | 后端路由 | 后端函数 | 说明 |
|---------|---------|------|---------|---------|------|
| AuthModal 登录按钮 | `authApi.login()` | POST | `/auth/login` | `login()` | 返回 JWT token |
| AuthModal 注册按钮 | `authApi.register()` | POST | `/auth/register` | `register()` | 创建用户 + 返回 token |
| 登录后获取用户信息 | `authApi.getCurrentUser()` | GET | `/auth/me` | `get_current_user()` | 返回 user 对象 |

### 会话 (`lib/api/sessions.ts` → `api/v1/sessions.py`)

| 前端触发 | 前端函数 | HTTP | 后端路由 | 后端函数 | 说明 |
|---------|---------|------|---------|---------|------|
| Explore 页 "新的开始" | `sessionsApi.create()` | POST | `/sessions` | `create_session()` | 创建 session，前端存入 sessionStore |
| History 页加载 | `sessionsApi.list()` | GET | `/sessions` | `list_sessions()` | 按活跃度排序 |
| History 页删除 | `sessionsApi.delete()` | DELETE | `/sessions/{id}` | `delete_session()` | 同时删除对话文件 |

### 核心对话 (`lib/api/chat.ts` → `api/v1/chat_optimized.py`)

| 前端触发 | 前端函数 | HTTP | 后端路由 | 后端函数 | 说明 |
|---------|---------|------|---------|---------|------|
| 输入框发送消息 | `chatApi.sendMessageStream()` | POST | `/chat-optimized/messages/stream` | `stream_message_optimized()` | **核心链路** SSE 流式 |
| Flow 页加载 | `chatApi.getHistory()` | GET | `/chat/history` | `get_conversation_history()` | 恢复聊天记录 |
| Flow 页加载 | `chatApi.getAnswerCards()` | GET | `/chat-optimized/answer-cards` | `get_answer_cards()` | 恢复已完成答题卡 |
| 用户中断流式 | `chatApi.recordInterrupt()` | POST | `/chat/record-interrupt` | `record_interrupt()` | 记录中断位置 |
| Debug 面板 | `chatApi.getDebugLogs()` | GET | `/chat/debug-logs` | `get_debug_logs()` | 仅超管可用 |

### 其他 API

| 模块 | 前端函数 | 后端路由 | 说明 |
|------|---------|---------|------|
| `answers.ts` | `answersApi.submit()` | POST `/answers` | 提交答案 |
| `answers.ts` | `answersApi.update()` | PATCH `/answers/{id}` | 更新答案 |
| `users.ts` | `usersApi.submitProfile()` | POST `/users/profile` | 提交用户画像 |
| `questions.ts` | `questionsApi.getQuestions()` | GET `/questions` | 获取题目列表 |
| `formula.ts` | `formulaApi.getFormula()` | GET `/formula` | 获取天命公式 |

---

## 核心链路：对话流程

这是系统最关键的链路，从用户输入到 AI 回复的完整路径：

```
┌─ 前端 ──────────────────────────────────────────────────────┐
│                                                               │
│  1. 用户在 ConversationInput 输入文字，点击发送               │
│     ↓                                                         │
│  2. flow/page.tsx → handleChatSubmit(content)                │
│     ├─ 添加用户消息到 chatMessages (临时显示)                 │
│     ├─ setStreaming(true)                                     │
│     └─ 调用 chatApi.sendMessageStream({                      │
│            session_id,    ← 来自 sessionStore                │
│            message,       ← 用户输入                         │
│            current_step,  ← 当前探索步骤                     │
│            category: 'main_flow'                              │
│        })                                                     │
│                                                               │
│  请求体 → POST /api/v1/chat-optimized/messages/stream        │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌─ 后端 chat_optimized.py ────────────────────────────────────┐
│                                                               │
│  3. stream_message_optimized(request, current_user)          │
│     ├─ 保存用户消息到 main_flow.json                         │
│     ├─ 加载已有的 question_progress                          │
│     ├─ get_or_create_graph(session_id)  ← 带缓存            │
│     ├─ create_initial_state(                                 │
│     │     user_input, current_step, session_id,              │
│     │     stream_queue=asyncio.Queue(),  ← SSE推送队列      │
│     │     question_progress=saved_qp                         │
│     │  )                                                      │
│     └─ 启动 graph.astream(state)                             │
│                                                               │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌─ LangGraph Agent ───────────────────────────────────────────┐
│                                                               │
│  4. reasoning_node(state)                                    │
│     ├─ 检查是否需要步骤介绍 / 出新题                         │
│     ├─ 构建 Prompt (YAML模板 + 上下文 + 用户输入)            │
│     ├─ 调用 LLM (chat_stream → stream_queue 实时推送)       │
│     ├─ 生成 answer_card (当 AI 判断回答充分时)               │
│     ├─ 生成 suggestions (3个引导标签)                        │
│     └─ 设置 state.final_response / should_continue           │
│                                                               │
│  5. action_node(state)  ← 如果需要搜索知识库                 │
│     └─ 执行 SearchTool / GuideTool / ExampleTool             │
│                                                               │
│  6. observation_node(state)  ← 处理工具结果                  │
│     └─ 判断是否继续循环 (最多 5 轮)                          │
│                                                               │
│  7. user_agent_node(state)  ← 转换为用户可见输出             │
│     ├─ 将 final_response 写入 state.messages                 │
│     └─ 格式化 answer_card / suggestions 元数据               │
│                                                               │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌─ 后端 SSE 响应 ────────────────────────────────────────────┐
│                                                               │
│  8. 流式事件序列:                                            │
│     {"started": true}                                        │
│     {"chunk": "你好"}                                        │
│     {"chunk": "！我理解..."}                                  │
│     ...                                                       │
│     {"done": true,                                           │
│      "response": "完整回复文本",                              │
│      "answer_card": {...} | null,                            │
│      "question_progress": {...} | null,                      │
│      "suggestions": ["继续聊聊", "下一题", "具体说说"]}      │
│                                                               │
│  9. 保存上下文:                                              │
│     ├─ main_flow.json  (用户可见对话)                        │
│     ├─ all_flow.json   (AI 思考过程)                         │
│     ├─ note.json       (答题卡/总结)                         │
│     └─ question_progress.json (题目状态)                     │
│                                                               │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌─ 前端回调处理 ──────────────────────────────────────────────┐
│                                                               │
│  10. onStarted() → 显示 "思考中…"                            │
│  11. onChunk(chunk) → 实时拼接显示 AI 回复                   │
│  12. onDone(fullResponse, meta):                             │
│      ├─ setStreamingContent('') → 清除流式内容               │
│      ├─ setAnswerCard(meta.answerCard) → 显示答题卡          │
│      ├─ setQuestionProgress(meta.questionProgress)           │
│      ├─ setSuggestions(meta.suggestions) → 显示引导标签       │
│      └─ loadChatHistory() → 从后端重新加载持久化消息         │
│                                                               │
│  13. 用户后续操作:                                           │
│      ├─ 确认答案 → handleConfirmAnswer()                     │
│      │   └─ 答题卡移入已完成列表, 清空对话, 触发下一题      │
│      ├─ 继续讨论 → handleDiscussMore()                       │
│      │   └─ 隐藏答题卡, 保留对话继续聊                       │
│      └─ 点击建议标签 → 自动填入输入框                        │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## Agent 节点链

### 状态对象 `AgentState` (state.py)

| 字段 | 类型 | 用途 | 暴露给前端？ |
|------|------|------|------------|
| `messages` | `List[LLMMessage]` | 用户可见的对话消息 | YES |
| `inner_messages` | `List[LLMMessage]` | AI 内部思考链 | NO |
| `logs` | `List[Dict]` | 过程日志 | DEBUG面板 |
| `final_response` | `str` | 本轮最终回复 | YES (通过 SSE) |
| `answer_card` | `Dict` | 答题卡元数据 | YES |
| `suggestions` | `List[str]` | 引导标签 | YES |
| `question_progress` | `Dict` | 题目进度状态 | YES |
| `current_step` | `str` | 当前步骤 ID | YES |
| `context` | `Dict` | 上下文变量 | NO |
| `stream_queue` | `asyncio.Queue` | SSE 推送队列 | NO (内部) |
| `should_continue` | `bool` | 是否继续循环 | NO |
| `session_token_usage` | `Dict` | Token 用量累计 | DEBUG日志 |

### 节点执行图

```
START
  │
  ▼
reasoning_node ◄──────────┐
  │                        │
  ▼                        │
action_node                │ (最多循环 5 次)
  │                        │
  ▼                        │
observation_node ──────────┘
  │           should_continue = false
  ▼
user_agent_node
  │
  ▼
END → SSE 推送
```

### 配置 `AgentRunConfig` (config.py)

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `use_user_agent_node` | `True` | 是否走 user_agent_node 输出 |
| `max_iterations` | `10` | 全局最大循环次数 |
| `compress_context` | `True` | 上下文压缩 |
| `max_rounds_per_step` | `5` | 单步骤最大循环 |

---

## SSE 流式协议

前端 `chatApi.sendMessageStream()` 解析以下 SSE 事件：

```
事件1:  data: {"started": true}
         → onStarted()

事件2~N: data: {"chunk": "一段文字"}
         → onChunk(chunk)  // 实时拼接

最终:    data: {"done": true,
                "response": "完整回复",
                "answer_card": {                    // 可能为 null
                  "question_id": 5,
                  "question_content": "...",
                  "user_answer": "...",
                  "ai_summary": "...",
                  "ai_analysis": "...",
                  "key_insights": ["...", "..."]
                },
                "question_progress": {              // 可能为 null
                  "current_index": 4,
                  "total_questions": 30,
                  "completed_count": 4
                },
                "suggestions": ["继续聊聊", "下一题", "具体说说"]}
         → onDone(response, meta)

异常:    data: {"error": "错误信息"}
         → onError(err)
```

---

## 数据持久化路径

所有复杂版 explore 的日志、对话、题目进度均存储在**项目根 ./data/** 下，不依赖 src/backend 目录：

```
项目根 (BeingDoing/)  data/
├── conversations/{session_id}/
│   ├── main_flow.json     ← 用户可见对话 (getHistory 读取)
│   ├── all_flow.json      ← AI 完整思考过程
│   └── note.json          ← 答题卡 + 总结 (getAnswerCards 读取)
├── question_progress/
│   └── {session_id}.json  ← 题目状态 (哪些完成/进行中/未开始)
├── debug_logs/
│   └── {session_id}.jsonl ← 按 session 的调试日志
├── logs/
│   └── {user_id}/{session_id}/
│       └── runs.jsonl     ← 按用户/会话的调试日志
└── simple/                ← 简单版（激活码、对话等）
    └── ...

src/backend/
└── app.db                 ← SQLite 数据库 (User, Session, Answer)
```

### 文件格式速查

**main_flow.json**
```json
{ "session_id": "...", "messages": [
    {"role": "user", "content": "...", "created_at": "..."},
    {"role": "assistant", "content": "...", "created_at": "..."}
]}
```

**note** (答题卡)
```json
{ "session_id": "...", "notes": [
    {"id": "answer_card_1", "type": "answer_card",
     "content": "{JSON: question_id, user_answer, ai_summary, ...}",
     "metadata": {"question_id": 1, "current_step": "values_exploration"}}
]}
```

**question_progress/{session_id}.json**
```json
{ "values_exploration": {
    "questions": [
      {"question_id": 1, "status": "completed", "turn_count": 5},
      {"question_id": 2, "status": "in_progress", "turn_count": 2},
      ...
    ],
    "current_question_index": 1
}}
```

---

## 探索步骤定义

源文件: `src/backend/app/domain/steps.py`

| 步骤 ID | 名称 | 知识库分类 | 顺序 |
|---------|------|-----------|------|
| `values_exploration` | 探索重要的事（价值观） | values | 1 |
| `strengths_exploration` | 探索擅长的事（才能） | strengths | 2 |
| `interests_exploration` | 探索喜欢的事（热情） | interests | 3 |
| `combination` | 组合分析 | - | 4 |
| `refinement` | 精炼结果 | - | 5 |

天命公式: **喜欢 x 擅长 x 价值观 = 天命**

---

## 调试脚本

```bash
cd src/backend

# 查看数据状态报告
python scripts/sync_data.py --report

# 同步 debug logs + 重建 answer cards
python scripts/sync_data.py

# 仅预览不写入
python scripts/sync_data.py --dry-run
```
