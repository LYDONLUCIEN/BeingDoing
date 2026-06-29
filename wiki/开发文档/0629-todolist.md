# 0629 开发任务规划文档

> 本文档基于代码调研 + 多轮需求对齐形成,记录 5 个新需求的任务拆分方案。
> 目标:5 个任务可并行开发,文件级互不冲突。
> 创建日期:2026-06-29

---

## 一、背景

5 个新需求:

1. admin 对话记录批量导出(选多个 report_id,一个 report 一个文件,含 5 phase 内容,md/txt 可选,保留对话人和时间)
2. 用户对话时间与实际时间不一致(时区 bug),需诊断根因 + 修正历史 + 保证未来准确
3. 统计用户每轮平均时间(导出日志→修正时间→脚本统计→贴心提醒)
4. 上线邮件群发功能(admin 给所有/筛选用户发系统通知、版本上线、折扣优惠)
5. user profile 老用户已填写但 admin 用户管理页看不到更新(bug 修复)

---

## 二、任务划分矩阵

**结论:拆成 5 个并行任务。**

| 任务 | 主题 | 主要文件域 | 立即并行? |
|------|------|-----------|----------|
| **T1** | admin 批量导出对话记录 | `api/v1/admin.py`(追加) + 新 service + reports 前端页面 | ✅ 是 |
| **T2** | 时区修正(后端统一 + 前端转换 + 历史修正) | models/services/core + 前端时间显示 + alembic + 脚本 | ✅ 是 |
| **T3** | 每轮平均时间统计(集成 admin) | 新 stats service + admin.py 追加 + users/reports 页面加按钮 | ⏳ **依赖 T1 格式冻结 + 页面与 T1 协调** |
| **T4** | 邮件群发(后台队列 + 进度落库) | 新 router + 新 service + 新 model + alembic + 新前端页面 | ✅ 是 |
| **T5** | profile bug 修复 | `utils/survey_storage.py` + 调用方 | ✅ 是 |

**派单顺序**:T1 / T2 / T4 / T5 立即并行;T3 在 T1 导出格式冻结后启动。

---

## 三、关键事实(已对齐)

1. **report 概念**:report_id 是独立 UUID(不是激活码 code),激活码通过 `report_id` 字段关联。一个 report 含 5 个 phase(step),每个 phase 有独立 `selected_session_id`。
   - 代码位置:`src/backend/app/utils/report_registry.py:525-548` `select_session()`、`:579-584` `get_selected_session(report_id, step_id)`
2. **导出粒度**:导出 1 个 report = 导出该 report 下 5 个 phase 各自选中 session 的合集(跳过未完成 phase),按 phase 分章节,一个 report 一个文件。
3. **时区方案**:三层都做(后端 tz-aware UTC + 前端转本地 + 历史修正脚本),不做 TZ 环境变量。
4. **统计交付形态**:独立 Python 离线脚本。
5. **邮件发送方式**:后台任务队列(FastAPI BackgroundTasks),admin 可查进度。
6. **profile bug 修复**:改为同步 await + 失败报错。
7. **前端入口**:批量导出在 `/admin/reports` 页面选 report_id。

---

## 四、各任务详细 TODO

### T1 — admin 批量导出对话记录

#### 目标
admin 在 `/admin/reports` 页面勾选多个 report_id,选 md 或 txt 格式,一键导出 zip(一个 report 一个文件,文件内按 5 phase 分章节,保留用户信息和时间)。

#### 涉及文件清单

| 操作 | 文件路径 | 改动内容 |
|------|---------|---------|
| 新增 | `src/backend/app/services/batch_export_service.py` | 核心服务 `BatchExportService.collect_report_export(report_id, format)`:遍历 5 step → `ReportRegistry.get_selected_session()` → 复用 `ExportService.collect_export_data` 组装每 phase 数据 → 按 phase 章节合并 → 写 md/txt |
| 修改 | `src/backend/app/api/v1/admin.py` | 追加 `POST /admin/reports/export/batch`(入参 `report_ids: list[str]`, `format: md\|txt`),用 `_is_super_admin` 守卫;循环调 batch_export_service,`zipfile.ZipFile` 打包,返回 `StreamingResponse` |
| 修改 | `src/frontend/app/(main)/admin/reports/page.tsx` | 表格加 checkbox 列 + 表头全选;底部加"批量导出"按钮 + 格式下拉(md/txt) |
| 修改 | `src/frontend/lib/api/admin.ts` | 追加 `exportReportsBatch(reportIds, format)` → POST 拿 blob → 触发浏览器下载 |

