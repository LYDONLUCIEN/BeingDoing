# Admin 二期功能方案与 TODO（待确认后开发）

> 来源：2026-03-18 需求新增（激活码全生命周期、报告结构化绑定、全局统计、会话检索、报告管理、日志调试、系统设置迁移）。  
> 状态：开发中（核心模块已落地，进入 E2E 联调阶段）。

---

## 1. 本期目标（你提出的 4-10 条）

- 激活码后台支持：批量创建 / 过期 / 删除（含垃圾桶，30 天后彻底清理）
- 数据模型升级：`activation_code_id + user_id -> report_id`，并绑定 5 个 step
- Dashboard 总览：用户、访问、报告、步骤漏斗、token 输入输出统计
- 对话与阶段：全量会话检索、过滤、查看 session 对话与日志
- 报告概览：按 `report_id` 列表展示，可预览/下载
- 日志调试：前后端错误、debug 运行信息可检索
- 系统设置：把原有配色/效果设置迁移到 Admin，并统一 UI 风格

---

## 2. 数据模型方案（核心）

## 2.1 关键实体与关系

- `users`
- `activation_codes`
- `reports`
- `report_steps`（5 个步骤）
- `chat_sessions`
- `chat_messages`
- `llm_usage_logs`
- `agents`（预留多 Agent）
- `activation_recycle_bin`

关系建议：

- `activation_codes (1) -> (N) reports`
- `reports (1) -> (5) report_steps`
- `report_steps (1) -> (N) chat_sessions`
- `chat_sessions (1) -> (N) chat_messages`
- `chat_messages (1) -> (0..N) llm_usage_logs`
- `llm_usage_logs` 可选关联 `agent_id`

## 2.2 report 绑定规则（按你的业务定义）

- 生成 `report_id` 的触发：当某用户首次用某激活码进入探索流程，创建一条 report。
- 唯一约束建议：
  - `UNIQUE (activation_code_id, user_id, report_version)`  
  - `report_version` 默认 `1`（未来支持“重做报告”）
- 5 个步骤固定为：
  - `values`
  - `strengths`
  - `interests`
  - `purpose`
  - `rumination`（沉淀 / combine）

## 2.3 激活码状态与回收策略

状态建议：

- `active`：可用
- `expired`：不可用（历史保留）
- `revoked`：手动停用（不可用）
- `deleted`：逻辑删除（进入垃圾桶）

删除策略（你要求）：

- 激活码“删除”时：
  - 主表标记删除并写入 `activation_recycle_bin`
  - 关联 report/session/message 标记“软删除可恢复”
- 垃圾桶保留 `N=30` 天
- 每日定时任务永久清理（物理删除）

---

## 3. Admin API 规划（新增/扩展）

## 3.1 激活码管理

- `POST /api/v1/admin/activations/batch-create`
- `POST /api/v1/admin/activations/batch-expire`
- `POST /api/v1/admin/activations/batch-delete`
- `POST /api/v1/admin/activations/batch-restore`（从垃圾桶恢复）
- `GET /api/v1/admin/activations/recycle-bin`
- `DELETE /api/v1/admin/activations/recycle-bin/purge`（手动触发清理，可选）

## 3.2 Dashboard 统计

- `GET /api/v1/admin/dashboard/overview`
  - 总用户数、访问次数、报告总数
  - 5 步漏斗（数量+比例）
  - token 输入输出（累计/分步骤）
- `GET /api/v1/admin/dashboard/trends?range=7d|30d|90d`

## 3.3 对话与阶段

- `GET /api/v1/admin/conversations`
  - 支持按 `report_id / step_id / session_id / user_id / activation_code` 过滤
- `GET /api/v1/admin/conversations/{session_id}`
  - 返回原始消息流 + token 使用日志 + agent 调用记录

## 3.4 报告概览

- `GET /api/v1/admin/reports`
- `GET /api/v1/admin/reports/{report_id}`
- `GET /api/v1/admin/reports/{report_id}/download`

