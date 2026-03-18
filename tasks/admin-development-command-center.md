# Admin 开发总指挥（长期任务文档）

> 用途：统一记录 `/admin` 开发全过程。  
> 规则：每次会话结束前必须更新本文件（勾选进度 + 追加历史记录）。

## 0. 文档信息

- 项目：BeingDoing
- 范围：`/admin` 管理后台（方案 B：独立子域 + 强鉴权）
- 当前建议方案：`admin.soulhappylab.com` + 后端 `super_admin` 强校验 + 二次验证（step-up）
- 文档位置：`tasks/admin-development-command-center.md`
- 维护方式：持续迭代，不删除历史条目，只追加

---

## 第一部分：TODO List（可打钩）

### 0) 里程碑总览（M1-M4）

> 使用方式：先看当前里程碑，再执行对应清单。  
> 规则：一个里程碑完成后再进入下一个，避免范围失控。

#### M1 - 安全底座与访问入口（先打地基）

- 目标：admin 子域可访问，且具备最小安全保护
- 验收标准：
  - `https://admin.soulhappylab.com` 可正常打开
  - `/api` 在 admin 子域下可通
  - 后端 admin 接口已有 `super_admin` 强校验
- 预计耗时：0.5 - 1 天
- 对应任务：
  - [ ] 完成 A1-A5（基础设施）
  - [ ] 完成 B1（后端 super_admin 校验）

#### M2 - 二次验证与审计闭环（安全闭环）

- 目标：进入 admin 需要 step-up，关键操作可审计
- 验收标准：
  - 进入 admin 前必须通过二次验证
  - step-up 失效后自动重新验证
  - 关键 admin 操作可追溯
- 预计耗时：1 - 1.5 天
- 对应任务：
  - [ ] 完成 B2-B4（step-up、短时会话、审计）
  - [ ] 完成 C1-C2（前端守卫 + step-up 页面）

#### M3 - 核心 Admin 页面可用（业务可用）

- 目标：管理后台核心页面从占位升级为可用
- 验收标准：
  - `/admin` 总览有真实指标
  - `activations/conversations/reports` 基础可用
  - `analytics/logs/system` 能提供核心信息
- 预计耗时：2 - 4 天
- 对应任务：
  - [ ] 完成 B5-B6（统计接口 + 脱敏）
  - [ ] 完成 C3-C9（主要 admin 页面）

#### M4 - 预发布、发布与回滚演练（上线保障）

- 目标：可控上线，出问题能快速回滚
- 验收标准：
  - 预发布环境通过
  - 回滚演练成功
  - 生产发布后巡检通过
- 预计耗时：0.5 - 1 天
- 对应任务：
  - [ ] 完成 D1-D5（联调、预发、回滚、上线、巡检）

### 0.1 当前冲刺（Current Sprint）

- 当前里程碑：`M3`
- 当前优先级（仅做这 3 件）：
  - [x] 完成核心 Admin 页面联通（activations/dashboard/conversations/reports/logs/system）
  - [x] 完成激活码生命周期（批量 + 垃圾桶 + deleted 保留）
  - [ ] 执行端到端 E2E 验收清单并收敛链路问题
- 完成定义（DoD）：
  - [ ] E2E 清单 P0 项全部通过
  - [ ] 关键链路：activation -> report -> step -> session -> message/token 可闭环追踪
  - [ ] 发布前风险项与回滚路径确认

### A. 上线前准备（基础设施）

- [x] 新增 DNS：`admin.soulhappylab.com` -> 服务器公网 IP
- [x] 在 1Panel 新增 admin 子域站点/反代
- [x] 为 admin 子域签发并启用 SSL 证书
- [ ] 确认 `/api` 在 admin 子域下可正确反代到后端
- [ ] 增加 admin 专用限流策略（`/admin`、`/api/v1/admin`）
- [ ] （可选）配置 IP 白名单（仅办公 IP 可访问）

### B. 后端安全与接口

- [x] 统一后端 `super_admin` 校验（覆盖全部 `/api/v1/admin/*`）
- [ ] 新增 admin 二次验证（step-up）接口
- [ ] 增加短时 admin token/session（建议 10-15 分钟）
- [ ] 管理操作审计日志（操作者、时间、IP、UA、操作内容）
- [ ] 补齐 admin 页面所需统计接口（dashboard/analytics/reports/logs）
- [ ] 对系统配置展示接口做脱敏（隐藏密钥/敏感字段）

### C. 前端 Admin 页面开发

- [x] `/admin/layout` 接入权限守卫（非 super_admin 禁止访问）
- [ ] 增加 step-up 验证页（进入 admin 前二次确认）
- [x] `/admin` 总览页：核心指标卡 + 趋势占位图
- [x] `/admin/activations`：完善筛选、分页、状态展示
- [x] `/admin/conversations`：会话列表 + 详情抽屉
- [x] `/admin/reports`：报告状态列表 + 基础预览入口
- [ ] `/admin/analytics`：调用量、错误率、Token 统计
- [x] `/admin/logs`：关键日志检索（支持按激活码/session）
- [x] `/admin/system`：只读环境配置页（脱敏）

### D. 验证与发布

- [ ] 本地联调通过（前后端 + 权限 + step-up）
- [ ] 预发布环境验证（admin 子域 + SSL + 反代 + CORS）
- [ ] 回滚预案演练（站点配置回滚 + 代码回滚）
- [ ] 生产发布窗口执行
- [ ] 发布后巡检（登录、权限、接口、日志、性能）