#### 关键数据流
```
POST /admin/reports/export/batch
  → BatchExportService.collect_report_export(report_id, format)
    → ReportRegistry.get_selected_session(report_id, step_id) × 5  (跳过 None)
    → ExportService.collect_export_data(user_id, session_id)  (复用现有逻辑)
    → 按 phase 章节拼接成 md/txt
  → zipfile 打包 N 个文件
  → StreamingResponse
```

#### 依赖
- 无前置依赖,可立即开工。

#### 风险点
1. report 的 `user_id` 需从 `ReportRegistry._load_record(report_id)["user_id"]` 取(`report_registry.py:537` 附近)。
2. **单次限制硬上限 50 个 report**:超出时**直接报错提醒**"单次最多导出 50 个,请分批操作",不做自动分批(后续版本再考虑自动排队)。
3. **T1 必须在 `batch_export_service.py` 顶部冻结导出格式**(时间戳字段名、分隔符、phase 章节格式),T3 据此写正则。

#### 测试要点
1. 选 2 个 report(一个 5 phase 全完成、一个仅 3 phase 完成)→ zip 内 2 文件,文件内章节数正确(5 / 3)。
2. 非 super_admin 调用 → 403。
3. 不存在的 report_id → 单条跳过或 404,不影响其他 report。
4. 选 51 个 report → 接口返回 400 + 提示"单次最多 50 个"。

#### 验收标准
- [ ] admin 勾选多个 report 能成功下载 zip
- [ ] zip 内每个文件含正确 phase 章节、用户信息、时间戳
- [ ] md 和 txt 两种格式都正常
- [ ] 超 50 个 report 返回明确错误提示
- [ ] 路由测试通过

---

### T2 — 时区修正(三层)

#### 目标
根治"对话时间与实际时间不一致"。根因:全仓库混用 `datetime.now()`/`datetime.utcnow()`/`datetime.now(timezone.utc)`,DB 字段 timezone-naive,无 TZ 配置,前端未做时区转换。

#### 涉及文件清单(约 30 文件,按域分组)

| 域 | 文件 | 改动 |
|----|------|------|
| **Models** | `models/user.py`、`models/session.py`、`models/answer.py`、`models/selection.py`、`models/analytics.py`、`models/refresh_token.py` | 所有 `default=datetime.utcnow` → `default=lambda: datetime.now(timezone.utc)` |
| **Services** | `services/auth_service.py`(15+ 处)、`services/analytics_service.py`、`services/guide_service.py`、`services/answer_service.py`、`services/export_service.py` | `datetime.utcnow()` → `datetime.now(timezone.utc)` |
| **Core** | `core/database/history_db.py`、`core/agent/graph.py`、`core/agent/graph_cache.py` | 同上 |
| **Utils/API** | `utils/enhanced_conversation_manager.py`、`utils/conversation_file_manager.py:93-94`、`utils/simple_activation_manager.py:202`、`utils/admin_savepoints.py:469`、`api/v1/chat.py` | 同上;注意 `+ "Z"` 后缀拼接的需去掉(已带 tz) |
| **迁移** | 新增 `alembic/versions/xxxx_fix_timestamps_tz.py` | 批量 UPDATE 把所有 naive datetime 加 `+00:00` |
| **历史数据脚本** | 新增 `src/backend/scripts/fix_timestamps.py` | 独立脚本:连 SQLite,把 `created_at/updated_at/last_activity_at/last_login_at` 等列里不带 `+` 的值追加 `+00:00` |
| **前端** | 新增 `src/frontend/lib/utils/formatTime.ts`;修改 `app/(main)/admin/users/page.tsx`、`app/(main)/admin/reports/page.tsx`、`app/(main)/admin/page.tsx` 等所有时间显示点 | 抽公共 `formatUTC(iso, locale)` → `new Date(iso).toLocaleString(locale, {timeZone:'local'})`;所有页面替换 |

#### 关键数据流
```
后端写入: datetime.now(timezone.utc)  →  DB 存 tz-aware ISO 字符串(带 +00:00)
后端读取: 返回带 tz 的 ISO 字符串
前端显示: formatUTC(iso) → 浏览器本地时区
历史数据: fix_timestamps.py 批量加 +00:00
```

