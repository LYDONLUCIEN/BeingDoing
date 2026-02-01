# API接口设计

## 一、接口规范

### 1.1 基础信息
- **Base URL**：`https://api.example.com/api/v1`
- **协议**：HTTPS
- **数据格式**：JSON（文本接口）/ Multipart（音频接口）
- **字符编码**：UTF-8
- **认证方式**：JWT Token (Bearer Token)
- **语音功能**：通过`AUDIO_MODE`配置控制，`False`时ASR/TTS相关接口不可用
- **架构模式**：通过`ARCHITECTURE_MODE`配置控制（simple/full）

### 1.2 通用响应格式

#### 成功响应
```json
{
  "code": 200,
  "message": "success",
  "data": {},
  "timestamp": "2024-01-01T00:00:00Z"
}
```

#### 错误响应
```json
{
  "code": 400,
  "message": "错误描述",
  "error": "详细错误信息",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

### 1.3 状态码
- `200`：成功
- `400`：请求参数错误
- `401`：未授权
- `404`：资源不存在
- `500`：服务器错误

## 二、API接口列表

### 2.1 认证与用户管理

#### 用户注册
```http
POST /auth/register
Content-Type: application/json

Request:
{
  "email": "user@example.com",  // 或 phone
  "phone": "13800138000",       // 或 email
  "password": "secure_password",
  "username": "optional_username"
}

Response:
{
  "code": 200,
  "data": {
    "user_id": "uuid",
    "token": "jwt_token",
    "email": "user@example.com",
    "created_at": "2024-01-01T00:00:00Z"
  }
}
```

#### 用户登录
```http
POST /auth/login
Content-Type: application/json

Request:
{
  "email": "user@example.com",  // 或 phone
  "password": "secure_password"
}

Response:
{
  "code": 200,
  "data": {
    "user_id": "uuid",
    "token": "jwt_token",
    "expires_in": 3600
  }
}
```

#### 获取当前用户信息
```http
GET /auth/me
Authorization: Bearer {token}

Response:
{
  "code": 200,
  "data": {
    "user_id": "uuid",
    "email": "user@example.com",
    "username": "username",
    "profile_completed": false,  // 是否完成信息收集
    "created_at": "2024-01-01T00:00:00Z"
  }
}
```

### 2.2 用户信息收集

#### 提交用户信息（注册后）
```http
POST /users/profile
Authorization: Bearer {token}
Content-Type: application/json

Request:
{
  "gender": "male",  // male, female, other
  "age": 28,
  "work_history": [
    {
      "company": "公司名称",
      "position": "职位",
      "start_date": "2020-01-01",
      "end_date": "2023-12-31",  // null表示当前
      "projects": [
        {
          "name": "项目名称",
          "description": "项目描述",
          "role": "担任角色",
          "achievements": "成就描述"
        }
      ],
      "evaluation": "对这段工作的评价和感受",
      "skills_used": ["技能1", "技能2"]
    }
  ]
}

Response:
{
  "code": 200,
  "data": {
    "profile_id": "uuid",
    "user_id": "uuid",
    "profile_completed": true,
    "created_at": "2024-01-01T00:00:00Z"
  }
}
```

#### 更新用户信息
```http
PATCH /users/profile
Authorization: Bearer {token}
Content-Type: application/json

Request:
{
  "gender": "female",
  "age": 29,
  "work_history": [...]  // 完整的工作履历
}
```

#### 获取用户信息
```http
GET /users/profile
Authorization: Bearer {token}

Response:
{
  "code": 200,
  "data": {
    "user_id": "uuid",
    "gender": "male",
    "age": 28,
    "work_history": [...],
    "profile_completed": true,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
  }
}
```

### 2.3 会话管理

#### 创建会话
```http
POST /sessions
Content-Type: application/json

Request:
{
  "user_id": "optional_user_id",  // 可选，匿名用户不传
  "device_id": "device_fingerprint"  // 设备指纹
}

Response:
{
  "code": 200,
  "data": {
    "session_id": "uuid",
    "created_at": "2024-01-01T00:00:00Z"
  }
}
```

#### 获取会话信息
```http
GET /sessions/{session_id}

