# 业务领域层（Domain）

本目录集中存放与业务相关的**领域知识**，便于专业人士修改，无需到其他文件查找。

## 目录说明

- **`steps.py`**  
  流程步骤定义（与 flowchart 一致）：
  - `DEFAULT_CURRENT_STEP`：默认当前步骤
  - `FLOW_STEPS`：步骤列表（id、name、description、order），供 `/formula/flowchart` 与前端展示
  - `STEP_TO_CATEGORY`：步骤 id → 问题/知识分类（values/strengths/interests），供 question_service、guide_tool 等使用
  - `EXPLORATION_STEP_IDS`：仅「探索类」步骤 id 列表，供工具 enum 等使用

- **`prompts/`**  
  领域提示词（智能体节点用）：
  - `templates/*.yaml`：reasoning、observation、guide 等节点系统提示，可用 Jinja2 注入 `current_step`、`step_summary`、`user_input`、`tool_output`、`knowledge_snippets` 等
  - 节点通过 `get_reasoning_prompt(ctx)`、`get_observation_prompt(ctx)`、`get_guide_prompt(ctx)` 获取内容，仅此一层调用，无多层嵌套

- **`knowledge_config.py`**  
  知识源配置（单点维护）：
  - `KNOWLEDGE_FILES`：知识库文件名（价值观/热情/才能 CSV 及 question.md）
  - `COLUMNS_*`：各 CSV 的列名映射（内部字段名 → 实际表头），供 `KnowledgeLoader` 使用
  - `get_knowledge_config()`：返回供 loader 注入的 config，便于扩展新 CSV

- **`knowledge_rules.py`**  
  知识检索规则（何时必须查知识、何时由 Agent 自判）：
  - `MUST_QUERY_KEYWORDS`：触发「必须查知识」的用户表述关键词（如「有哪些」「列举」「什么是」）
  - `STEPS_REQUIRING_KNOWLEDGE`：与知识库强相关的步骤
  - `should_force_knowledge_query(state)`：是否本轮预填知识库片段（reasoning 节点用）
  - `get_search_category_for_step(current_step)`：当前步骤对应的知识分类（values/strengths/interests）

## 修改指南

- **调整流程步骤**：只改 `steps.py`（步骤名、顺序、分类映射）。
- **调整节点提示词**：只改 `prompts/templates/*.yaml`；若需新增变量，在 loader 的 `get_*_prompt` 传入的 context 中增加即可。
- **知识源与列名**：只改 `knowledge_config.py`（文件路径、列名映射）；新增 CSV 时在此增加条目，loader 按 config 加载。
- **何时必须查知识**：只改 `knowledge_rules.py`（关键词、步骤列表）；reasoning 节点会据此预填 `knowledge_snippets`。
- **公式文案**（如「喜欢的事 × 擅长的事 = 真正想做的事」）：仍在 `api/v1/formula.py` 的 `get_formula()` 中，步骤 id 与 domain 一致即可。

## 与框架的关系

- **智能体框架**（`app/core/agent/`）：state、graph、context_manager、config、models、nodes、tools 等与具体业务解耦，可复用到不同场景。
- **本层（domain）**：仅被「节点」和「API/服务」引用，用于注入步骤与提示词；框架层不依赖 domain，保持可替换。
