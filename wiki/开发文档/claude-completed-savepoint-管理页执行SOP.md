# Savepoint 管理页执行 SOP（管理员）

本文用于管理员在不写命令的情况下完成 Savepoint 导出、执行、排错与批量重跑。

## 1. 前置条件

- 使用超级管理员账号登录。
- 后端与前端服务已启动。
- 已存在可用 Savepoint（在调试聊天页 AI 消息下方点击“保存为检查点”创建）。

## 2. 导出场景

1. 打开 `管理后台 -> 调试沙箱 Fork` 页面。
2. 在 `Savepoints（检查点）` 列表找到目标 Savepoint。
3. 点击 `Export`。
4. 页面会显示导出结果：
   - fixture 路径
   - playwright 命令
   - replay 命令
   - case/scenario 路径

导出后会自动写入 `test_agent/scenarios/generated/generated_index.json`，并出现在 `已导出场景（generated_index）` 列表。

## 3. 单条执行与排错

1. 在 `已导出场景（generated_index）` 中点击行内 `执行`。
2. 等待状态回写（`最近执行` 列会更新）。
3. 若失败，点击 `日志` 展开：
   - `stdout tail`
   - `stderr tail`
4. 可复制：
   - `Playwright` 命令
   - `Replay` 命令
   - `场景路径`
   - `日志路径`

## 4. 批量执行

### 4.1 重跑失败项（异步）

1. 在列表右上角点击 `重跑失败项`。
2. 页面会显示任务进度：
   - `progress processed/total`
   - `passed/failed`
3. 任务运行中可点击 `取消任务`。

### 4.2 执行选中项

1. 用状态筛选（全部/仅失败/仅通过）缩小范围。
2. 点击 `全选筛选` 或逐条勾选。
3. 设置 `retry`（0~3）。
4. 点击 `执行选中(n)` 启动异步任务。

## 5. 快速跳转与人工复核

- 行内点击 `进入检查点`，直接跳转到对应 phase/thread。
- 用于人工验证“为什么失败”以及是否是用例本身过严。

## 6. 任务历史

页面下方 `批量任务历史` 保存最近任务摘要：

- job_id
- 状态（running/completed/cancelled）
- 时间
- 参数（engine/retry）
- 结果（processed/total、passed/failed）
- 状态可能包含：`running / completed / cancelled / interrupted`

可点击 `查看详情` 查看任务内每个场景项的状态、摘要、报告路径、日志路径。
可按状态过滤历史，并通过 `清理旧历史` 仅保留最近批量任务记录。

说明：若服务重启，进行中的任务不会继续执行，会被自动标记为 `interrupted` 便于追踪。

## 7. 常见问题

- 提示“已有批量任务运行中”：
  - 说明已有任务正在执行，请等待或先取消当前任务。
- 提示“该 savepoint 正在执行中”：
  - 同一 savepoint 被并发触发，稍后重试。
- 执行超时：
  - 可提高 timeout 或先用 Replay 快速定位。

## 8. 自动化测试教学（管理员到研发一体化）

本节补充“如何真正写和跑自动化样例”，避免只会点页面按钮。

### 8.1 三条常用执行链路

1. **管理页一键执行（非技术同学）**
   - Savepoint -> Export -> generated_index -> 执行/批量执行。

2. **命令行执行 L2（页面回归）**
   - 单条：
     - `python test_agent/l2/run_scenario.py --scenario test_agent/scenarios/l2/sample_playwright_rumination.yaml --engine playwright`
   - 批量：
     - `python test_agent/l2/run_batch.py --scenarios-dir test_agent/scenarios/l2 --engine auto`

3. **命令行执行 L3/L4（BDD + Agent）**
   - L3 单条：
     - `python test_agent/pipelines/run_l3.py --scenario test_agent/adapters/beingdoing/scenarios/l3/rumination_guidance.feature --engine local`
   - L4 单条：
     - `python test_agent/pipelines/run_l4.py --task test_agent/adapters/beingdoing/scenarios/l4/values_persona_001.yaml --engine local --bridge-mode stub`
   - 一键分层（推荐）：
     - `python test_agent/pipelines/run_all_levels.py --profile nightly`

### 8.2 如何写 L2 场景样例（YAML）

