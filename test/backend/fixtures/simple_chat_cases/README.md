# Simple Chat Replay 测试验收说明

本文档用于说明如何使用 `replay_simple_chat.py` 做单条/批量验收，以及不同模式是否会改动原始数据。

## 1. 相关文件

- 回放脚本：`src/backend/scripts/replay_simple_chat.py`
- 回放测试：`test/backend/test_simple_chat_replay_cases.py`
- 单条示例：`test/backend/fixtures/simple_chat_cases/single_values_continue.json`
- 批量示例：`test/backend/fixtures/simple_chat_cases/batch_basic.json`
- 假数据 report：`test/backend/fixtures/simple_chat_reports/mock_values_pending/`

## 2. 三种数据模式（最重要）

### A. 假数据模式（推荐日常调试）

通过 `--seed-report-dir` 或 `seed_fixture.report_dir` 运行。

- 数据来源：`test/backend/fixtures/simple_chat_reports/...`
- 写入位置：`data/test/simple/replay_runs/run_xxx/`（临时目录）
- 是否改动真实数据：**不会**
- 适用：改 `simple_chat.py` 逻辑、调 prompt、做稳定回归

### B. 真实激活码直连模式（谨慎）

通过 `--activation-code` 运行。

- 数据来源：你指定的真实激活码
- 写入位置：真实 `data/simple/...`
- 是否改动真实数据：**会**（会新增消息、可能更新 metadata）
- 适用：线上等价行为核验（建议仅在测试环境）

### C. 真实数据 + Fork 沙箱模式（推荐真实调试）

通过 `--fork-from SOURCE_CODE` 运行。

- 数据来源：从真实激活码 fork
- 写入位置：`data/test/simple/sandboxes/{fork_id}/...`
- 是否改动源激活码数据：**不会**
- 是否改动沙箱数据：**会**（这是预期）
- 适用：用真实上下文调试，但隔离风险

## 3. 快速开始

> 建议在项目根目录执行。

### 3.1 单条回放（假数据，安全）

```bash
python src/backend/scripts/replay_simple_chat.py \
  --seed-report-dir test/backend/fixtures/simple_chat_reports/mock_values_pending \
  --phase values \
  --thread-id t_mock_pending_001 \
  --message "继续聊聊" \
  --mock-stream-reply "收到，我们继续。[STATE_JSON]{\"state\":\"continue\",\"draft\":null}[/STATE_JSON]"
```

### 3.2 批量回放（假数据，安全）

```bash
python src/backend/scripts/replay_simple_chat.py \
  --cases-file test/backend/fixtures/simple_chat_cases/batch_basic.json \
  --output-json data/test/simple/replay_runs/last_batch_result.json
```

### 3.3 真实激活码（会改真实数据）

```bash
python src/backend/scripts/replay_simple_chat.py \
  --activation-code YOUR_CODE \
  --phase values \
  --thread-id t_123 \
  --message "我补充一下"
```

### 3.4 真实数据 Fork 后回放（推荐）

```bash
python src/backend/scripts/replay_simple_chat.py \
  --fork-from SOURCE_CODE \
  --phase values \
  --thread-id t_123 \
  --message "我补充一下" \
  --user-id admin-001 \
  --user-email admin@example.com
```

## 4. 关键参数说明

### 4.1 基础参数

- `--activation-code`：直接使用该激活码（会写入对应数据）
- `--fork-from`：先从源激活码 Fork 沙箱，再执行回放
- `--phase`：阶段（`values|strengths|interests|purpose|rumination`）
- `--thread-id`：线程 ID
- `--message`：发送消息内容
- `--name`：本次 case 名称（用于输出）
- `--output-json`：保存总结结果（总数、失败、每 case 结果）

### 4.2 用例/批量参数

- `--cases-file`：批量用例 JSON 文件路径（相对项目根目录）
- `--seed-report-dir`：从 fixture report 目录 seed 临时数据
- `--seed-ttl-minutes`：seed 生成激活码有效期（默认 180）

### 4.3 Prompt 相关参数

- `--prompt-profile-id`：复用 Prompt Lab 的 profile 绑定
- `--prompt-version-id`：先切换 profile 当前版本，再绑定
- `--prompt-template-file`：一次性模板覆盖（仅本次回放生效）
- `--extra-goal-hint`：附加目标提示

> 优先建议：
> - 稳定回归：`prompt-profile-id/version-id`
> - 临时调试：`prompt-template-file`

### 4.4 Mock 相关参数（用于稳定回归）

- `--mock-stream-reply`
- `--mock-chat-reply`
- `--mock-pending-state`
- `--mock-pending-content`
- `--mock-conclusion-summary`
- `--mock-conclusion-keywords`（逗号分隔）

## 5. 用例文件格式（cases-file）

支持两种格式：

1) 顶层对象，包含 `cases` 数组  
2) 顶层直接是数组

单个 case 常用字段示例：

```json
{
  "name": "batch_continue",
  "seed_fixture": {
    "report_dir": "test/backend/fixtures/simple_chat_reports/mock_values_pending",
    "ttl_minutes": 180
  },
  "phase": "values",
  "thread_id": "t_mock_pending_001",
  "message": "继续聊聊",
  "mock": {
    "stream_reply": "收到，我们继续。[STATE_JSON]{\"state\":\"continue\",\"draft\":null}[/STATE_JSON]"
  }
}
```

## 6. 验收建议（推荐顺序）

1. 先跑假数据单条（确认命令与环境正常）  
2. 再跑假数据批量（确认逻辑回归稳定）  
3. 需要真实上下文时，优先 `--fork-from` 模式  
4. 最后再用 `--activation-code` 对真实数据做小范围核验

## 7. 验收关注项（建议勾选）

- SSE 正常结束（`done=true`）
- 不泄漏 `[STATE_JSON]` 到可见 chunk
- `history.metadata` 状态符合预期（如 `thread_completed`、`conclusion_state`）
- confirmed 分支能写入 `conclusion_card`
- 拒绝/继续分支能正确更新 pending 状态

## 8. pytest 回归

```bash
pytest test/backend/test_simple_chat_replay_cases.py -v
```

说明：
- 该测试默认使用 fixture 假数据 + monkeypatch，不依赖前端。
- 与脚本一样，默认不会写真实 report（写到 pytest 临时目录）。

## 9. 常见问题

- 报 `ModuleNotFoundError`：先确认后端依赖已安装（venv 激活后执行）。
- 报认证/权限错误：脚本内部已覆盖 `get_current_user`，通常是路径或配置错误。
- 想看详细结果：加 `--output-json`，并查看 `results` 字段。

## 10. 目录隔离迁移（方案 A）

当你需要把 `data/simple` 下的调试数据迁到 `data/test/simple`，并在确认后清理旧数据时：

### 10.1 迁移（默认 dry-run）

```bash
python src/backend/scripts/migrate_simple_debug_data.py
```

执行迁移：

```bash
python src/backend/scripts/migrate_simple_debug_data.py --apply
```

会生成 manifest 到 `data/test/simple/migration_manifests/`。

### 10.2 清理（默认 dry-run）

```bash
python src/backend/scripts/cleanup_simple_debug_data.py
```

执行清理（双确认）：

```bash
python src/backend/scripts/cleanup_simple_debug_data.py \
  --manifest data/test/simple/migration_manifests/<manifest>.json \
  --apply \
  --confirm-manifest-id <manifest_id> \
  --remove-directories
```

说明：
- 只会清理已迁移的调试激活码索引项。
- 目录清理不是直接删除，而是移动到 `data/backups/simple-debug-cleanup-<ts>/`。