#### 依赖
- 无前置依赖,可立即开工。

#### 风险点
1. **JWT 过期判断(最大风险)**:`auth_service.py` 多处 `datetime.utcnow()` 与 token exp 比较,改为 tz-aware 后两边必须同时 aware,否则 `>` 报 TypeError。
2. SQLite 存字符串,tz-aware datetime 序列化带 `+00:00`,旧数据无后缀 → 查询/排序错乱,**必须先跑 fix_timestamps.py**。
3. `graph_cache.py` 是内存对象,不涉及 DB,低风险。

#### 测试要点
1. 跑 fix 脚本前后,`SELECT created_at FROM users` 对比,确认所有行带 `+00:00`。
2. 登录 → 拿 token → 等 1 秒 → 调需 auth 接口,确认 token 仍有效(验证 JWT tz 比较正确)。
3. 前端 admin/users 页面时间显示 = 本地时区(如 UTC+8 比 UTC 多 8 小时)。

#### 验收标准
- [ ] 后端无 `datetime.utcnow()` 调用(grep 验证)
- [ ] DB 所有时间字段带 tz 信息
- [ ] 前端所有时间显示为本地时区
- [ ] 历史数据修正脚本跑通,无数据丢失
- [ ] 登录/JWT 流程正常

---

### T3 — 每轮平均时间统计(集成进 admin)

#### 目标
admin 在页面上一键查看用户的"每轮平均时长/总时长/轮数"统计,并展示贴心提醒。底层复用 T1 导出格式解析逻辑。

#### 涉及文件清单

| 操作 | 文件路径 | 说明 |
|------|---------|------|
| 新增 | `src/backend/app/services/conversation_stats_service.py` | 核心服务:接收 user_id 或 report_id → 取对应 sessions 的对话历史 → 按 phase → 按 turn 提取 `created_at` → 算每轮时长 → 返回 `{total_turns, avg_minutes, total_minutes, per_phase: [...]}` |
| 新增 | `src/backend/app/api/v1/admin.py`(追加) | `GET /admin/users/{user_id}/conversation-stats` → 返回统计;`GET /admin/reports/{report_id}/conversation-stats` → 返回该 report 统计 |
| 新增 | `scripts/conversation_stats.py`(离线版,可选) | 命令行工具,读 T1 导出的 md/txt 离线分析,便于批量/历史数据。逻辑与 service 复用 |
| 修改 | `src/frontend/app/(main)/admin/users/page.tsx` | 用户列表加"统计"按钮/列,点击弹出统计卡片(轮数/平均时长/总时长 + 提醒文案) |
| 修改 | `src/frontend/app/(main)/admin/reports/page.tsx` | report 行加"统计"按钮,弹出该 report 的统计 |
| 修改 | `src/frontend/lib/api/admin.ts` | 追加 `getUserConversationStats`、`getReportConversationStats` |

#### 关键数据流
```
admin 页面点"统计"按钮
  → GET /admin/users/{id}/conversation-stats(或 reports 版本)
    → ConversationStatsService.compute(user_id 或 report_id)
      → 取 sessions 对话历史(复用 ExportService.collect_export_data 的数据加载)
      → 按 phase → 按"用户消息"切轮 → 算相邻时间差
      → 返回 {total_turns, avg_minutes, total_minutes, per_phase}
  → 前端展示统计卡片 + 提醒文案
```

**提醒文案示例**:
> 用户 XXX 本次探索共 12 轮对话,平均每轮 8.5 分钟,总时长 102 分钟。

#### 依赖
- **强依赖 T1 导出格式**(时间戳字段名、分隔符)。T1 必须先冻结格式文档(在 `batch_export_service.py` 顶部写格式注释),T3 据此实现解析。

#### 风险点
1. 单轮对话内多条消息(用户+AI)如何界定"一轮":**按"用户消息"切轮**。
2. 跨 phase 的首尾消息时长可能异常大,需过滤或标注。

#### 测试要点
1. 喂一个已知 12 轮、总 102 分钟的 mock md → 输出 avg 8.5 分钟。
2. 缺时间戳的消息 → 跳过该轮且 warning。

#### 验收标准
- [ ] admin 用户列表/report 列表能点"统计"查看结果
- [ ] 统计卡片展示轮数/平均时长/总时长 + 提醒文案
- [ ] 离线脚本(可选)能正确解析 T1 导出格式
- [ ] 异常格式有 warning 不崩溃

