# BeingDoing 领域驱动设计（DDD）全景文档

> 版本：v1.0（基于当前仓库实现对齐）  
> 适用范围：`src/backend`、`src/frontend`、`data/`、`wiki/`、`docs/` 中与主业务相关模块  
> 目标：统一领域术语、边界上下文、核心流程与数据模型，为后续重构/扩展提供统一语言

---

## 1. 设计目标与范围

本系统核心使命：帮助用户通过「喜欢的事 × 擅长的事 × 重要的事」完成探索，并沉淀为可复用的职业方向结论。

本 DDD 文档覆盖以下核心关注点：

- 前端与后端的主业务流程（从登录到探索、报告、管理）
- 激活码机制、身份认证机制、管理员权限机制
- 关系型数据模型 + 文件型数据模型的双存储体系
- 领域术语统一（避免 `session` / `thread` / `phase` / `step` 混用）
- 边界上下文（Bounded Context）与上下文映射（Context Map）

---

## 2. 业务域核心陈述（Domain Statement）

BeingDoing 是一个「探索旅程系统」，通过阶段式对话与问卷数据，帮助用户形成职业认知结果。  
系统当前存在两条并行业务路径：

- **经典会话路径（DB Session Path）**：以 `sessions` 表为核心，围绕 `progress/answers/selections` 运作。
- **激活旅程路径（Simple Activation Path）**：以 `ActivationRecord + report(record.json + thread files)` 为核心，围绕 `simple-auth/simple-chat` 运作。

二者共享同一用户身份（JWT），但在业务编排与存储事实源上并行存在。

---

## 3. 统一语言（Ubiquitous Language）词汇表

以下术语作为本项目 DDD 标准词汇，后续文档、需求、代码评审统一采用。

| 中文术语 | 英文术语 | 统一定义 | 代码落点 |
|---|---|---|---|
| 用户 | User | 系统认证主体，可登录并拥有探索数据 | `models/user.py` |
| 访问令牌 | Access Token | 短期 JWT，`type=access`，用于接口鉴权 | `services/auth_service.py` |
| 刷新令牌 | Refresh Token | 可轮换 JWT + DB 持久化记录，用于续期 access | `models/refresh_token.py` |
| 超级管理员 | Super Admin | 由环境变量白名单定义的高权限用户 | `utils/super_admin.py` |
| 激活码 | Activation Code | 探索旅程通行凭证，与用户首次绑定归属 | `utils/simple_activation_manager.py` |
| 激活记录 | Activation Record | 激活码的文件持久化实体 | `ActivationRecord` dataclass |
| 激活会话标识 | Activation Session ID | 激活旅程关联会话 ID（区别于对话线程） | `frontend/lib/explore/session.ts` |
| 对话线程 | Chat Thread | 单阶段或多阶段中的具体消息线程 | `simple-chat` 相关 API + 本地缓存 |
| 探索阶段 | Exploration Phase | `values/strengths/interests/purpose/rumination` | 前端 `PhaseKey` |
| 探索步骤 | Exploration Step | `values_exploration/...` 的经典流程步骤 | `domain/steps.py` |
| 旅程 | Journey | 用户与激活码绑定后的探索实例视图 | `GET /simple-auth/journeys` |
| 探索会话 | Exploration Session | 经典 DB 会话聚合（`sessions` 根） | `models/session.py` |
| 报告 | Report | 激活旅程下的阶段结果与总结产物 | `utils/report_registry.py` |
| 埋点轮次 | Analytics Chat Turn | 对话统计读模型（非强一致业务实体） | `models/analytics.py` |
| 领域知识 | Domain Knowledge | CSV/Markdown 题库与知识源 | `domain/knowledge_config.py` |

### 3.1 明确禁止混用的词

- `session` 不能泛指所有会话，必须注明：
  - `DB Session`（`sessions.id`）
  - `Activation Session ID`
  - `Thread ID`
- `step` 与 `phase` 必须区分：
  - `step`：经典流程 `values_exploration` 等
  - `phase`：Simple 探索 `values/.../rumination`

---

## 4. 边界上下文（Bounded Context）划分

## 4.1 身份与访问控制上下文（IAM Context）

**职责**

- 注册、登录、Access Token 签发
- Refresh Token 轮换、撤销、重放检测
- 当前用户解析（`get_current_user`）
- 超级管理员判定

**核心对象**

