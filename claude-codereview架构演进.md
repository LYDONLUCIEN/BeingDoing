# BeingDoing 架构演进 — Code Review 与治理建议

> 审查日期：2026-04-03
> 范围：全项目架构、安全、性能、可维护性、可扩展性评估
> 目标读者：项目负责人、AI 编程助手

---

## 一、项目画像

| 指标 | 数值 |
|------|------|
| 后端 Python 文件 | 127 |
| 前端 TS/TSX 文件 | 133 |
| API 端点 | 114 |
| 前端页面 | 29 |
| React 组件 | 35 |
| Zustand Store | 9 |
| 数据库模型 | 7 |
| 测试函数 | ~102 |
| 后端代码量 | ~29 MB |
| 数据库文件 | 152 KB |

---

## 二、模块评分总览

| 模块 | 设计 | 安全 | 性能 | 可维护 | 可扩展 | 综合 | 紧急度 |
|------|------|------|------|--------|--------|------|--------|
| **Agent 框架** (core/agent/) | 7 | 7 | 6 | 6 | 6 | **6.4** | 中 |
| **LLM 接口层** (core/llmapi/) | 7 | 6 | 5 | 6 | 7 | **6.2** | 中 |
| **API 路由层** (api/v1/) | 6 | 4 | 5 | 5 | 5 | **5.0** | 🔴高 |
| **业务服务层** (services/) | 6 | 7 | 5 | 6 | 6 | **6.0** | 中 |
| **数据模型/数据库** (models/) | 6 | 7 | 4 | 5 | 5 | **5.4** | 🔴高 |
| **领域层** (domain/) | 8 | 7 | 7 | 8 | 7 | **7.4** | 低 |
| **知识库** (core/knowledge/) | 6 | 7 | 5 | 6 | 4 | **5.6** | 中 |
| **前端-路由/页面** | 7 | 5 | 6 | 5 | 6 | **5.8** | 🔴高 |
| **前端-状态管理** | 6 | 4 | 6 | 6 | 5 | **5.4** | 🔴高 |
| **前端-API Client** | 8 | 5 | 7 | 7 | 7 | **6.8** | 中 |
| **前端-组件** | 7 | 6 | 5 | 6 | 6 | **6.0** | 中 |
| **测试** | — | — | — | 7 | 5 | **6.0** | 中 |
| **部署** | 5 | 4 | 5 | 5 | 3 | **4.4** | 🔴高 |
| **配置管理** (settings.py) | 5 | 3 | 7 | 5 | 5 | **5.0** | 🔴高 |

**项目综合评分：5.8 / 10** — 功能基本完整，但在安全、性能和可扩展性方面需要系统性治理后才适合多用户生产环境。

---

## 三、关键问题清单（按风险排序）

### 🔴 P0 — 安全风险（必须立即修复）

#### 1. 前端 Token 存储在 localStorage — XSS 可窃取全部凭证
- **位置**: `stores/authStore.ts:36-38`，`lib/api/client.ts:129`，`lib/api/chat.ts:106`
- **影响**: 任何 XSS 注入即可窃取所有用户 token，获取完整账户权限
- **修复**: Token 迁移到 httpOnly + Secure + SameSite=Strict Cookie，前端不再直接接触 token

#### 2. 全局无速率限制
- **位置**: 后端无任何 rate limiting middleware，nginx 配置也无 `limit_req`
- **影响**: 单用户可无限调用 LLM API，造成高额费用或 DoS
- **修复**: 添加 `slowapi` 或 nginx `limit_req_zone`，按用户/IP 限制

#### 3. settings.py 不安全默认值
- **位置**: `config/settings.py:15` — `SECRET_KEY = "your-secret-key-here-change-in-production"`
- **位置**: `config/settings.py:30` — `REFRESH_COOKIE_SECURE: bool = False`
- **影响**: 如忘记修改，JWT 可被伪造；Cookie 在 HTTP 下明文传输
- **修复**: 启动时检查 SECRET_KEY 是否为默认值，生产环境强制 COOKIE_SECURE=True