---

## 第二部分：额外信息（决策、配置、风险）

### 1) 当前安全决策

- 采用方案 B（推荐）：
  - admin 使用独立子域（`admin.soulhappylab.com`）
  - 不暴露裸端口，统一经 1Panel/Nginx 反代
  - 服务端强制 `super_admin` + step-up 双层校验

### 2) 与方案 A 的差异（简版）

- 方案 A：同域 `/admin`，改动小，隔离弱
- 方案 B：独立子域，改动中等，隔离更清晰，长期更稳
- 预估额外工作量：约 `+30% ~ +60%`

### 3) 关键配置检查清单（每次发布前）

- [ ] `.env` 关键项完整（JWT、LLM、SMTP、SUPER_ADMIN）
- [ ] 后端 CORS 包含 `https://admin.soulhappylab.com`
- [ ] 前端 `NEXT_PUBLIC_API_URL` 与反代策略一致
- [ ] 1Panel 反代规则未误改 `_next` 与 `/api`
- [ ] HTML 缓存与静态资源缓存策略正确

### 4) 风险与回滚

- 主要风险：
  - CORS 配置不全导致 admin 调用失败
  - 反代规则冲突导致 404/503
  - 鉴权逻辑仅在前端拦截（后端漏拦截）
- 回滚原则：
  - 先回滚 1Panel 站点配置
  - 再回滚代码到上一个可用 tag/commit
  - 回滚后立即做最小功能巡检（登录、admin 访问、关键 API）

---

## 第三部分：历史解决问题（持续追加）

> 记录格式：日期 | 问题 | 根因 | 处理 | 结果 | 后续动作

### 历史记录

- [2026-02-12] Admin 开发方向确定：采用方案 B（独立子域 + 双层鉴权），先做规划文档与任务拆分。  
  - 状态：已确认方向，待进入实现阶段。
- [2026-02-12] 文档升级为里程碑管理（M1-M4），新增 Current Sprint，后续按里程碑推进并逐项勾选。  
  - 状态：已生效，当前执行 M1。
- [2026-03-18] M1 进展更新：DNS、admin 子域建站、SSL 已完成；后端 `super_admin` 校验与 admin CORS 已就绪。  
  - 状态：进入 7/8/9 联调与回滚演练阶段。
- [2026-03-18] 收到 Admin 二期需求（激活码批量生命周期、report-step-session-message-agent 数据链路、Dashboard 统计、对话检索、报告概览、日志调试、系统设置迁移），已落地专项方案文档。  
  - 文档：`tasks/admin-phase2-feature-plan.md`
  - 状态：待需求确认后进入开发。
- [2026-03-18] Admin 二期第一批开发完成：激活码批量创建/状态调整/删除入垃圾桶/恢复 API，上线 `/admin/activations` 多选批量操作与垃圾桶视图；新增文件版 report 注册表（activation+user -> report -> 5 steps -> session 绑定）。  
  - 状态：已可测试，待继续补“30天自动清理定时任务”和 Dashboard/对话/报告模块。
- [2026-03-18] Admin 二期第二批开发完成：已加入垃圾桶 30 天自动清理后台任务；新增 Dashboard 概览接口（用户/访问/报告/5步漏斗/token总量与分步骤）；`/admin` 页面接入真实数据展示。  
  - 状态：Dashboard 首版可用，下一步进入“对话与阶段 / 报告概览 / 日志调试”模块。
- [2026-03-18] Dashboard 统计改为“默认读取 data/static 缓存 + 手动同步从 /data 重算”；report 五步骤命名统一为 `values/strength/interest/purpose/rumination`（兼容旧命名 strengths/interests/filter）。  
  - 状态：可进行联调验证（手动同步按钮 + 缓存文件生成）。
- [2026-03-18] 激活码管理增强：删除后保留在主列表（status=deleted），并提供“从数据库同步激活码列表”能力；新增 `sync_simple_storage_alias.py`，可在 data/simple 下生成 `激活码__session_id` 目录别名用于排查。  
  - 状态：已可测试。
- [2026-03-18] Admin 页继续落地：`/admin/conversations` 已接入 report-step-session 检索和会话详情查看；`/admin/reports` 已接入列表、详情与 JSON 下载。  
  - 状态：进入 `logs/system` 页面开发与链路总验收阶段。
- [2026-03-18] 第 9/10 项完成首版：`/admin/logs` 已支持按 session/dimension 检索埋点并查看 session/like 详情；`/admin/system` 已迁移主题、效果、配色控制并接入只读系统配置。此外 `/admin/reports` 增加“从激活码补齐报告”操作，解决报告列表初始为空问题。  
  - 状态：进入全链路联调与问题清单收敛阶段。
- [2026-03-18] 新增端到端验收清单：`tasks/admin-e2e-checklist.md`，用于统一执行上线前链路验证并打勾记录。  
  - 状态：待逐项验收。

### 追加模板（复制使用）

```md
- [YYYY-MM-DD] 问题标题
  - 现象：
  - 根因：
  - 处理动作：
  - 验证结果：
  - 后续动作：
```

---

## 更新约定（每次都执行）

- [ ] 本次新增/修改了哪些页面与接口（写在历史记录）
- [ ] 本次完成了哪些 TODO（勾选）
- [ ] 本次是否引入新风险（若有，写明回滚方案）
- [ ] 下一步最小可执行动作（只写 1-3 条）