最小模板：

```yaml
schema_version: 1
id: l2_pw_demo
engine: playwright
data:
  base_url: http://127.0.0.1:3000
  backend_url: http://127.0.0.1:8000
  phase: rumination
steps:
  - action: goto
    url: /explore/chat/rumination
  - action: chat_send
    text: "确认，可以继续"
  - action: wait_for_ai
    delta: 1
assertions:
  expected_keywords: ["确认", "继续"]
```

编写原则：

- 场景要有唯一 `id`
- `steps` 要尽量短小（3~8 步）
- 断言先写“关键成功信号”，避免一开始写太严导致高噪声

### 8.3 如何写 L3 场景样例（Gherkin/YAML 双轨）

Gherkin 示例：

```gherkin
Feature: Rumination 引导顺序
  Scenario: 编辑假设后失焦，应出现正确引导
    Given 我已进入 "rumination" 阶段
    When 我把第 1 行假设修改为 "我想做独立咨询"
    And 我点击表格外空白区域
    Then 右侧应出现引导语 "是否填写好了"
```

YAML 示例：

```yaml
id: l3_yaml_demo
title: Rumination 引导顺序（YAML）
steps:
  - keyword: Given
    text: 我已进入 "rumination" 阶段
  - keyword: When
    action: domain_action
    name: table_edit
    payload:
      row: 1
      field: hypothesis
      value: 我想做独立咨询
  - keyword: Then
    action: assert_text
    text: 是否填写好了
```

### 8.4 如何写 L4 TaskSpec（Agent 测试用户）

最小模板：

```yaml
task_id: l4_values_demo
goal: 在 12 轮内完成价值观阶段
persona:
  role: 产品经理
  style: 表达简洁，偶尔犹豫
budget:
  max_steps: 40
  max_turns: 12
  max_runtime_sec: 900
scoring:
  completion_weight: 0.4
  consistency_weight: 0.3
  ux_risk_weight: 0.3
stop_conditions:
  - reached_phase: talents
  - hard_error: true
```

建议：

- `goal` 只写一个核心目标
- 先用 `bridge-mode=stub` 稳链路，再切 `cli`
- 跑真浏览器时使用 `--engine playwright`

### 8.5 当前推荐执行顺序（避免踩坑）

1. 先 `--dry-run` 看命令链路
2. 再跑 `local` 引擎确认编排/解析
3. 最后跑 `playwright` 验证真实页面链路
4. 失败先看 report 里的 `failure_type + error`，再看 artifacts/log

## 9. 当前未完成项（核心）

以下是截至当前版本仍未完成的核心项（用于排期）：

1. **L4 稳定化阶段未完成**
   - 重试与 fallback 策略（系统级）仍较简化
   - 失败聚类 TopN 与 flakiness 基线统计未落地

2. **L3 断言分层未完整工程化**
   - `AssertionContract` 已有，但“通用断言 + 业务断言”执行层未完全独立

3. **统一 orchestrator / reporting 模块未独立**
   - 已有 `run_all_levels.py` 可用，但 `core/runner/orchestrator.py`、`core/reporting/*` 仍未成型

4. **L1 报告并轨未完全完成**
   - 目前 L1 可跑 pytest，但尚未完全统一到跨层同构分析模型

## 10. L4 稳定闭环规则（本轮已定）

为避免过度优化，本阶段固定执行以下最小规则：

1. **瞬时错误重试 1 次**
   - 仅对 `timeout`、`llm_invalid_json` 自动重试一次
   - 其余错误不重试，直接失败

2. **不自动降级**
   - `engine=playwright` 失败时，不自动回退到 `local`
   - 保持真实链路信号纯度

3. **最小失败分类集合**
   - `timeout`
   - `selector_not_found`
   - `assertion_failed`
   - `runtime_error`
   - `llm_invalid_json`
   - `env_unavailable`

4. **稳定性验收标准**
   - 同一 task 连跑 3 次，至少 2 次通过
   - 失败项必须带 `failure_type`（可分类）

5. **稳定性验收命令**
   - `python test_agent/pipelines/run_l4_stability.py --task test_agent/adapters/beingdoing/scenarios/l4/values_persona_001.yaml --engine playwright --bridge-mode stub`