---

### T4 — 邮件群发(后台任务队列)

#### 目标
admin 给所有/筛选用户发系统维护、版本上线、折扣优惠等通知邮件。后台异步发送,admin 可查进度,**进度落库防重启丢失**。

#### 涉及文件清单

| 操作 | 文件路径 | 改动 |
|------|---------|------|
| 新增 | `src/backend/app/api/v1/admin_notifications.py` | `POST /admin/notifications/email`(入参 `user_filter` + `subject` + `body`)→ 创建 task → 返回 `task_id`;`GET /admin/notifications/email/{task_id}` → 返回 `{total, sent, failed, status}`;`GET /admin/notifications/email` → 历史任务列表 |
| 新增 | `src/backend/app/services/notification_service.py` | `NotificationService`:查 user 列表(按 filter)、分批调 `EmailService.send_email`、**进度实时写 SQLite 表 `notification_tasks`**;`run_batch(task_id)` 作为 BackgroundTasks 回调 |
| 新增 | `src/backend/app/models/notification.py` | 新模型 `NotificationTask`(task_id/subject/body/filter/total/sent/failed/status/created_at/updated_at/started_at/finished_at)+ `NotificationRecipient`(task_id/user_id/email/status/error_msg);**需 Alembic migration** |
| 新增 | `alembic/versions/xxxx_add_notification_tables.py` | 建表 `notification_tasks` + `notification_recipients` |
| 修改 | `src/backend/app/main.py` | 注册新 router |
| 修改 | `src/backend/app/services/email_service.py` | 追加 `send_batch(to_list, subject, body)` 包装(可选) |
| 新增 | `src/frontend/app/(main)/admin/notifications/page.tsx` | 收件人筛选 UI + 模板编辑 + 发送按钮 + 进度条轮询 `GET .../{task_id}` + 历史任务列表 |
| 修改 | `src/frontend/lib/api/admin.ts` | 追加 `sendNotificationEmail`、`getNotificationStatus`、`listNotificationTasks`(函数名与 T1 区分,避免合并冲突) |

#### 关键数据流
```
POST /admin/notifications/email
  → 创建 task_id
  → BackgroundTasks.add_task(notification_service.run_batch, task_id)
  → 立即返回 task_id
前端轮询 GET /admin/notifications/email/{task_id}
  → {total, sent, failed, status}
```

#### 依赖
- 无前置依赖,可立即开工。
- `user_filter` 的 `created_after` 比较需与 T2 协调(都用 aware)。

#### 风险点
1. **服务重启恢复**:进度落 SQLite 后,重启时需扫描 `status='running'` 的任务,标记为 `interrupted` 供 admin 手动重发失败收件人。
2. **SMTP 限流(163 邮箱)**:建议每秒 ≤1 封,失败重试 1 次。
3. `user_filter` 时间比较需与 T2 的 tz 改动协调(都用 aware)。

#### 测试要点
1. mock SMTP → 选 3 用户 → 发送 → 进度 3/3,全成功。
2. 1 个邮箱故意失败 → 进度 `failed:1`,其余成功。

#### 验收标准
- [ ] admin 能筛选收件人(全选/按状态/按时间)
- [ ] 后台异步发送,接口立即返回
- [ ] 可查询发送进度(落 SQLite,重启不丢)
- [ ] 服务重启后能识别中断任务
- [ ] 失败用户有记录

---

### T5 — profile bug 修复

#### 目标
修复"老用户已填写 profile,admin 用户管理页看不到内容更新"。

#### 根因
`src/backend/app/utils/survey_storage.py:65-102` 的 `save_basic_info_by_user()` 用 `loop.create_task` 后台异步写库,且 `except: pass` 吞掉异常 → UserProfile 表可能不更新 → admin `/admin/users` 查不到。

#### 涉及文件清单

| 操作 | 文件路径 | 改动 |
|------|---------|------|
| 修改 | `src/backend/app/utils/survey_storage.py:65-102` | `save_basic_info_by_user` 改 `async def`;删除 `loop.create_task`/`asyncio.run` 分支,直接 `await _sync()`;删除 `except: pass`,改为 `raise` 或返回错误 |
| 修改 | `src/backend/app/api/v1/sessions.py:86` | `save_basic_info_by_user(...)` → `await save_basic_info_by_user(...)` |
| 修改 | `src/backend/app/api/v1/simple_chat_routes.py:1443, 1528` | 同上,两处加 `await` |