Response:
{
  "code": 200,
  "data": {
    "session_id": "uuid",
    "user_id": "user_id_or_null",
    "current_step": "values_exploration",  // 当前步骤
    "progress": {
      "values_completed": 5,    // 已完成问题数
      "values_total": 30,        // 总问题数
      "strengths_completed": 0,
      "strengths_total": 30,
      "interests_completed": 0,
      "interests_total": 30
    },
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
  }
}
```

#### 更新会话进度
```http
PATCH /sessions/{session_id}/progress
Content-Type: application/json

Request:
{
  "current_step": "strengths_exploration",
  "step_progress": {
    "step": "values_exploration",
    "completed": 30,
    "total": 30
  }
}
```

### 2.2 问题相关

#### 获取问题列表
```http
GET /questions?category={category}&step={step}&limit={limit}&offset={offset}

Query Parameters:
- category: "values" | "strengths" | "interests"
- step: 当前步骤（可选）
- limit: 每页数量（默认10）
- offset: 偏移量（默认0）

Response:
{
  "code": 200,
  "data": {
    "questions": [
      {
        "id": 1,
        "category": "values",
        "number": 1,
        "title": "遇见谁时你会深受震撼？",
        "content": "那个人的哪些特征让你深受震撼？那些特征跟你的哪些价值观有关？",
        "hints": ["思考你尊敬的人", "关注共同特征"],
        "is_starred": false  // 是否带⭐（用于工作目的）
      }
    ],
    "total": 30,
    "limit": 10,
    "offset": 0
  }
}
```

#### 获取单个问题
```http
GET /questions/{question_id}

Response:
{
  "code": 200,
  "data": {
    "id": 1,
    "category": "values",
    "number": 1,
    "title": "遇见谁时你会深受震撼？",
    "content": "那个人的哪些特征让你深受震撼？那些特征跟你的哪些价值观有关？",
    "hints": ["思考你尊敬的人", "关注共同特征"],
    "examples": [
      {
        "text": "示例回答...",
        "source": "参考案例"
      }
    ],
    "related_content": {
      "values": ["发现", "正确性"],  // 相关价值观
      "questions": [2, 3]  // 相关问题ID
    }
  }
}
```

#### 获取默认引导问题
```http
GET /questions/guide-questions?step={step}&category={category}

Query Parameters:
- step: 当前步骤（values_exploration, strengths_exploration, interests_exploration）
- category: 问题类别（可选）

Response:
{
  "code": 200,
  "data": {
    "guide_questions": [
      {
        "id": "guide_1",
        "text": "这个问题是什么意思？",
        "type": "concept_query"
      },
      {
        "id": "guide_2",
        "text": "能给我一个示例吗？",
        "type": "example_request"
      },
      {
        "id": "guide_3",
        "text": "我不太确定怎么回答",
        "type": "confusion"
      }
    ]
  }
}
```

#### 获取问题建议（主动引导）
```http
GET /questions/suggestions?session_id={session_id}&context={context}

Query Parameters:
- session_id: 会话ID
- context: 上下文信息（JSON字符串）

Response:
{
  "code": 200,
  "data": {
    "suggestions": [
      {
        "type": "next_question",  // 或 "similar_example", "clarification"
        "content": "建议继续回答下一个问题...",
        "question_id": 2
      }
    ]
  }
}
```

### 2.3 回答相关

#### 提交回答
```http
POST /answers
Content-Type: application/json

Request:
{
  "session_id": "uuid",
  "question_id": 1,
  "content": "用户的回答内容",
  "metadata": {
    "time_spent": 120,  // 秒
    "word_count": 150
  }
}

Response:
{
  "code": 200,
  "data": {
    "answer_id": "uuid",
    "session_id": "uuid",
    "question_id": 1,
    "content": "用户的回答内容",
    "created_at": "2024-01-01T00:00:00Z"
  }
}
```

#### 更新回答
```http
PATCH /answers/{answer_id}
Content-Type: application/json

Request:
{
  "content": "更新后的回答内容"
}
```

#### 获取回答列表
```http
GET /answers?session_id={session_id}&category={category}

Response:
{
  "code": 200,
  "data": {
    "answers": [
      {
        "id": "uuid",
        "question_id": 1,
        "question_title": "遇见谁时你会深受震撼？",
        "content": "用户的回答",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z"
      }
    ],
    "total": 10
  }
}
```

#### 获取单个回答
```http
GET /answers/{answer_id}
```

### 2.4 语音服务（ASR/TTS）- 可选，AUDIO_MODE控制

#### 语音转文字（ASR）
```http
POST /audio/transcribe
Content-Type: multipart/form-data
Authorization: Bearer {token}

