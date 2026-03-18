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

- 当前里程碑：`M1`
- 当前优先级（仅做这 3 件）：
  - [x] 完成 admin 子域 DNS + SSL
  - [ ] 完成 1Panel 反代（`/` 到前端，`/api` 到后端）
  - [x] 完成后端 admin 路由 `super_admin` 强校验梳理
- 完成定义（DoD）：
  - [ ] admin 子域打开正常
  - [ ] `/api/v1/admin/*` 非 super_admin 返回 403
  - [ ] super_admin 可正常访问 admin 页面和接口

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

- [ ] `/admin/layout` 接入权限守卫（非 super_admin 禁止访问）
- [ ] 增加 step-up 验证页（进入 admin 前二次确认）
- [ ] `/admin` 总览页：核心指标卡 + 趋势占位图
- [ ] `/admin/activations`：完善筛选、分页、状态展示
- [ ] `/admin/conversations`：会话列表 + 详情抽屉
- [ ] `/admin/reports`：报告状态列表 + 基础预览入口
- [ ] `/admin/analytics`：调用量、错误率、Token 统计
- [ ] `/admin/logs`：关键日志检索（支持按激活码/session）
- [ ] `/admin/system`：只读环境配置页（脱敏）

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

