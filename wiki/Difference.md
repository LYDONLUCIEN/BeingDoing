# 智能体框架对比：reference/new_agent vs src/backend

本文对比 **reference/new_agent**（参考框架）与 **src/backend**（当前项目）的智能体设计，并给出可改进点与实施计划。

---

## 一、整体架构对比

| 维度 | reference/new_agent | src/backend（当前） |
|------|---------------------|----------------------|
| **图结构** | 多节点、显式路由（initial_setup → front_agent ⇄ planner_agent → db_writer / note_writer / knowledge_node） | 固定循环：reasoning → action → observation → (条件) reasoning 或 END |
| **状态模型** | 消息双轨（messages / inner_messages）、队列（db_records、notes）、logs、plan | 单轨消息 + context、tool_results、reasoning、迭代计数、步骤轮数 |
| **路由方式** | Planner 输出结构化决策（Pydantic），用 `Command(goto=...)` 显式跳转 | 条件边 `should_continue` 根据 state 字段决定 continue/end |
| **提示词** | 独立 YAML 模板 + Jinja2 渲染，可注入 theory_snippets、user_history_summary | 硬编码在节点内的 Python 字符串 |
| **上下文压缩** | 独立 SimpleContextManager：按消息数截断 + 早期消息折叠为 summary | 无独立压缩；observation 内维护 summaries/step_rounds，无消息级压缩 |
| **工具层** | 工具为「函数」(state, config, …) → (state, result)，由专用节点调用 | 工具为「类」+ 注册表，由 action 节点统一根据 reasoning 结果调用 |
| **前端对接** | messages 对用户可见，logs 做进度条；Planner 不直接对用户说话 | final_response + tools_used；无 logs，无「进度」语义 |

---

## 二、状态设计差异

### reference/new_agent（AgentState）

- **messages**：对用户可见的消息（前端展示）。
- **inner_messages**：供 LLM/Planner 使用的内部消息，可与 messages 同步或扩展。
- **logs**：过程日志，用于前端进度/调试。
- **plan / current_step / context**：Planner 写入的结构化信息。
- **db_records / notes**：待处理队列；**db_records_written**：已写入记录（可回溯）。
- **completed**：会话是否结束。
- 使用 LangChain `AnyMessage` + `add_messages` 做消息归并。

### src/backend（AgentState）

- **messages**：LLMMessage 列表，未区分「对用户可见」与「内部」。
- **context**：包含 reasoning、summaries、profile、step_rounds、limits 等。
- **current_step**：固定枚举（values_exploration, strengths_exploration 等）。
- **tools_used / tool_results**：工具调用历史。
- **iteration_count / should_continue / final_response / error**：控制循环与输出。

**主要差别**：参考框架明确区分「用户可见消息」与「内部消息」，并有 logs、队列式持久化（db_records → db_writer）；当前项目是单轨消息 + 控制字段，无 logs、无队列式写库/写笔记。

---

## 三、图与节点对比

### reference/new_agent

- **initial_setup**：初始化 session_id、logs，标准化状态。
- **front_agent**：面向用户应答，写 messages/inner_messages；可先做上下文压缩。
- **planner_agent**：不直接对用户说话，输出 `PlannerDecision`（next, ask_user, db_record, note, final_answer 等），用 `Command(update=state, goto=...)` 路由到 front_agent / db_writer / note_writer / knowledge_node / __end__。
- **db_writer / note_writer**：从队列取一条，调用工具，写回 state，再回到 planner_agent。
- **knowledge_node**：查知识库，结果写入 inner_messages，回到 planner_agent。

特点：**Planner 驱动**，一次决策决定下一步是「问用户」「写库」「写笔记」「查知识库」还是「结束」。

### src/backend

- **reasoning**：根据 current_step、summaries、user_input 决定 action（use_tool / respond / guide），写 context["reasoning"]。
- **action**：根据 reasoning 调用 ToolRegistry 中的工具，或直接写 final_response。
- **observation**：处理 tool_results，用 LLM 分析是否继续，更新 summaries/profile/contradictions/step_rounds。
- **guide**：独立入口，用于「主动引导」用户（当前在 API 层通过 GuideService 调用，未接入图内）。

