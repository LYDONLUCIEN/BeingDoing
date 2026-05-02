# 探索流程重构实施计划

## 一、需求总结

### 1.1 核心变更
- **逐题呈现**：每个步骤(values/strengths/interests)包含多道题，逐题呈现
- **步骤引导**：每个步骤开始时AI讲解理论基础
- **题目引导**：每道题开始前AI给出引导语
- **充分性判断**：AI判断回答充分后才弹出answer_card
- **UI分离**：answer_card只显示问题+答案，AI分析在对话中
- **折叠展示**：完成的题目折叠，出现下一题
- **上下文连续**：每题UI隔离但后端上下文连续

### 1.2 当前问题
- ❌ 回答完一题就跳到下一步骤
- ❌ 没有步骤理论讲解
- ❌ 没有题目引导语
- ❌ answer_card过早弹出
- ❌ UI缺乏视觉层次

## 二、实施阶段

### 阶段1：后端配置和数据结构 ✅
- [x] 创建 step_guidance.py（理论基础、引导语）
- [x] 创建 question_progress.py（题目进度管理）
- [x] 修改 AgentState（添加 question_progress 字段）

### 阶段2：后端Agent逻辑改造
- [ ] 修改 reasoning_node：增加题目状态判断逻辑
- [ ] 修改 action_node：处理步骤介绍、题目引导
- [ ] 修改 observation_node：判断回答充分性
- [ ] 创建辅助函数：获取当前题目、判断是否需要下一题

### 阶段3：后端API调整
- [ ] 修改 chat API：返回题目进度信息
- [ ] 修改 session API：初始化题目进度
- [ ] 修改 progress API：更新题目完成状态

### 阶段4：前端数据流改造
- [ ] 修改 chatApi：处理新的题目进度字段
- [ ] 修改 sessionStore：存储题目进度
- [ ] 修改 flow/page.tsx：集成题目进度逻辑

### 阶段5：前端UI组件重构
- [ ] 创建 QuestionCard：可折叠的题目卡片
- [ ] 优化 AnswerCard：只显示问题+答案
- [ ] 创建 StepIntro：步骤理论讲解组件
- [ ] 引入UI库（framer-motion/react-spring）增强视觉效果

### 阶段6：测试和优化
- [ ] 端到端测试
- [ ] 性能优化
- [ ] 边界情况处理

## 三、技术细节

### 3.1 数据流
```
用户输入
→ Agent reasoning（判断：是否需要步骤介绍/题目引导/回答充分性）
→ Agent action（执行：展示介绍/引导/返回AI回复/生成answer_card）
→ 前端（根据状态：显示对话/弹出answer_card/折叠并移动到下一题）
```

### 3.2 Session Metadata 结构
```python
{
    "question_progress": {
        "values_exploration": {
            "step_id": "values_exploration",
            "category": "values",
            "current_question_index": 0,
            "is_intro_shown": True,
            "questions": [
                {
                    "question_id": 1,
                    "question_content": "...",
                    "status": "in_progress",  # not_started/in_progress/completed
                    "turn_count": 2,
                    "user_answer": None
                },
                ...
            ]
        }
    }
}
```

### 3.3 Agent 判断逻辑
```python
# reasoning_node
if not step_progress.is_intro_shown:
    action = "show_step_intro"
elif current_question.status == "not_started":
    action = "show_question_guidance"
elif current_question.turn_count < 5:  # 限制对话轮数
    if is_answer_sufficient(conversation):
        action = "show_answer_card"
    else:
        action = "continue_conversation"
else:
    action = "show_answer_card"  # 超过轮数，强制结束
```

## 四、下一步行动

当前已完成阶段1，接下来需要：
1. 修改Agent节点（reasoning/action/observation）
2. 创建辅助函数处理题目进度
3. 修改API返回结构

是否继续？