- 实体：`User`、`RefreshToken`
- 值对象：`JWT Claims`（`sub/type/exp/jti/family_id`）
- 领域策略：`SuperAdminPolicy`（由配置驱动）

**核心不变式**

- Access Token 仅作为短期调用凭证
- Refresh Token 必须可撤销，且支持轮换后旧 token 不可复用
- `super_admin` 权限仅由白名单定义，不来自普通用户字段编辑

---

## 4.2 激活旅程上下文（Activation Journey Context）

**职责**

- 激活码创建、查询、归属绑定、状态流转
- 激活码与用户的一次性绑定（claim owner）
- 旅程恢复（`journeys`）与报告注册
- 沙箱（SBX/ADM）与工作区策略

**核心对象**

- 实体：`ActivationRecord`（文件存储实体）
- 值对象：`ActivationStatus`、`workspace_kind`
- 领域服务：`SimpleActivationManager`、`ReportRegistry`

**核心不变式**

- 激活码首次使用后绑定归属；非归属用户不可使用
- `revoked/deleted` 状态不可继续激活
- 终端用户不得删除已形成探索数据（策略型约束）

---

## 4.3 探索编排上下文（Exploration Orchestration Context）

分为两条实现路径：

- **经典 DB 路径**：`Session + Progress + Answer + Selection + ExplorationResult`
- **Simple 路径**：按 `phase/thread` 写入 report 与对话文件

**职责**

- 对话驱动探索推进
- 阶段解锁与恢复
- 问卷与探索状态联动
- 结果汇总与报告可用性判定

**核心对象（经典）**

- 聚合根候选：`Session`
- 聚合成员：`Progress`、`Answer`、`UserSelection`、`GuidePreference`、`ExplorationResult`

**核心对象（Simple）**

- 聚合根候选：`Report`（以 `record.json + thread files` 为事实集合）
- 外部引用：`ActivationRecord`（索引/权限/归属）

---

## 4.4 内容知识上下文（Knowledge Context）

**职责**

- 管理题库与知识源（CSV/Markdown）
- 为探索流程提供问题与知识素材

**核心对象**

- 主数据：`Question`（DB）
- 外部知识文件：项目根 CSV、`question.md`

该上下文更接近「内容主数据子域」，可视作共享内核（Shared Kernel）。

---

## 4.5 运营分析上下文（Analytics & Admin Context）

**职责**

- 对话轮次、报告生成、点赞等埋点采集与统计
- 管理端激活码批量管理、审计、沙箱管理

**核心对象**

- 读模型：`AnalyticsChatTurn`、`AnalyticsReport`、`AnalyticsLike`
- 管理策略：`AdminDebugPolicy`、`SuperAdminPolicy`

该上下文与核心探索上下文是弱一致关系（可异步、可补录）。

---

## 4.6 支撑能力上下文（Supporting Context）

- LLM Provider 与 Agent 图编排
- 语音（ASR/TTS）
- 导出（json/md/pdf）
- 邮件验证码等基础能力

---

## 5. 上下文映射（Context Map）

- IAM ->（身份令牌）-> Activation Journey
- IAM ->（身份令牌）-> Exploration Orchestration
- Activation Journey <-> Exploration Orchestration（通过 `activation_code/report/phase/thread`）
- Exploration Orchestration -> Analytics（埋点投影）
- Knowledge -> Exploration Orchestration（只读素材供给）
- Admin Context -> Activation Journey / Analytics（管理与审计）

集成方式以同步 API + 文件读取为主，尚未形成事件总线。

---

## 6. 核心聚合设计（按当前实现映射）

## 6.1 聚合 A：用户身份聚合（User Identity Aggregate）

**聚合根**：`User`  
**实体成员**：`RefreshToken`（建议独立子聚合）  
**关键行为**

- `register`
- `login`
- `refresh_access_token`（含 rotate/revoke/reuse_detected）
- `logout`

**一致性边界**

- 认证相关一致性在单库事务内完成
- Access token 本身无服务端回收表，依赖过期 + 客户端清理

---

## 6.2 聚合 B：经典探索会话聚合（DB Exploration Session Aggregate）

**聚合根**：`Session`  
**实体成员**：`Progress`、`Answer`、`UserSelection`、`GuidePreference`、`ExplorationResult`

**关键行为**

- 创建会话（初始 `current_step`）
- 更新步骤与状态（`active/paused/completed`）
- 记录阶段进度与答案
- 生成/更新探索结果

