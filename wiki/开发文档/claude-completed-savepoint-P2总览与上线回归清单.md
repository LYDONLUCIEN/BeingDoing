# Savepoint / L2 执行体系总览（P2）

> 更新时间：2026-06-01  
> 适用对象：管理员、测试负责人、研发同学

---

## 1. 现在到底有什么（你可以直接用）

当前已经落地并可用的能力：

1. **Savepoint 管理闭环**
   - 创建 / 加载 / 删除 / 导出
   - 管理页可操作（管理员可见）

2. **导出即执行**
   - `Export` 后自动生成 Playwright 场景（`engine: playwright`）
   - 自动写入 `generated_index.json`
   - 同时提供：
     - `playwright_command`
     - `replay_command`

3. **单条执行闭环**
   - 管理页可一键执行场景
   - 回写执行状态（passed/failed）
   - 记录 stdout/stderr tail
   - 完整日志落盘到 `test_agent/reports/job_logs/`

4. **批量执行闭环**
   - 状态筛选（全部/仅失败/仅通过）
   - 失败项批量重跑
   - 选中项批量执行
   - 可配置 `retry`（0~3）
   - 异步任务 + 进度轮询
   - 支持取消任务

5. **任务可追踪与可恢复**
   - 任务状态持久化到 `data/test/simple/savepoints/batch_jobs_state.json`
   - 服务重启后，未完成任务自动标记为 `interrupted`
   - 批量任务历史可查看、可按状态过滤、可清理旧历史

6. **可靠性保护**
   - 同一时刻仅允许一个批量任务 running
   - 同一 savepoint 单条执行互斥，防止并发覆盖

7. **L3/L4 执行框架已接入主流程**
   - L3：支持 Gherkin + YAML 双轨输入，支持 local / playwright 引擎
   - L4：支持 TaskSpec + Agent Loop + Judge，支持 local / playwright 引擎
   - 支持统一入口：`run_all_levels.py`（含 `--profile nightly`）

---

## 2. 一页操作 SOP（管理员）

### 场景 A：从检查点做单条验证

1. 在调试聊天页创建 Savepoint
2. 在管理页 `Savepoints` 点击 `Export`
3. 在 `已导出场景（generated_index）` 点击 `执行`
4. 失败时点 `日志` 看 tail，必要时复制日志路径查看完整日志

### 场景 B：批量回归（推荐）

1. 在 `已导出场景（generated_index）` 先做状态筛选（如“仅失败”）
2. 设置 `retry`（建议默认 1）
3. 选择：
   - `重跑失败项`，或
   - `全选筛选` + `执行选中(n)`
4. 观察进度条（processed/total，passed/failed）
5. 如需停止，点击 `取消任务`
6. 完成后到 `批量任务历史` 看总览；点 `查看详情` 看每条 item 结果

### 场景 C：人工复核

1. 从 generated 列表点击 `进入检查点`
2. 在对应 phase/thread 做人工复查
3. 需要复现时复制 Playwright / Replay 命令

---

## 3. 数据与文件索引（关键）

### 场景与索引

- 场景目录：`test_agent/scenarios/generated/`
- 场景索引：`test_agent/scenarios/generated/generated_index.json`

### 任务与历史

- 批量任务运行态：`data/test/simple/savepoints/batch_jobs_state.json`
- 批量任务历史：`data/test/simple/savepoints/batch_job_history.jsonl`
- 回放历史：`data/test/simple/savepoints/replay_logs.jsonl`

### 执行日志

- 单条完整日志：`test_agent/reports/job_logs/*.log`
- 单次执行报告：`test_agent/reports/l2_<id>_<timestamp>.json`
- 分层汇总报告：`test_agent/reports/all_levels_<timestamp>.json`

### L3/L4 场景与任务

- L3 场景目录：`test_agent/adapters/beingdoing/scenarios/l3/`
- L4 任务目录：`test_agent/adapters/beingdoing/scenarios/l4/`
- L3 批量报告：`test_agent/reports/l3_batch_<timestamp>.json`
- L4 批量报告：`test_agent/reports/l4_batch_<timestamp>.json`