#### 4. 会话所有权未校验
- **位置**: `api/v1/chat.py:585-587` — 获取对话历史不检查 session 归属
- **影响**: 用户 A 可通过猜测 session_id 读取用户 B 的对话记录
- **修复**: 所有 session 相关 API 加 `user_id == session.owner_id` 校验

#### 5. 系统以 root 用户运行
- **位置**: `deploy/systemd/beingdoing-backend.service:8`
- **影响**: 如有任何 RCE 漏洞，攻击者直接获得 root 权限
- **修复**: 创建专用用户 `beingdoing`，使用 `User=beingdoing` 运行

### 🟡 P1 — 稳定性与性能（影响用户体验和多人并发）

#### 6. LLM 调用无重试/超时/熔断
- **位置**: `core/agent/nodes/observation_node.py:48`，`reasoning_v2.py:359`
- **影响**: 单次 LLM 超时 = 用户请求失败，无恢复机制
- **修复**: 添加指数退避重试（3次）、30s 超时、Circuit Breaker 模式

#### 7. GraphCache 使用 threading.Lock（异步环境中阻塞事件循环）
- **位置**: `core/agent/graph_cache.py:81`
- **影响**: 高并发下阻塞整个 asyncio 事件循环，所有用户请求延迟
- **修复**: 改用 `asyncio.Lock`

#### 8. 数据库缺少关键索引
- **位置**: `models/` — Session.user_id、Answer.session_id、Progress.session_id 均无索引
- **影响**: 用户量增长后查询变慢，O(n) 全表扫描
- **修复**: 对所有 foreign key 和频繁 WHERE 条件的列添加 `index=True`

#### 9. N+1 查询问题
- **位置**: `services/user_service.py:154-185` — 循环查询每个工作经历的项目
- **位置**: `services/export_service.py:38-66` — 7 个独立查询可合并
- **影响**: 用户数据越多，页面加载越慢
- **修复**: 使用 `selectinload()` 进行 eager loading

#### 10. 前端核心页面组件过大（1376 行）
- **位置**: `app/(main)/explore/chat/[phase]/page.tsx` — 1376 行
- **影响**: 无法维护、无法测试、性能差（每次状态变更重新渲染全部）
- **修复**: 拆分为 ChatContainer + ChatMessages + ChatInput + ChatSidebar + useChat hook

### 🔵 P2 — 架构治理（影响后期维护和演进）

#### 11. Prompt 注入风险
- **位置**: `core/agent/nodes/reasoning_v2.py:305-316` — 用户输入直接拼入 system prompt
- **修复**: 使用结构化模板参数化用户输入，不做字符串拼接

#### 12. 服务层违反分层规则
- **位置**: `services/export_service.py:58-66` — 直接写 SQLAlchemy 查询
- **位置**: `services/auth_service.py:119-128` — 直接操作 RefreshToken 模型
- **修复**: 创建 ExportDB、RefreshTokenDB 类，维持 Service → Database 分层

#### 13. 无并发控制/乐观锁
- **位置**: 所有 Model 均无 `version` 字段
- **影响**: 两个请求同时更新 Progress，后者覆盖前者
- **修复**: 添加 `version = Column(Integer, default=0)` 实现乐观锁

#### 14. 测试覆盖不足
- **现状**: 102 个测试，但缺少：集成测试、并发测试、错误路径测试、前端测试
- **修复**: 分阶段补充（见下方路线图）

#### 15. 部署无健康检查
- **位置**: Docker Compose 和 systemd 均无 healthcheck
- **修复**: `/health` 端点检查数据库连接 + LLM 可用性，Docker 和 systemd 配置探活

---

## 四、面向未来场景的架构差距分析

### 场景 A：多人同时使用（10-100 并发用户）