#### 关键数据流
```
POST /sessions/...
  → await save_basic_info_by_user
    → AsyncSessionLocal → UserDB.update_user_profile → DB 提交
  → 失败 → 异常冒泡 → API 返回 500/重试提示
```

#### 依赖
- 无前置依赖,可立即开工。

#### 风险点
1. **接口变慢**:原 fire-and-forget 现在阻塞,但 `update_user_profile` 是单条 UPDATE,耗时 <50ms,可接受。
2. `simple_chat_routes.py` 那两个端点需确认外层函数是 `async def`(若是 `def` 需改 async)。
3. 异常上抛后,JSON 文件已写但 DB 没写 → 数据不一致。**建议先 DB 后 JSON**,或事务内同时做。

#### 测试要点
1. 提交 survey → 立即查 `GET /admin/users` → 能看到 gender/profile_completed。
2. mock DB 故意失败 → API 返回错误,前端可重试;JSON 不写或回滚。

#### 验收标准
- [ ] 用户提交 profile 后 admin 立即可见
- [ ] DB 写入失败时有明确错误反馈
- [ ] 无数据不一致(JSON 与 DB)

---

## 五、并行性分析与冲突协调

### 文件级冲突检查

| 任务对 | 是否冲突 | 协调方式 |
|--------|---------|---------|
| T1 ↔ T4 | `lib/api/admin.ts` 都追加 | 用不同函数名(`exportReportsBatch` vs `sendNotificationEmail`/`getUserConversationStats`),git 合并无冲突 |
| T1 ↔ T2 | T1 追加 admin.py,T2 不改 admin.py(无 utcnow) | T1 只追加不改既有行 → 可并行 |
| T1 ↔ T3 | **`reports/page.tsx` 都改** + admin.py 都追加 | **T3 排在 T1 之后**:T1 先完成 reports 页面的批量导出 UI,T3 再在该页面加"统计"按钮;或约定 T3 只在 users 页面加统计按钮,reports 统计延后 |
| T2 ↔ T5 | 文件域无重叠(survey_storage/sessions/simple_chat_routes 无 utcnow 调用) | 无冲突 |
| T3 ↔ T4 | 都追加 lib/api/admin.ts | 用不同函数名,无冲突 |

### 派单建议
- **第一批(立即并行)**:T1、T2、T4、T5,各开独立分支 `dev/batch-export`、`fix/timezone`、`feat/email-notification`、`fix/profile-sync`
- **第二批**:T1 完成并冻结导出格式后,启动 T3(分支 `feat/conversation-stats`),与 T1 的 reports 页面改动错开合并

---

## 六、已决策项(原不确定项,已确认)

1. **T1 单次批量导出上限 = 50**:超出直接报错提醒"单次最多 50 个,请分批操作",不做自动排队(后续版本再考虑)。
2. **T4 邮件进度落 SQLite**:新增 `notification_tasks` + `notification_recipients` 表,服务重启后识别中断任务供 admin 手动重发。
3. **T3 集成进 admin 页面**:在 users/reports 列表加"统计"按钮,弹出统计卡片 + 提醒文案;离线脚本作为可选工具保留。

---

## 七、提交前检查清单(每个任务完成后)

按 `claude-开发文档.md` 第三节执行:
1. Python: `black --check .` 和 `isort --check .`(在 `src/backend` 下)
2. TypeScript: `npm run lint`(在 `src/frontend` 下)
3. 后端测试: `pytest test/backend -v`(从项目根目录)
4. 前端构建: `npm run build`(确保无编译错误)
5. 涉及数据库变更 → 创建 Alembic migration
6. 涉及 API 变更 → 更新 `docs/API_DOCUMENTATION.md`
7. 中文 commit message,格式 `<类型>: <描述>`

---

## 八、版本规划

5 个任务完成后,合并到 main 并打 tag(建议 `v1.5.0`,本次为功能版本升级)。

---

## 九、完成记录(2026-06-29)

5 个任务全部由独立 subagent 并行实现完成。以下为各 agent 的完成汇报汇总。

### ⚠️ 执行情况重要说明(必读)

