# BeingDoing 项目 - AI对话提示词与对话逻辑分析

> 分析时间：2026-03-19
> 更新时间：2026-03-20（已同步.cursor架构变更：Rumination阶段、锚点摘要、Widget体系、并发锁）

---

## 一、AI对话架构概览

项目当前使用**双模式架构**：

| 模式 | 实现方式 | 状态 | 适用场景 |
|-----|---------|------|---------|
| **简单模式** | 直接LLM调用 + 长system_prompt | ✅ 主要使用 | 快速引导、标准化流程 |
| **完整模式** | LangGraph ReAct智能体 | ⚠️ 备用 | 深度探索、复杂推理 |
| **Rumination** | Python实现 + Widget交互 | 🆕 新增 | 第五步沉淀、表格筛选 |

---

## 二、简单模式对话逻辑（当前主要使用）

### 2.1 核心文件

```
src/backend/app/api/v1/simple_chat.py          # API入口
│                                               # 新增：rumination分支、锚点摘要、并发锁
src/backend/app/utils/admin_mock.py            # 新增：Mock数据管理（跳步测试）
src/backend/app/utils/context_refiner.py       # 新增：锚点摘要生成（规划中）
```

### 2.2 对话流程

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           简单模式对话流程                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. 初始化阶段                                                               │
│     ├─→ 验证激活码                                                          │
│     ├─→ 加载历史消息                                                        │
│     ├─→ 构建 system_prompt                                                  │
│     │      ├─ 阶段定义（values/strengths/interests/purpose）               │
│     │      ├─ 题目库（随机抽取6题）                                         │
│     │      ├─ 用户基本信息（调研问卷）                                      │
│     │      └─ 上一轮结果（values→空, strengths→values结果, ...）          │
│     └─→ LLM生成开场问题                                                     │
│                                                                             │
│  2. 对话阶段                                                                 │
│     ├─→ 接收用户输入                                                        │
│     ├─→ 加载历史（当前thread）                                              │
│     │      └─→ 文件级并发锁（防止多请求同时写丢失）                        │
│     ├─→ 构造 messages: [system, anchor_summary, ...recent_history, user]   │
│     │      └─→ 锚点摘要 + 最近20轮（替代完整历史）                         │
│     ├─→ 流式调用 LLM.chat_stream()                                         │
│     └─→ 保存 assistant 回复                                                │
│                                                                             │
│  3. 完成判断                                                                 │
│     ├─→ 检测 "完成" 关键词                                                  │
│     ├─→ 触发 dimension_conclusion                                          │
│     ├─→ 生成答题卡                                                          │
│     └─→ 用户确认后锁定阶段                                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 System Prompt 结构

简单模式为每个阶段构建了完整的system prompt：

#### Values 阶段 Prompt 结构

```yaml
角色定义:
  - 专业的职业规划咨询师
  - 拥有逻辑思辨、内观内省、心理治疗背景

目标:
  - 帮助用户发现并确认对其职业发展最重要的5个价值观关键词

咨询流程（8步）:
  1. 开场提问: 询问用户心中最重要的5个价值观关键词
  2. 记录初始答案: 记录用户自述的关键词
  3. 深度提问探索: 
     - 每次只提一个问题
     - 问题可涉及生活、过往经历、未来畅想
     - 追问引导用户深入思考
  4. 记录关键词: 标记为"探索发现"
  5. 整合与确认: 对比初始答案和探索发现
  6. 收敛判断: 直到无法再发现新关键词（或达10题上限）
  7. 排序与整合: 引导用户排序，合并相近词
  8. 最终确认: 呈现最终5个价值观关键词

重要准则:
  - 引导而非灌输
  - 一次一问
  - 完整收敛（不能凑够5个就停止）
  - 完成即引导答题卡

输入变量:
  - question_bank: 随机抽取的6个题目
  - basic_info: 来访者基本信息
  - prior_context: 上一轮咨询结果（values阶段为空）
  - anchor_summary: 锚点摘要（包含goals、性格、风格等，替代完整历史）
```

#### Strengths 阶段 Prompt 结构