| 现状 | 差距 | 优先改进 |
|------|------|----------|
| 单实例后端 | 无法水平扩展 | 支持多 worker（gunicorn + uvicorn） |
| SQLite 数据库 | 不支持并发写 | 迁移到 PostgreSQL |
| 内存缓存 (GraphCache) | 进程间不共享 | 引入 Redis |
| threading.Lock | 阻塞事件循环 | 改 asyncio.Lock |
| 无连接池管理 | LLM 连接浪费 | 配置连接池 |

### 场景 B：用户社群功能

| 需要能力 | 现状 | 差距 |
|----------|------|------|
| 用户关系（关注/社区） | 仅单用户模型 | 需新增社交模型 |
| 内容分享 | 导出功能存在但无分享 | 需分享链接 + 权限 |
| 通知系统 | 仅邮件 | 需 WebSocket 推送 |
| 数据隔离 | 弱（session 无 owner 校验） | 需完善多租户隔离 |

### 场景 C：App 版本（移动端）

| 需要能力 | 现状 | 差距 |
|----------|------|------|
| API 版本管理 | 仅 v1，无版本策略 | 需 API 版本化机制 |
| 身份认证 | JWT + Cookie | App 需纯 Bearer Token 方案 |
| 离线支持 | 无 | 需考虑离线缓存 |
| 推送通知 | 无 | 需 FCM/APNs 集成 |
| 响应式 UI | 部分支持 | 前端需移动端适配或 React Native |
| 图片/文件上传 | 基础支持 | 需 CDN + OSS |

### 场景 D：大规模知识库

| 现状 | 差距 | 改进 |
|------|------|------|
| 关键词匹配搜索 | 无语义理解 | 引入向量嵌入 (FAISS/Chroma) |
| ~100 条 CSV 数据 | 无法扩展 | 数据库化知识管理 |
| 无搜索缓存 | 重复搜索浪费 | Redis 缓存热门查询 |

---

## 五、分阶段演进路线图

### 🔴 阶段一：安全加固（建议 1-2 周完成）

**目标**：消除所有 P0 安全风险，达到基本安全可部署状态。

| 序号 | 任务 | 工作量 | 影响范围 |
|------|------|--------|----------|
| 1.1 | Token 迁移到 httpOnly Cookie | 2-3天 | 前端 authStore + 后端 auth API |
| 1.2 | 添加速率限制（slowapi） | 1天 | 后端 middleware + nginx |
| 1.3 | settings.py 安全默认值 + 启动校验 | 0.5天 | config/settings.py |
| 1.4 | 所有 session API 加 owner 校验 | 1天 | api/v1/ 多个文件 |
| 1.5 | systemd 非 root 用户运行 | 0.5天 | deploy/systemd/ |
| 1.6 | 消息长度限制 | 0.5天 | Pydantic model 加 max_length |

**验收标准**：
- [ ] 浏览器 DevTools 中看不到 token（仅在 Cookie 中）
- [ ] 同一 IP 1分钟内超过 30 次请求被拒绝
- [ ] 默认 SECRET_KEY 启动时报错退出
- [ ] 用户 A 无法读取用户 B 的 session 数据
- [ ] `ps aux` 显示进程用户非 root

### 🟡 阶段二：稳定性加固（建议 2-3 周完成）

**目标**：支持 10-50 并发用户稳定运行，LLM 调用可恢复。

| 序号 | 任务 | 工作量 | 影响范围 |
|------|------|--------|----------|
| 2.1 | LLM 调用加重试 + 超时 + 熔断 | 2天 | core/llmapi/ + core/agent/nodes/ |
| 2.2 | GraphCache 改 asyncio.Lock | 0.5天 | core/agent/graph_cache.py |
| 2.3 | 数据库加索引 | 0.5天 | models/ + Alembic 迁移 |
| 2.4 | 修复 N+1 查询（eager loading） | 1天 | services/ + core/database/ |
| 2.5 | Docker 健康检查 | 0.5天 | docker-compose.yml + main.py |
| 2.6 | 结构化日志 + 请求 ID 追踪 | 1天 | middleware + logging config |
| 2.7 | Prompt 注入防护 | 1天 | core/agent/nodes/reasoning_v2.py |