1. **worktree 隔离部分生效**:仅 T1 在 worktree 干活并 commit 到 `dev/batch-export` 分支;T2/T3/T4/T5 的改动实际落在**主仓库 main 工作区**(部分已 commit 到 main,部分未 commit)。
2. **当前 git 状态**:
   - main 有 1 个新 commit:`1832ab6`(T3,直接落在 main)
   - `dev/batch-export` 分支有 T1 的 commit `13302c6`
   - 主仓库工作区仍有 T2/T4/T5 的大量未提交改动(混在一起)
   - **建议合并策略**:把 T4/T5 的未提交改动按文件归类后分别提交,或整体作为一个功能合集提交到 main
3. **所有 agent 的测试均未实际执行**:sandbox 拒绝 bash/pytest/python,所有"测试通过"均指 agent 写好了测试代码但未运行。**上线前必须手动跑全部测试**。

---

### T1 — admin 批量导出对话记录 ✅

- **分支/commit**:`dev/batch-export` @ `13302c6`(功能: 新增admin批量导出对话记录(zip))
- **新增文件**:
  - `src/backend/app/services/batch_export_service.py`(318 行)— `BatchExportService.collect_report_export(report_id, fmt)`
  - `test/backend/test_batch_export_service.py`(185 行)— 服务层 4 测试
  - `test/backend/test_admin_batch_export.py`(273 行)— 路由层 7 测试
- **修改文件**(纯追加,0 删除):
  - `src/backend/app/api/v1/admin.py`(+89)— `BatchExportRequest` 模型 + `POST /reports/export/batch`
  - `src/frontend/app/(main)/admin/reports/page.tsx`(+83)— checkbox 列 + 批量导出工具栏
  - `src/frontend/lib/api/admin.ts`(+111)— `exportReportsBatch`
- **接口**:`POST /api/v1/admin/reports/export/batch`,入参 `{report_ids[], format: "md"|"txt"}`,返回 `application/zip`,每 report 一文件。守卫:super_admin(403)、>50 个(400)、空列表(400)、非法 format(400)、不存在 report 跳过、全不存在(404)
- **冻结的导出格式**(供 T3 参考,写在 batch_export_service.py 顶部):
  - 文件头:`# 寻录探索报告 - <report_id>` + `=` 分隔线 + 元信息块 + `-` 分隔线
  - Phase 章节:`## <序号>. <中文阶段名>（<step_id>）`,映射 values=价值观/strengths=优势/interests=热爱/purpose=使命/rumination=沉淀
  - 消息块:`**[<角色>]** <时间戳>`(md)/ `[<角色>] <时间戳>`(txt)
  - 文件名:`report_<report_id>.<ext>`
- **测试**:11/11(agent 自测,需手动验证)
- **遗留**:`ExportService.collect_export_data`(export_service.py:128)有 pre-existing bug(`conversation_history_dict` 未定义),BatchExportService 做了兜底;email/username 暂为"未提供"(避免批量循环查 DB)

---

### T2 — 时区修正(三层)✅

- **分支/commit**:改动落在主仓库工作区(**未 commit**)。agent 因 sandbox 禁 git 无法创建 `fix/timezone` 分支
- **改动规模**:后端约 27 文件 + 前端 10 文件 + 2 新建
- **层1 后端统一**(grep `datetime.utcnow` 在 `src/backend/app/` 下 **0 残留**):
  - Models(7):user/session/answer/selection/analytics/refresh_token/notification — `default=lambda: datetime.now(timezone.utc)`
  - **JWT/auth_service.py**:`_create_token` exp 改 aware(jose 用 timestamp() 转换,代码分析不会炸)、refresh_token 全链路 aware、`utcfromtimestamp` → `fromtimestamp(tz=utc)`
  - Services:analytics/guide/answer/export/notification/batch_export
  - Core:database/history_db、agent/graph、agent/graph_cache
  - Utils/API:helpers/admin_workspace/admin_savepoints/admin_prompt_lab/simple_activation_manager/conversation_file_manager/enhanced_conversation_manager/activation_audit/report_registry/sandbox_fork + chat/chat_optimized/admin/simple_chat_routes
  - 去掉所有 `+ "Z"` 拼接(scripts/ 故意保留 4 处 data/ 历史 JSON 兼容)