```yaml
目标: 帮助用户发现并确认其最突出的10个优势

特殊流程:
  1. 开场询问用户自评优势
  2. 深度提问探索（每次一问）
  3. 记录与确认（对比初始答案）
  4. 重复提问直至10个不重复优势
  5. 标记优势（三档标记）:
     - a. 有充实感，与成功有关
     - b. 有充实感
     - c. 目前还不确定
  6. 确认标记结果
  7. 结束对话

prior_context: 包含values阶段的结果
```

#### Interests 阶段 Prompt 结构

```yaml
目标: 帮助用户发现3个"热爱"（名词形式的领域）

特殊流程:
  1. 开场询问用户热爱的领域
  2. 深度提问探索
  3. 记录与确认
  4. 收集候选热爱清单（至少6个）
  5. 引导用户选出TOP 3
  6. 确认最终结果
  7. 结束对话

约束: 热爱必须是名词形式（如"人工智能"、"心理学"）
```

#### Purpose 阶段 Prompt 结构

```yaml
目标: 帮助用户发现工作使命（最希望为他人提供的核心价值）

特殊流程:
  1. 开场与回顾（回忆values阶段的5个关键词）
  2. 梳理价值经历（10个为他人提供价值的经历）
  3. 匹配价值观（逐个经历分析对应的价值观）
  4. 统计与总结:
     - 经历-价值观对应表格
     - 核心使命陈述
  5. 确认总结
  6. 结束对话

prior_context: 包含values、strengths、interests三阶段结果
```

### 2.4 完整 Prompt 示例（Values阶段）

```markdown
你是一名专业的职业规划咨询师，同时拥有非常强的逻辑思辨能力，内观内省能力与心理治疗、心理资讯背景。
现在你在做一项工艺事业，是帮助用户探索他们的价值观、才能和兴趣，最终找到他们真正想做的事。

### 咨询流程

1. **开场提问**：直接询问用户："你能否直接告诉我，在你心中对你最重要的5个价值观关键词是什么？"
...

### 重要准则

- **引导而非灌输**：始终给用户思考和回答的空间，不要直接替用户下结论。
- **一次一问**：严格遵守每轮对话只提一个问题。
- **完整收敛**：务必确认无论问什么都无法再提取新词，才算收敛。
- **完成即引导答题卡**：当你判断用户已明确确认完成时，必须明确告知"将生成本维度答题卡总结"。
- 【对话续写】若对话已有历史，必须在已有探索基础上继续深挖，禁止重复开场式提问。

### 题库参考

以下题库可供选择，你也可以根据对话情境灵活提问：
1. 最近一次让你"很有意义感"的事情是什么？
2. 如果钱不是问题，你会选择做什么？
3. ...

来访者基本信息：
- 年龄范围：25-30
- 当前职业：产品经理
- ...

请直接用中文和用户继续这一轮对话。
```

---

## 三、完整模式对话逻辑（LangGraph，备用）

### 3.1 核心文件

```
src/backend/app/core/agent/graph.py            # 状态图定义
src/backend/app/core/agent/state.py            # 状态定义
src/backend/app/core/agent/nodes/reasoning_v2.py   # 推理节点
src/backend/app/core/agent/nodes/action.py     # 行动节点
src/backend/app/core/agent/nodes/observation.py # 观察节点
src/backend/app/core/agent/nodes/user_agent.py # 用户代理节点
src/backend/app/core/agent/question_flow.py    # 题目流程
```