**验收标准**：
- [ ] LLM 超时后自动重试，3 次失败后返回友好错误
- [ ] 50 并发用户压测无 500 错误
- [ ] 日志中每个请求可通过 request_id 追踪全链路

### 🔵 阶段三：架构优化（建议 3-4 周完成）

**目标**：代码可维护性提升，支持团队协作开发。

| 序号 | 任务 | 工作量 | 影响范围 |
|------|------|--------|----------|
| 3.1 | 拆分前端 chat 大组件 | 3天 | explore/chat/[phase]/page.tsx |
| 3.2 | 服务层分层合规整改 | 2天 | services/ + 新建 DB 类 |
| 3.3 | 统一 API 错误响应格式 | 1天 | middleware + 全部路由 |
| 3.4 | 合并冗余 Chat API（3→1） | 2天 | api/v1/chat*.py + simple_chat.py |
| 3.5 | 数据库乐观锁 | 1天 | models/ + services/ |
| 3.6 | 完善 Alembic 迁移体系 | 1天 | alembic/ |
| 3.7 | 前端 i18n 补全 | 2天 | 全部 hardcoded 中文字符串 |
| 3.8 | 补充关键路径测试 | 3天 | test/ |

**验收标准**：
- [ ] 最大单文件不超过 500 行
- [ ] `pytest --cov` 核心模块覆盖率 > 60%
- [ ] 只有一个 Chat API 端点（版本化）
- [ ] Alembic 有完整迁移历史

### ⚪ 阶段四：可扩展性演进（根据业务需求排期）

**目标**：支持多人、App、社群等未来场景。

| 序号 | 任务 | 前置条件 | 场景 |
|------|------|----------|------|
| 4.1 | SQLite → PostgreSQL 迁移 | 阶段三完成 | 多人并发 |
| 4.2 | 引入 Redis（缓存 + 会话） | PostgreSQL 就绪 | 多人并发 |
| 4.3 | Gunicorn 多 worker 部署 | Redis 就绪 | 多人并发 |
| 4.4 | 知识库向量化搜索 | — | 大规模知识 |
| 4.5 | API 版本化机制（v1/v2 共存） | Chat API 合并后 | App 版本 |
| 4.6 | WebSocket 实时通知 | — | 社群功能 |
| 4.7 | CDN + OSS 静态资源 | — | App 版本 |
| 4.8 | 多租户数据隔离 | Owner 校验就位 | 社群/企业版 |

---

## 六、各模块详细审查结论

### 6.1 Agent 框架 (core/agent/) — 综合 6.4/10

**优点**：
- 清晰的 ReAct 节点分离（reasoning → action → observation → user_agent）
- 双轨消息系统（messages 给用户、inner_messages 给思维链）设计合理
- 工具注册模式可扩展

**关键问题**：
- `reasoning_v2.py` 427 行，混合了问题流、LLM 调用、知识搜索、token 追踪、流式处理 5 个关注点 — 应拆分
- 上下文压缩是朴素的字符串截断（`context_manager.py:44-46`），丢失语义信息
- 工具执行异常未捕获（`action_node.py:41`）
- Token budget 设置了但从未执行限制检查
- 知识搜索每次 reasoning 调用都执行，无结果缓存

**改进方向**：
1. 拆分 reasoning_v2.py 为独立模块（reasoning_logic、knowledge_query、token_tracker、stream_handler）
2. 实现基于 token 的上下文窗口管理，替代字符截断
3. 所有 LLM 调用加 try/except + 重试
4. 硬编码阈值（跳过关键词、最大摘要字符等）迁移到 config

### 6.2 LLM 接口层 (core/llmapi/) — 综合 6.2/10

**优点**：
- `BaseLLMProvider` 抽象层设计清晰，支持多厂商切换
- 流式传输支持完整，能区分推理模型 thinking 和 content
- Factory 模式支持 VIP 分级选择模型