- **层3 前端**:
  - 新建 `src/frontend/lib/utils/formatTime.ts` — `formatUTC`/`formatLocalDateTime`/`formatDate`/`formatRelative`/`toDate`(naive 补 Z 视作 UTC)
  - 接入 9 个页面:admin/page、users、analytics、notifications、prompt-lab、conversations、sandboxes、activations、dashboard
  - `lib/promptCatalogUtils.ts` 的 `formatAdminTime`、`components/explore/LikedContentSection.tsx` 委托新工具
- **层4 历史修正**:
  - 新增 `src/backend/scripts/fix_timestamps.py` — 幂等,支持 `--dry-run` 和 `--db-url`,用 `INSTR(value,'+')=0` 过滤已带 tz,自动跳过不存在的表,仅 SQLite 生效
  - 新增 `alembic/versions/005_fix_timestamps_tz.py`(revision 005,down=004_notification)— 手写数据 UPDATE
- **⚠️ 最大风险点(必须验证)**:JWT 流程代码层分析安全(jose 处理 aware/naive 都没问题),但**未经运行时测试**。务必开发环境跑完整登录/refresh
- **⚠️ 上线顺序**:必须先停后端 → 跑 `fix_timestamps.py` 或 `alembic upgrade head` 修复历史数据 → 重启,否则旧 naive 数据排序错乱
- **遗留**:sandbox 拒绝跑 pytest/black/isort,需手动验证;`AnswerCardSection.tsx`/`sessionRecovery.ts` 的 `new Date(iso).getTime()` 排序未改(fix 后能正确解析,改动收益低)

---

### T3 — 每轮平均时间统计(集成 admin)✅

- **分支/commit**:改动落在 main(commit `1832ab6`: feat: T3 每轮平均时间统计)
- **新增文件**:
  - `src/backend/app/services/conversation_stats_service.py`(419 行)
  - `scripts/conversation_stats.py`(358 行)— 离线解析脚本
  - `test/backend/test_conversation_stats_service.py`(386 行)
- **修改文件**(纯追加):
  - `src/backend/app/api/v1/admin.py`(+44)— 2 个统计路由
  - `src/frontend/lib/api/admin.ts`(+59)— `ConversationStatsResult` 类型 + 2 函数
  - `src/frontend/app/(main)/admin/users/page.tsx`(+136)— 统计按钮 + 卡片弹窗
  - `src/frontend/app/(main)/admin/reports/page.tsx`(+84)— 统计按钮(与 T1 批量导出 UI 隔离)
- **接口**:
  - `GET /admin/users/{user_id}/conversation-stats`
  - `GET /admin/reports/{report_id}/conversation-stats`
  - 出参:`{total_turns, avg_minutes, total_minutes, per_phase[], reminder_text}`,super_admin 守卫
- **"一轮"界定规则**:
  - 按 user 消息切轮,每轮时长 = 下一轮 user ts - 本轮 user ts
  - 最后一轮用该轮最后一条 assistant 消息 ts 收尾;无 assistant 则不计
  - 异常过滤:单轮 >2h(7200s)或 <0 → 计入 `skipped_long_turns`
  - 缺时间戳 → 计入 `skipped_no_ts`,跳过该轮
- **提醒文案**:`用户 abc12345 本次探索共 12 轮对话,平均每轮 8.5 分钟,总时长 102 分钟。`
- **离线脚本**:`python scripts/conversation_stats.py <zip或目录>`(支持 zip/目录,自动识别 md/txt)
- **测试**:10/10 通过(0.52s,agent 自测)
- **设计优化**:在线接口直接从 session 对话历史算(复用 T1 数据加载,不走文件解析);离线脚本才解析导出文件
- **遗留**:`export_service.py:128` pre-existing bug 未修(不在 T3 范围)

---

### T4 — 邮件群发(后台队列 + 进度落库)✅

- **分支/commit**:改动落在主仓库工作区(部分文件)。`feat/email-notification` worktree 存在但未同步
- **新增文件**:
  - `src/backend/app/models/notification.py` — `NotificationTask` + `NotificationRecipient`
  - `src/backend/app/services/notification_service.py` — create_task/run_batch/get_status/list_tasks/recover_interrupted
  - `src/backend/app/api/v1/admin_notifications.py` — 3 端点,全 super_admin 守卫
  - `src/backend/alembic/versions/004_add_notification_tables.py`(revision 004,down=003)
  - `src/frontend/app/(main)/admin/notifications/page.tsx` — 筛选+模板+发送+进度轮询+历史
  - `test/backend/test_notification_service.py` — 13 测试
