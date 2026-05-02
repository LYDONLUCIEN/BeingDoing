# Simple 模式数据存储与 Thread 概念说明

> 本文档说明 `data/simple` 目录下的存储逻辑、Thread（线程）概念，及前后端数据流，便于团队概念对齐。

## 一、核心概念

### 1. Report（报告）

- **定义**：一次完整的职业探索流程，由「激活码 + 用户」唯一确定。
- **标识**：`report_id`（UUID）
- **存储**：`data/simple/reports/{report_id}/record.json`

### 2. Thread（线程 / 对话）

- **定义**：某个探索维度（phase）下的一条**独立对话线**。用户可在同一维度下开多条对话（例如「价值观」下最多 5 条），每条对话即一个 thread。
- **标识**：`thread_id`，格式如 `t_{timestamp}_{random}`，例如 `t_1773119248061_4oxrs0r`
- **与 phase 关系**：每个 phase（values/strengths/interests/purpose/rumination）有各自的 thread 列表，互不共享
- **后端术语**：在 record.json 和文件路径中称为 `session_id`，与前端 `thread_id` 为同一概念

### 3. Phase（阶段 / 维度）

- **定义**：探索流程的 5 个阶段
- **值**：`values` | `strengths` | `interests` | `purpose` | `rumination`

---

## 二、目录结构

### 当前标准结构（reports/）

```
data/simple/
├── activations.json          # 激活码索引
├── activations_recycle_bin.json
├── reports/
│   └── {report_id}/
│       ├── record.json       # 报告元信息 + 各 phase 的 thread 列表
│       ├── values__{thread_id}.json
│       ├── strengths__{thread_id}.json
│       ├── interests__{thread_id}.json
│       ├── purpose__{thread_id}.json
│       ├── rumination__{thread_id}.json
│       └── rumination_progress.json
└── sandboxes/                # 沙箱 fork 使用
```

### record.json 结构

```json
{
  "report_id": "uuid",
  "activation_code": "XXX",
  "user_id": "user-uuid",
  "created_at": "...",
  "updated_at": "...",
  "status": "in_progress",
  "steps": {
    "values": {
      "step_id": "values",
      "selected_session_id": "t_xxx",  // 用户确认完成的那条
      "locked": false,
      "session_ids": ["t_xxx", "t_yyy"],  // 该 phase 下所有 thread
      "updated_at": "..."
    },
    "strengths": { ... },
    ...
  }
}
```

- `session_ids`：该 phase 下所有 thread 的 id 列表（即前端的 threads 列表）
- `selected_session_id`：用户点击「确认没有问题」后选定的 thread

### 对话文件 `{phase}__{thread_id}.json`

```json
{
  "session_id": "report_id",
  "category": "values__t_1773119248061_4oxrs0r",
  "messages": [ ... ],
  "metadata": {
    "created_at": "...",
    "updated_at": "...",
    "thread_completed": false,
    "dimension_conclusion": { ... }
  }
}
```

---

## 三、数据流（后端为数据源）

### 1. 线程列表加载

1. 前端进入 chat 页 → 调用 `GET /api/v1/simple-chat/threads?activation_code=X&phase=Y`
2. 后端从 `record.json` 的 `steps[phase].session_ids` 读取 thread 列表
3. 对每个 thread_id 读取对应 `{phase}__{thread_id}.json` 的 metadata，补齐 title、status、createdAt 等
4. 返回 `{ threads: [...] }`
5. **跨设备 / 换浏览器**：只要激活码 + 用户匹配，就能从后端拿到完整列表

### 2. 消息加载

1. 用户选中某 thread → 调用 `GET /api/v1/simple-chat/history?activation_code=X&phase=Y&thread_id=Z`
2. 后端读取 `reports/{report_id}/{phase}__{thread_id}.json` 的 messages
3. 返回 `{ messages: [...], metadata: {...} }`

### 3. 新建对话

1. 用户点击新建 → 前端生成 `thread_id`，调用 `POST /api/v1/simple-chat/init` 传入 `thread_id`
2. 后端 `_resolve_report_context` 会调用 `registry.bind_session`，把 `thread_id` 加入 `session_ids`
3. 后端写入首条 assistant 消息到 `{phase}__{thread_id}.json`
4. 下次 `GET /threads` 会返回该新 thread

### 4. localStorage 角色（仅缓存）

- `explore_threads_{code}`：可作本地缓存，**不再是主数据源**
- `explore_active_thread_{code}`：记录用户当前选中的 thread，用于同设备内的 UX 持久化
- 换设备后，以后端返回为准

---

## 四、 legacy 结构与迁移

### 旧版 flat 结构

部分历史数据可能在：

```
data/simple/{activation_session_id}/
├── basic_info.json
├── values__t_xxx.json
├── strengths__t_yyy.json
└── ...
```

- `{activation_session_id}` 来自 activations 的 `session_id`
- 与 reports 结构不同，需通过迁移脚本合并到 `reports/{report_id}/`

### 迁移

运行 `scripts/migrate_simple_to_report_dirs.py --apply` 可将旧结构迁移到 reports 布局。详见脚本说明。

---

## 五、概念对照表

| 前端 | 后端存储 | 说明 |
|------|----------|------|
| thread / thread_id | session_id（在 steps 与文件名中） | 同一条对话线 |
| threads 列表 | steps[phase].session_ids | 该 phase 下所有 thread |
| activeThreadId | - | 前端 UI 状态，可选存 localStorage |
| ChatThread | record + {phase}__{tid}.json | 需合并 record 的 session_ids 与文件的 metadata/messages |
| phase | step_id / phase | values, strengths, interests, purpose, rumination |

---

## 六、API 一览

| 接口 | 用途 |
|------|------|
| `GET /simple-chat/threads` | 拉取某 phase 的线程列表（后端主数据源） |
| `GET /simple-chat/history` | 拉取某 thread 的消息历史 |
| `POST /simple-chat/init` | 新建 thread 并写首条消息 |
| `POST /simple-chat/message/stream` | 流式对话，写入当前 thread |
| `POST /simple-chat/thread/complete` | 标记 thread 完成，更新 selected_session_id |