### 3.2 ReAct 智能体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LangGraph ReAct 状态图                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│                        ┌─────────────┐                                      │
│                        │   START     │                                      │
│                        └──────┬──────┘                                      │
│                               │                                             │
│                               ▼                                             │
│   ┌─────────────────────────────────────────────────────────────┐          │
│   │  ┌───────────┐    ┌───────────┐    ┌───────────┐           │          │
│   │  │ reasoning │───→│  action   │───→│observation│           │          │
│   │  │  推理节点  │    │  行动节点  │    │  观察节点  │           │          │
│   │  └─────┬─────┘    └───────────┘    └─────┬─────┘           │          │
│   │        │                                   │                │          │
│   │        │         ┌─────────────────────────┘                │          │
│   │        │         │           ▲                              │          │
│   │        │         │           │  should_continue?            │          │
│   │        │         │           │  - 有错误 → end              │          │
│   │        │         │           │  - 迭代超限 → end            │          │
│   │        │         │           │  - step轮数超限 → end        │          │
│   │        │         │           │  - should_continue=False     │          │
│   │        │         │           │    → end                     │          │
│   │        │         │           │                              │          │
│   │        └─────────┴───────────┘                              │          │
│   │                                                             │          │
│   └─────────────────────────────────────────────────────────────┘          │
│                               │                                             │
│                               ▼                                             │
│                        ┌─────────────┐                                      │
│                        │ user_agent  │  ← 将思考转为用户可见消息             │
│                        └──────┬──────┘                                      │
│                               │                                             │
│                               ▼                                             │
│                          ┌─────────┐                                        │
│                          │   END   │                                        │
│                          └─────────┘                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.3 状态定义（AgentState）

```python
class AgentState(TypedDict, total=False):
    # === 用户可见（前端展示）===
    messages: List[LLMMessage]           # 用户可见消息

    # === 内部消息（思考链使用）===
    inner_messages: List[LLMMessage]     # 内部思考消息

    # === 过程日志 ===
    logs: List[Dict[str, Any]]           # 过程日志

    # === 上下文与步骤 ===
    context: Dict[str, Any]              # 上下文数据
    current_step: str                    # 当前步骤ID

    # === 工具 ===
    tools_used: List[str]                # 已使用工具
    tool_results: List[Dict[str, Any]]   # 工具结果

    # === 输入与身份 ===
    user_input: Optional[str]            # 用户输入
    user_id: Optional[str]               # 用户ID
    session_id: Optional[str]            # 会话ID

    # === 循环控制 ===
    iteration_count: int                 # 迭代计数
    should_continue: bool                # 是否继续

    # === 输出 ===
    final_response: Optional[str]        # 最终响应
    error: Optional[str]                 # 错误信息

    # === 答题卡 ===
    answer_card: Dict[str, Any]          # 答题卡元信息

    # === 建议标签 ===
    suggestions: List[str]               # 3个建议方向

    # === 题目进度 ===
    question_progress: Dict[str, Any]    # 题目进度

    # === 流式队列 ===
    stream_queue: Any                    # SSE流式队列

    # === Token用量 ===
    session_token_usage: Dict[str, Any]  # Token统计
```

### 3.4 推理节点（reasoning_v2.py）详细逻辑

