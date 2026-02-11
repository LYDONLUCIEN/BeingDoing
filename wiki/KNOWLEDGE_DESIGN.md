# 知识库与检索设计说明

本文回答：渐进式加载的 CSV 知识库（喜欢的事、擅长的事、重要的事等）是否已有「知识检索」能力、当前实现状态，以及如何在不破坏解耦、知识集中的前提下，设计「何时必须查知识 / 何时由 Agent 自判」及如何约束 Agent 的查知识逻辑。

---

## 一、当前实现状态

### 1.1 已实现的部分

| 能力 | 位置 | 说明 |
|------|------|------|
| **知识库加载** | `app/core/knowledge/loader.py` | `KnowledgeLoader` 从项目根目录加载 `重要的事_价值观.csv`、`喜欢的事_热情.csv`、`擅长的事_才能.csv`、`question.md`，带内存缓存，支持按类别渐进加载（values/interests/strengths/questions）。 |
| **知识检索** | `app/core/knowledge/search.py` | `KnowledgeSearcher` 基于关键词匹配，对价值观/兴趣/才能/问题做搜索，返回带分数的结果。 |
| **检索工具** | `app/core/agent/tools/search_tool.py` | 已注册的 `search_tool`：Agent 在 **reasoning** 节点输出 `action=use_tool, tool_name=search_tool, tool_input={query, category}` 时，**action** 节点会调用该工具，把检索结果写入 `tool_results`，供 **observation** 使用。 |

结论：**「知识检索」已实现**，形式是「Agent 通过推理决定是否调用 search_tool」，没有单独的「知识检索节点」，也没有「某类问题必须查知识」的规则。

### 1.2 当前流程

- 用户输入 → **reasoning**（决定 action：use_tool / respond / guide）→ **action**（若 use_tool 则调用 ToolRegistry 中的 search_tool）→ **observation**（根据工具结果决定是否继续或给出最终回答）。
- 是否查知识完全由 **reasoning** 的 LLM 输出决定；提示词里只写了「可以使用 search_tool、guide_tool 等」，没有明确「什么情况必须查 / 什么情况可自判」的规则。

### 1.3 与 CSV 表头的对应关系（实现时需核对）

- `loader.py` 中使用的列名与当前 CSV 表头可能不一致，需要在实现/联调时统一：
  - 价值观 CSV：代码用 `名称`、`定义`，实际文件为 `价值观`、`定义`。
  - 热情 CSV：代码用 `名称`，实际为 `领域`。
  - 才能 CSV：代码用 `名称`、`优势`、`劣势`，实际为 `才能`、`成为长处`、`成为短处`。
- 建议：**知识源配置（文件路径、列名映射）** 放在 **domain 或统一配置** 中，loader 只做「按配置加载」，便于后续加新 CSV 且保持知识集中。

---

## 二、设计目标（解耦 + 知识集中）

1. **解耦**：知识检索能力与具体业务解耦，可复用到其他场景；图结构上可以是「工具调用」或「独立知识节点」，由配置/策略决定。
2. **知识集中**：哪些数据源、哪些类型的问题必须/优先查知识，应由 **domain 或独立知识配置** 维护，而不是散落在各节点提示词里。
3. **可扩展**：未来更多 CSV/数据源时，通过配置或注册方式接入，不破坏现有图与节点接口。

---

## 三、设计方案概述

### 3.1 是否要「专门的知识检索节点」？

- **方案 A：保持现状（仅 search_tool）**  
  - 不增加新节点，继续由 reasoning → action 调用 search_tool。  
  - 优点：图简单，逻辑清晰。  
  - 增强点：在 **domain** 中明确「何时必须查 / 何时可自判」的规则，并通过 **提示词 + 可选的结构化字段** 约束 reasoning 的输出。

- **方案 B：增加「知识检索」节点**  
  - 在图中增加独立节点（例如 `knowledge_node`）：根据当前步骤或用户意图，**先查知识库**，把结果写入 state（如 `context["knowledge_snippets"]`），再进入 reasoning；或作为「reasoning 之前/之后的固定一步」。  
  - 优点：适合「某类问题一律先查再答」的策略；检索逻辑集中在一个节点，便于做缓存、限流、审计。  
  - 缺点：图多一个节点，需要明确该节点与 reasoning/action 的先后关系（例如 用户输入 → knowledge_node → reasoning → action → observation）。

推荐：**先采用方案 A**，用「规则 + 提示词 + 可选 need_knowledge 字段」约束 Agent；若后续出现大量「必须先查再答」的场景，再引入方案 B 的独立 knowledge 节点，两者可并存（例如：规则命中则走 knowledge_node，否则走 reasoning 自判是否用 search_tool）。

### 3.2 什么类型的问题「必须查知识」 vs 「由 Agent 自判」？

建议在 **domain** 中集中定义（例如 `app/domain/knowledge_rules.py` 或配置）：

- **必须查知识**（主动查）  
  - 当前步骤与「价值观/才能/兴趣」强相关，且用户问题属于「列举/选择/解释专业概念」时，例如：  
    - 「有哪些价值观？」「才能里有什么选项？」「喜欢的事有哪些领域？」  
  - 规则形式：按 `current_step` + 意图关键词/意图分类 匹配，命中则 **强制** 本轮先执行 search_tool（或走 knowledge_node），再生成回答。  
  - 意图可由简单关键词列表或小模型分类得到，结果写回 state，供 reasoning/observation 使用。