---

## 4. API 速查（仅管理员）

### Savepoint

- `GET /api/v1/admin/savepoints`
- `POST /api/v1/admin/savepoints/create`
- `POST /api/v1/admin/savepoints/load`
- `DELETE /api/v1/admin/savepoints`
- `POST /api/v1/admin/savepoints/export`

### 场景执行

- `GET /api/v1/admin/savepoints/generated-scenarios`
- `POST /api/v1/admin/savepoints/generated-scenarios/run`
- `POST /api/v1/admin/savepoints/generated-scenarios/run-batch`
- `POST /api/v1/admin/savepoints/generated-scenarios/run-batch-async`
- `GET /api/v1/admin/savepoints/generated-scenarios/run-batch-async/{job_id}`
- `GET /api/v1/admin/savepoints/generated-scenarios/run-batch-async-jobs`
- `POST /api/v1/admin/savepoints/generated-scenarios/run-batch-async/{job_id}/cancel`
- `GET /api/v1/admin/savepoints/generated-scenarios/run-batch-async-history`
- `POST /api/v1/admin/savepoints/generated-scenarios/run-batch-async-history/cleanup`

---

## 5. 上线检查清单（执行前打勾）

- [ ] 管理员账号可访问 `admin/sandboxes` 页面
- [ ] Savepoint 列表可加载
- [ ] Export 成功后，`generated_index` 出现新记录
- [ ] 单条 `执行` 成功回写状态
- [ ] 失败 case 可展开看到 stdout/stderr tail
- [ ] 可复制日志路径且日志文件存在
- [ ] 批量任务可启动并显示进度
- [ ] 批量任务可取消
- [ ] 取消后状态变为 `cancelled`，不再继续执行后续项
- [ ] 服务重启后，之前 running 的任务可见为 `interrupted`
- [ ] 历史过滤正常（all/running/completed/cancelled/interrupted）
- [ ] 清理旧历史后计数变化正确

---

## 6. 回归用例清单（建议每次发版跑）

### P0（必须）

1. **Export 基线**
   - 任意 Savepoint 执行 Export
   - 断言：生成 scenario、写入 generated_index、返回双命令

2. **单条执行成功路径**
   - 执行 1 条稳定 case
   - 断言：status=passed，report_file 有值

3. **单条执行失败路径**
   - 人为构造失败 case
   - 断言：status=failed，tail 可见，log_file 可访问

4. **批量失败重跑**
   - 先有失败项，再点重跑
   - 断言：进度推进，历史新增，结果回写

5. **取消任务**
   - 启动批量后立即取消
   - 断言：状态 cancelled，processed < total（通常）

6. **重启恢复**
   - 任务 running 时重启服务
   - 断言：任务状态 interrupted，历史可追踪

### P1（建议）

7. **执行选中项**
   - 筛选 + 全选 + 执行选中
   - 断言：仅选中项执行

8. **retry 生效**
   - 设 retry=1，构造首轮失败次轮成功
   - 断言：attempts=2，最终 passed

9. **互斥保护**
   - 并发触发同一 savepoint
   - 断言：第二次请求被拒绝（正在执行中）

10. **并发任务保护**
   - 已有 running 任务时再启动
   - 断言：返回“已有批量任务运行中”

11. **L3 双表示一致性**
   - 同一业务场景分别使用 `.feature` 与 `.yaml` 执行
   - 断言：主结论一致（通过/失败及关键断言）

12. **L4 真浏览器可达性**
   - 使用 `--engine playwright` 执行 1 条 TaskSpec
   - 断言：能访问前端页面且不出现 runtime 级环境错误

---

## 7. 常见问题与处理

1. **“已有批量任务运行中”**
   - 看页面顶部任务进度，等待完成或取消后重试

2. **“该 savepoint 正在执行中”**
   - 同一 savepoint 并发触发，稍后再试

3. **任务显示 interrupted**
   - 表示服务重启中断，不是业务逻辑失败
   - 可直接再次执行该任务/场景