```python
async def reasoning_node(state: AgentState) -> AgentState:
    """
    推理节点核心逻辑：
    
    1. 检查题目进度状态
    2. 根据状态决定行动
    3. 如需LLM推理，则调用LLM
    """
    
    # === 场景1: 需要展示步骤介绍 ===
    if q_state.get("need_step_intro"):
        intro_message = generate_step_intro_message(current_step)
        # 同时生成第一个题目引导
        if current_question and q_state.get("need_question_guidance"):
            guidance_message = generate_question_guidance_message(...)
            intro_message += f"\n\n---\n\n{guidance_message}"
        return state_with_decision(action="respond", response=intro_message)
    
    # === 场景2: 需要展示题目引导 ===
    if q_state.get("need_question_guidance"):
        guidance_message = generate_question_guidance_message(...)
        return state_with_decision(action="respond", response=guidance_message)
    
    # === 场景3: 所有题目已完成 ===
    if q_state.get("all_completed"):
        return state_with_decision(
            action="respond", 
            response="太棒了！你已经完成了..."
        )
    
    # === 场景4: 正在进行题目对话，判断充分性 ===
    if step_progress and q_state.get("current_question"):
        
        # 检测跳过意图
        if detect_skip_intent(user_input) and current_question.turn_count >= 1:
            # 生成带AI分析的answer_card
            card_analysis = await generate_answer_card_analysis(...)
            state["answer_card"] = {
                "question_id": ...,
                "question_content": ...,
                "user_answer": ...,
                "ai_summary": card_analysis["ai_summary"],
                "ai_analysis": card_analysis["ai_analysis"],
                "key_insights": card_analysis["key_insights"],
                "should_show": True,
            }
            return state_with_decision(action="respond", response=summary_text)
        
        # 判断是否应该展示answer_card
        should_show, reason = should_show_answer_card(step_progress, conversation_history)
        
        if should_show:
            # 回答充分，生成answer_card
            card_analysis = await generate_answer_card_analysis(...)
            # ...设置answer_card
            return state_with_decision(action="respond", response=response_parts)
        else:
            # 回答不充分，继续对话挖掘
            # ...继续LLM推理流程
    
    # === 场景5: 正常的LLM推理流程 ===
    # 构建system_prompt
    system_content = get_reasoning_prompt({
        "current_step": current_step,
        "step_summary": step_summary,
        "user_input": user_input,
        "tools_used": tools_used,
        "knowledge_snippets": knowledge_snippets,
        "question_goal": question_goal,
        "question_content": question_content_str,
        "current_turn_count": current_turn_count,
        "counselor_guidelines": COUNSELOR_RESPONSE_GUIDELINES,
        "basic_info": basic_info_str,
    })
    
    # 调用LLM
    messages = [
        LLMMessage(role="system", content=system_content),
        LLMMessage(role="user", content=user_input),
    ]
    
    # 流式输出处理
    if stream_queue is not None:
        async for chunk in llm.chat_stream(messages, temperature=0.7):
            # 边生成边推送到stream_queue
            await stream_queue.put(chunk)
    
    # 解析LLM返回的JSON决策
    decision = ReasoningDecision.model_validate(data)
    # decision包含: action, response, reasoning, suggestions
```

### 3.5 Reasoning Prompt 模板

```yaml
# src/backend/app/domain/prompts/templates/reasoning.yaml

name: reasoning
description: 推理节点系统提示

prompt: |
  你是一个专业的职业规划助手，同时拥有非常强的逻辑思辨能力，内观内省能力与心理治疗、心理资讯背景。
  现在你在做一项工艺事业，是帮助用户探索他们的价值观、才能和兴趣，最终找到他们真正想做的事。

  {% if basic_info %}
  来访者基本信息：
  {{ basic_info }}
  {% endif %}

  当前步骤：{{ current_step }}
  该步骤的阶段性总结（供你参考，不要逐字复述）：{{ step_summary }}
  用户输入：{{ user_input }}
  已使用的工具：{{ tools_used }}

  {% if knowledge_snippets %}
  以下为已检索到的知识库片段（供参考）：
  {{ knowledge_snippets }}
  {% endif %}

  {% if question_goal %}
  --- 当前题目引导（不要直接告知用户以下内容）---
  题目：{{ question_content }}
  隐藏目标：{{ question_goal.goal }}
  需要提取的信息：{{ question_goal.extract | join("、") }}
  当前对话轮数：{{ current_turn_count }} / 最多 {{ question_goal.max_turns }} 轮
  {% endif %}

  {% if counselor_guidelines %}
  {{ counselor_guidelines }}
  {% endif %}

  请分析用户输入，决定下一步应该：
  1. 使用工具（如 search_tool, guide_tool 等）
  2. 直接回答用户问题
  3. 引导用户继续探索

  输出格式（必须严格遵守）：
  - 先输出给用户看的回复（可多行），然后换行写 RESPONSE_END 紧跟一行 JSON。
  - JSON 必须包含：action, reasoning, suggestions（3个简短建议方向）
  
  示例：
  这是给用户看的回复内容，可以多行。
  RESPONSE_END{"action":"respond","reasoning":"...","suggestions":["...","...","..."]}
```

---

## 四、答题卡生成逻辑

### 4.1 充分性判断