**关键问题**：
- 错误处理粗粒度：rate limit(429)、auth(401)、timeout 全部归为 `LLMError`（`openai_provider.py:106-108`）
- `_last_stream_usage` 存在并发竞态（`openai_provider.py:44`），两个并发流互相覆盖
- `_encoding` 懒加载无锁保护（`openai_provider.py:46-58`）
- 超时硬编码 60s（`openai_provider.py:37`），不可配置
- 多个 factory 函数造成混乱：`create_llm_provider`、`get_llm_provider_for_vip`、`get_default_llm_provider`

**改进方向**：
1. 区分异常类型：LLMRateLimitError、LLMTimeoutError、LLMAuthError
2. `_last_stream_usage` 改为请求级变量，不在实例上共享
3. 超时从 settings.py 读取
4. 合并 factory 函数为统一入口

### 6.3 API 路由层 (api/v1/) — 综合 5.0/10

**优点**：
- FastAPI Depends() 模式统一注入 auth
- Pydantic 模型覆盖所有请求体

**关键问题**：
- **无速率限制**（整个 API 层）
- **Session 所有权未校验**（`chat.py:585-587` 等多处）
- **消息体无长度限制**（`SendMessageRequest.message: str` 无 max_length）
- 三套 Chat API 并存（chat、chat_optimized、simple_chat），语义重叠
- 错误响应格式不一致（有 HTTPException、有 StandardResponse、有直接 dict）
- Debug 信息在 500 响应中泄露（`middleware.py:47-55`）
- CORS 配置中硬编码了服务器 IP

**改进方向**：
1. 统一错误响应中间件，所有错误返回 `{code, message, detail}` 格式
2. 合并三套 Chat API 为单一端点 + 参数区分模式
3. 添加全局 RequestValidation（消息长度、session_id 格式）
4. DEBUG 模式的错误详情仅在响应头中返回，不在 body 中

### 6.4 业务服务层 (services/) — 综合 6.0/10

**优点**：
- 服务职责清晰，按业务域拆分
- 静态方法为主，无状态设计

**关键问题**：
- `export_service.py:58-66` 直接写 SQLAlchemy 查询，违反分层
- `auth_service.py:119-128` 直接操作 RefreshToken，绕过 DB 层
- `user_service.py:154-185` 存在 N+1 查询（循环加载项目）
- 无事务边界：refresh token 涉及多步操作，中间失败会数据不一致
- 进度计算逻辑重复 3 处（`progress_service.py:32-34, 78-79, 109-111`）

**改进方向**：
1. 严格执行 Service → DB 分层，创建缺失的 DB 类
2. 多步数据库操作包装在事务中
3. 提取公共计算为工具函数

### 6.5 数据模型/数据库 — 综合 5.4/10

**优点**：
- UUID 主键全局统一
- 外键带 CASCADE delete
- 时间戳字段完整

**关键问题**：
- 缺少索引：Session.user_id、Answer.session_id、Progress.session_id 无索引
- 无乐观锁（version 字段），并发更新互相覆盖
- JSON 字段（Answer.extra_metadata 等）存为 Text，无 schema 校验
- RefreshToken.user_id 无外键约束
- Progress 无 (session_id, step) 唯一约束，可能产生重复
- Alembic 仅 1 个迁移文件，迁移体系未真正使用
- 列名混淆：Answer 的实际列名 "metadata" 对应属性 "extra_metadata"

**改进方向**：
1. 所有 FK 列加 `index=True`
2. 添加 version 字段和乐观锁机制
3. Progress 加 `UniqueConstraint('session_id', 'step')`
4. 建立完整 Alembic baseline migration

### 6.6 领域层 (domain/) — 综合 7.4/10 ✅ 最佳模块

**优点**：
- 业务知识与基础设施完全解耦
- Jinja2 模板化 prompt 管理
- 步骤流程配置清晰
- 问题目标定义深入，含提取目标和充分性提示

