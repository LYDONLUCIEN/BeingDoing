# claude-test 自动化测试框架

基于 **4.28 开发待测清单** 搭建的端到端测试框架。从 MD 清单自动解析测试项 → 执行 pytest → 生成 JSON + Markdown 报告。

---

## 环境要求

- Python 3.10+，依赖项目 `src/backend` 代码（`app` 包）
- 无需数据库、无需前端 dev server、无需浏览器
- 所有测试基于文件系统（`tmp_path`）隔离运行

---

## 快速开始

```bash
# 进入项目根目录
cd /home/gitclone/BeingDoing

# 一键运行全部测试（解析清单 → 执行 → 报告）
python test/claude-test/run_all.py
```

---

## 命令行参数

### run_all.py（统一入口）

```bash
# 基本用法
python test/claude-test/run_all.py                              # 全部
python test/claude-test/run_all.py --type backend               # 只跑后端
python test/claude-test/run_all.py --task-ids S-02,P-06         # 指定 Task ID
python test/claude-test/run_all.py --task-ids O-03,S-05,S-10    # 多个 ID
python test/claude-test/run_all.py -v                           # 显示 pytest 逐条输出
python test/claude-test/run_all.py --no-show-unmapped           # 不显示未映射项
```

### 标记人工评审项

```bash
# 单项标记
python test/claude-test/run_all.py --human-mark U-01=pass
python test/claude-test/run_all.py --human-mark U-05=fail

# 多项标记
python test/claude-test/run_all.py \
  --human-mark U-01=pass \
  --human-mark U-02=pass \
  --human-mark U-03=pass \
  --human-mark U-05=pass \
  --human-mark U-08=pass
```

### 指定清单文件

```bash
python test/claude-test/run_all.py --checklist 4.28开发待测清单.md
python test/claude-test/run_all.py --checklist wiki/某待测清单.md
```

### 自定义报告输出目录

```bash
python test/claude-test/run_all.py --output-dir /tmp/test-reports
```

---

## 直接运行 pytest

当不需要清单解析和报告生成时，可以直接用 pytest：

```bash
# 运行全部后端测试（137 个用例）
PYTHONPATH=src/backend python -m pytest test/claude-test/backend/ -v

# 运行单个文件
PYTHONPATH=src/backend python -m pytest test/claude-test/backend/test_activation_security.py -v

# 运行单个测试
PYTHONPATH=src/backend python -m pytest test/claude-test/backend/test_activation_security.py::TestIsOwner::test_o03_is_owner_returns_true_for_matching_user -v

# 只运行失败的测试
PYTHONPATH=src/backend python -m pytest test/claude-test/backend/ --lf

# 显示 print 输出
PYTHONPATH=src/backend python -m pytest test/claude-test/backend/ -s
```

---

## 测试文件清单

### 后端测试（14 个文件，137 个用例）

| 文件 | Task IDs | 用例数 | 覆盖内容 |
|------|----------|--------|---------|
| `test_table_widgets.py` | S-02, P-06, U-04, P-05, U-07 | 11 | 列定义、可编辑性、引导文案、括号配对 |
| `test_rumination_ops.py` | S-03, S-09 | 22 | 关键词来源优先级、句子片段过滤、括号清洗、快照一致性 |
| `test_neg_gate.py` | P-04, S-07, P-07 | 16 | 字段级模板注入、闸门触发逻辑、步骤独立 system |
| `test_opening_chain.py` | O-01 | 5 | Step 7 引导语来源、不泄漏其他步骤 system |
| `test_prompt_strings.py` | P-02, P-03, P-08 | 8 | 多值允许、无统计语言、冷启动容错 |
| `test_activation_security.py` | O-03 | 10 | 激活码归属安全、审计日志、PermissionError 防护 |
| `test_survey_user_dimension.py` | O-04, S-04 | 10 | 用户维度问卷存储、跨激活码持久化、merge 策略 |
| `test_conversation_dedup.py` | O-05 | 5 | 会话绑定幂等性、目录创建、select/get |
| `test_journey_resume.py` | S-05, S-06 | 12 | Journey 自动定位 phase、步骤锁定/解锁逻辑 |
| `test_rumination_recall.py` | S-08, S-10 | 11 | 回看默认 step7 降级、neg_gate 触发/清除持久化 |
| `test_completion_flow.py` | S-01 | 4 | 完成并继续竞态保护、并发 lock 安全 |
| `test_dropdown_naming.py` | U-06 | 8 | 下拉选项命名映射、"其他"→"自定义"、前端源码一致性 |
| `test_login_redirect.py` | O-02 | 7 | 登录后统一跳 /explore/intro、无残留旧路由逻辑 |
| `test_cross_device_sync.py` | O-06 | 7 | 对话删除后不残留、跨设备 report 一致、进度持久化 |