```python
def should_show_answer_card(
    step_progress: StepProgress,
    conversation_history: List[Dict],
    force_regenerate_card: bool = False,
) -> Tuple[bool, str]:
    """
    判断是否应该展示 answer_card
    
    判断标准：
    1. 对话轮数达到 min_turns 以上（默认2轮）
    2. 用户回答包含具体例子和感受（sufficiency_hints）
    3. 不超过 max_turns（默认5轮）
    4. force_regenerate_card=True 时强制生成
    """
    
    # 强制重新生成模式
    if force_regenerate_card and current_question.turn_count > 0:
        return True, "继续讨论后重新生成答题卡"
    
    # 最少轮数检查
    if turn_count < min_turns:
        return False, "对话轮数不足，需要继续挖掘"
    
    # 最多轮数检查
    if turn_count >= max_turns:
        return True, "对话轮数已达上限，总结回答"
    
    # 分析最近的对话内容
    latest_user_msg = user_messages[-1].get("content", "")
    
    # 太短的回答
    if len(latest_user_msg) < 30:
        return False, "回答过于简短"
    
    # 包含充分性关键词（如"因为"、"比如"、"感觉"等）
    has_concrete = any(kw in latest_user_msg for kw in hints)
    
    if turn_count >= (min_turns + 1) and has_concrete:
        return True, "回答充分，包含具体例子和感受"
    
    return False, "需要继续挖掘更多细节"
```

### 4.2 AI分析生成

```python
async def generate_answer_card_analysis(
    category: str,
    question_id: int,
    question_content: str,
    conversation_history: List[Dict],
) -> Dict[str, Any]:
    """
    调用LLM为答题卡生成结构化分析
    
    返回:
        {
            "ai_summary": str,     # 1-2句核心观点概括
            "ai_analysis": str,    # 深层分析
            "key_insights": list,  # 3-5个关键洞察短语
        }
    """
    
    # 使用 answer_card_summary.yaml 提示词
    prompt_content = get_answer_card_prompt({
        "category_label": CATEGORY_LABELS.get(category, category),
        "question_content": question_content,
        "question_goal": question_goal,
        "conversation_text": conversation_text,
    })
    
    messages = [
        LLMMessage(role="system", content=prompt_content),
        LLMMessage(role="user", content="请生成答题卡总结。"),
    ]
    
    response = await llm.chat(messages, temperature=0.5)
    data = json.loads(response.content)
    
    return {
        "ai_summary": data.get("ai_summary", ""),
        "ai_analysis": data.get("ai_analysis", ""),
        "key_insights": data.get("key_insights", []),
    }
```

### 4.3 Answer Card Prompt 模板

```yaml
# src/backend/app/domain/prompts/templates/answer_card_summary.yaml

name: answer_card_summary
description: 答题卡总结提示

prompt: |
  你是一名专业的职业规划咨询师。请基于以下对话内容，为用户生成一份结构化的答题卡总结。

  维度：{{ category_label }}
  题目：{{ question_content }}
  
  题目目标：
  {{ question_goal }}

  对话内容：
  {{ conversation_text }}

  请生成以下JSON格式的总结：
  {
    "ai_summary": "1-2句话概括用户的核心观点",
    "ai_analysis": "对用户回答的深层分析，包括潜在模式和洞察",
    "key_insights": ["洞察1", "洞察2", "洞察3"]
  }
```

---

## 五、题目进度管理

### 5.1 进度数据结构

```python
class QuestionProgress(BaseModel):
    """单个题目的进度"""
    question_id: int                    # 题目ID
    question_content: str               # 题目内容
    status: str                         # 状态: not_started/in_progress/completed
    turn_count: int                     # 对话轮数
    user_answer: Optional[str]          # 用户答案摘要

class StepProgress(BaseModel):
    """单个步骤的进度"""
    step_id: str                        # 步骤ID
    category: str                       # 分类: values/strengths/interests
    questions: List[QuestionProgress]   # 题目列表
    current_question_index: int         # 当前题目索引
    is_intro_shown: bool                # 是否已展示介绍

class RuminationProgress(BaseModel):
    """Rumination阶段进度（新增）"""
    main_section: str                   # 主页面: opening/review/filter/final_choice/recommend/end
    review_sub_index: int               # 回顾子索引: 0=values 1=strengths 2=interests 3=purpose
    filter_step: int                    # 筛选步骤: 0=未进入 1~9=筛选步骤
    filter_table: Optional[Dict]        # 当前表格数据

# 存储在 state["question_progress"] 中
{
    "values_exploration": StepProgress(...),
    "strengths_exploration": StepProgress(...),
    "interests_exploration": StepProgress(...),
    "rumination": RuminationProgress(...),  # 新增
}
```

