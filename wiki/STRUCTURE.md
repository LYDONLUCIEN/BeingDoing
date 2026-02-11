# 项目结构说明：框架与领域分离

为便于复用与维护，智能体相关代码分为**框架层**与**领域层**，调用逻辑保持不变。

## 1. 框架层（可复用到不同场景）

**位置**：`src/backend/app/core/agent/`

- **state.py**：AgentState 定义（messages / inner_messages / logs / context / current_step 等），与业务无关。
- **graph.py**：图结构（reasoning → action → observation → user_agent）、条件边、create_initial_state；current_step 默认值从 domain 读取。
- **config.py**：AgentRunConfig（use_user_agent_node、max_iterations、compress_context 等）。
- **context_manager.py**：消息级上下文压缩（按条数折叠早期消息），与业务无关。
- **models.py**：ReasoningDecision、ObservationDecision 等结构化输出模型，与业务无关。
- **nodes/**：reasoning、action、observation、guide、user_agent；**提示词内容**从 domain 获取（get_*_prompt），节点内仅保留极短通用 fallback。
- **tools/**：工具基类与注册表、search_tool / guide_tool 等；**步骤与分类映射**从 domain 读取（STEP_TO_CATEGORY、EXPLORATION_STEP_IDS）。

框架层不依赖具体业务文案与流程步骤，只依赖「步骤 id」「提示词字符串」等由外部注入（domain）。

## 2. 领域层（业务知识集中）

**位置**：`src/backend/app/domain/`

- **steps.py**：流程步骤单点维护  
  - DEFAULT_CURRENT_STEP、FLOW_STEPS、STEP_TO_CATEGORY、EXPLORATION_STEP_IDS  
  - 供 formula API、chat、sessions、create_initial_state、question_service、guide_tool 等使用。
- **prompts/**：领域提示词  
  - templates/*.yaml（reasoning、observation、guide）  
  - 对外仅暴露 get_reasoning_prompt(ctx)、get_observation_prompt(ctx)、get_guide_prompt(ctx)，节点直接调用，一层读取，无多层嵌套。

专业人士只需改 **domain/** 下的 steps 与 prompts，无需到其他文件查找。

## 3. 调用关系（不变）

- API（chat、formula、sessions）→ 使用 domain 的默认步骤与流程数据；创建 initial_state 时传入 current_step（或用 domain 默认）。
- create_agent_graph(config) → 创建图；create_initial_state(...) 的 current_step 默认来自 domain。
- 节点 reasoning / observation / guide → 调用 domain.prompts.get_*_prompt(context) 获取系统提示；短 fallback 保留在节点内。
- 工具 guide_tool、服务 question_service → 使用 domain 的 STEP_TO_CATEGORY、EXPLORATION_STEP_IDS。

## 4. 可读性与性能

- **短、通用提示**：保留在节点内 1～2 行 fallback，不强行迁到 YAML。
- **领域提示**：仅一层「domain.prompts.get_*_prompt(ctx) → YAML 渲染」，无多层嵌套读取。
- **步骤与分类**：统一从 domain.steps 读取，避免在多个文件中重复定义。
