# 寻录 安全整改 Todo List（2026-06-10）

> 依据：[0610-开发检测.md](./0610-开发检测.md) 静态审计 + Grill 决策（2026-06-10）  
> 范围：仅文档与任务拆解，**不含代码改动**。实施前请对照 Grill 决策表逐项确认。

---

## 总览

| 优先级 | 任务数 | 是否需要 DB 迁移 | 预估改动规模 |
|--------|--------|------------------|--------------|
| **P0**（公网前必做） | 12 | **0 项必须**（推荐方案均无需 migration） | 2 大 + 4 中 + 6 小 |
| **P1**（1–2 周） | 10 | **1 项必须**（用户隐私同意字段） | 3 中 + 5 小 + 2 大（若 Legacy 未在 P0 下线） |
| **P2**（约 1 月） | 12 | **0–1 项可选**（导出记录表仅当不用 signed token 时） | 多为中 |
| **P3**（持续/可选） | 8 | 否 | 小 |
| **合计** | **42** | **1 项必须 + 1 项可选** | — |

---

## 风险一览（按级别）

| 级别 | 风险简述 | 审计编号 | 对应 Todo |
|------|----------|----------|-----------|
| **Critical** | 激活码创建接口无认证，可批量刷码 | #1 | [P0-01](#p0-01-激活码创建接口强制-super_admin-认证) |
| **Critical** | 导出下载 IDOR，可读他人邮箱/问卷/对话 | #2 | [P0-02](#p0-02-导出-download-idor-修复)、[P0-03](#p0-03-导出-generate-增加-session-归属校验) |
| **Critical** | Analytics 未鉴权，可拉取对话快照/篡改点赞 | #3 | [P0-04](#p0-04-analytics--report-全端点鉴权与归属校验) |
| **High** | Legacy chat/answers 无 session 归属（IDOR） | #4 | [P0-05](#p0-05-legacy-api-处置策略下线或修补)、[P1-08](#p1-08-legacy-chatanswers-idor-修补若-p0-未下线) |
| **High** | 全站无 API 速率限制 | #5 | [P1-04](#p1-04-全站-api-速率限制基础版) |
| **High** | 密码重置 6 位验证码可暴力破解 | #6 | [P1-05](#p1-05-密码重置验证码加固) |
| **High** | SUPER_ADMIN_EMAILS 邮箱抢占 | #7 | [P1-06](#p1-06-super_admin-预注册与邮箱抢占缓解) |
| **High** | 默认 SECRET_KEY / JWT 弱密钥 | #8 | [P0-06](#p0-06-密钥与凭证轮换公网前) |
| **High** | Docker PostgreSQL 5432 对外暴露 | #9 | [P0-08](#p0-08-基础设施端口与安全组加固) |
| **High** | DEBUG_MODE / .env.dev 误用于生产 | #10 | [P0-07](#p0-07-生产-debug_mode-与启动校验)、[P1-09](#p1-09-生产启动配置强制校验脚本) |
| **Medium** | Access Token 存 localStorage | #11 | [P2-04](#p2-04-access-token-存储加固) |
| **Medium** | REFRESH_COOKIE_SECURE 默认 False | #12 | [P0-09](#p0-09-全环境-https-cookie-配置) |
| **Medium** | LLM 提示词注入 / system 泄露 | #13 | [P2-02](#p2-02-提示词泄露防护方案-ab) |
| **Medium** | work_history 项目经历 IDOR | #14 | [P2-06](#p2-06-work_history-项目经历-idor-修复) |
| **Medium** | 文件路径未约束在 base 内 | #15 | [P2-07](#p2-07-simple-工作区路径遍历防护) |
| **Medium** | data/ 明文存储 | #16 | [P2-08](#p2-08-静态数据-at-rest-加密与权限) |
| **Medium** | Admin 沙箱 Fork 复制 PII | #17 | [P1-07](#p1-07-admin-沙箱-fork-确认框与审计强化) |
| **Medium** | 音频上传无大小/MIME 校验 | #18 | [P2-09](#p2-09-音频上传校验与大小限制) |
| **Low** | CORS 硬编码 IP/域名 | #19 | [P2-03](#p2-03-cors-收紧与环境变量化) |
| **Low** | 架构信息未鉴权暴露 | #20 | [P3-02](#p3-02-架构配置端点处置) |
| **Low** | Next.js Server Actions 加密密钥 | #21 | [P0-06](#p0-06-密钥与凭证轮换公网前) |
| **Low** | Markdown XSS 依赖第三方库 | #22 | [P3-04](#p3-04-markdown-渲染-xss-复核) |
| **Low** | 密码重置用户枚举 | #23 | [P3-05](#p3-05-密码重置反用户枚举) |
| **Info** | Swagger UI 生产暴露 | #24 | [P3-03](#p3-03-生产禁用-swagger-ui) |

---

## 改动规模说明

- **小**：单文件或少量文件，几行到几十行；无 schema 变更；或仅环境/运维配置。
- **中**：多文件业务逻辑（API + Service + 前端调用）；可能涉及新工具函数/中间件；**通常无 DB migration**。
- **大**：跨前后端、架构决策、或需同时改路由注册 + 多模块；Legacy 整批下线/修补属此类。

### 哪些项需要数据库迁移？哪些不需要？

