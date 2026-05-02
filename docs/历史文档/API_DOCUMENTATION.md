# API接口文档

## 📡 基础信息

- **Base URL**: `http://localhost:8000/api/v1`
- **认证方式**: Bearer Token (JWT)
- **数据格式**: JSON

## 🔐 认证API

### POST /auth/register
用户注册

**请求体**:
```json
{
  "email": "user@example.com",  // 可选
  "phone": "13800138000",       // 可选
  "username": "username",       // 可选
  "password": "password123"
}
```

**响应**:
```json
{
  "code": 200,
  "message": "注册成功",
  "data": {
    "user_id": "uuid",
    "token": "jwt_token",
    "expires_in": 2592000
  }
}
```

### POST /auth/login
用户登录

**请求体**:
```json
{
  "email": "user@example.com",  // 可选
  "phone": "13800138000",       // 可选
  "password": "password123"
}
```

**响应**: 同注册接口

### GET /auth/me
获取当前用户信息

**Headers**: `Authorization: Bearer {token}`

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "user_id": "uuid",
    "email": "user@example.com",
    "username": "username"
  }
}
```

## 👤 用户信息API

### POST /users/profile
提交用户基本信息

**请求体**:
```json
{
  "gender": "male",  // 可选
  "age": 25          // 可选
}
```

### GET /users/profile
获取用户完整信息

### POST /users/work-history
提交工作履历

**请求体**:
```json
{
  "company": "公司名称",
  "position": "职位",
  "start_date": "2020-01-01",
  "end_date": "2023-12-31",  // 可选，留空表示当前工作
  "evaluation": "工作评价",
  "skills_used": ["技能1", "技能2"]  // 可选
}
```

### POST /users/work-history/{work_history_id}/projects
提交项目经历

**请求体**:
```json
{
  "name": "项目名称",
  "description": "项目描述",  // 可选
  "role": "担任角色",         // 可选
  "achievements": "成就描述"  // 可选
}
```

## 💬 会话管理API

### POST /sessions/
创建会话

**请求体**:
```json
{
  "device_id": "device_id",           // 可选
  "current_step": "values_exploration" // 可选
}
```

### GET /sessions/{session_id}
获取会话信息

### PATCH /sessions/{session_id}/progress
更新会话进度

**Query参数**:
- `step`: 探索步骤
- `completed_count`: 已完成数量（可选）
- `total_count`: 总数量（可选）

## ❓ 问题API

### GET /questions
获取问题列表

**Query参数**:
- `category`: 问题分类（values/strengths/interests）

### GET /questions/{question_id}
获取单个问题

### GET /questions/guide-questions/list
获取默认引导问题

**Query参数**:
- `current_step`: 当前步骤
- `limit`: 返回数量限制（默认5）

### GET /questions/starred/list
获取带星号的问题

**Query参数**:
- `category`: 问题分类

## 📝 回答API

### POST /answers
提交回答

**请求体**:
```json
{
  "session_id": "session_id",
  "category": "values",  // values/strengths/interests
  "content": "回答内容",
  "question_id": 1,      // 可选
  "metadata": {}         // 可选
}
```

### PATCH /answers/{answer_id}
更新回答

### GET /answers
获取回答列表

**Query参数**:
- `session_id`: 会话ID
- `category`: 问题分类（可选）

### GET /answers/{answer_id}
获取单个回答

## 💬 对话API

### POST /chat/messages
发送消息

**请求体**:
```json
{
  "session_id": "session_id",
  "message": "用户消息",
  "current_step": "values_exploration",
  "category": "main_flow"  // main_flow/guidance/clarification/other
}
```

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "response": "AI回复",
    "session_id": "session_id",
    "tools_used": ["search_tool", "guide_tool"]
  }
}
```

### GET /chat/history
获取对话历史

**Query参数**:
- `session_id`: 会话ID
- `category`: 对话分类（可选）
- `limit`: 限制数量（可选）

### POST /chat/guide
触发主动引导

**请求体**:
```json
{
  "session_id": "session_id",
  "current_step": "values_exploration"
}
```

### POST /chat/guide-preference
设置引导偏好

**请求体**:
```json
{
  "session_id": "session_id",
  "preference": "normal"  // normal/quiet
}
```

## 🧭 简单模式对话 API (Simple Chat)

> 激活码模式下的对话与线程管理，**后端为数据源**，支持跨设备同步。

### GET /simple-chat/threads
获取某阶段的线程列表（后端主数据源，跨设备可见）

**Query 参数**:
- `activation_code`: 激活码
- `phase`: 阶段 (values/strengths/interests/purpose/rumination)

**响应**:
```json
{
  "code": 200,
  "data": {
    "threads": [
      {
        "id": "t_1773119248061_4oxrs0r",
        "title": "对话 1",
        "status": "in-progress",
        "createdAt": 1773119248061,
        "dimensionConclusion": null,
        "selected": false
      }
    ],
    "report_id": "uuid",
    "step_id": "values"
  }
}
```

### GET /simple-chat/history
获取某线程的消息历史

**Query 参数**:
- `activation_code`: 激活码
- `phase`: 阶段
- `thread_id`: 线程 ID

### POST /simple-chat/init
新建线程并获取首条引导消息

**请求体**:
- `activation_code`: 激活码
- `phase`: 阶段
- `thread_id`: 新建的线程 ID（前端生成）

## 🔍 内容检索API

### POST /search
搜索内容

**请求体**:
```json
{
  "query": "搜索关键词",
  "category": "values",  // 可选：values/interests/strengths/questions
  "limit": 10
}
```

### GET /search/similar
获取相似示例

**Query参数**:
- `query`: 查询文本
- `category`: 分类（values/interests/strengths）
- `limit`: 返回数量限制（默认5）

## 📊 公式和流程API

### GET /formula
获取公式信息

### GET /formula/flowchart
获取流程图信息

## 🎤 语音API（可选）

### POST /audio/transcribe
转录音频（ASR）

**请求**: multipart/form-data
- `file`: 音频文件
- `language`: 语言代码（可选）

**注意**: 需要 `AUDIO_MODE=True`

### POST /audio/synthesize
合成语音（TTS）

**请求体**:
```json
{
  "text": "要合成的文本",
  "voice": "alloy",  // alloy/echo/fable/onyx/nova/shimmer
  "speed": 1.0       // 0.25-4.0
}
```

**注意**: 需要 `AUDIO_MODE=True`

## 📥 导出API

### POST /export/generate
生成导出文件

**请求体**:
```json
{
  "user_id": "user_id",
  "session_id": "session_id",
  "format": "json"  // json/markdown/pdf
}
```

**响应**:
```json
{
  "code": 200,
  "message": "导出成功",
  "data": {
    "export_id": "export_id",
    "format": "json",
    "file_path": "/tmp/export_id.json"
  }
}
```

### GET /export/download
下载导出文件

**Query参数**:
- `export_id`: 导出ID

## ⚙️ 配置API

### GET /config/architecture
获取架构配置

**响应**:
```json
{
  "architecture_mode": "simple",
  "audio_mode": false,
  "features": {
    "gateway": false,
    "vector_db": false,
    "redis": false,
    "celery": false
  }
}
```

## 🔗 在线文档

启动后端服务后，访问：
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 📝 错误码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 401 | 未认证或Token无效 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |

## 🔒 认证说明

大部分API需要JWT Token认证，在请求头中添加：

```
Authorization: Bearer {token}
```

Token在注册或登录时获取，有效期为30天。