4. **Playwright 无法执行**
   - 优先用 Replay 快速定位
   - 检查运行环境的 npm/playwright 依赖与网络

---

## 8. 建议默认参数（团队统一）

- 批量 `engine=auto`
- `timeout_sec=900`
- `max_retries=1`
- 历史清理策略：保留最新 200 条

---

## 9. 自动化教学（样例如何编写）

### 9.1 L3（BDD）写法建议

1. 优先写业务语句，不写 selector
2. 每个场景先保持 4~8 步
3. 第一期只保留 1~2 个关键断言（降低噪声）
4. 若场景复杂，先用 YAML 明确动作，再补 Gherkin 业务表达

L3 常用命令：

- 单条（feature）：
  - `python test_agent/pipelines/run_l3.py --scenario test_agent/adapters/beingdoing/scenarios/l3/xxx.feature --engine local`
- 单条（yaml）：
  - `python test_agent/pipelines/run_l3.py --scenario test_agent/adapters/beingdoing/scenarios/l3/xxx.yaml --engine local`
- 批量：
  - `python test_agent/pipelines/run_l3_batch.py --scenarios-dir test_agent/adapters/beingdoing/scenarios/l3 --engine local`

### 9.2 L4（Agent）写法建议

1. 一个 task 只聚焦一个目标（goal）
2. persona 信息保持“足够但不冗长”
3. budget 先保守（turns <= 12）
4. 先跑 `engine=local`，稳定后切 `engine=playwright`

L4 常用命令：

- 单条：
  - `python test_agent/pipelines/run_l4.py --task test_agent/adapters/beingdoing/scenarios/l4/xxx.yaml --engine local --bridge-mode stub`
- 真浏览器：
  - `python test_agent/pipelines/run_l4.py --task test_agent/adapters/beingdoing/scenarios/l4/xxx.yaml --engine playwright --bridge-mode stub`
- 批量：
  - `python test_agent/pipelines/run_l4_batch.py --tasks-dir test_agent/adapters/beingdoing/scenarios/l4 --engine local --bridge-mode stub`

### 9.3 一键执行（推荐）

- 夜跑推荐：
  - `python test_agent/pipelines/run_all_levels.py --profile nightly`
- 自定义层级：
  - `python test_agent/pipelines/run_all_levels.py --levels l1,l2,l3,l4`

---

## 10. 还没做完的核心项（当前判断）

1. **L4 稳定化能力不足**
   - 全局重试/回退策略尚未系统化
   - 失败聚类（TopN）与 flakiness 趋势统计未落地

2. **L3 断言层仍偏轻量**
   - `AssertionContract` 与业务断言分层未完全解耦成独立模块

3. **统一 core 编排层未独立成型**
   - 目前以 pipeline 脚本为主，`orchestrator` 与 `reporting` 核心层仍待建设

4. **L1 跨层报告并轨不完整**
   - L1 能跑，但与 L2/L3/L4 的统一分析维度还未完全打通

---

## 11. L4 最小稳定闭环（当前执行标准）

本节用于统一团队对 L4“已完成/未完成”的判断口径。

### 已完成（本轮）

1. `engine=playwright` 已可走真实浏览器执行链路
2. 瞬时错误重试策略已落地（1 次）
3. 失败分类已收敛到最小集合
4. 稳定性验收脚本已提供（3 次跑 + 2 次通过阈值）

### 验收命令

- 单条：
  - `python test_agent/pipelines/run_l4.py --task test_agent/adapters/beingdoing/scenarios/l4/values_persona_001.yaml --engine playwright --bridge-mode stub`
- 稳定性（推荐）：
  - `python test_agent/pipelines/run_l4_stability.py --task test_agent/adapters/beingdoing/scenarios/l4/values_persona_001.yaml --engine playwright --bridge-mode stub`

### 通过判定

- `runs=3` 且 `min_pass=2`
- 失败项全部有 `failure_type`

---

## 12. 关联文档

- `test_agent/L1-L4测试框架设计_v1.md`
- `test_agent/l2/README.md`
- `wiki/开发文档/claude-completed-savepoint-管理页执行SOP.md`

