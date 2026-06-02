# 对技术专家问询的逐条答复（v1）

本文对应 `test_agent/claude_check.md` 的 10 个问题，给出当前决策、实现建议与待确认项。

## 1) L2 设计不具体

**答复：同意，需要补全。**

- **用例组织**：L2 采用 `YAML 场景 + 少量 Python helper`，避免纯代码脚本碎片化
- **执行路径**：L2 也走 `ActionContract`，不允许“绕过编排器直接写散装 Playwright”作为主路径
- **分级标准**：
  - `smoke`：< 3 分钟，1~3 条阻断级场景（登录/核心入口/关键弹窗）
  - `core`：< 15 分钟，P0/P1 高风险交互（如不再提示、关键引导）
  - `extended`：nightly 扩展集（多分支、长流程、边界 case）

---

## 2) L1 编排模糊

**答复：统一进同一 ResultModel，但保留原 pytest 细节。**

- `l1/run_l1.py` 执行 pytest（JSON/JUnit 输出）
- 通过 `pytest_adapter` 转为统一 `ResultModel`（suite/case/status/duration/error）
- 报告入口统一为 `run_all_levels.py`，按 level 聚合（L1~L4）
- 保留 “原生 pytest 报告” 作为附录证据，避免信息损失

---

## 3) core 与 adapter 边界

**答复：按“配置归属 + 行为归属”切分。**

- `core`：
  - Playwright driver 生命周期管理
  - 标准动作执行（goto/click/fill/...）
  - 通用等待、重试、超时
- `adapter`：
  - `base_url`、auth 注入策略、selector alias、domain_action、domain_assertion
  - 业务上下文准备（seed/fork）

**关键规则**：L2/L3/L4 全部进入 orchestrator；L2 不单开旁路执行系统。

---

## 4) L4 成本与可靠性

**答复：按“外部 Agent Bridge + 强校验”处理。**

已定项（与你讨论后）：

- L4 仅单代理 `Test User Agent`
- 可复用现有 `kimi` CLI，不重造模型调用层
- 输出协议：双通道（执行 JSON + 可读解释）
- JSON 失败重试策略：`1 次重试 + fallback`
- fallback：场景级优先，全局兜底
- 终止条件：目标达成或触发 `max_steps/max_turns/max_runtime`

成本控制：

- 默认小模型（执行决策）+ token 上限
- PR 不跑全量 L4；nightly 为主

---

## 5) BDD step definition 映射

**答复：不用 LLM 语义匹配做主路径，采用“规则匹配优先”。**

- 匹配顺序：
  1. 精确模板匹配
  2. 正则匹配（参数提取）
  3. 同义词词典匹配（有限集合）
  4. 未命中即报错（不自动猜）

- 一个 step definition **允许映射多个 action**（如“我已登录”）
- 放置路径：`adapters/beingdoing/step_definitions.py`（或 `step_definitions/` 目录）

---

## 6) 数据隔离与环境管理

**答复：采用“作用域隔离 + 命名空间隔离 + 产物隔离”。**

- 默认 `local` 测试环境，禁用生产写入
- 每条用例生成 `run_id`，数据目录挂到 `tmp/run_id/...`
- 并行执行通过 `run_id + case_id` 隔离资源
- L4 探索数据落独立沙箱目录，测试后清理；失败样本可保留（可配置）

---

## 7) 证据优先规范

**答复：制定强制证据矩阵。**

- 截图：
  - 关键步骤截图（必须）
  - 失败前后截图（必须）
  - 结束态截图（必须）
- trace：
  - Playwright trace（默认开启，失败必留）
  - LLM 决策 trace（默认摘要，debug 开关可留完整）
- 保留策略：
  - PR：保留最近 N 次
  - nightly：保留 14~30 天（可配置）

---

## 8) 配置文件定义不清

**答复：采用三层覆盖模型。**

- `configs/base.yaml`：全局默认（超时、重试、报告、artifact）
- `configs/{local,ci}.yaml`：环境覆盖（URL、并发、保留策略）
- `scenario.yaml`：场景覆盖（steps、目标、阈值、评分参数）

优先级：`scenario > env(local/ci) > base`

---

## 9) L4 评分可操作性

**答复：以规则为主，LLM 评分为辅。**

- `completion`：规则（是否达成目标/阶段）
- `consistency`：规则（重复、矛盾、非法状态）
- `ux_risk`：规则触发（超时、卡死、找不到元素、无下一步引导）
- 可选 LLM 打分仅作“解释增强”，不作为门禁真值

不同 persona：

- 共享同一“硬阈值”
- 可有不同“软阈值权重”（例如 novice 更重引导清晰度）

---

## 10) 失败分析与趋势闭环

**答复：需要补，且建议第一期就做最小闭环。**

- 失败自动分类（taxonomy）：
  - `network_timeout`
  - `assertion_failed`
  - `selector_not_found`
  - `page_crash`
  - `llm_invalid_json`
  - `fallback_exhausted`
- nightly 汇总趋势：
  - 通过率趋势
  - 平均时长趋势
  - Top 失败类型
  - flaky 场景名单

---

## 当前已拍板（来自本轮讨论）

1. L3/L4 核心引擎与业务解耦（adapter 接入）
2. L3 用双层模式（自然语言编写 -> 规范步骤执行）
3. L4 单代理 Test User Agent
4. L4 默认策略：目标驱动优先，失败后探索补测
5. L4 报告默认 B（可复现包），且截图强制
6. Bridge 协议双通道；执行只认 JSON
7. JSON 失败：重试 1 次后 fallback
8. fallback：场景级优先，全局兜底
9. 终止条件：目标达成或命中 steps/turns/runtime 阈值

