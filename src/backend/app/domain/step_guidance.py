"""
步骤引导配置：包含每个步骤的理论基础、目的说明、每道题的引导语等
"""
from typing import Dict, List, Any

# 每个步骤的理论基础和目的说明
STEP_THEORY: Dict[str, Dict[str, str]] = {
    "values_exploration": {
        "purpose": "探索你内心真正看重的价值观",
        "theory": """
价值观是指引人生方向的核心信念。通过探索价值观，我们能够：
1. 明确什么对你来说真正重要
2. 理解你做决策时的内在驱动力
3. 找到让你感到有意义的人生方向

价值观探索不是寻找"正确答案"，而是发现你内心真实的声音。
        """.strip(),
    },
    "strengths_exploration": {
        "purpose": "发现你的天赋优势和核心能力",
        "theory": """
才能是你天生擅长且容易做好的事情。探索才能可以帮助你：
1. 识别你的天赋优势领域
2. 了解你能在哪些方面出类拔萃
3. 找到能发挥优势的职业方向

真正的才能往往表现为：做这件事时感到轻松、自然，且能比他人做得更好。
        """.strip(),
    },
    "interests_exploration": {
        "purpose": "探索你内心真正感兴趣和充满热情的事物",
        "theory": """
热情是驱动你持续投入的内在动力。探索热情能够：
1. 发现让你充满活力的事物
2. 识别你愿意长期投入的方向
3. 找到工作与乐趣结合的可能性

热情的标志是：即使遇到困难，你仍然愿意继续，并从中获得满足感。
        """.strip(),
    },
}

# 每道题的引导语（当题目开始时AI会说这段话）
# 格式：category -> question_id -> guidance
QUESTION_GUIDANCE: Dict[str, Dict[int, str]] = {
    "values": {
        # 这里可以配置具体题目的引导语
        # 如果没有配置，会使用默认引导语
    },
    "strengths": {
    },
    "interests": {
    },
}

# 默认引导语模板（当具体题目没有配置时使用）
DEFAULT_GUIDANCE_TEMPLATE = {
    "values": "让我们来探索一下这个关于价值观的问题。请根据你的真实想法回答，不必考虑社会期待或他人看法。",
    "strengths": "现在让我们聊聊你的才能和优势。请分享你在这方面的真实体验和感受。",
    "interests": "让我们谈谈你的兴趣和热情。请告诉我，什么事情能让你感到充满活力？",
}

# 咨询AI判断回答充分性的标准提示
ANSWER_SUFFICIENCY_PROMPT = """
你是一位专业的职业咨询师。当前用户正在回答关于 {category} 的问题："{question}"

用户已经给出了以下回答：
{conversation_history}

请判断：
1. 用户的回答是否已经充分表达了他们的想法？
2. 是否还需要进一步挖掘更深层的原因或感受？

判断标准：
- 如果用户只是简单回答了"是"或"不是"，需要继续引导
- 如果用户只列举了现象，但没有说明原因或感受，需要继续挖掘
- 如果用户已经说明了原因、感受、以及具体的例子，可以认为充分
- 不要过度挖掘，3-5轮对话即可

请返回JSON格式：
{{
    "is_sufficient": true/false,
    "reason": "判断理由",
    "next_action": "continue" 或 "show_answer_card"
}}
"""

# 咨询AI回应用户的指导原则
COUNSELOR_RESPONSE_GUIDELINES = """
你是一位温和、专业的职业咨询师。在与用户对话时：

1. 回应风格：
   - 简短、温暖、鼓励性的回应（1-3句话）
   - 不要过度分析或给出建议
   - 使用共情式语言（"我理解"、"听起来"）

2. 挖掘深度：
   - 如果用户回答浅显，用开放式问题引导（"能具体说说吗？"、"这让你有什么感受？"）
   - 如果用户回答充分，表示认可并提示即将总结
   - 限制在3-5轮对话内，不要过度挖掘

3. 避免的行为：
   - 不要长篇大论
   - 不要过早给出结论
   - 不要质疑用户的想法
   - 不要急于转移话题

4. 示例：
   好的回应："听起来这对你很重要。能说说为什么吗？"
   不好的回应："根据你的描述，我认为你应该……（长篇分析）"
"""


def get_step_theory(step_id: str) -> Dict[str, str]:
    """获取步骤的理论基础"""
    return STEP_THEORY.get(step_id, {
        "purpose": "探索这个主题",
        "theory": "让我们开始这个阶段的探索。"
    })


def get_question_guidance(category: str, question_id: int) -> str:
    """获取题目的引导语"""
    if category in QUESTION_GUIDANCE and question_id in QUESTION_GUIDANCE[category]:
        return QUESTION_GUIDANCE[category][question_id]
    return DEFAULT_GUIDANCE_TEMPLATE.get(category, "让我们开始这道题的探索。")


def get_answer_sufficiency_prompt(category: str, question: str, conversation_history: str) -> str:
    """获取判断回答充分性的提示词"""
    return ANSWER_SUFFICIENCY_PROMPT.format(
        category=category,
        question=question,
        conversation_history=conversation_history
    )