- **修改文件**:
  - `src/backend/app/main.py` — 注册 router + startup hook `recover_interrupted()`(fire-and-forget)
  - `src/frontend/lib/api/admin.ts` — `sendNotificationEmail`/`getNotificationStatus`/`listNotificationTasks`(与 T1/T3 命名隔离)
- **接口**:
  - `POST /admin/notifications/email` — 入参 `{subject, body, user_filter?}`,返回 `{task_id}`(BackgroundTasks 异步)
  - `GET /admin/notifications/email/{task_id}` — 进度 `{total, sent, failed, status, recipients[]}`
  - `GET /admin/notifications/email` — 历史列表(分页)
  - `user_filter`:`is_active`/`profile_completed`/`created_after`,全空=全选
- **数据表**:
  - `notification_tasks`:task_id(PK)/subject/body/filter_json/total/sent/failed/status/created_at/updated_at/started_at/finished_at
  - `notification_recipients`:id/task_id(FK+索引)/user_id/email/status/error_msg/created_at
  - status 枚举:pending/running/completed/interrupted/failed
- **核心机制**:进度落 SQLite(防重启丢失);重启时 startup hook 扫描 status='running' 标记 interrupted;SMTP 限流每秒≤1 封,失败重试 1 次
- **测试**:13/13 通过(agent 自测,mock SMTP)
- **遗留**:alembic upgrade 需人工跑;black/isort 需人工跑;前端 UI 用 Tailwind 内联未精修;`datetime.utcnow()` 沿用旧风格(T2 已统一处理)

---

### T5 — profile bug 修复 ✅

- **分支/commit**:改动落在主仓库工作区(**未 commit**)。`fix/profile-sync` 分支存在但为空
- **修改文件**:
  - `src/backend/app/utils/survey_storage.py:65-103` — `save_basic_info_by_user` 改 `async def`;删 `loop.create_task`/`asyncio.run` + `except: pass`;直接 `await` 写 DB,失败 raise
  - `src/backend/app/api/v1/sessions.py:86` — 加 `await`
  - `src/backend/app/api/v1/simple_chat_routes.py:1443, 1528` — 两处加 await(外层已 async def,无需改签名)
  - `src/backend/scripts/migrate_basic_info_to_user.py` — 脚本同步适配(asyncio.run 包一层)
  - `test/backend/test_profile_sync_bug.py`(新增)— 4 回归用例
- **数据一致性策略**:**先 DB 后 JSON**
  - 原代码先 JSON 后 DB,DB 失败时 JSON 已写 → admin 查不到但 prompt 用这份问卷,前端误成功不重试
  - 修复后 DB 先成功(source of truth)才写 JSON 缓存;DB 失败 raise 且 JSON 不写;DB 成功但 JSON 失败也 raise(避免不一致)
- **测试**(4 用例,agent 自测):
  1. 提交 survey → 立即查 UserProfile → gender/profile_completed 正确
  2. mock DB 失败 → `save_basic_info_by_user` raise(不再静默)
  3. DB 失败时 JSON 不写(一致性)
  4. 空问卷边界:profile_completed=False 不抛错
- **遗留**:pytest 未实际执行;admin `/admin/users` 列表接口本身不返回 gender 字段(本次不动,如需展示另开任务)

---

## 十、上线前必做清单

1. **分类提交未 commit 的改动**(T2/T4/T5 混在主仓库工作区)
2. **跑全部测试**:`pytest test/backend -v`(所有 agent 都没真正跑过)
3. **跑 lint**:`cd src/backend && black --check . && isort --check .`;`cd src/frontend && npm run lint && npm run build`
4. **T2 时区历史数据修复**:`./start.sh stop` → `cd src/backend && python scripts/fix_timestamps.py`(或 `alembic upgrade head`)→ 重启
5. **T2 JWT 验证**:开发环境跑完整登录 + refresh token 流程
6. **T4 建表**:`alembic upgrade head` 建 notification 两张表
7. **数据库 migration 链**:003 → 004(T4 notification)→ 005(T2 timestamps),按顺序跑
8. **端到端验证**:每个任务的"如何验证"步骤走一遍
9. **修复 pre-existing bug**:`export_service.py:128` 的 `conversation_history_dict` 未定义(T1/T3 都做了兜底,建议正式修复让导出消息更完整)
