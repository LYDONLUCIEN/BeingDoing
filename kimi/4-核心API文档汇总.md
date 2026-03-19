# BeingDoing 项目 - 核心API文档汇总

> 分析时间：2026-03-19
> 基础URL: `http://localhost:8000/api/v1`

---

## 一、API概览

### 1.1 接口分类

| 分类 | 前缀 | 说明 |
|-----|------|------|
| 简单模式对话 | `/simple-chat/*` | 当前主要使用的对话接口 |
| 完整模式对话 | `/chat/*` | LangGraph智能体对话（备用） |
| 认证 | `/auth/*`, `/simple-auth/*` | 用户认证与激活码验证 |
| 用户 | `/users/*` | 用户信息管理 |
| 会话 | `/sessions/*` | 会话管理 |
| 管理 | `/admin/*` | 后台管理接口 |
| 其他 | `/formula/*`, `/export/*` 等 | 辅助功能接口 |

### 1.2 通用响应格式

```typescript
// 标准响应
interface StandardResponse<T> {
  code: number;      // 200 成功，其他为错误码
  message: string;   // 提示信息
  data: T;          // 响应数据
}

// 错误响应
interface ErrorResponse {
  code: number;      // 400/401/403/500等
  message: string;   // 错误描述
  detail?: string;   // 详细错误信息
}
```

---

## 二、简单模式对话API（主要使用）

### 2.1 初始化对话

```http
POST /simple-chat/init
```

**请求体：**
```typescript
interface SimpleInitRequest {
  activation_code: string;    // 激活码
  phase: string;              // 阶段: values | strengths | interests | purpose
  thread_id?: string;         // 可选，指定对话线程ID
}
```

**响应：**
```typescript
interface SimpleInitResponse {
  messages: Array<{
    role: 'assistant';
    content: string;
  }>;                         // 初始消息列表
  activation: {
    activation_code: string;
    session_id: string;
    mode: string;
    created_at: string;
    expires_at: string;
    status: string;
  };
  report_id: string;          // 报告ID
  step_id: string;            // 阶段ID
}
```

**说明：**
- 如果该阶段已有历史消息，直接返回历史
- 如果没有历史，生成一条首轮引导问题的assistant消息

---

### 2.2 发送消息（流式）

```http
POST /simple-chat/message/stream
Content-Type: application/json
Authorization: Bearer {token}
```

**请求体：**
```typescript
interface SimpleChatStreamRequest {
  activation_code: string;    // 激活码
  message: string;            // 用户消息
  phase?: string;             // 阶段，默认values
  thread_id?: string;         // 对话线程ID
}
```

**响应：** SSE流式响应

```
data: {"started": true}

data: {"chunk": "这是"}

data: {"chunk": "流式"}

data: {"chunk": "输出"}

data: {
  "done": true,
  "response": "这是完整的助手回复",
  "dimension_conclusion": {    // 可选，当检测到完成时
    "question_id": 1,
    "question_content": "...",
    "user_answer": "...",
    "ai_summary": "...",
    "ai_analysis": "...",
    "key_insights": ["..."]
  },
  "suggestions": ["建议1", "建议2", "建议3"]
}
```

**错误响应：**
```
data: {"error": "激活码已过期"}
```

---

### 2.3 获取历史消息

```http
GET /simple-chat/history?activation_code={code}&phase={phase}&thread_id={tid}
Authorization: Bearer {token}
```

**查询参数：**
| 参数 | 类型 | 必填 | 说明 |
|-----|------|------|------|
| activation_code | string | ✅ | 激活码 |
| phase | string | ✅ | 阶段 |
| thread_id | string | ❌ | 对话线程ID |