特点：**ReAct 式循环**（推理 → 行动 → 观察 → 再推理），由 observation 的 should_continue 与 step_rounds 控制深度；无「前台应答 vs 背后规划」的角色分离。

---

## 四、提示词与上下文

| 项目 | reference/new_agent | src/backend |
|------|---------------------|-------------|
| 提示词存储 | prompts/templates/*.yaml，Jinja2 渲染 | 节点内 Python 字符串 |
| 注入内容 | theory_snippets、user_history_summary | current_step、step_summary、user_input、tools_used |
| 上下文压缩 | SimpleContextManager：消息数超阈值则早期消息折叠为一条 summary | 无；仅有 summaries 按步骤的文本截断 |

参考框架便于运维和迭代提示词（改 YAML 即可）；当前项目改提示需要改代码。

---

## 五、工具层对比

- **reference**：工具是**异步函数** `(state, config, ...) -> (state, result)`，由**专用节点**（db_writer、note_writer、knowledge_node）调用；节点与 IO 解耦，易于替换实现。
- **src/backend**：工具是**类**（BaseAgentTool）+ **ToolRegistry**，由 **action 节点**根据 reasoning 的 tool_name 统一调用；扩展新工具需注册，适合「LLM 选工具名」的 ReAct 模式。

两者各有优劣：参考框架更贴近「流程节点 + 专用工具」；当前项目更贴近「通用工具池 + 推理选择」。

---

## 六、可改进点与实施计划

### 6.1 高优先级

1. **引入「用户可见消息」与「内部消息」分离（可选）**
   - 在 AgentState 中增加 `inner_messages` 或明确约定 `messages` 中哪些仅内部使用。
   - API 返回给前端的只从「用户可见」列表取，避免把中间推理、工具结果直接暴露。
   - **实施**：扩展 state 定义与 chat API 的返回结构；observation/reasoning 写入内部通道。

2. **提示词外置为 YAML + 渲染**
   - 建立 `prompts/templates/`（或等价目录），将 reasoning、observation、guide 等提示词迁入 YAML。
   - 使用 Jinja2 注入 current_step、step_summary、user_history_summary、theory_snippets 等。
   - **实施**：新增 PromptLoader，与 reference 的 loader 对齐；各节点改为从 loader 取模板并渲染。

3. **结构化决策输出（Planner/Reasoning）**
   - 将 reasoning 节点的输出改为 Pydantic 模型（如 ReasoningDecision：action, tool_name, tool_input, response, reasoning），替代手写 JSON 解析。
   - 降低解析错误率，便于扩展字段（如 confidence、next_step 等）。
   - **实施**：在 reasoning_node 内用 model_validate 解析 LLM 输出；action_node 只读结构化结果。

### 6.2 中优先级

4. **上下文压缩（消息级）**
   - 当 messages 或 inner_messages 长度超过阈值时，将较早消息折叠为一条「summary」消息，再送入 LLM。
   - 可复用 reference 的 SimpleContextManager 思路，或与现有 context["summaries"] 结合（按步骤的摘要保留，再增加全局消息压缩）。
   - **实施**：新增 ContextManager，在 reasoning 或 observation 入口调用 maybe_compress。

5. **过程日志（logs）**
   - 在 state 中增加 `logs: List[Dict]`，在各节点追加「当前步骤、结果摘要、错误」等，便于前端展示进度与调试。
   - **实施**：AgentState 增加 logs；reasoning/action/observation 在关键步骤 append log；chat API 在响应中可选返回 logs。

6. **持久化队列与专用写节点（可选）**
   - 若需要「先积累再写库/写笔记」，可引入 db_records/notes 队列 + db_writer/note_writer 节点，由「规划节点」往队列推，写节点消费；与 reference 行为一致。
   - **实施**：在状态中增加 db_records、notes；增加 planner 或 reasoning 输出「写库/写笔记」意图与 payload；新增 db_writer/note_writer 节点并在图中连接。

### 6.3 低优先级 / 可选

7. **图 API 与路由方式**
   - 若希望更灵活的「多步路由」（如一次推理后可选：问用户 / 查知识库 / 写笔记 / 结束），可考虑引入类似 `Command(goto=...)` 的显式路由，或增加子图（如 planner 子图）。
   - 当前固定 reasoning→action→observation 循环已满足「工具 + 深度控制」需求，可在需要时再演进。

8. **guide 节点入图**
   - 将「主动引导」从独立 API + GuideService 改为图内节点（例如由条件边「需要引导时」进入 guide_node），可统一状态与流程。
   - **实施**：在 observation 或 reasoning 中增加「需要引导」分支，条件边指向 guide_node，guide_node 再回到 reasoning 或 END。

9. **工具层统一接口（可选）**
   - 若希望与 reference 一致，可将部分工具改为 `(state, config, ...) -> (state, result)`，由专用节点调用；其余保留 Registry 供 action 使用，形成「混合」模式。

---

## 七、总结表

| 改进项 | 目标 | 参考来源 |
|--------|------|----------|
| 消息双轨 + logs | 前端只展示用户相关消息与进度 | new_agent state + graph |
| 提示词 YAML + 渲染 | 可维护、可注入上下文 | new_agent prompts/ |
| 结构化 Reasoning 输出 | 稳定解析、易扩展 | new_agent PlannerDecision |
| 上下文压缩 | 控制 token、避免截断突兀 | new_agent context_manager |
| 持久化队列 + 写节点 | 解耦「规划」与「写库/写笔记」 | new_agent db_writer/note_writer |

当前项目在「ReAct 循环 + 步骤深度控制 + 摘要/矛盾检测」上已有自己的设计；上述改进可在不推翻现有图的前提下，逐步吸收 reference 的优点，提升可维护性和可观测性。

---

## 八、双轨与等待时间说明（已实现）

- **思考链（后端）**：reasoning → action → observation 循环，只写 `inner_messages`、`context`、`logs` 和 `final_response`，**不直接写用户可见的 messages**。
- **用户侧输出（前端对接）**：图结束前经过 **user_agent** 节点，该节点**仅**读取思考链的 `final_response`（或 `error`），写入对用户可见的 `messages`。  
  因此「用户每次拿到的都是思考 Agent 后端的结果」，前端只消费 `messages` 和可选 `logs`，无需区分内部状态。
- **等待时间**：当前实现是「同步一轮」：整条思考链跑完后再执行 user_agent，所以**用户需等待整轮思考结束**才能看到一条回复。  
  若后续要缩短体感等待，可考虑：  
  1）**流式**：思考链每完成一步向通道推送 `logs`，前端先展示进度，最后再流式或一次性推送 user_agent 的回复；  
  2）**分步返回**：在 observation 中允许「中间回复」写入 messages（需与产品约定何时算「最终回复」）。  
  架构上已做到「思考链与用户侧输出分离」，便于后续加流式或分步策略。

---

## 九、灵活调用方式（已实现）

- **AgentRunConfig**：`use_user_agent_node`（是否在结束时经过 user_agent）、`max_iterations`、`compress_context`、`max_rounds_per_step` 等可配置。
- **create_agent_graph(config)**：  
  - `use_user_agent_node=True`（默认）：observation 结束 → **user_agent** → END，适合正常对话，前端从 `state["messages"]` 取回复。  
  - `use_user_agent_node=False`：observation 结束 → END，仅跑思考链，适合调试或由调用方自行把 `final_response` 转成用户消息。
- **API**：`POST /chat/messages` 使用默认 config（含 user_agent），返回 `data.response` 与 `data.logs`；后续若需要「仅思考」接口，可传参并使用 `AgentRunConfig(use_user_agent_node=False)` 构建图。
