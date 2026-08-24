# 0823-全部场景切 deepseek-v4-pro 思维链 + max_tokens 额度整治

> 日期：2026-08-23
> 关联：GitHub issue #82（AI 回复截断/重复 + balance 判定 JSONDecodeError，8-21 修复）、commit 2f7763c（v1.6.0 微调）
> 性质：配置口径变更（效果优先，成本不敏感）+ 存量小额度 max_tokens 集中排雷

## 背景与决策

维护者决策：**全部 LLM 场景统一使用 deepseek-v4-pro + 思维链模式，先保证效果，成本不作为约束**。

此前口径（2026-08-19 引入的场景分流）：scene=chat（前四 phase values/strengths/interests/purpose 的对话+结论卡）→ `deepseek-v4-flash`；rumination / report / team_analysis / 未知 → `deepseek-v4-pro`。本次将 chat 场景也切到 pro，flash 不再使用（分流机制保留，回退只改 `.env` 一行）。

## 每轮对话用什么模型 / 什么模式（切换前 → 切换后）

| 环节 | scene | 切换前 | 切换后 |
|---|---|---|---|
| 前四轮对话流式回复 | chat | v4-flash，非思维链，max_tokens=8192 | v4-pro，思维链，max_tokens=8192 |
| 前四轮结论卡生成 / pending 判定 | chat | flash，非流式，**不传 max_tokens（默认 4096）** | pro，非流式，max_tokens=8192 |
| 第五轮 rumination（v4 combo-chat 等） | rumination | v4-pro 思维链，但多处小额度 450~1500 | v4-pro 思维链，统一 8192 |
| 平衡点判定（balance judge） | rumination | pro，2000/8000 逐次放大 | pro，8000/16000 |
| 报告生成 | report | pro，65536 | 不变 |
| 团队分析 | team_analysis | pro，4000 | pro，16384 |

思维链生效条件（`openai_provider._is_reasoning_model`）：`LLM_THINKING_ENABLED=True` 且模型名含 `reasoner` 或 `v4-pro`；`.env` 中 `LLM_THINKING_ENABLED=True` 原本已开。思维链模式下不传 temperature（API 侧静默忽略），流式 yield `think_start/think_chunk/think_end` 控制帧与正文分离。

## 历史问题的根因分析（本次一并回答）

### 1. 前四轮结论卡偶尔出不来

分层原因，历代修复：

- **状态机/链路设计**（4 月）：手动确认稿与自动出卡双链路并行，状态分支复杂导致卡片悬挂。收敛为单一自动出卡链路（`wiki/开发文档/4.20-结论卡状态机梳理与优化建议.md`、`4-26最新出卡链路.md`），生成失败降级回退 pending draft。
- **动态注入扰动**（7 月，commit 0a516c4）：nudge/rejected_injection/pending_addon 等零散注入导致行为不稳 + prefix cache 命中率波动 → 统一为 `build_conclusion_state_injection` 放 system prompt 末尾。
- **工程加固**（现行）：pending 判定超时 20s、结论生成超时 25s，超时降级。

### 2. rumination 重复同一句话

- **同族问题的正式记录**在 purpose 阶段（`wiki/开发文档/5-21todo文档.md` R5-21-03）：模型无结构化进度记录、每轮把对话当"第一条经历" → 修法是 `purpose_progress` 持久化 + 每轮注入进度块，已确认经历不得再问。
- rumination 侧：提示词层有"不要整段复读"条款；架构层根治见 **ADR-0015**——v4 主对话 LLM 同时当咨询师+书记员+裁判，三重职责互相干扰、prompt 补丁层层叠加导致行为不稳定（复读/漂移），判定移交独立后台 AI。
- 另见 #82 问题 2：历史窗口仅最近 30 轮 + 历史含 AI 自身回复 + 每轮重复注入摘要/draft，诱发自我复述（未调参，观察项）。

### 3. 输出不全 / 截断（#82 已修主流，本次扫尾）