Request:
- file: 音频文件 (audio/wav, audio/mp3, audio/webm)
- language: "zh" (可选，默认中文)
- provider: "openai" (可选，openai/local/web_speech)

Response:
{
  "code": 200,
  "data": {
    "text": "转换后的文字内容",
    "language": "zh",
    "confidence": 0.95,
    "duration": 5.2  // 音频时长（秒）
  }
}
```

#### 文字转语音（TTS）
```http
POST /audio/synthesize
Content-Type: application/json
Authorization: Bearer {token}

Request:
{
  "text": "要转换的文字内容",
  "voice": "alloy",  // 可选，不同提供商支持不同声音
  "provider": "openai",  // openai/pyttsx3/gtts
  "format": "mp3"  // mp3/wav/opus
}

Response:
{
  "code": 200,
  "data": {
    "audio_url": "https://...",  // 音频文件URL
    "audio_base64": "base64编码的音频数据",  // 或直接返回base64
    "duration": 3.5,  // 音频时长（秒）
    "format": "mp3"
  }
}
```

**注意**：当`AUDIO_MODE=False`时，这些接口返回403错误

### 2.5 对话/问答相关

#### 发送消息（智能问答）
```http
POST /chat/messages
Content-Type: application/json

Request:
{
  "session_id": "uuid",
  "message": "用户的问题或选中的文本",
  "context": {
    "current_step": "values_exploration",
    "current_question_id": 1,
    "selected_text": "选中的文本内容（可选）"
  },
  "message_type": "text"  // 或 "voice"（语音转文字后的内容）
}

Response:
{
  "code": 200,
  "data": {
    "message_id": "uuid",
    "response": "AI的精炼回答（不超过200字）",
    "suggestions": [
      {
        "type": "related_question",
        "content": "相关问题...",
        "question_id": 2
      }
    ],
    "related_content": {
      "values": ["发现", "正确性"],
      "examples": ["示例1", "示例2"]
    },
    "created_at": "2024-01-01T00:00:00Z"
  }
}
```

#### 获取对话历史
```http
GET /chat/history?session_id={session_id}&limit={limit}&offset={offset}

Response:
{
  "code": 200,
  "data": {
    "messages": [
      {
        "id": "uuid",
        "role": "user",  // 或 "assistant"
        "content": "消息内容",
        "created_at": "2024-01-01T00:00:00Z"
      }
    ],
    "total": 20
  }
}
```

#### 主动引导（AI主动发起）
```http
POST /chat/guide
Content-Type: application/json

Request:
{
  "session_id": "uuid",
  "trigger": "idle_timeout",  // 或 "short_answer", "vague_answer", "stuck"
  "user_preference": "normal"  // normal, quiet（用户要求安静）
}

Response:
{
  "code": 200,
  "data": {
    "guidance": "引导性提示",
    "suggestions": ["建议1", "建议2"],
    "examples": ["示例1", "示例2"],
    "guide_questions": [  // 快速点选的引导问题
      {
        "id": "guide_1",
        "text": "这个问题是什么意思？",
        "type": "concept_query"
      }
    ]
  }
}
```

#### 设置引导偏好
```http
POST /chat/guide-preference
Content-Type: application/json

Request:
{
  "session_id": "uuid",
  "preference": "quiet"  // normal, quiet
}

Response:
{
  "code": 200,
  "data": {
    "preference": "quiet",
    "updated_at": "2024-01-01T00:00:00Z"
  }
}
```

### 2.6 内容检索

#### 搜索相关内容
```http
POST /search
Content-Type: application/json

Request:
{
  "query": "搜索关键词或问题",
  "category": "values",  // 或 "strengths", "interests", "all"
  "limit": 10
}

Response:
{
  "code": 200,
  "data": {
    "results": [
      {
        "type": "value",  // 或 "strength", "interest", "question"
        "id": 1,
        "title": "发现",
        "content": "找出新的东西",
        "relevance_score": 0.95,
        "source": "重要的事_价值观.csv"
      }
    ],
    "total": 10
  }
}
```

#### 获取相似示例
```http
GET /search/similar?answer_id={answer_id}&limit={limit}