## 3.5 日志调试

- `GET /api/v1/admin/logs/backend`
- `GET /api/v1/admin/logs/frontend`
- `GET /api/v1/admin/logs/errors`

## 3.6 系统设置（只读/低风险可写）

- `GET /api/v1/admin/system/theme-config`
- `PUT /api/v1/admin/system/theme-config`（仅样式类配置）

---

## 4. 前端页面方案（Admin）

- `/admin/activations`
  - 表格 + 多选框 + 批量操作（创建/过期/删除/恢复）
  - 增加“垃圾桶”Tab（显示剩余清理天数）
- `/admin`（Dashboard）
  - 4 核心卡片 + 5 步漏斗 + token 图表
- `/admin/conversations`
  - 列表页（筛选）+ 右侧详情抽屉（session 对话）
- `/admin/reports`
  - report 列表 + 详情页 + 下载按钮
- `/admin/logs`
  - 前后端日志检索，按级别/时间/session 过滤
- `/admin/system`
  - 迁移原配色/视觉设置入口，样式与 admin 一致

---

## 5. 开发分期（建议）

## Phase 1（先做可用）

- 激活码批量创建/过期/删除 + 垃圾桶 + 30 天清理任务
- 报告主链路建模：`report -> step -> session`
- Dashboard 基础统计（不含复杂图表）

## Phase 2（增强）

- 对话与阶段检索页 + session 详情
- 报告概览 + 下载
- token 分步骤统计 + agent 使用日志联动

## Phase 3（运维）

- 日志调试页（前后端统一检索）
- 系统设置迁移与 UI 打磨

---

## 6. 待确认项（确认后再写代码）

- [ ] `report_id` 是否允许同一 `activation_code + user` 生成多个版本（默认支持 version）
- [ ] 删除激活码时是否允许“仅删除激活码，不删历史 report”
- [ ] 垃圾桶恢复时是否要恢复所有关联数据（建议是）
- [ ] `filter` 步骤是否单独对话，还是由系统 agent 汇总生成
- [ ] 报告下载格式优先级：PDF / Markdown / JSON

---

## 7. 可打钩执行清单（开发任务）

### A. 后端模型与迁移

- [ ] 新增 `reports` / `report_steps` / `activation_recycle_bin` 表
- [ ] 扩展 `chat_sessions`、`chat_messages`、`llm_usage_logs` 外键关系
- [ ] 补 Alembic 迁移与历史数据兼容脚本

### B. 激活码与垃圾桶

- [x] 批量创建激活码 API
- [x] 批量过期激活码 API
- [x] 批量删除（进垃圾桶）API
- [x] 垃圾桶恢复 API
- [x] 定时清理任务（30 天，服务启动后后台循环执行）
- [x] 删除后主列表保留记录（status=deleted），并支持数据库补齐同步

### C. report 主链路

- [x] 激活时创建/绑定 `report_id`（文件版注册表）
- [x] 创建 5 个 `step_id` 记录（values/strengths/interests/purpose/rumination）
- [x] 对话 `session_id` 绑定对应 step（先按现有 simple session 承接）
- [ ] 消息与 token 使用日志绑定 `session_id` + `agent_id`

### D. Admin 页面

- [x] `/admin/activations` 多选批量操作 + 垃圾桶
- [x] `/admin` Dashboard 统计卡片 + 漏斗 + token（首版）
- [x] `/admin/conversations` 检索 + 详情（首版）
- [x] `/admin/reports` 列表 + 详情 + 下载（JSON）
- [x] `/admin/logs` 调试日志检索（首版）
- [x] `/admin/system` 样式设置迁移（首版）

### E. 验收与发布

- [ ] 权限与数据隔离测试（含 A/B 用户激活码隔离）
- [ ] 统计口径对账（token / session / step / report）
- [ ] 回滚与垃圾桶恢复演练
- [ ] 发布说明与运维手册更新

