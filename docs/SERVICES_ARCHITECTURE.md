# 服务层架构说明

## 分层结构

```
api/v1/          →  HTTP 层：路由、请求校验、依赖注入
     ↓ 调用
services/        →  业务逻辑层：业务规则、DB/外部系统交互
     ↓ 调用
core/database/   →  数据层：HistoryDB、ORM
core/knowledge/  →  知识层：KnowledgeLoader、KnowledgeSearcher
utils/           →  工具：ConversationFileManager 等
```

## 服务列表

| 服务 | 职责 | 被调用的 API |
|------|------|--------------|
| **SessionService** | 会话 CRUD、更新会话、删除会话（含对话文件） | sessions.py, chat.py, chat_optimized.py |
| **ProgressService** | 进度 CRUD、计算百分比 | sessions.py (PATCH progress) |
| **AnswerService** | 回答 CRUD、验证 | answers.py |
| **AuthService** | 注册、登录、Token | auth.py |
| **UserService** | 用户、工作履历 | users.py |
| **QuestionService** | 题目、知识库问题 | questions.py, guide_service, question_flow |
| **ExportService** | 导出 PDF | export.py |
| **GuideService** | 引导内容 | chat.py |
| **SearchService** | 知识库检索（价值观/兴趣/才能） | search.py |

## API 与服务的对应关系

| API 文件 | 使用的服务 |
|----------|------------|
| sessions.py | SessionService, ProgressService |
| search.py | SearchService |
| answers.py | AnswerService |
| auth.py | AuthService |
| users.py | UserService |
| questions.py | QuestionService |
| export.py | ExportService |
| chat.py | SessionService, GuideService |
| chat_optimized.py | SessionService |

## 设计原则

1. **API 不直接调用 HistoryDB**：会话、进度、回答相关操作统一通过 Service。
2. **API 不直接调用 KnowledgeLoader/Searcher**：检索 API 通过 SearchService。
3. **Agent 内部**（reasoning_v2, search_tool, example_tool）仍可直接使用 KnowledgeLoader/Searcher，因其非 HTTP 入口。
4. **删除会话**：SessionService.delete_session 负责 DB 删除 + 对话文件清理。