**响应：**
```typescript
interface SimpleHistoryResponse {
  messages: Array<{
    id?: string;
    role: 'user' | 'assistant' | 'conclusion_card';
    content: string;
    created_at?: string;
    session_id?: string;
    step_id?: string;
    event?: string;
    card_type?: string;
    card_payload?: any;
  }>;
  metadata: {
    thread_completed: boolean;      // 是否已完成
    dimension_conclusion?: any;     // 维度结论
  };
  activation: {
    activation_code: string;
    session_id: string;
    mode: string;
    created_at: string;
    expires_at: string;
    status: string;
  };
  report_id: string;
  step_id: string;
}
```

---

### 2.4 标记对话完成

```http
POST /simple-chat/thread/complete
```

**请求体：**
```typescript
interface ThreadCompleteRequest {
  activation_code: string;    // 激活码
  phase: string;              // 阶段
  thread_id: string;          // 对话线程ID
}
```

**说明：**
- 用户点击"确认没有问题"后调用
- 将当前对话标记为已完成
- 生成conclusion_card消息

---

### 2.5 重新打开对话

```http
POST /simple-chat/thread/reopen
```

**请求体：**
```typescript
interface ThreadReopenRequest {
  activation_code: string;    // 激活码
  phase: string;              // 阶段
  thread_id: string;          // 对话线程ID
}
```

**说明：**
- 用户选择"再聊聊"完善答案时调用
- 清除完成状态以便继续对话
- 如果阶段已锁定，返回400错误

---

### 2.6 问卷相关接口

#### 获取问卷数据
```http
GET /simple-chat/survey?activation_code={code}
```

**响应：**
```typescript
{
  survey_data: {
    ageRange?: string;
    gender?: string;
    occupation?: string;
    // ... 其他字段
  }
}
```

#### 保存问卷数据
```http
POST /simple-chat/survey
```

**请求体：**
```typescript
interface SurveySaveRequest {
  activation_code: string;
  survey_data: {
    ageRange?: string;
    gender?: string;
    occupation?: string;
    // ... 其他字段
  };
}
```

---

### 2.7 上一轮结果接口

#### 获取上一轮结果
```http
GET /simple-chat/prior-context?activation_code={code}&phase={phase}
```

**响应：**
```typescript
{
  context_text: string;    // 上一轮咨询结果文本
}
```

#### 保存上一轮结果
```http
POST /simple-chat/prior-context
```

**请求体：**
```typescript
interface PriorContextSaveRequest {
  activation_code: string;
  phase: string;           // 目标阶段
  context_text: string;    // 上一轮结果文本
}
```

---

## 三、完整模式对话API（备用）

### 3.1 发送消息

```http
POST /chat/messages
```

**请求体：**
```typescript
interface SendMessageRequest {
  session_id: string;         // 会话ID
  message: string;            // 用户消息
  current_step?: string;      // 当前步骤，默认values_exploration
  category?: string;          // 分类: main_flow/guidance/clarification/other
  force_regenerate_card?: boolean;  // 强制重新生成答题卡
}
```

**响应：**
```typescript
interface SendMessageResponse {
  response: string;           // 助手回复
  session_id: string;
  tools_used: string[];       // 使用的工具
  logs: any[];               // 调试日志
  question_progress?: {      // 题目进度（v2.4新增）
    current_question_id: number | null;
    current_index: number;
    total_questions: number;
    completed_count: number;
    current_question_content: string | null;
    is_intro_shown: boolean;
  };
  answer_card?: {            // 答题卡（v2.4新增）
    question_id: number;
    question_content: string;
    user_answer: string;
    ai_summary: string;
    ai_analysis: string;
    key_insights: string[];
  } | null;
  suggestions: string[];      // 建议标签
}
```

---

### 3.2 发送消息（流式）

```http
POST /chat/messages/stream
```

**请求体：** 同 `/chat/messages`

**响应：** SSE流式响应

```
data: {"started": true}

data: {"chunk": "流式内容..."}

data: {
  "done": true,
  "response": "完整回复",
  "answer_card": {...},
  "question_progress": {...},
  "suggestions": ["..."]
}
```

---

### 3.3 获取对话历史

