# 系统架构文档

## 🏗️ 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                      前端层 (Next.js)                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │  页面    │  │  组件    │  │  状态管理 │            │
│  └──────────┘  └──────────┘  └──────────┘            │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP/HTTPS
┌──────────────────────┴──────────────────────────────────┐
│                    API层 (FastAPI)                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │ 认证API  │  │ 业务API  │  │ 对话API  │            │
│  └──────────┘  └──────────┘  └──────────┘            │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────┐
│                  业务逻辑层 (Services)                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │ 认证服务 │  │ 用户服务 │  │ 引导服务 │            │
│  └──────────┘  └──────────┘  └──────────┘            │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────┐
│                 核心服务层 (Core)                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │ LLM API  │  │ 智能体   │  │ 知识库   │            │
│  └──────────┘  └──────────┘  └──────────┘            │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────┐
│                   数据层                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │ 数据库   │  │ JSON文件 │  │ CSV文件  │            │
│  └──────────┘  └──────────┘  └──────────┘            │
└─────────────────────────────────────────────────────────┘
```

## 🔧 技术栈

### 后端

- **框架**: FastAPI 0.104+
- **数据库**: SQLAlchemy 2.0+ (SQLite/PostgreSQL)
- **智能体**: LangGraph 0.0.20+
- **LLM**: OpenAI API
- **认证**: JWT (python-jose)
- **迁移**: Alembic

### 前端

- **框架**: Next.js 14 (App Router)
- **语言**: TypeScript
- **样式**: Tailwind CSS
- **状态管理**: Zustand
- **表单**: React Hook Form + Zod
- **动画**: Framer Motion

## 📦 模块设计

### 1. 核心AI服务 (`src/backend/app/core/`)

#### LLM API (`llmapi/`)
- **接口**: `BaseLLMProvider`
- **实现**: `OpenAILLMProvider`
- **功能**: 统一LLM调用接口，支持流式输出

#### ASR API (`asr/`)
- **接口**: `BaseASRProvider`
- **实现**: `OpenAIWhisperProvider`
- **功能**: 语音转文字

#### TTS API (`tts/`)
- **接口**: `BaseTTSProvider`
- **实现**: `OpenAITTSProvider`
- **功能**: 文字转语音

#### 智能体框架 (`agent/`)
- **状态**: `AgentState` (TypedDict)
- **节点**: reasoning, action, observation, guide
- **工具**: SearchTool, GuideTool, ExampleTool
- **框架**: LangGraph状态图

#### 知识库 (`knowledge/`)
- **加载器**: `KnowledgeLoader` (CSV/Markdown)
- **检索**: `KnowledgeSearcher` (关键词检索)
- **向量**: `BaseVectorStore` (接口保留)

### 2. 业务逻辑层 (`src/backend/app/services/`)

- **认证服务**: 注册、登录、Token管理
- **用户服务**: 信息收集、工作履历
- **问题服务**: 问题加载、分类、引导问题
- **回答服务**: 回答保存、验证、查询
- **进度服务**: 进度跟踪、计算
- **引导服务**: 主动/被动引导、偏好管理
- **导出服务**: JSON/Markdown/PDF导出

### 3. API接口层 (`src/backend/app/api/v1/`)

- **认证API**: `/auth/*`
- **用户API**: `/users/*`
- **会话API**: `/sessions/*`
- **问题API**: `/questions/*`
- **回答API**: `/answers/*`
- **对话API**: `/chat/*`
- **检索API**: `/search/*`
- **公式API**: `/formula/*`
- **语音API**: `/audio/*` (可选)
- **导出API**: `/export/*`

### 4. 数据层

#### 数据库 (`src/backend/app/models/`)
- **用户模型**: User, UserProfile, WorkHistory, ProjectExperience
- **会话模型**: Session, Progress
- **回答模型**: Question, Answer
- **选择模型**: UserSelection, GuidePreference, ExplorationResult

#### 文件存储
- **对话记录**: `data/conversations/{session_id}/{category}.json`
- **知识库**: CSV和Markdown文件

## 🔄 数据流

### 用户探索流程

```
用户输入
  ↓
前端组件 (AnswerInput)
  ↓
API层 (POST /answers)
  ↓
业务逻辑 (AnswerService)
  ↓
数据库 (保存回答)
  ↓
智能体框架 (处理引导)
  ↓
LLM API (生成回复)
  ↓
对话记录 (保存到JSON)
  ↓
前端显示 (ChatAssistant)
```

### 智能体工作流程

```
用户消息
  ↓
推理节点 (reasoning_node)
  ↓
行动节点 (action_node) → 调用工具
  ↓
观察节点 (observation_node)
  ↓
判断是否继续 (should_continue)
  ↓
是 → 回到推理节点
  ↓
否 → 返回最终响应
```

## 🔐 安全设计

### 认证机制

1. **JWT Token**: 30天有效期
2. **密码加密**: bcrypt
3. **Token验证**: 中间件自动验证

### 数据安全

1. **输入验证**: Pydantic模型验证
2. **SQL注入防护**: SQLAlchemy ORM
3. **文件上传**: 类型和大小限制

## 📊 性能优化

### 当前架构（简化模式）

- **数据库**: SQLite（开发）/ PostgreSQL（生产）
- **缓存**: 内存缓存（知识库）
- **并发**: 异步处理（FastAPI + async/await）

### 完整架构（生产模式）

- **数据库**: PostgreSQL
- **缓存**: Redis（可选）
- **消息队列**: Celery（可选）
- **向量数据库**: ChromaDB/FAISS（可选）
- **网关**: Nginx（可选）

## 🔌 接口设计原则

### 统一响应格式

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

### 错误处理

```json
{
  "code": 400,
  "message": "错误描述",
  "detail": "详细错误信息"
}
```

### RESTful设计

- GET: 查询
- POST: 创建
- PATCH: 更新
- DELETE: 删除

## 📈 扩展性设计

### 模块化

- 所有核心服务都有接口定义
- 实现可以轻松替换
- 新功能可以独立开发

### 配置驱动

- `ARCHITECTURE_MODE`: 控制架构复杂度
- `AUDIO_MODE`: 控制音频功能
- 环境变量配置所有关键参数

### 接口保留

- 完整架构的接口已定义
- 可以逐步实现复杂功能
- 保持向后兼容

## 🔗 相关文档

- 详细设计: 查看 `planning/` 目录
- API文档: 查看 `docs/API_DOCUMENTATION.md`
- 数据库设计: 查看 `docs/DATABASE_SCHEMA.md`