Response:
{
  "code": 200,
  "data": {
    "similar_examples": [
      {
        "type": "value",
        "content": "相似内容",
        "similarity": 0.85
      }
    ]
  }
}
```

### 2.7 公式和流程

#### 获取公式说明
```http
GET /formula

Response:
{
  "code": 200,
  "data": {
    "formula1": {
      "expression": "喜欢的事 × 擅长的事 = 想做的事",
      "description": "基础公式",
      "elements": {
        "喜欢的事": {
          "definition": "指向自己有热情的领域",
          "examples": ["AI", "艺术", "创业"]
        },
        "擅长的事": {
          "definition": "自然而然就比别人做得好",
          "examples": ["构建体系", "解决问题"]
        }
      }
    },
    "formula2": {
      "expression": "喜欢的事 × 擅长的事 × 重要的事 = 真正想做的事",
      "description": "完整公式",
      "elements": {
        "重要的事": {
          "definition": "价值观/工作目的",
          "examples": ["自由", "成长", "贡献"]
        }
      }
    }
  }
}
```

#### 获取流程图数据
```http
GET /flowchart

Response:
{
  "code": 200,
  "data": {
    "steps": [
      {
        "id": "step1",
        "name": "寻找价值观",
        "description": "找到重要的事",
        "questions_count": 30,
        "estimated_time": "30分钟"
      }
    ],
    "current_step": "step1",
    "progress": 0.1
  }
}
```

### 2.8 结果和导出

#### 生成探索结果
```http
POST /results/generate
Content-Type: application/json

Request:
{
  "session_id": "uuid"
}

Response:
{
  "code": 200,
  "data": {
    "result_id": "uuid",
    "summary": {
      "values": ["发现", "成长", "自由"],
      "strengths": ["构建体系", "解决问题"],
      "interests": ["AI", "心理学"],
      "wanted_thing": "构建AI辅助的自我认知体系",
      "true_wanted_thing": "为了让更多人找到想做的事，构建AI辅助的自我认知体系"
    },
    "created_at": "2024-01-01T00:00:00Z"
  }
}
```

#### 导出结果
```http
GET /results/{result_id}/export?format={format}

Query Parameters:
- format: "pdf" | "json" | "markdown"  # 三选一

Response:
- PDF: 返回PDF文件 (Content-Type: application/pdf)
- JSON: 返回JSON数据 (Content-Type: application/json)
- Markdown: 返回Markdown文本 (Content-Type: text/markdown)

Response Headers:
Content-Disposition: attachment; filename="exploration_result.{ext}"
```

#### 获取导出状态（异步导出时）
```http
GET /results/{result_id}/export-status

Response:
{
  "code": 200,
  "data": {
    "status": "processing",  // processing, completed, failed
    "progress": 0.5,
    "download_url": "https://...",  // 完成后的下载链接
    "estimated_time": 30  // 预计剩余时间（秒）
  }
}
```

### 2.9 架构配置查询

#### 获取架构配置
```http
GET /config/architecture

Response:
{
  "code": 200,
  "data": {
    "architecture_mode": "simple",  // simple | full
    "audio_mode": false,
    "features": {
      "gateway": false,  // 是否使用网关
      "vector_db": false,  // 是否使用向量数据库
      "redis": false,  // 是否使用Redis
      "celery": false  // 是否使用Celery
    }
  }
}
```

## 三、WebSocket接口（可选，P2功能）

### 3.1 实时对话
```javascript
// 连接
ws://api.example.com/ws/chat?session_id={session_id}

// 发送消息
{
  "type": "message",
  "content": "用户消息"
}

// 接收消息
{
  "type": "response",
  "content": "AI回复"
}
```

## 四、接口认证

### 4.1 认证方式
- **方案A**：Session Token（存储在Cookie）
- **方案B**：JWT Token（存储在LocalStorage）
- **推荐**：方案B，更适合前后端分离

### 4.2 请求头
```http
Authorization: Bearer {token}
Content-Type: application/json
```

## 五、限流和缓存

### 5.1 限流
- **普通接口**：100次/分钟
- **对话接口**：20次/分钟
- **搜索接口**：50次/分钟

### 5.2 缓存策略
- **问题列表**：缓存5分钟
- **公式说明**：缓存1小时
- **搜索结果**：缓存10分钟