```http
GET /chat/history?session_id={id}&category={cat}&limit={n}
```

**查询参数：**
| 参数 | 类型 | 必填 | 说明 |
|-----|------|------|------|
| session_id | string | ✅ | 会话ID |
| category | string | ❌ | 分类筛选 |
| limit | number | ❌ | 限制数量 |

---

### 3.4 触发主动引导

```http
POST /chat/guide
```

**请求体：**
```typescript
interface GuideRequest {
  session_id: string;
  current_step: string;
}
```

---

### 3.5 设置引导偏好

```http
POST /chat/guide-preference
```

**请求体：**
```typescript
interface GuidePreferenceRequest {
  session_id: string;
  preference: 'normal' | 'quiet';  // 正常/安静模式
}
```

---

### 3.6 重新梳理总结

```http
POST /chat/resummarize
```

**请求体：**
```typescript
interface ResummarizeRequest {
  session_id: string;
  current_step?: string;
}
```

---

### 3.7 记录打断

```http
POST /chat/record-interrupt
```

**请求体：**
```typescript
interface RecordInterruptRequest {
  session_id: string;
  partial_content: string;    // 截至内容
  current_step?: string;
}
```

---

### 3.8 获取调试日志（仅超级管理员）

```http
GET /chat/debug-logs?session_id={id}
Authorization: Bearer {admin_token}
```

**响应：**
```typescript
{
  entries: Array<{
    timestamp: string;
    user_id: string;
    session_id: string;
    user_input: string;
    response_preview: string;
    logs: any[];
    tools_used: string[];
    context_keys: string[];
    token_usage: {
      prompt_tokens: number;
      completion_tokens: number;
      total_tokens: number;
    };
  }>;
}
```

---

## 四、认证API

### 4.1 用户注册

```http
POST /auth/register
```

**请求体：**
```typescript
interface RegisterRequest {
  email: string;
  password: string;
  name?: string;
}
```

---

### 4.2 用户登录

```http
POST /auth/login
```

**请求体：**
```typescript
interface LoginRequest {
  email: string;
  password: string;
}
```

**响应：**
```typescript
{
  access_token: string;    // JWT Token
  token_type: "bearer";
  user: {
    user_id: string;
    email: string;
    name: string;
  };
}
```

---

### 4.3 激活码验证（简单模式）

```http
POST /simple-auth/activate
```

**请求体：**
```typescript
interface ActivateRequest {
  activation_code: string;    // 激活码
}
```

**响应：**
```typescript
{
  activation_code: string;
  session_id: string;
  mode: string;
  created_at: string;
  expires_at: string;
  status: string;
}
```

---

## 五、会话API

### 5.1 创建会话

```http
POST /sessions
```

**请求体：**
```typescript
interface CreateSessionRequest {
  device_id?: string;
  current_step?: string;      // 默认values_exploration
}
```

---

### 5.2 获取会话列表

```http
GET /sessions
Authorization: Bearer {token}
```

**响应：**
```typescript
{
  sessions: Array<{
    session_id: string;
    user_id: string;
    current_step: string;
    status: string;
    created_at: string;
    updated_at: string;
    last_activity_at: string;
  }>;
}
```

---

### 5.3 获取会话详情

```http
GET /sessions/{session_id}
```

---

### 5.4 删除会话

```http
DELETE /sessions/{session_id}
```

---

### 5.5 更新会话进度

```http
PATCH /sessions/{session_id}/progress?step={step}&completed_count={n}&total_count={m}
```

---

### 5.6 获取会话问卷

```http
GET /sessions/{session_id}/survey
```

---

### 5.7 保存会话问卷

```http
POST /sessions/{session_id}/survey
```

**请求体：**
```typescript
{
  survey_data: object;
}
```

---

## 六、用户API

### 6.1 获取当前用户

```http
GET /users/me
Authorization: Bearer {token}
```

---

### 6.2 更新用户信息