| 类别 | 是否需要 migration | 说明 |
|------|-------------------|------|
| **P0 激活码 super_admin 门控** | **否** | `simple_auth.py` 加 `Depends(get_current_user)` + `is_super_admin_user`，与 `admin.py` 一致 |
| **P0 导出 IDOR** | **否**（推荐） | 推荐 **HMAC signed export token** 或内存/Redis 映射（`export_id` UUID + `user_id` + TTL），无需新表；`export_id` 格式 `export_{session_id}_{format}` 必须废弃 |
| **P0 导出 IDOR（备选）** | **是**（可选） | 若选 DB 持久化导出记录，需新表 `export_jobs(id, user_id, session_id, format, created_at, expires_at)` + Alembic revision |
| **P0 Analytics 鉴权** | **否** | `AnalyticsLike` 已有 `user_id`、`activation_code`；`User`/`Session` 表已存在；仅需 API 层 JWT + `resolve_activation_for_user` 归属校验 |
| **P0 Legacy chat/answers IDOR 或 410** | **否** | 代码层 `assert_session_owner` 或 `main.py` 条件注册路由；`Session` 表已有 `user_id` |
| **P0 密钥 / Cookie / DEBUG** | **否** | 仅 `.env*`、`start.sh` 校验逻辑 |
| **P0 端口/安全组** | **否** | ECS 安全组、Nginx 反代、`docker-compose.yml` 去掉 `ports` 映射 |
| **P1 隐私政策 + 注册勾选** | **是** | `User` 模型**当前无** `privacy_policy_accepted_at` / `privacy_policy_version`（见 `models/user.py`）；需 Alembic + `RegisterRequest` 字段 |
| **P1 激活码首次进入勾选** | **否** | `ActivationRecord`（`activations.json`）可加 `ai_consent_at` 等字段，文件 schema 扩展，不走 SQL |
| **P1 速率限制** | **否** | Simple 模式可用内存限流或 Nginx `limit_req`；Full 模式可选 Redis，非当前阻塞 |
| **P1 Admin 沙箱确认框** | **否** | 前端 `admin.py` Fork 入口 + 已有 `sandbox_fork_audit.jsonl` |
| **P2 提示词泄露过滤** | **否** | `simple_chat_routes.py` 流式包装 + 配置项 |
| **P2 work_history IDOR** | **否** | `users.py` + `user_service.py` join 校验 |
| **其余 P2/P3** | **否** | 配置、中间件、文档、运维 |

**结论（与 Grill Q7 一致）**：当前生产主链路为 **Simple 模式（SQLite + JSON）**；P0 核心修复均为**鉴权与归属校验**，**不依赖** PostgreSQL migration。唯一**必须** migration 的是 **P1 用户级隐私同意落库**。

---

## P0 Todo（立即，公网前必做）

### P0-01 激活码创建接口强制 super_admin 认证

- [ ] **P0-01** 激活码创建接口强制 super_admin 认证

