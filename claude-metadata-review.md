# Metadata 与数据一致性审查报告

> 审查日期：2026-04-05
> 范围：全项目数据存储、metadata 字段、前后端同步、admin/sandbox 数据流

---

## 一、数据存储全景图

```
项目根目录/
├── data/
│   ├── simple/                          # 生产环境数据
│   │   ├── activations.json             # 所有激活码记录
│   │   ├── activations_recycle_bin.json  # 软删除的激活码
│   │   └── reports/
│   │       └── {report_id}/
│   │           ├── record.json          # 报告元数据 + 步骤进度
│   │           ├── values__{session_id}.json    # 对话消息
│   │           ├── strengths__{session_id}.json
│   │           ├── interests__{session_id}.json
│   │           ├── purpose__{session_id}.json
│   │           ├── rumination__{session_id}.json
│   │           ├── rumination_progress.json     # rumination 筛选进度
│   │           └── prior_context_{phase}.txt    # 前序阶段结论
│   │
│   ├── test/simple/                     # 测试/调试环境数据
│   │   ├── activations.json             # SBX/ADM 前缀的激活码
│   │   ├── sandboxes/
│   │   │   └── {fork_id}/              # 沙箱 fork 数据
│   │   │       ├── reports/             # 从生产环境复制
│   │   │       └── {session_id}/        # 问卷/prior_context
│   │   ├── admin_prompt_lab/
│   │   │   ├── profiles.json            # 提示词实验室配置
│   │   │   └── activation_bindings.json # 激活码→配置绑定
│   │   └── sandbox_fork_audit.jsonl     # fork 审计日志
│   │
│   ├── user/                            # 用户级数据
│   │   └── {user_id}/
│   │       └── basic_info.json          # 问卷数据
│   │
│   └── admin_mock/                      # 管理员模拟数据模板
│       ├── record_template.json
│       └── prior_context/
│           └── prior_context_{phase}.txt
│
└── 前端 localStorage
    ├── explore_session_{code}            # 会话状态
    ├── explore_threads_{code}            # 线程列表+消息缓存
    ├── explore_active_thread_{code}      # 当前活跃线程
    ├── explore_last_code                 # 最近使用的激活码
    ├── rumination_step_boundary_{code}_{tid}  # rumination 步骤边界
    ├── token                             # JWT token
    └── session-storage                   # Zustand 持久化
```

---

## 二、对话文件 metadata 字段审查

### 2.1 新旧字段对照

对话文件 `{phase}__{session_id}.json` 的 `metadata` 中存在新旧两套结论状态字段：

| 新字段 (当前使用) | 旧字段 (兼容) | 类型 | 说明 |
|-------------------|--------------|------|------|
| `conclusion_state` | `pending_status` | string | none/pending/confirmed/rejected |
| `conclusion_draft` | `pending_conclusion` | dict/null | 待确认草案 |
| `conclusion_final` | `dimension_conclusion` | dict/null | 最终结论 |
| `conclusion_feedback` | `pending_last_rejected.feedback` | string | 否定反馈 |

### 2.2 代码访问路径分析

**读取路径**：所有读取都经过 `_read_conclusion_meta()` 兼容层
- simple_chat.py 中 7 处调用 `_read_conclusion_meta(meta)`
- 该函数优先读新字段，新字段为空时回退到旧字段
- 无任何代码绕过此函数直接读取旧字段

**写入路径**：所有写入都经过 `_build_conclusion_meta_update()` 兼容层
- simple_chat.py 中 7 处调用此函数
- 当前同时写入新旧两套字段（双写）

**前端读取**：
- `page.tsx` 读取 `meta.dimension_conclusion`（旧字段名）用于显示结论卡
- 该字段由后端 API 响应中的 `metadata.dimension_conclusion` 提供
- 后端通过 `_build_conclusion_meta_update()` 确保该字段始终被填充

**Sandbox Fork**：
- `shutil.copytree()` 原样复制所有文件，包含旧格式 metadata
- 复制后不做任何格式转换

### 2.3 结论：可以安全删除旧字段

**前提条件**：
1. 运行迁移脚本将所有历史数据中的旧字段转换为新字段
2. `_read_conclusion_meta()` 保留旧字段读取兼容（处理未迁移的边缘数据）
3. `_build_conclusion_meta_update()` 停止写入旧字段
4. 前端改为读取 `conclusion_final` 替代 `dimension_conclusion`

---

## 三、数据访问路径与一致性风险

### 3.1 Admin 入口矩阵

| 入口 | 数据操作 | 风险 |
|------|----------|------|
| `POST /admin/sandboxes/fork` | 复制生产数据到沙箱 | 旧格式 metadata 被原样复制 |
| `POST /admin/conversations/apply-mock-to-activation` | 应用模拟数据 | mock 模板可能含旧格式 |
| `POST /admin/conversations/jump-to-rumination` | 跳步到 rumination | 直接修改 record.json |
| `POST /admin/conversations/clone` | 克隆对话 | 原样复制，无格式转换 |
| `POST /admin/prompt-lab/bindings` | 绑定提示词配置 | 仅影响 system prompt，不影响 metadata |
| `DELETE /admin/sandboxes` | 删除沙箱 | 清理数据，无一致性风险 |

### 3.2 前后端数据不一致场景