**小问题**：
- Prompt 模板缺少变量缺失时的错误处理（`prompts/loader.py:44-46`）
- knowledge_rules 仅关键词匹配，无语义层

### 6.7 知识库 (core/knowledge/) — 综合 5.6/10

**优点**：
- Loader 有缓存和强制刷新支持
- CSV 解析对缺失列容错

**关键问题**：
- **搜索纯关键词匹配**（`search.py:32-53`），无语义理解
- 向量检索目录存在但是空壳实现（`vector/memory.py` 仅做子串匹配）
- CSV 数据量极小（每个约 100 行），搜索评分算法过于简单
- 无分页或结果数限制

**改进方向**：阶段四引入向量嵌入（FAISS 或 Chroma），当前关键词搜索对小数据集够用

### 6.8 前端整体 — 综合 5.8/10

**优点**：
- API Client 设计良好：集中式 axios 实例、token 刷新防重入、自定义事件系统
- Zustand 选型合理，持久化中间件使用正确
- i18n 基础框架已搭建（lib/i18n/）
- 响应式布局基础到位（Tailwind 断点）

**关键问题**：
- **Token 在 localStorage**（P0 安全问题，见上）
- **chat 页面 1376 行**，15+ useEffect，混合状态管理、API 调用、渲染逻辑
- 硬编码中文字符串散落在组件中，i18n 未覆盖完整
- 无错误边界（Error Boundary），组件崩溃白屏
- 长消息列表无虚拟化，大量对话时渲染卡顿
- react-markdown 和 @uiw/react-markdown-preview 两个 markdown 库重复

**改进方向**：
1. 拆分 chat 大组件（P1）
2. Token 迁移 Cookie（P0）
3. 添加 Error Boundary
4. 长列表虚拟化（react-virtual）
5. 去掉重复 markdown 库

### 6.9 测试 — 综合 6.0/10

**优点**：
- 102 个测试函数，异步测试模式成熟
- fixture 使用规范（临时 CSV、mock）
- 缓存测试验证内存优化

**差距**：
- 无集成测试（完整 Agent graph + 真实 LLM）
- 无并发测试
- 无前端测试
- 错误路径覆盖不足（畸形 CSV、空输入、超长对话）
- LLM 测试仅验证调用，不验证输出格式

### 6.10 部署 — 综合 4.4/10

**优点**：
- tmux 管理脚本完整
- systemd 有 restart 策略
- nginx 支持 SSE 流式传输

**关键问题**：
- 以 root 运行（systemd）
- Docker/systemd 均无健康检查
- 无资源限制（CPU/内存）
- 硬编码数据库密码（docker-compose.yml:11 — `postgres:postgres`）
- 单实例，无水平扩展能力
- 无日志轮转
- 硬编码 conda 路径（`start.sh:44`）
- 无优雅停机（kill 可能丢失进行中的 LLM 请求）

---

## 七、架构演进优先级矩阵

```
        高影响
          │
    P0    │    P1
  安全加固 │  稳定性
  Token   │  LLM重试
  限流    │  索引
  owner校验│  N+1修复
          │
──────────┼──────────
          │
    P2    │    P3
  架构优化 │  扩展性
  拆组件   │  PostgreSQL
  合并API  │  Redis
  分层合规 │  向量搜索
          │  App适配
        低影响
  
  紧急 ←────────→ 可延后
```

---

## 八、总结建议

1. **先安全、后性能、再扩展** — 阶段一（安全加固）是前置条件，不做完不应上线多用户
2. **不要跳阶段** — 每个阶段的输出是下一阶段的输入（如 owner 校验是多租户的基础）
3. **领域层是项目亮点** — 7.4 分，业务知识解耦做得好，继续保持
4. **最大技术债在 API 层和数据库层** — 这两层的问题会随用户增长指数级放大
5. **前端的核心问题是 Token 存储和组件粒度** — 修复这两项后，前端架构基本合格
6. **测试是长期投资** — 每次修改后补充对应测试，不要攒到最后一起补