- **根因**：不显式传 `max_tokens` 时 DeepSeek 服务端默认 **4096**；可见回复与 `[STATE_JSON]` 协议块共享额度，聊长后从句中硬截断（`finish_reason=length`，此前无人检查）。**"不传 max_tokens"不等于"不限制"，恰恰相反**。
- **思维链放大效应**：v4-pro 的 max_tokens 是**思维链+正文合计上限**，小额度会被 reasoning 耗尽导致 `content` 为空（balance judge `max_tokens=400` → JSONDecodeError char 0，#82 问题 3 即此）。
- #82 修了主对话流（8192）、balance judge（2000/8000）、报告（65536），但 rumination 里还残留一批 450~1500 的小额度，且结论卡/pending 判定链路根本没传 max_tokens —— 本次集中整治。

## 本次改动清单

### 配置（.env，不进 git）

- `LLM_FLASH_MODEL=deepseek-v4-pro`（取消注释并改值）→ chat 场景也走 pro；回退只需改回 `deepseek-v4-flash`
- `LLM_THINKING_ENABLED=True`（原有，未动）
- ⚠️ **生产注意**：`.env.prod`（生产服务器）未设置该项，上线时需在 `.env.prod` 同步加 `LLM_FLASH_MODEL=deepseek-v4-pro`，否则生产 chat 场景仍是 flash

### max_tokens 统一放大（思维链会吃额度，小额度必炸）

| 文件 | 调用点 | 原值 → 新值 |
|---|---|---|
| `simple_chat_routes.py` | rumination 开场白流 | 600 → 8192 |
| `simple_chat_routes.py` | step3 combo 开场引导（2 处） | 600 → 8192 |
| `simple_chat_routes.py` | step3 matrix/proto 生成（3 处） | 1500 → 8192 |
| `simple_chat_routes.py` | pending 判定（2 个 chat + 1 个 stream） | **未传(4096)** → 8192 |
| `core/dimension_completion_checker.py` | 结论卡判定 + 生成 | **未传(4096)** → 8192 |
| `rumination_v4_routes.py` | v4 combo-chat 主对话流 | 800 → 8192 |
| `rumination_v4_service.py` | summarizer | 600 → 8192 |
| `rumination_v4_service.py` | `BALANCE_JUDGE_MAX_TOKENS` | (2000, 8000) → (8000, 16000) |
| `rumination_neg_gate.py` | neg gate 质检 | 800 → 8192 |
| `rumination_finalize.py` | 收尾语 | 450 → 8192 |
| `rumination_hypothesis_service.py` | 假设生成 | 500 → 8192 |
| `rumination_init_greeting.py` | 入口问候（默认值） | 500 → 8192 |
| `team_analysis_service.py` | 团队分析报告 | 4000 → 16384 |

### 测试与文档

- `test/backend/test_llm_scene_model_split.py`：默认值断言增加 fixture 屏蔽 `.env` 覆盖（否则 .env 设了 LLM_FLASH_MODEL 后断言代码默认值会失败）
- `AGENTS.md`：模型场景分流一节更新为新口径 + "新增 LLM 调用点必须显式传大额度 max_tokens" 的规范

## 验证

- 改动文件全部 `py_compile` 通过
- `test_llm_scene_model_split.py` + `test_llm_usage.py` 26 个测试全过
- 实测：`scene=chat → deepseek-v4-pro`、`scene=rumination → deepseek-v4-pro`，`LLM_THINKING_ENABLED=True`
- 4 个测试失败（neg_gate / step3 提示词相关）经 git stash 对比确认为历史遗留，与本次无关
- 生效方式：`./start.sh restart backend`

## 后续观察项

- 全场景 pro + 思维链后，token 成本与首字延迟上升，可在 admin「埋点与 Token 统计」页观察分场景用量
- 关注日志 `[llm_stream] 回复被 max_tokens 截断`（finish_reason=length），若出现说明 8192 仍不够再调
- 对话重复问题（#82 问题 2）换 pro 后观察是否缓解；未缓解再考虑 `frequency_penalty` 或调大历史窗口