| 场景 | 原因 | 影响 |
|------|------|------|
| Admin fork 后前端未刷新 | localStorage 缓存旧线程数据 | 前端显示旧对话，后端已是 fork 数据 |
| 用户在两个设备登录 | localStorage 各自独立 | 线程列表不同步 |
| Admin jump-to-rumination | 后端直接修改 record.json | 前端 unlockedPhases 未更新 |
| 网络断开后恢复 | 前端 localStorage 有离线消息 | 后端无此消息 |
| Admin 删除线程 | 后端删除文件 | 前端 localStorage 仍有该线程 |

### 3.3 Report Registry 跨环境一致性

```
get_effective_simple_root(rec) 路径选择逻辑：
├── rec.workspace_kind == "fork"
│   └── data/test/simple/sandboxes/{fork_id}/
├── rec.workspace_kind == "resident"
│   └── data/test/simple/
├── rec.is_sandbox == True (旧沙箱)
│   └── data/test/simple/sandboxes/{sandbox_root}/
└── 默认
    └── data/simple/
```

**风险**：不同 workspace_kind 的激活码指向不同存储根，但 ReportRegistry 实例化时只接收一个 base_dir。如果激活码的 workspace_kind 被错误设置，会读取错误的数据目录。

---

## 四、迁移计划

### 4.1 旧 metadata 字段迁移

**迁移脚本**：`scripts/migrate_metadata_fields.py`

**执行步骤**：
1. 备份 `data/` 目录
2. 扫描所有 `{phase}__{session_id}.json` 文件
3. 对每个文件的 metadata：
   - 若有旧字段但无新字段 → 写入新字段
   - 若新旧都有 → 保留新字段，删除旧字段
   - 若只有新字段 → 无需操作
4. 删除旧字段
5. 输出迁移报告

**影响范围**：
- `data/simple/reports/` 下所有对话文件
- `data/test/simple/sandboxes/` 下所有对话文件
- `data/admin_mock/` 下的模板文件

### 4.2 前端同步策略

**策略：后端优先，localStorage 仅作缓存**

```
进入阶段页面
    │
    ├─ 1. GET /simple-chat/threads (后端)
    │     ├─ 成功 → 用后端数据覆盖 localStorage
    │     └─ 失败 → 降级使用 localStorage
    │
    ├─ 2. 对每个线程 GET /simple-chat/history
    │     ├─ 成功 → 用后端消息覆盖 localStorage
    │     └─ 失败 → 使用 localStorage 缓存
    │
    └─ 3. 后续操作
          ├─ 发送消息 → 后端成功后更新 localStorage
          ├─ 创建线程 → 后端成功后更新 localStorage
          └─ 删除线程 → 后端成功后从 localStorage 移除
```

**关键变更**：
- 前端不再从 localStorage 初始化线程列表
- 每次进入页面强制从后端拉取
- localStorage 仅用于离线降级和减少加载闪烁

### 4.3 Admin Debug 端点

新增 `GET /admin/activation-data-inspect` 端点：
- 输入：activation_code
- 输出：该激活码关联的所有数据位置、文件列表、metadata 摘要

---

## 五、执行记录

### Phase 1: 数据安全 ✅ 已完成

- [x] 备份 `data/` 目录 → `data_backup_20260405_203535/`
- [x] 编写并运行 metadata 迁移脚本 → `scripts/migrate_metadata_fields.py`，23 个文件已迁移
- [x] 添加 admin 数据检查端点 → `GET /admin/activation-data-inspect`
- [x] 验证迁移结果 → 重新扫描 0 个文件需要迁移

### Phase 2: 代码清理 ✅ 已完成

- [x] `_build_conclusion_meta_update()` 停止写入旧字段 → 已删除 `pending_status`、`pending_conclusion`、`dimension_conclusion`、`pending_last_rejected` 的写入
- [x] `_read_conclusion_meta()` 保留旧字段读取兼容 → 防御性保留，处理未迁移的边缘数据
- [ ] 前端 API 响应中 `dimension_conclusion` 字段名保持不变（API 契约，非 metadata 字段）
- [x] 更新测试 fixtures → `test_flow_3` 测试已修复
- [ ] 更新 admin_mock 模板数据 → 待后续确认

### Phase 3: 前端同步 ✅ 已完成

- [x] 实现后端优先同步策略 → 已有机制（进入页面时 GET /threads → 覆盖 localStorage）
- [x] 添加缓存有效期机制 → `isCacheStale()` 函数，5 分钟过期
- [x] `markSynced()` — 每次后端同步成功后记录时间戳
- [x] 缓存过期时不使用 localStorage 降级 → 避免展示过期数据
- [x] 添加 `clearThreadCache()` — 供激活码切换/登出时清理
- [x] TypeScript 编译 + ESLint 通过

### Phase 4: Sandbox Fork 加固（待后续）

- [ ] Fork 时对 metadata 做格式标准化
- [ ] 添加 fork 后数据校验

---

## 六、迁移脚本使用说明

### 脚本位置
`src/backend/scripts/migrate_metadata_fields.py`

### 用法
```bash
# 预览模式（不修改文件）
python src/backend/scripts/migrate_metadata_fields.py --dry-run

# 执行迁移
python src/backend/scripts/migrate_metadata_fields.py

# 指定扫描目录
python src/backend/scripts/migrate_metadata_fields.py --dirs data/simple/reports data/test/simple
```

### Admin 数据检查端点
```
GET /api/v1/admin/activation-data-inspect?activation_code=CODE
```
返回该激活码的：
- 激活码基本信息（状态、归属、workspace_kind）
- 存储根路径
- 报告结构（步骤锁定状态、会话列表、锚点）
- 所有关联文件（名称、大小、消息数、metadata 摘要）
- 用户级数据文件