### 5.2 题目目标配置

```python
# src/backend/app/domain/question_goals.py

QUESTION_GOALS = {
    "values": {
        1: {
            "goal": "了解用户认为重要的价值观",
            "extract": ["具体价值观关键词", "为什么重要", "相关经历"],
            "min_turns": 2,
            "max_turns": 5,
            "sufficiency_hints": ["因为", "比如", "感觉", "重要"]
        },
        # ...
    },
    "strengths": { ... },
    "interests": { ... },
}
```

---

## 六、对话流程总结

### 6.1 简单模式 vs 完整模式对比

| 特性 | 简单模式 | 完整模式 | Rumination（新增） |
|-----|---------|---------|-------------------|
| **实现** | 直接LLM调用 | LangGraph状态机 | Python + Widget交互 |
| **Prompt** | 长system_prompt（完整流程） | 短system_prompt + 节点提示词 | section级prompt |
| **状态管理** | 无状态/简单历史 | 复杂状态（AgentState） | RuminationProgress |
| **工具使用** | 无 | search_tool, guide_tool等 | gen_table, filter_match等 |
| **流式输出** | ✅ 支持 | ✅ 支持 | ✅ 支持 |
| **答题卡** | 基于关键词检测 | 基于充分性判断 | 表格Widget + Top3选择 |
| **适用场景** | 标准化快速引导 | 深度个性化探索 | 第五步沉淀整合 |
| **当前状态** | ✅ 主要使用 | ⚠️ 备用 | 🆕 新增 |

### 6.2 当前对话流程图（简单模式）

```
用户访问 /explore/chat/values
  │
  ▼
检查激活码和会话
  │
  ▼
初始化对话（simple-chat/init）
  ├─→ 构建system_prompt（含阶段定义+题目库+用户信息）
  └─→ LLM生成开场问题
  │
  ▼
用户输入消息
  │
  ▼
发送消息（simple-chat/message/stream）
  ├─→ 加载历史消息
  │      └─→ 文件级并发锁（防止并发写丢失）
  ├─→ 构造messages [system, anchor_summary, ...recent_history, user]
  │      └─→ 锚点摘要（含goals/性格/风格）+ 最近20轮
  ├─→ 流式调用LLM
  └─→ 保存assistant回复
         └─→ 后台异步生成锚点摘要（每20轮/结论卡后）
  │
  ▼
检测完成意图
  │
  ├─→ 未完成：继续对话
  │
  └─→ 完成：
      ├─→ 生成dimension_conclusion
      ├─→ 展示答题卡
      ├─→ 用户确认
      └─→ 锁定阶段，可进入下一阶段
```

---

## 七、未来优化建议

### 7.1 提示词优化（已部分实现）

1. **动态Prompt生成**：根据用户回答质量动态调整Prompt
2. **多语言支持**：✅ 已接入i18n，探索流程支持中英文切换
3. **A/B测试**：不同Prompt版本效果对比
4. **锚点摘要**：✅ 用结构化摘要替代完整历史，减少token消耗

### 7.2 对话逻辑优化

1. **意图识别**：更精准的用户意图检测
2. **情感分析**：识别用户情绪，调整引导策略
3. **个性化推荐**：基于历史数据个性化引导

### 7.3 智能体增强

1. **重新启用LangGraph**：在简单模式基础上增加智能体能力
2. **多Agent协作**：values/strengths/interests各一个专家Agent
3. **A2A协议**：支持Agent间通信协作
4. **Rumination Widget体系**：✅ 已规划表格Widget、筛选弹窗、Top3选择卡