**一致性边界**

- 通过 DB 事务保证同一请求下写入一致
- 与对话文件、分析表为跨边界操作，非强一致

---

## 6.3 聚合 C：激活旅程聚合（Activation Journey Aggregate）

**聚合根候选**：`ActivationRecord + Report`（逻辑双根，当前实现分散在索引文件与报告目录）  
**实体成员**

- `ActivationRecord`
- `record.json`（report 元信息）
- `phase-thread` 对话文件

**关键行为**

- 激活码创建与过期策略
- 首次 claim 归属
- 旅程恢复（journeys）
- 沙箱 fork 与过期控制

**一致性边界**

- 文件系统级一致性（多文件写入顺序保证）
- 不存在分布式事务；需要应用层补偿设计

---

## 7. 主流程设计（Domain Process）

## 7.1 用户探索主流程（推荐主路径）

1. 用户访问站点（首页可匿名）
2. 进入探索入口时触发登录门禁（`AuthGate`）
3. 登录成功后获得 access token（前端本地保存）
4. 进入激活页输入 `activation code`
5. 后端校验激活码存在性、归属、状态、沙箱有效性
6. 若首次使用则绑定归属并创建/关联 report
7. 返回 `explore_resume`，前端恢复 `currentPhase/unlockedPhases`
8. 用户在各 phase 对话，推进阶段解锁
9. 达到报告解锁条件后进入报告预备/查看
10. 仪表盘可通过 `journeys` 跨设备恢复状态

## 7.2 Token 续期流程

1. 前端请求业务 API 遇到 401
2. `apiClient` 触发 single-flight refresh
3. 后端校验 refresh token（哈希匹配、未撤销、未过期）
4. 成功则返回新 access（可选新 refresh）
5. 失败则前端清理身份态并触发 `auth:required`

---

## 8. 激活码与权限模型（重点对齐）

## 8.1 激活码状态机

- `active`：可用
- `expired`：过期（历史可保留）
- `revoked`：已撤销（不可用）
- `deleted`：已删除（不可用）

## 8.2 归属模型

- 未绑定：可首次绑定
- 已绑定：仅 `owner_user_id/owner_email` 匹配者可使用
- 不匹配：返回 403（“该激活码已被其他用户使用”）

## 8.3 管理员与调试策略

- 超级管理员由 `SUPER_ADMIN_USER_IDS/SUPER_ADMIN_EMAILS` 白名单决定
- 管理能力受 `ADMIN_DEBUG_POLICY_ENABLED` 总开关约束
- 沙箱能力受 `ADMIN_SANDBOX_ENABLED` 约束

---

## 9. 数据结构设计（关系型 + 文件型）

## 9.1 关系型核心结构（简版 ER）

- `users` 1-1 `user_profiles`
- `users` 1-N `work_history` 1-N `project_experiences`
- `users` 1-N `sessions`
- `sessions` 1-N `progress`
- `sessions` 1-N `answers` N-1 `questions`
- `sessions` 1-N `user_selections`
- `sessions` 1-1 `guide_preferences`
- `sessions` 1-1 `exploration_results`
- `refresh_tokens` 与 `users` 逻辑关联（当前无 FK）
- `analytics_*` 作为统计读模型（与 `sessions` 多为松耦合关联）

## 9.2 文件型核心结构

- `data/simple/activations.json`：激活码索引
- `data/simple/reports/{report_id}/record.json`：旅程主记录
- `data/simple/reports/{report_id}/{phase}__{thread_id}.json`：阶段线程对话
- `data/test/simple/...`：沙箱/管理员工作区数据
- `data/conversations/{session_id}/...`：经典会话对话文件

## 9.3 事实源定义（Source of Truth）

- 身份事实源：关系库 + JWT 校验
- 激活旅程事实源：`ActivationRecord + report 文件`
- 前端 `localStorage`：仅缓存投影，不是最终事实源

---

## 10. 前端领域模型对齐

## 10.1 应用层状态对象

前端 `ExploreSession` 属于应用层投影模型，不是后端领域实体。

关键字段：

- `activationCode`
- `currentPhase`
- `unlockedPhases`
- `surveyCompleted`
- `activationSessionId`（兼容期可能双写 `sessionId`）

## 10.2 防腐层（ACL）职责

前端需要将后端 DTO 翻译为稳定的前端领域视图：

