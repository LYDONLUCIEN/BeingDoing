"""
知识检索规则：何时「必须查知识」、何时由 Agent 自判，单点维护。
供 reasoning 节点在调用 LLM 前预填 knowledge_snippets 使用。
"""
from typing import List
from app.domain.steps import STEP_TO_CATEGORY, EXPLORATION_STEP_IDS

# 触发「必须查知识」的用户表述关键词（列举/选择/解释类）
MUST_QUERY_KEYWORDS: List[str] = [
    "有哪些", "列举", "选项", "什么是", "解释", "介绍",
    "多少种", "几种", "有什么", "能选", "怎么选",
]

# 与知识库强相关的步骤（仅在这些步骤下才可能触发「必须查」）
STEPS_REQUIRING_KNOWLEDGE: List[str] = list(EXPLORATION_STEP_IDS)


def should_force_knowledge_query(state: dict) -> bool:
    """
    根据当前步骤与用户输入判断是否本轮必须预填知识库片段。
    若为 True，reasoning 节点会在调用 LLM 前先检索并写入 context["knowledge_snippets"]。
    """
    current_step = (state.get("current_step") or "").strip()
    user_input = (state.get("user_input") or "").strip()
    if not user_input or current_step not in STEPS_REQUIRING_KNOWLEDGE:
        return False
    return any(kw in user_input for kw in MUST_QUERY_KEYWORDS)


def get_search_category_for_step(current_step: str) -> str:
    """当前步骤对应的知识分类（values/strengths/interests），供检索使用。"""
    return STEP_TO_CATEGORY.get(current_step, "values")
