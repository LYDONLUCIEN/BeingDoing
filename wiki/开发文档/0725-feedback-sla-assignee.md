# 0725 反馈 SLA 时限 + 处理人 + 超时提醒

> 状态：已完成（2026-07-25）
> 前置功能：0716 反馈浮窗（`claude-completed-0716-feedback-widget.md`）

## 需求背景

用户反馈功能已上线（bug/idea 分类、截图、三态流转、邮件回复），本次按产品要求补充：

- 分类文案口径统一为「问题反馈 / 意见建议」（枚举值 `bug`/`idea` 不变，仅改展示文案）
- 按类型区分承诺处理时限：问题反馈 3 个工作日、意见建议 5 个工作日
- 提交后明确告知用户预计回复时间与方式（邮箱）
- admin 后台增加：处理人、承诺截止时间、超时提醒

## 关键决策（与用户逐项确认）

1. **枚举不动**：`bug`/`idea` 不变，只改前端文案（存量数据零迁移成本）。
2. **due_at 落库**：提交时按类型计算截止时间存库；工作日 = 跳过周六日，法定节假日不计算（文案提示"法定节假日可能略有延期"）。
3. **处理人**：`assignee_id` 可空，admin 详情页下拉指派（选项 = super_admin 用户），手动认领制。
4. **超时提醒**：cron 每日扫描 `due_at < now 且 status != done`，站内信通知所有 super_admin，当天幂等；列表/详情页红色「已超时」标签（前端按 due_at 实时判断）。
5. **存量数据**：老反馈 `due_at = NULL`，后台显示「—」，不参与超时扫描。
6. **处理方式**：维持"邮箱回复"为唯一承诺通道（SMTP 现状不变）。

## 改动清单

### 后端

| 文件 | 改动 |
|---|---|
| `app/models/feedback.py` | `Feedback` 新增 `due_at`、`assignee_id`（FK users，SET NULL） |
| `alembic/versions/016_feedback_sla_assignee.py` | 新迁移；SQLite 需 batch 模式且加列/加外键分两个 batch |
| `app/services/feedback_service.py` | `calc_due_at()` 工作日计算（zoneinfo 北京时间）；`FEEDBACK_DUE_WORKDAYS = {bug:3, idea:5}`；auto_ack 文案按类型生成（含预计日期+节假日提示）；`REPLY_TYPE_LABEL` 改为「问题反馈/意见建议」；`_get_super_admin_ids` 增强为同时解析 SUPER_ADMIN_EMAILS；新增 `list_assignees` / `admin_update_assignee` |
| `app/services/feedback_overdue_scan.py` | 新增：超时扫描 + 幂等站内信（type=`feedback_overdue`） |
| `app/config/settings.py` | 新增 `FEEDBACK_OVERDUE_SCAN_CRON`（默认 `0 9 * * *`） |
| `app/main.py` | 注册 `feedback_overdue_scan` cron job（safe wrapper，异常不影响调度器） |
| `app/schemas/feedback.py` | `FeedbackOut`/`AdminFeedbackItem`/`AdminFeedbackDetailOut` 加 due_at/assignee 字段；新增 `FeedbackAssigneeUpdate`、`AdminAssigneeOut` |
| `app/api/v1/admin_feedbacks.py` | 新增 `GET /admin/feedbacks/assignees`（注意注册在 `/{feedback_id}` 之前）、`PATCH /admin/feedbacks/{id}/assignee`；列表/详情返回 due_at + assignee_email（批量查避免 N+1） |
| `app/api/v1/feedbacks.py` | 提交反馈响应返回 `due_at` |

### 前端

| 文件 | 改动 |
|---|---|
| `components/feedback/FeedbackForm.tsx` | 类型按钮文案「问题反馈/意见建议」；选中类型显示承诺时限；成功页显示预计回复日期 + 节假日提示 |
| `components/feedback/FloatingFeedbackWidget.tsx` | 入口文案更新 |
| `lib/api/feedback.ts` | `Feedback.due_at`；`NotificationType` 加 `feedback_overdue` |
| `lib/api/admin.ts` | `AdminFeedbackItem` 加 due_at/assignee 字段；新增 `fetchAdminFeedbackAssignees` / `assignAdminFeedback` |
| `app/(main)/admin/feedbacks/page.tsx` | 筛选项文案；每行显示类型标签、处理人、截止时间、红色「已超时」标签 |
| `app/(main)/admin/feedbacks/[id]/page.tsx` | 承诺截止时间展示；处理人下拉指派；「已超时」标签 |

### 测试

`test/backend/test_feedback_service.py` 新增 5 个用例：

- `test_calc_due_at_skips_weekends`：周六/周五提交跨周末计算正确
- `test_create_feedback_sets_due_at`：due_at 落库 + auto_ack 文案
- `test_admin_update_assignee`：指派/越权指派/不存在用户/清除/不存在反馈
- `test_list_assignees`
- `test_overdue_scan_notify_and_idempotent`：过期未完结才提醒、done/未到期/存量 NULL 不提醒、当天幂等

## 注意点

- **SQLite 迁移**：batch_alter_table 加列与加外键必须分两个 batch，否则报 CircularDependencyError；失败重跑前需检查列是否已部分落库。
- **时区**：`due_at` 按 UTC 存（与全项目一致，SQLite 读回为 naive，比较/展示时用 `as_utc()` 兜底）；工作日边界按北京时间（zoneinfo）。
- **幂等口径**：同一天（北京时间 0 点起）同一条反馈只提醒一次，以当天已存在 `feedback_overdue` 通知为准。