```http
PUT /users/me
```

**请求体：**
```typescript
{
  name?: string;
  // 其他可更新字段
}
```

---

## 七、公式API

### 7.1 获取流程图数据

```http
GET /formula/flowchart
```

**响应：**
```typescript
{
  steps: Array<{
    id: string;
    name: string;
    description: string;
    order: number;
  }>;
}
```

---

## 八、导出API

### 8.1 导出报告

```http
GET /export/report?session_id={id}&format={format}
```

**查询参数：**
| 参数 | 类型 | 必填 | 说明 |
|-----|------|------|------|
| session_id | string | ✅ | 会话ID |
| format | string | ❌ | 格式: json/md/pdf，默认json |

---

## 九、管理API

### 9.1 获取系统统计

```http
GET /admin/stats
Authorization: Bearer {admin_token}
```

---

### 9.2 获取激活码列表

```http
GET /admin/activations
Authorization: Bearer {admin_token}
```

---

### 9.3 创建激活码

```http
POST /admin/activations
Authorization: Bearer {admin_token}
```

**请求体：**
```typescript
{
  count?: number;        // 创建数量，默认1
  expires_in_days?: number;  // 过期天数
}
```

---

### 9.4 获取对话记录

```http
GET /admin/conversations?session_id={id}
Authorization: Bearer {admin_token}
```

---

## 十、API调用示例

### 10.1 完整对话流程（简单模式）

```typescript
// 1. 验证激活码
const activateRes = await fetch('/api/v1/simple-auth/activate', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ activation_code: 'ABC123' }),
});

// 2. 初始化对话
const initRes = await fetch('/api/v1/simple-chat/init', {
  method: 'POST',
  headers: { 
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  },
  body: JSON.stringify({ 
    activation_code: 'ABC123',
    phase: 'values',
    thread_id: 'thread_001'
  }),
});

// 3. 发送消息（流式）
const response = await fetch('/api/v1/simple-chat/message/stream', {
  method: 'POST',
  headers: { 
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  },
  body: JSON.stringify({ 
    activation_code: 'ABC123',
    message: '我觉得成就感对我很重要',
    phase: 'values',
    thread_id: 'thread_001'
  }),
});

// 4. 读取流式响应
const reader = response.body.getReader();
const decoder = new TextDecoder();
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  const text = decoder.decode(value);
  // 处理SSE数据
  const lines = text.split('\n');
  for (const line of lines) {
    if (line.startsWith('data: ')) {
      const data = JSON.parse(line.slice(6));
      if (data.chunk) {
        // 处理流式内容
        console.log(data.chunk);
      }
      if (data.done) {
        // 对话完成
        console.log('完整回复:', data.response);
        if (data.dimension_conclusion) {
          // 显示答题卡
          console.log('答题卡:', data.dimension_conclusion);
        }
      }
    }
  }
}

// 5. 标记完成
await fetch('/api/v1/simple-chat/thread/complete', {
  method: 'POST',
  headers: { 
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  },
  body: JSON.stringify({ 
    activation_code: 'ABC123',
    phase: 'values',
    thread_id: 'thread_001'
  }),
});
```

---

## 十一、错误码说明

| 状态码 | 说明 | 常见场景 |
|-------|------|---------|
| 200 | 成功 | 请求正常处理 |
| 400 | 请求参数错误 | 缺少必填参数、参数格式错误 |
| 401 | 未认证 | Token缺失或过期 |
| 403 | 无权限 | 非超级管理员访问管理接口 |
| 404 | 资源不存在 | 激活码不存在、会话不存在 |
| 500 | 服务器错误 | 内部处理异常 |

---

## 十二、WebSocket/SSE说明

当前项目使用 **SSE (Server-Sent Events)** 实现流式输出：

```
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no
```

数据格式：
```
data: {"key": "value"}\n\n
```

前端使用 `EventSource` 或 `fetch + ReadableStream` 接收。
