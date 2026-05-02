# 管理员调试沙箱（Fork）

## 用途

从**正式激活码**做**完整克隆**到独立路径 `data/simple/sandboxes/{fork_id}/`：

- 整目录复制 `data/simple/reports/{report_id}/`（含 `record.json`、全部 `{step}__{thread}.json`、`rumination_progress.json` 等），**保留各 step 的 locked、selected_session_id、session_ids、锚点等**；仅改写 `report_id`、`activation_code`、`user_id` 与 fork 元数据，**不重置**源端的 `created_at` / `updated_at`。
- 合并 `data/simple/{源激活码 session_id}/` 下遗留的 `阶段__线程.json`（若消息多于 reports 内同名片段则覆盖），避免历史数据只写在激活目录时 Fork 丢对话。
- 整目录复制问卷目录到沙箱内新 `{session_id}/`（`basic_info`、`prior_context_*.txt` 等）。
- 沙箱激活时 **`ensure_report` 不再把新 `rec.session_id` 绑进 values**，避免污染已克隆的 `session_ids`。

生成以 **`SBX` 前缀**的新激活码，归属当前超级管理员。

- **禁止**从沙箱再次 Fork。
- **默认保留 15 天**（`sandbox_expires_at`），过期后接口拒绝访问；可调用清理接口删除数据。
- **审计**：`data/simple/sandbox_fork_audit.jsonl`（追加 JSON 行）。

## API（需超级管理员）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/admin/sandboxes` | 列表 |
| POST | `/api/v1/admin/sandboxes/fork` | body: `{ "source_activation_code": "..." }` |
| DELETE | `/api/v1/admin/sandboxes?activation_code=SBX...` | 删除沙箱目录与激活记录 |
| POST | `/api/v1/admin/sandboxes/purge-expired` | 清理所有已过期的沙箱 |

## 定时清理（可选）

对 `POST /api/v1/admin/sandboxes/purge-expired` 配置 cron（需携带管理员 JWT 或使用服务端脚本调用），例如每日一次。

## 前端

Admin 侧栏 **「调试沙箱 Fork」**：新建 Fork、列表、复制激活码、跳转 `/explore/activate?code=...`、删除、手动清理过期。

## 实现要点

- `ActivationRecord` 扩展字段：`is_sandbox`、`sandbox_root`、`fork_id`、`forked_from_code`、`sandbox_expires_at` 等。
- `get_effective_simple_root(rec)`：`simple_chat` / `simple_auth` / 问卷与 `ReportRegistry` 均按激活码解析存储根目录。
- **默认对话线程**：未传 `thread_id` 时，不能仅用 `rec.session_id`（那是问卷目录用 UUID）；后端会在 `record.json` 的 `session_ids` 中优先选用**已有对话文件且消息最多**的 thread，避免 Fork 新码后误开空线程。
- **激活码管理**：列表字段 `activation_type` 为 `normal` | `fork`，并支持按类型筛选；Fork 行展示紫色 **Fork** 标签。
