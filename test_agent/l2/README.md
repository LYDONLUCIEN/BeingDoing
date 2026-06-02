# L2 场景执行器（MVP）

当前目录提供两种执行器：

- `replay`：最小可用执行器（调用 `replay_simple_chat.py`）
- `playwright`：真浏览器执行器（真实页面交互 + 截图 + trace）

## 快速开始

在项目根目录执行：

```bash
python test_agent/l2/run_scenario.py --scenario test_agent/scenarios/l2/sample_savepoint_smoke.yaml --engine replay
```

仅查看将执行的命令（不执行）：

```bash
python test_agent/l2/run_scenario.py --scenario test_agent/scenarios/l2/sample_savepoint_smoke.yaml --engine replay --dry-run
```

Playwright 真浏览器执行（先安装依赖）：

```bash
cd test_agent/l2
npm install
npx playwright install chromium

cd /home/gitclone/BeingDoing
python test_agent/l2/run_scenario.py --scenario test_agent/scenarios/l2/sample_playwright_rumination.yaml --engine playwright
```

从 Savepoint 一键起跑（自动 load）：

```bash
export L2_ADMIN_BEARER_TOKEN="<admin_jwt_token>"
python test_agent/l2/run_scenario.py --scenario test_agent/scenarios/l2/sample_playwright_savepoint_bootstrap.yaml --engine playwright
```

## 批量执行（推荐）

默认执行导出目录下全部场景：

```bash
python test_agent/l2/run_batch.py --engine replay
```

指定目录：

```bash
python test_agent/l2/run_batch.py --scenarios-dir test_agent/scenarios/l2 --engine auto
```

仅预览（不执行）：

```bash
python test_agent/l2/run_batch.py --scenarios-dir test_agent/scenarios/generated --engine auto --dry-run
```

按关键词过滤场景文件名（例如只跑 rumination）：

```bash
python test_agent/l2/run_batch.py --scenarios-dir test_agent/scenarios/generated --engine auto --filter rumination
```

失败即停（fail-fast）：

```bash
python test_agent/l2/run_batch.py --scenarios-dir test_agent/scenarios/generated --engine auto --fail-fast
```

显式继续执行（默认行为）：

```bash
python test_agent/l2/run_batch.py --scenarios-dir test_agent/scenarios/generated --engine auto --continue-on-error
```

执行完成后会输出报告到：

- `test_agent/reports/l2_<scenario_id>_<timestamp>.json`
- `test_agent/reports/l2_batch_<timestamp>.json`（批量执行）

## 场景字段（MVP 版）

Replay 模式最小必填：

- `id`
- `data.fixture_report_dir`
- `data.phase`
- `data.thread_id`

消息提取优先级：

1. `steps` 中第一条 `action: chat_send` 的 `text`
2. `assertions.expected_hint`
3. 默认 `"请继续"`

## 说明

- `run_scenario.py` 支持 `--engine replay|playwright|auto`
- `auto` 规则：若场景包含 `engine: playwright` 则走 Playwright，否则走 replay
- Playwright 当前支持动作：
  - `goto`
  - `chat_send`
  - `wait_for_ai`
  - `wait_ms`
  - `screenshot`
  - `click`
  - `fill`
  - `assert_text`
- Playwright 产物目录：`test_agent/reports/artifacts/<scenario_id>_<timestamp>/`
  - `final.png`
  - `trace.zip`

## Savepoint 导出场景（Admin Export）

- 管理页 `Export` 生成的 `test_agent/scenarios/generated/<savepoint_id>.yaml` 默认已是 Playwright 场景。
- 同步维护 `test_agent/scenarios/generated/generated_index.json`（按导出时间倒序）。
- 导出结果会包含两条命令：
  - `playwright_command`：真浏览器执行（推荐）
  - `replay_command`：回放执行（兼容老链路）
- 管理页可直接在 `generated_index` 列表中点击“执行”，后端会调用 `run_scenario.py` 并回写最近执行状态。
- 管理页支持展开最近执行的 `stdout/stderr tail`（失败定位优先看这里）。
- 管理页支持状态筛选（全部/仅失败/仅通过）和“重跑失败项”批量执行。
- “重跑失败项”采用异步任务，页面显示实时进度（processed/total、passed/failed）。
- 支持取消运行中的批量任务、查看批量任务历史（job_id、参数、结果）。
- 支持“执行选中项”批量任务（可配置 retry 次数 0~3）。
- 批量任务运行态会持久化；服务重启后未完成任务自动转为 `interrupted`，可在历史中查看。

## Playwright 场景 data 字段

- `base_url`：前端地址，默认 `http://127.0.0.1:3000`
- `backend_url`：后端地址（savepoint 自动 load 用），默认 `http://127.0.0.1:8000`
- `phase`：默认进入阶段（若 savepoint load 返回 phase，会自动覆盖）
- `activation_code`：可选；用于 deep link 到指定激活码
- `thread_id`：可选；用于 deep link 到指定线程
- `savepoint_id`：可选；配置后会先调用 `/api/v1/admin/savepoints/load`

当配置了 `savepoint_id` 时，需要设置以下环境变量之一：

- `L2_ADMIN_BEARER_TOKEN`
- `L2_ADMIN_TOKEN`

## 功能目的（为什么有这些参数）

- `--dry-run`：先看命令不执行，避免误操作真实环境
- `--filter`：快速聚焦单一问题域（如 rumination）
- `--fail-fast`：回归门禁场景下尽快失败返回
- `--continue-on-error`：夜间巡检场景下尽可能收集全量失败信息