- **由 Agent 自判**  
  - 开放式问答、澄清、引导类（如「我不太确定」「帮我分析一下」），不强制查知识；由 reasoning 根据提示词和结构化输出（见下）决定是否调用 search_tool。  
  - 自判时通过 **提示词规则 + 可选结构化字段** 约束「何时应查」：例如仅当用户问题涉及具体概念、选项、定义时，才输出 use_tool + search_tool。

这样：**规则集中、易维护**；框架层只负责「按 state/context 执行检索或调用工具」，不写死业务规则。

### 3.3 如何约束 Agent「自判时何时查知识」？

- **提示词约束（推荐优先）**  
  - 在 **domain 的 reasoning 提示词**（如 `prompts/templates/reasoning.yaml`）中增加一小节，例如：  
    - 「当用户问题涉及具体价值观/才能/兴趣的名称、定义、选项或需要从知识库列举/核实内容时，应使用 search_tool；若仅为一般性讨论、澄清或引导，可不必查知识。」  
  - 保持提示词在 domain 内，便于专业人士修改，且不增加新节点或复杂分支。

- **结构化输出约束（可选增强）**  
  - 在 `ReasoningDecision` 中增加可选字段，例如 `need_knowledge: bool` 或 `intent: "lookup" | "discuss" | "guide"`。  
  - reasoning 节点解析 LLM 输出后：若 `need_knowledge=True` 且当前未命中「必须查」规则，仍可强制补一次 search_tool（或在 action 节点中根据该字段决定是否先查再答）。  
  - 这样既保留「Agent 自判」，又可在代码层做一层兜底约束，避免该查未查。

- **不推荐**  
  - 在框架层写死「某类问题必须查知识」的具体关键词或业务规则；应放在 domain 或配置中。

---

## 四、推荐落地步骤（保持解耦、知识集中）

1. **知识源与 loader 配置集中**  
   - 在 **domain**（或统一配置）中定义：  
     - 知识库文件列表（如三个 CSV + question.md）及路径；  
     - 各 CSV 的列名映射（名称/定义/优势/劣势 等），供 loader 使用。  
   - 修正 `KnowledgeLoader` 与当前 CSV 表头一致（或通过配置读取列名），便于后续加新 CSV。

2. **「何时必须查」规则集中**  
   - 在 **domain** 中新增如 `knowledge_rules.py` 或 YAML：  
     - 按 `current_step` + 意图类型（如「列举」「选一项」「解释某概念」）定义「必须查知识」的规则。  
   - 在 **reasoning 之前**（或图入口）根据用户输入 + current_step 判断是否命中「必须查」：  
     - 若命中，可：  
       - 直接在本轮先执行一次 search_tool（或在 action 前插入一次检索），把结果写入 `context["knowledge_snippets"]`，再交给 reasoning；或  
       - 引入独立 knowledge_node，仅在被规则命中时执行，结果写入 state，再进入 reasoning。  
   - 这样「什么类型的问题必须查」全部在 domain 维护，框架只负责执行。

3. **「自判查知识」的约束**  
   - 在 **domain 的 reasoning 提示词** 中增加「何时应使用 search_tool」的简短规则（如上），并保持 action 的 tool 列表包含 search_tool。  
   - 可选：在 `ReasoningDecision` 中增加 `need_knowledge` 或 `intent`，在 action 节点中若发现应查未查（例如 need_knowledge=True 但未调用 search_tool），可补一次检索，逻辑集中在 action 或单独小函数中，便于维护。

4. **渐进式加载与扩展**  
   - 新 CSV 加入时：在 domain 的「知识源配置」中增加条目，在 loader 中按配置加载（或按类别懒加载），search_tool 的 category 与 loader 的类别对齐。  
   - 检索实现（关键词 / 向量）保留在 `app/core/knowledge/`，与业务规则分离；domain 只决定「查什么、何时查」。

---

## 五、小结

| 问题 | 结论 |
|------|------|
| 知识检索是否已实现？ | 已实现：KnowledgeLoader + KnowledgeSearcher + search_tool，Agent 通过 reasoning 决定是否调用 search_tool。 |
| 是否有「专门的知识检索节点」？ | 当前没有；可选后续增加 knowledge_node，与「规则驱动的必须查」配合使用。 |
| 如何保证解耦、知识集中？ | 知识源配置与「必须查/自判」规则放在 domain（或统一配置）；框架只负责执行检索与工具调用。 |
| 什么类型必须查 vs 自判？ | 在 domain 用规则定义「强相关步骤 + 列举/选择/解释类」为必须查；其余为 Agent 自判。 |
| 如何约束 Agent 自判？ | 提示词中明确「何时应使用 search_tool」；可选增加 ReasoningDecision.need_knowledge 等做兜底。 |

按上述步骤落地，即可在保持架构解耦、知识集中的前提下，支持「渐进式加载的 CSV 知识库 + 快速检索」，并清晰区分「必须查知识」与「Agent 自判查知识」的逻辑。