### 人工评审项（5 个 Task ID）

| Task ID | 内容 | 标记方式 |
|---------|------|---------|
| U-01 | 表头透明 | `--human-mark U-01=pass` |
| U-02 | 气泡显示 | `--human-mark U-02=pass` |
| U-03 | 列宽 | `--human-mark U-03=pass` |
| U-05 | hover 样式 | `--human-mark U-05=pass` |
| U-08 | 点赞颜色 | `--human-mark U-08=pass` |

---

## Task ID 快速索引

| 前缀 | 含义 | 测试方式 |
|------|------|---------|
| S-* | 状态/流程 | pytest mock |
| P-* | 提示词/Prompt | pytest 静态分析 |
| O-* | 开场/入口/整体流程 | pytest mock / 源码 cross-check |
| U-* | UI/交互 | pytest 源码 cross-check / 人工评审 |

---

## 报告输出

运行后自动在 `test/claude-test/reports/` 目录下生成：

```
reports/
├── run_20260429_113651.json   # 机器可读（CI 消费）
└── run_20260429_113651.md     # 人类可读（含失败详情、按章节汇总）
```

Markdown 报告包含：
- 摘要统计（通过/失败/跳过/人工待办）
- 失败项详情（Task ID + 错误信息）
- 按章节分组的逐项结果（`[x]` 通过 / `[!]` 失败 / `[ ]` 待办）
- 测试套件详情（每个文件的 pass/fail 计数）

---

## 目录结构

```
test/claude-test/
├── run_all.py                    # 统一入口：解析清单 → 分发执行 → 汇总报告
├── pytest.ini                    # 独立 pytest 配置（与项目根隔离）
│
├── common/
│   ├── models.py                 # TestItem / TestSuiteResult 数据模型
│   ├── task_mapping.py           # Task ID → 测试文件映射 + 人工评审判定
│   └── report.py                 # 报告生成（JSON + Markdown）
│
├── parser/
│   ├── md_checklist_parser.py    # MD 清单解析器（- [ ] + **(TASK-ID)**）
│   └── test_md_parser.py         # parser 自测
│
├── backend/                      # pytest 后端测试（14 个文件，137 个用例）
│   ├── conftest.py               # 公共 fixture
│   └── test_*.py                 # 各模块测试
│
├── frontend/                     # vitest 前端测试（当前全部由后端 cross-check 覆盖）
├── e2e/                          # playwright E2E（当前全部由后端 API 测试覆盖）
│
└── reports/                      # 生成的测试报告
```

---

## 添加新测试项

1. 在 `backend/test_xxx.py` 中编写测试函数（命名格式：`test_{task_id}_{描述}`）
2. 在 `common/task_mapping.py` 的 `TASK_ID_TO_TEST_FILE` 中添加映射
3. 在 MD 清单中用 `**(TASK-ID)**` 格式标注
4. 运行 `run_all.py` 即可自动关联

### 新增人工评审项

在 `common/task_mapping.py` 的 `HUMAN_REVIEWED_IDS` 中添加 Task ID，或确保清单描述中包含 `HUMAN_REVIEW_KEYWORDS` 中的关键词。

---

## 测试策略说明

| 场景 | 策略 | 说明 |
|------|------|------|
| 纯函数/数据映射 | 直接调用 + assert | 如 `normalizeRuminationValue`、`merge_basic_info_sources` |
| 文件读写模块 | `tmp_path` 隔离 | 激活码、问卷、进度模块基于 JSON 文件，用临时目录替代 |
| 并发安全 | `ThreadPoolExecutor` | 如 `lock_previous_step_when_entering` 竞态测试 |
| 前端 UI 逻辑 | TS/TSX 源码 cross-check | 解析前端源码验证路由、映射表、i18n 配置一致性 |
| 视觉/交互 | 人工评审 | 需要人眼验证的样式、动画等标记为 `human_reviewed` |