- `explore_resume` -> `ExploreSession` 局部覆盖
- `history metadata` -> `thread_id` 兼容读取
- `activation API` -> `activation_session_id` 标准化读取

建议继续收敛到专门 mapper，避免页面层直接消费原始 API 形状。

---

## 11. API 与应用服务映射

## 11.1 IAM

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`

## 11.2 激活旅程

- `POST /api/v1/simple-auth/activation`（内部/开发生成）
- `POST /api/v1/simple-auth/activate`
- `GET /api/v1/simple-auth/journeys`

## 11.3 探索编排

- `simple-chat/*`（Simple 主链路）
- `chat/*`、`sessions/*`（经典链路）

## 11.4 管理与运营

- `admin/*`（激活码、沙箱、审计、同步）
- `analytics/*`（统计查询）

---

## 12. 领域事件视角（当前实现映射）

当前无统一事件总线，但可抽象为隐式事件：

- `UserLoggedIn`
- `RefreshTokenRotated`
- `ActivationClaimed`
- `ActivationOwnerDenied`
- `JourneyResumed`
- `PhaseAdvanced`
- `ReportUnlocked`
- `LikeRecorded`

这些事件目前分散在 API/service/file 写入中，可作为后续显式事件化改造目标。

---

## 13. 术语冲突与最终标准

## 13.1 冲突点

- `Session` 在前后端含义不唯一
- `step` 与 `phase` 同时存在
- 经典与 Simple 两条链路并存，DTO 结构不同

## 13.2 标准命名（建议强制）

- `db_session_id`：仅指 `sessions.id`
- `activation_session_id`：仅指激活旅程会话标识
- `thread_id`：仅指消息线程
- `exploration_step`：仅指 `values_exploration/...`
- `exploration_phase`：仅指 `values/.../rumination`

---

## 14. 战术 DDD 重构建议（按优先级）

1. 将 `simple_chat_routes.py` 继续拆分为应用服务 + 领域服务 + 基础设施适配器  
2. 为激活旅程建立显式仓储接口（可先包裹 `SimpleActivationManager`）  
3. 将 `explore_resume`、`journeys`、`history` 的 DTO 映射集中化（前后端双侧）  
4. 引入显式领域事件（先做内部事件对象，不急于消息队列）  
5. 统一 session/thread/phase/step 命名并落地 lint 规则  
6. 完善 refresh token 建表迁移一致性，减少运行时建表隐式行为  

---

## 15. 附录：关键代码位置索引

### 后端核心

- `src/backend/app/api/v1/auth.py`
- `src/backend/app/services/auth_service.py`
- `src/backend/app/api/v1/simple_auth.py`
- `src/backend/app/utils/simple_activation_manager.py`
- `src/backend/app/utils/report_registry.py`
- `src/backend/app/utils/super_admin.py`
- `src/backend/app/models/user.py`
- `src/backend/app/models/session.py`
- `src/backend/app/models/answer.py`
- `src/backend/app/models/selection.py`
- `src/backend/app/models/analytics.py`
- `src/backend/app/models/refresh_token.py`
- `src/backend/app/domain/steps.py`
- `src/backend/alembic/versions/001_add_analytics_tables.py`
- `src/backend/alembic/versions/002_enhance_likes_table.py`

### 前端核心

- `src/frontend/components/layout/AuthGate.tsx`
- `src/frontend/components/layout/AuthModal.tsx`
- `src/frontend/lib/api/client.ts`
- `src/frontend/lib/explore/session.ts`
- `src/frontend/app/(main)/explore/activate/page.tsx`
- `src/frontend/app/(main)/explore/chat/[phase]/page.tsx`
- `src/frontend/app/(main)/dashboard/page.tsx`
- `src/frontend/app/(main)/admin/layout.tsx`

### 数据与文档

- `data/simple/`
- `data/test/simple/`
- `data/conversations/`
- `docs/DATA_STORAGE_SIMPLE.md`

---

## 16. 最终对齐结论

本项目当前最重要的领域事实是：  
**“用户身份体系（JWT）”与“激活旅程体系（Activation + Report）”已形成双核心。**

后续所有需求评审与研发执行建议先回答三件事：

1. 这个需求属于哪个 Bounded Context？
2. 它操作的是哪个聚合根（`User` / `DB Session` / `Activation Journey`）？
3. 它产生的状态变更事实源是数据库还是文件系统？

只要三问先答清，术语、接口、数据结构和边界就能稳定一致。