| 字段 | 内容 |
|------|------|
| **风险级别** | Critical (#1) |
| **风险说明** | `POST /api/v1/simple-auth/activation` 无任何认证，公网可批量创建激活码 |
| **涉及文件/模块** | `src/backend/app/api/v1/simple_auth.py`（`create_activation`）；参考 `admin.py` 的 `_is_super_admin` 模式 |
| **改动规模** | **小** |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | 未登录或非 super_admin 调用返回 401/403；Admin UI 创建激活码流程正常；审计日志可记录创建者 |
| **依赖关系** | 无；可与 [P1-06](#p1-06-super_admin-预注册与邮箱抢占缓解) 并行，但须先完成管理员预注册 |

**Grill 对齐**：Q2 — 全环境保留路由，**必须** super_admin JWT，**不得**用 `APP_ENV` 裸奔禁用。

---

### P0-02 导出 download IDOR 修复

- [ ] **P0-02** 导出 download IDOR 修复

| 字段 | 内容 |
|------|------|
| **风险级别** | Critical (#2) |
| **风险说明** | `GET /export/download?export_id=export_{session_id}_{format}` 仅校验 JWT，不校验文件归属，可下载他人导出 |
| **涉及文件/模块** | `src/backend/app/api/v1/export.py`（`download_export`）；`src/backend/app/services/export_service.py`；前端导出下载调用（如有） |
| **改动规模** | **中** |
| **是否需要 DB 迁移** | **否**（推荐 signed token / 服务端内存映射 + UUID `export_id`） |
| **验收标准** | 用户 A 无法下载用户 B 的 `export_id`；`export_id` 不可从 `session_id` 猜测；文件 TTL ≤24h；过期返回 404 |
| **依赖关系** | 与 [P0-03](#p0-03-导出-generate-增加-session-归属校验) 同批发布 |

---

### P0-03 导出 generate 增加 session 归属校验

- [ ] **P0-03** 导出 generate 增加 session 归属校验

| 字段 | 内容 |
|------|------|
| **风险级别** | Critical (#2) 辅助 |
| **风险说明** | `generate_export` 仅校验 `request.user_id == current_user`，未校验 `session_id` 是否属于该用户 |
| **涉及文件/模块** | `export.py`；复用 `sessions.py` 的 `_check_session_access` 或抽取 `assert_session_owner` |
| **改动规模** | **小** |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | 传入他人 `session_id` 返回 403；本人 session 可正常生成 |
| **依赖关系** | [P0-02](#p0-02-导出-download-idor-修复) |

---

### P0-04 Analytics / Report 全端点鉴权与归属校验

- [ ] **P0-04** Analytics / Report 全端点鉴权与归属校验

| 字段 | 内容 |
|------|------|
| **风险级别** | Critical (#3) |
| **风险说明** | `unlike`、`likes`、`likes/check`、`likes/message/{id}`、`report-generated`、`like/legacy` 等可无认证访问或缺少归属校验 |
| **涉及文件/模块** | `src/backend/app/api/v1/analytics.py`；`src/backend/app/services/analytics_service.py`；`src/backend/app/api/v1/simple_chat/context_resolver.py`（`resolve_activation_for_user`）；前端 `src/frontend/lib/api/analytics.ts`、报告页点赞展示 |
| **改动规模** | **中** |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | 未登录访问上述 GET 返回 401；用户 A 无法用用户 B 的 `activation_code` 拉取 `content_snapshot`；`unlike` 仅允许点赞所有者或 super_admin；super_admin 可查看（Admin 统计需求）；`report-generated` 需登录 + activation 归属 |
| **依赖关系** | 无；前端须同步携带 JWT（报告页已登录场景） |

**Grill 对齐**：Q5 — 报告与 analytics **PRIVATE**；仅管理员 + 数据所属用户；禁止 `activation_code` 裸访问。

---

### P0-05 Legacy API 处置策略（下线或修补）

- [ ] **P0-05** Legacy API 处置策略（下线或修补）

| 字段 | 内容 |
|------|------|
| **风险级别** | High (#4)，Simple 主链路不经过但路由仍注册 |
| **风险说明** | `chat`、`answers`、`chat_optimized`、`export/generate`（Legacy 路径）、`sessions` 部分端点存在 IDOR 或攻击面；`main.py` 仍注册 10+ Legacy 路由 |
| **涉及文件/模块** | `src/backend/app/main.py`；`chat.py`、`answers.py`、`chat_optimized.py`、`export.py`、`sessions.py`；`ARCHITECTURE_MODE` 配置 |
| **改动规模** | **大** |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | **方案 A（推荐短期）**：`ARCHITECTURE_MODE=simple` 时 Legacy 路由返回 410 或不再注册；**方案 B**：全路由加 `assert_session_owner`；OWASP 手工 IDOR 测试通过；Simple Chat 主链路无回归 |
| **依赖关系** | 若选方案 A，[P1-08](#p1-08-legacy-chatanswers-idor-修补若-p0-未下线) 可取消；若选 B，P1-08 合并入本项 |

**Grill 对齐**：Q1=C — 主链路 Simple；Legacy **仍注册**；短期修补 IDOR **或** 410；长期评估下线。

---

### P0-06 密钥与凭证轮换（公网前）

- [ ] **P0-06** 密钥与凭证轮换（公网前）

| 字段 | 内容 |
|------|------|
| **风险级别** | High (#8, #21) |
| **风险说明** | 默认 `SECRET_KEY` 占位符；access/refresh 可能共用密钥；`NEXT_SERVER_ACTIONS_ENCRYPTION_KEY` 未设导致 Server Action 异常 |
| **涉及文件/模块** | `.env`、`.env.prod`、`.env.dev`、`.env.test`；`src/backend/app/config/settings.py`；`start.sh`；运维密钥保管 |
| **改动规模** | **小**（运维为主） |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | 三密钥均为 `openssl rand` 生成且非占位符；轮换后全员重新登录；前端 rebuild + 硬刷新无 Server Action 错误；旧 LLM/SMTP key 已吊销 |
| **依赖关系** | 维护窗口执行；先于公网流量切入 |

详见审计文档「密钥与凭证轮换清单」。

---

### P0-07 生产 DEBUG_MODE 与启动校验

- [ ] **P0-07** 生产 DEBUG_MODE 与启动校验

| 字段 | 内容 |
|------|------|
| **风险级别** | High (#10) |
| **风险说明** | `.env.dev` 默认 `DEBUG_MODE=True`；super_admin 可跳过激活码过期、解锁全部阶段；`DEBUG=True` 时 500 泄露异常详情 |
| **涉及文件/模块** | `.env.prod`；`settings.py`；`start.sh`；`src/backend/app/api/middleware.py`；`simple_chat/context_resolver.py` |
| **改动规模** | **小** |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | 生产 `.env.prod` 中 `DEBUG_MODE=False`、`DEBUG=False`、`ADMIN_DEBUG_POLICY_ENABLED=False`；`APP_ENV=production` 时误配 DEBUG 启动失败或告警 |
| **依赖关系** | [P0-06](#p0-06-密钥与凭证轮换公网前) 同窗口 |

**Grill 对齐**：Q4 — 生产 `DEBUG_MODE=False`。

---

### P0-08 基础设施端口与安全组加固

- [ ] **P0-08** 基础设施端口与安全组加固

| 字段 | 内容 |
|------|------|
| **风险级别** | High (#9) |
| **风险说明** | `docker-compose.yml` 映射 `8000:8000`、`5432:5432`；默认 `postgres/postgres`；ECS 若直出后端端口可被扫描 |
| **涉及文件/模块** | `docker-compose.yml`；ECS 安全组；Nginx/Caddy（`deploy/nginx-api-stream.conf`）；阿里云 CDN 回源配置 |
| **改动规模** | **小**（运维/配置） |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | 公网仅 443（+ CDN）；8000/3000/5432 不对 `0.0.0.0` 暴露；`ss -tlnp` / 安全组审计通过；compose 生产用法去掉 `db.ports` |
| **依赖关系** | 与 [P0-09](#p0-09-全环境-https-cookie-配置) 同批部署 |

**Grill 对齐**：Q7=C — PG 非当前生产必需；compose 面向 Full 预留，但**不得**公网暴露 5432。

---

### P0-09 全环境 HTTPS Cookie 配置

- [ ] **P0-09** 全环境 HTTPS Cookie 配置

| 字段 | 内容 |
|------|------|
| **风险级别** | Medium (#12)，公网前提升为 P0 |
| **风险说明** | `REFRESH_COOKIE_SECURE` 默认 `False`；HTTP 下 refresh token 可被中间人窃取 |
| **涉及文件/模块** | `.env`、`.env.dev`、`.env.prod`、`.env.test`；`settings.py`；`auth.py` cookie 设置 |
| **改动规模** | **小** |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | dev/test/prod 均为 `REFRESH_COOKIE_SECURE=True`；`FRONTEND_URL` 均为 `https://`；DevTools 中 refresh cookie 带 Secure；无 mixed content |
| **依赖关系** | TLS 证书与反代就绪（见审计「HTTPS 全环境配置指南」） |

**Grill 对齐**：Q4 — 全环境 HTTPS，不再保留 HTTP 模式。

---

### P0-10 动态验证（P0 修复后）

- [ ] **P0-10** P0 修复后动态安全验证

| 字段 | 内容 |
|------|------|
| **风险级别** | —（验收门禁） |
| **风险说明** | 静态审计未覆盖运行时 race、CDN 实际配置 |
| **涉及文件/模块** | 测试记录；可选 OWASP ZAP |
| **改动规模** | **小** |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | 手工 IDOR 用例（export、analytics、activation）全部失败；激活码批量创建脚本返回 403；检查清单存档 |
| **依赖关系** | 依赖 P0-01～P0-09 全部完成 |

---

### P0-11 生产 ADMIN_SANDBOX_ENABLED 关闭

- [ ] **P0-11** 生产 `ADMIN_SANDBOX_ENABLED=False`

| 字段 | 内容 |
|------|------|
| **风险级别** | Medium (#17)，生产硬门禁 |
| **风险说明** | 沙箱 Fork 可复制生产用户 PII 至 `data/test/simple/sandboxes/` |
| **涉及文件/模块** | `.env.prod`；`settings.py`；`admin.py` Fork 端点 |
| **改动规模** | **小** |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | 生产环境 Fork API 返回 403 或功能不可用；dev/test 可按需开启 |
| **依赖关系** | [P1-07](#p1-07-admin-沙箱-fork-确认框与审计强化) 为体验层增强 |

**Grill 对齐**：Q9 — 生产 `ADMIN_SANDBOX_ENABLED=False`。

---

### P0-12 LLM / SMTP 等第三方凭证审查

- [ ] **P0-12** LLM / SMTP 等第三方凭证审查

| 字段 | 内容 |
|------|------|
| **风险级别** | High（凭证泄露成本攻击） |
| **风险说明** | API Key 泄露可导致 LLM 账单异常、邮件滥用 |
| **涉及文件/模块** | `.env.prod`；供应商控制台 |
| **改动规模** | **小** |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | 生产 key 非测试 key；旧 key 吊销；`.env` 未入库 |
| **依赖关系** | [P0-06](#p0-06-密钥与凭证轮换公网前) |

---

## P1 Todo（短期，1–2 周）

### P1-01 隐私政策页面

- [ ] **P1-01** 隐私政策页面

| 字段 | 内容 |
|------|------|
| **风险级别** | 合规（Grill Q6） |
| **风险说明** | 尚无 `/privacy` 页面；页脚链接指向不存在路由 |
| **涉及文件/模块** | 新建 `src/frontend/app/privacy/page.tsx`（或 `(main)/privacy`）；`page.tsx` footer；`zh.ts`/`en.ts` 文案 |
| **改动规模** | **中** |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | `/privacy` 可访问；说明对话由**第三方 AI 服务**处理，**不点名**供应商；中英文版本 |
| **依赖关系** | [P1-02](#p1-02-注册页隐私勾选--后端落库)、[P1-03](#p1-03-激活码首次进入-ai-同意勾选) |

---

### P1-02 注册页隐私勾选 + 后端落库

- [ ] **P1-02** 注册页隐私勾选 + 后端落库

| 字段 | 内容 |
|------|------|
| **风险级别** | 合规（Grill Q6） |
| **风险说明** | 注册无 consent；`User` 表无同意字段 |
| **涉及文件/模块** | `AuthModal.tsx`（注册表单）；`auth.py` `RegisterRequest`；`auth_service.py`；`models/user.py`；`alembic/versions/` 新 revision |
| **改动规模** | **中** |
| **是否需要 DB 迁移** | **是** — 建议字段：`privacy_policy_accepted_at` (DateTime)、`privacy_policy_version` (String) |
| **验收标准** | 未勾选无法提交注册；DB 记录同意时间与版本；已有用户不受影响（可为 NULL，激活时补勾） |
| **依赖关系** | [P1-01](#p1-01-隐私政策页面) |

---

### P1-03 激活码首次进入 AI 同意勾选

- [ ] **P1-03** 激活码首次进入 AI 同意勾选

| 字段 | 内容 |
|------|------|
| **风险级别** | 合规（Grill Q6） |
| **风险说明** | 首次 `activate` 或进入 explore 前无二次确认 |
| **涉及文件/模块** | `explore/activate/page.tsx`；可选 `simple_auth.py` `activate` 校验；`ActivationRecord` + `activations.json` 持久化 `ai_consent_at` |
| **改动规模** | **中** |
| **是否需要 DB 迁移** | **否**（文件字段） |
| **验收标准** | 首次绑定激活码须勾选；未勾选无法进入对话；回访用户不重复勾选（已记录 `ai_consent_at`） |
| **依赖关系** | [P1-01](#p1-01-隐私政策页面) |

---

### P1-04 全站 API 速率限制（基础版）

- [ ] **P1-04** 全站 API 速率限制（基础版）

| 字段 | 内容 |
|------|------|
| **风险级别** | High (#5) |
| **风险说明** | 登录、注册、验证码、LLM、激活码创建可无限制调用 |
| **涉及文件/模块** | 新建 rate limit 中间件或 Nginx `limit_req`；重点：`auth.py`、`simple_chat_routes.py`、`simple_auth.py` |
| **改动规模** | **中** |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | 登录 5 次/分钟/IP 触发 429；LLM 流式 per-user 并发上限可配置；与 CDN 限流不冲突 |
| **依赖关系** | [P0-01](#p0-01-激活码创建接口强制-super_admin-认证) 降低激活码滥用面 |

---

### P1-05 密码重置验证码加固

- [ ] **P1-05** 密码重置验证码加固

| 字段 | 内容 |
|------|------|
| **风险级别** | High (#6) |
| **风险说明** | 6 位数字、5 分钟有效、无 attempt 上限 |
| **涉及文件/模块** | `auth_service.py`；可选 Redis/内存 attempt 计数 |
| **改动规模** | **中** |
| **是否需要 DB 迁移** | **否**（内存即可）；可选 `password_reset_attempts` 表 |
| **验收标准** | ≥8 位字母数字或 6 位+5 次失败作废；生产禁用 stdout 假 SMS |
| **依赖关系** | [P1-04](#p1-04-全站-api-速率限制基础版) |

---

### P1-06 SUPER_ADMIN 预注册与邮箱抢占缓解

- [ ] **P1-06** SUPER_ADMIN 预注册与邮箱抢占缓解

| 字段 | 内容 |
|------|------|
| **风险级别** | High (#7) |
| **风险说明** | 开放注册可抢占 `SUPER_ADMIN_EMAILS` 中的邮箱 |
| **涉及文件/模块** | 部署 Runbook；`auth_service.py` 注册时检查 reserved emails；`super_admin.py` |
| **改动规模** | **小–中** |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | 部署 checklist：先注册管理员邮箱再开放注册；或注册拒绝 reserved 列表邮箱；文档化 |
| **依赖关系** | [P0-01](#p0-01-激活码创建接口强制-super_admin-认证) |

**Grill 对齐**：Q3 — 方案 A `SUPER_ADMIN_EMAILS`；部署前预注册。

---

### P1-07 Admin 沙箱 Fork 确认框与审计强化

- [ ] **P1-07** Admin 沙箱 Fork 确认框与审计强化

| 字段 | 内容 |
|------|------|
| **风险级别** | Medium (#17) |
| **风险说明** | Fork 复制生产 PII，误操作风险 |
| **涉及文件/模块** | Admin 前端 Fork UI；`admin.py`；`sandbox_fork_audit.jsonl`（已有） |
| **改动规模** | **小** |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | Fork 前二次确认对话框（说明复制 PII）；审计日志含操作者、源激活码、时间 |
| **依赖关系** | [P0-11](#p0-11-生产-admin_sandbox_enabled-关闭) |

**Grill 对齐**：Q9 — 无审批链；确认框 + 审计日志。

---

### P1-08 Legacy chat/answers IDOR 修补（若 P0 未下线）

- [ ] **P1-08** Legacy chat/answers IDOR 修补（若 P0 未下线）

| 字段 | 内容 |
|------|------|
| **风险级别** | High (#4) |
| **风险说明** | `chat/messages`、`answers/*` 等无 `_check_session_access` |
| **涉及文件/模块** | `chat.py`、`answers.py`；抽取 `src/backend/app/utils/session_access.py`（建议）；`sessions.py` |
| **改动规模** | **大**（若逐端点修补） |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | 所有 `session_id` 入参 API 调用 `assert_session_owner`；单元测试覆盖 |
| **依赖关系** | 若 [P0-05](#p0-05-legacy-api-处置策略下线或修补) 选 410 方案，**取消本项** |

---

### P1-09 生产启动配置强制校验脚本

- [ ] **P1-09** 生产启动配置强制校验脚本

| 字段 | 内容 |
|------|------|
| **风险级别** | High (#8, #10, #12) |
| **风险说明** | 弱密钥、DEBUG、Cookie 误配可静默上线 |
| **涉及文件/模块** | `start.sh` 或 `scripts/preflight_prod.py` |
| **改动规模** | **小** |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | `APP_ENV=production` 时：默认 SECRET_KEY → 拒绝启动；`REFRESH_COOKIE_SECURE!=True` → 拒绝；`DEBUG_MODE=True` → 拒绝 |
| **依赖关系** | [P0-06](#p0-06-密钥与凭证轮换公网前)、[P0-07](#p0-07-生产-debug_mode-与启动校验)、[P0-09](#p0-09-全环境-https-cookie-配置) |

---

### P1-10 抽取统一 session 归属中间件

- [ ] **P1-10** 抽取统一 `assert_session_owner` 工具

| 字段 | 内容 |
|------|------|
| **风险级别** | High (#4) 工程化 |
| **风险说明** | `_check_session_access` 仅在 `sessions.py`，未复用 |
| **涉及文件/模块** | 新建 `utils/session_access.py`；`sessions.py`、`export.py`、`chat.py`、`answers.py` |
| **改动规模** | **中** |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | 单一函数供全站调用；文档说明 Simple 模式 session vs activation 区别 |
| **依赖关系** | [P0-03](#p0-03-导出-generate-增加-session-归属校验)、[P1-08](#p1-08-legacy-chatanswers-idor-修补若-p0-未下线) |

---

## P2 Todo（中期，约 1 月）

### P2-01 WAF 接入（阿里云）

- [ ] **P2-01** WAF 接入指南与落地

| 字段 | 内容 |
|------|------|
| **风险级别** | 基础设施 |
| **风险说明** | CDN 已接入，WAF 未接入；无 WAF 时 rate limit 单点脆弱 |
| **涉及文件/模块** | 运维文档；阿里云 WAF 控制台；CDN 回源 |
| **改动规模** | **中**（运维） |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | WAF 规则启用；OWASP 核心规则集；与 [P1-04](#p1-04-全站-api-速率限制基础版) 联动 |
| **依赖关系** | 公网已 HTTPS（P0-09） |

**Grill 对齐**：Q8 — WAF 待接入。

---

### P2-02 提示词泄露防护方案 A+B

- [ ] **P2-02** 提示词泄露防护（输入 gate + 流式输出过滤）

| 字段 | 内容 |
|------|------|
| **风险级别** | Medium (#13) |
| **风险说明** | 无输出审查；用户可诱导模型复述 system prompt |
| **涉及文件/模块** | `simple_chat_routes.py`；新建 `prompt_leak_filter.yaml` 或 settings；`test/` 单元测试 |
| **改动规模** | **中**（约 3–5 人日） |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | 常见 jailbreak 短语短路；流式黑名单命中停止 SSE 并兜底回复；`PROMPT_LEAK_FILTER_ENABLED` feature flag |
| **依赖关系** | 无 |

**Grill 对齐**：Q10=A 当前接受 residual risk；A+B 为后续加固，非 P0。

---

### P2-03 CORS 收紧与环境变量化

- [ ] **P2-03** CORS 收紧与环境变量化

| 字段 | 内容 |
|------|------|
| **风险级别** | Low (#19) |
| **风险说明** | `main.py` 硬编码 IP/域名 |
| **涉及文件/模块** | `main.py`；`settings.py` 新增 `CORS_ORIGINS` |
| **改动规模** | **小** |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | 仅 env 列出的 origin；移除不必要的裸 IP |
| **依赖关系** | 无 |

---

### P2-04 Access Token 存储加固

- [ ] **P2-04** Access Token 存储加固

| 字段 | 内容 |
|------|------|
| **风险级别** | Medium (#11) |
| **风险说明** | JWT 存 `localStorage`，XSS 可窃取 |
| **涉及文件/模块** | `client.ts`、`authStore.ts`；可选 BFF cookie 方案 |
| **改动规模** | **大**（若改 BFF）/ **小**（若仅缩短 TTL + CSP） |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | 评估报告选型；至少缩短 access TTL + 强化 CSP |
| **依赖关系** | [P3-04](#p3-04-markdown-渲染-xss-复核) |

---

### P2-05 启动时 REFRESH_COOKIE_SECURE 强制校验

- [ ] **P2-05** 启动时 Cookie Secure 强制校验

| 字段 | 内容 |
|------|------|
| **风险级别** | Medium (#12) |
| **风险说明** | 仅靠文档易遗漏 |
| **涉及文件/模块** | `start.sh` / `preflight_prod.py` |
| **改动规模** | **小** |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | 与 [P1-09](#p1-09-生产启动配置强制校验脚本) 合并或增强 |
| **依赖关系** | [P0-09](#p0-09-全环境-https-cookie-配置) |

---

### P2-06 work_history 项目经历 IDOR 修复

- [ ] **P2-06** work_history 项目经历 IDOR 修复

| 字段 | 内容 |
|------|------|
| **风险级别** | Medium (#14) |
| **风险说明** | `POST /users/work-history/{id}/projects` 未校验 work_history 归属 |
| **涉及文件/模块** | `users.py`；`user_service.py` |
| **改动规模** | **小** |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | 他人 `work_history_id` 返回 403 |
| **依赖关系** | 无 |

---

### P2-07 Simple 工作区路径遍历防护

- [ ] **P2-07** Simple 工作区路径遍历防护

| 字段 | 内容 |
|------|------|
| **风险级别** | Medium (#15) |
| **风险说明** | `get_effective_simple_root` 未 `is_relative_to(base)` |
| **涉及文件/模块** | `simple_activation_manager.py`；`admin_workspace.py` |
| **改动规模** | **小** |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | 含 `..` 或解析后逃逸 base 的路径被拒绝 |
| **依赖关系** | 无 |

---

### P2-08 静态数据 at-rest 加密与权限

- [ ] **P2-08** 静态数据 at-rest 加密与权限

| 字段 | 内容 |
|------|------|
| **风险级别** | Medium (#16) |
| **风险说明** | `data/` 明文挂载，备份即泄露 |
| **涉及文件/模块** | 运维；`docker-compose.yml` volume；OS 文件权限 |
| **改动规模** | **大** |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | 备份加密；容器非 root 运行；敏感字段脱敏策略文档 |
| **依赖关系** | 无 |

---

### P2-09 音频上传校验与大小限制

- [ ] **P2-09** 音频上传校验与大小限制

| 字段 | 内容 |
|------|------|
| **风险级别** | Medium (#18) |
| **风险说明** | `transcribe_audio` 无大小/MIME 校验 |
| **涉及文件/模块** | `audio.py` |
| **改动规模** | **小** |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | ≤10MB；`audio/*` 白名单；超时 |
| **依赖关系** | 仅 `AUDIO_MODE=True` 时 |

---

### P2-10 生产 CSP 部署

- [ ] **P2-10** 生产 CSP 部署

| 字段 | 内容 |
|------|------|
| **风险级别** | Medium (#11, #22) |
| **风险说明** | 缺少 `Content-Security-Policy` |
| **涉及文件/模块** | `next.config.js` 或 Nginx headers |
| **改动规模** | **中** |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | `script-src 'self'`；不破坏流式/chat |
| **依赖关系** | [P3-04](#p3-04-markdown-渲染-xss-复核) |

---

### P2-11 提示词泄露方案 B（可选）

- [ ] **P2-11** 提示词泄露方案 B（分类器 + 监控，可选）

| 字段 | 内容 |
|------|------|
| **风险级别** | Medium (#13) |
| **风险说明** | A+B 不足或合规要求提高时 |
| **涉及文件/模块** | 新服务/模型；监控告警 |
| **改动规模** | **大** |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | Red team 评估后决策是否启动 |
| **依赖关系** | [P2-02](#p2-02-提示词泄露防护方案-ab) |

---

### P2-12 Admin 操作审计告警

- [ ] **P2-12** Admin 操作审计告警

| 字段 | 内容 |
|------|------|
| **风险级别** | Medium (#17) |
| **风险说明** | 审计日志已有但无告警 |
| **涉及文件/模块** | `sandbox_fork_audit.jsonl`；日志采集 |
| **改动规模** | **中** |
| **是否需要 DB 迁移** | **否** |
| **验收标准** | 异常 Fork 频率告警；保留期清理自动化验证 |
| **依赖关系** | [P1-07](#p1-07-admin-沙箱-fork-确认框与审计强化) |

---

## P3 / 可选

### P3-01 定期依赖扫描与渗透测试

- [ ] **P3-01** 定期依赖扫描与 LLM red team

| 改动规模 | 小（流程） | DB 迁移 | 否 |

---

### P3-02 架构配置端点处置

- [ ] **P3-02** `GET /api/v1/config/architecture` 处置

| 风险 | Low (#20) | 改动规模 | 小 | DB | 否 |
| 说明 | 可保持公开或仅内网；低危 |

---

### P3-03 生产禁用 Swagger UI

- [ ] **P3-03** 生产禁用 Swagger UI

| 风险 | Info (#24) | 涉及 | `main.py` `docs_url=None` | 改动规模 | 小 | DB | 否 |

---

### P3-04 Markdown 渲染 XSS 复核

- [ ] **P3-04** Markdown 渲染 XSS 复核

| 风险 | Low (#22) | 涉及 | `MessageContent.tsx` | 改动规模 | 小 | DB | 否 |
| 验收 | 确认 `rehype-sanitize` 启用 |

---

### P3-05 密码重置反用户枚举

- [ ] **P3-05** 密码重置反用户枚举

| 风险 | Low (#23) | 涉及 | `auth_service.py` | 改动规模 | 小 | DB | 否 |
| 验收 | 统一返回「若邮箱存在则已发送」 |

---

### P3-06 CORS 移除历史裸 IP

- [ ] **P3-06** CORS 移除历史裸 IP

| 改动规模 | 小 | 依赖 | [P2-03](#p2-03-cors-收紧与环境变量化) |

---

### P3-07 第三方 LLM DPA 与用户告知完善

- [ ] **P3-07** 第三方 LLM 数据处理协议文档化

| 改动规模 | 小（法务/文档） | 依赖 | [P1-01](#p1-01-隐私政策页面) |

---

### P3-08 导出记录 DB 表（仅当不用 signed token）

- [ ] **P3-08** 导出记录持久化表（可选架构增强）

| 改动规模 | 中 | DB 迁移 | **是**（可选） |
| 说明 | 仅当 [P0-02](#p0-02-导出-download-idor-修复) 不采用 signed token 时的长期方案 |

---

## 建议实施顺序（甘特式文字）

### 第 0 周（部署前硬门禁，1–3 天）

| 顺序 | 任务 | 说明 |
|------|------|------|
| 1 | [P0-06](#p0-06-密钥与凭证轮换公网前) | 维护窗口；全员重登 |
| 2 | [P0-07](#p0-07-生产-debug_mode-与启动校验)、[P0-09](#p0-09-全环境-https-cookie-配置)、[P0-11](#p0-11-生产-admin_sandbox_enabled-关闭) | 同步改 `.env.prod` |
| 3 | [P0-08](#p0-08-基础设施端口与安全组加固) | 安全组 + Nginx 仅 443 |
| 4 | [P0-01](#p0-01-激活码创建接口强制-super_admin-认证) | 代码首发 |
| 5 | [P0-04](#p0-04-analytics--report-全端点鉴权与归属校验) | 与前端 analytics 调用同步 |
| 6 | [P0-02](#p0-02-导出-download-idor-修复)、[P0-03](#p0-03-导出-generate-增加-session-归属校验) | 同 PR |
| 7 | [P0-05](#p0-05-legacy-api-处置策略下线或修补) | **架构决策日**：410 vs 修补 |
| 8 | [P0-10](#p0-10-动态验证p0-修复后) | 上线门禁 |

### 第 1–2 周（P1）

| 顺序 | 任务 |
|------|------|
| 1 | [P1-06](#p1-06-super_admin-预注册与邮箱抢占缓解)（若未在 P0 前完成） |
| 2 | [P1-09](#p1-09-生产启动配置强制校验脚本) |
| 3 | [P1-01](#p1-01-隐私政策页面) → [P1-02](#p1-02-注册页隐私勾选--后端落库) → [P1-03](#p1-03-激活码首次进入-ai-同意勾选) |
| 4 | [P1-04](#p1-04-全站-api-速率限制基础版)、[P1-05](#p1-05-密码重置验证码加固) |
| 5 | [P1-07](#p1-07-admin-沙箱-fork-确认框与审计强化) |
| 6 | [P1-10](#p1-10-抽取统一-session-归属中间件)、[P1-08](#p1-08-legacy-chatanswers-idor-修补若-p0-未下线)（若需要） |

### 第 3–4 周（P2 起步）

| 顺序 | 任务 |
|------|------|
| 1 | [P2-01](#p2-01-waf-接入阿里云) |
| 2 | [P2-02](#p2-02-提示词泄露防护方案-ab) |
| 3 | [P2-03](#p2-03-cors-收紧与环境变量化)、[P2-06](#p2-06-work_history-项目经历-idor-修复)、[P2-07](#p2-07-simple-工作区路径遍历防护) |
| 4 | [P2-09](#p2-09-音频上传校验与大小限制)、[P3-03](#p3-03-生产禁用-swagger-ui) |

### 持续（P3）

- 季度依赖扫描、[P3-01](#p3-01-定期依赖扫描与渗透测试)
- Red team 后评估 [P2-11](#p2-11-提示词泄露方案-b可选)、[P2-04](#p2-04-access-token-存储加固)

---

## 与 Grill 决策的对照

| Grill # | 决策摘要 | 本 Todo 落点 |
|---------|----------|--------------|
| **Q1** | Simple 主链路；Legacy 仍注册；短期 410 或修补 IDOR | [P0-05](#p0-05-legacy-api-处置策略下线或修补)、[P1-08](#p1-08-legacy-chatanswers-idor-修补若-p0-未下线) |
| **Q2** | 激活码创建 **必须 super_admin**，全环境，非 APP_ENV 禁用 | [P0-01](#p0-01-激活码创建接口强制-super_admin-认证) |
| **Q3** | `SUPER_ADMIN_EMAILS` + 部署前预注册 | [P1-06](#p1-06-super_admin-预注册与邮箱抢占缓解) |
| **Q4** | 轮换 `SECRET_KEY`；生产 `DEBUG_MODE=False`；全环境 HTTPS + Secure Cookie | [P0-06](#p0-06-密钥与凭证轮换公网前)、[P0-07](#p0-07-生产-debug_mode-与启动校验)、[P0-09](#p0-09-全环境-https-cookie-配置) |
| **Q5** | Analytics/Report **PRIVATE**；JWT + 归属；禁止裸 activation_code | [P0-04](#p0-04-analytics--report-全端点鉴权与归属校验) |
| **Q6** | 注册勾选 + 激活首次勾选 + 隐私政策页；第三方 AI 不点名 | [P1-01](#p1-01-隐私政策页面)、[P1-02](#p1-02-注册页隐私勾选--后端落库)、[P1-03](#p1-03-激活码首次进入-ai-同意勾选) |
| **Q7** | 生产 Simple/SQLite；PG 非阻塞；不暴露 5432 | [P0-08](#p0-08-基础设施端口与安全组加固)；无 PG migration 需求 |
| **Q8** | 阿里云 CDN 有；WAF 待接入 | [P2-01](#p2-01-waf-接入阿里云)、[P1-04](#p1-04-全站-api-速率限制基础版) |
| **Q9** | 沙箱无审批；确认框 + 审计；生产 `ADMIN_SANDBOX_ENABLED=False` | [P0-11](#p0-11-生产-admin_sandbox_enabled-关闭)、[P1-07](#p1-07-admin-沙箱-fork-确认框与审计强化) |
| **Q10** | 当前纯提示词防护；接受 residual risk；后续 A+B | [P2-02](#p2-02-提示词泄露防护方案-ab)、[P2-11](#p2-11-提示词泄露方案-b可选) |

---

*文档版本：2026-06-10 | 对应审计：[0610-开发检测.md](./0610-开发检测.md)*
