"""
结论卡目标配置（可扩展）。

该配置独立于主对话提示词，用于约束不同 step 的结论卡输出重点。
"""

from typing import Dict


# 各阶段结论卡重要原则（从主对话提示词「重要准则」提取，用于生成结论时的硬性约束）
# 【通用】严禁在结论卡或回复中提及下一阶段的目标、流程或问题；仅聚焦本阶段结论。
_COMMON_NO_NEXT_PHASE = "- 【硬性】严禁在输出中提及、暗示或提问下一阶段的目标、内容或流程；即便已知下一阶段信息，也绝不要开始下一轮的提问。仅输出本阶段结论。\n"

# 与 simple_chat 系统提示、[STATE_JSON] draft、结论卡 summary_prompt 保持一致
_NAMING_SINGLE_CONCEPT = (
    "- 【命名约束】每条必须是单一概念词（或本阶段要求的单一短语），不得使用「/、或、以及、&、|」并列多个候选。"
    "若存在近义词，须在对话中与用户探讨差异并明确更想保留哪一个后再记录。"
)

CONCLUSION_RULES: Dict[str, str] = {
    "values": (
        _COMMON_NO_NEXT_PHASE
        + "- keywords 提炼出五个价值观相关的词。必须仅使用用户在对话中亲自提到、并已确认的价值观词，严禁添加、改写或杜撰\n"
        + "- 用户未明确确认的词汇不得写入 keywords\n"
        + "- 用户若暂时答不上来，需通过有限引导帮助其思考后回答；结论卡只能基于用户实际说出的词\n"
        + _NAMING_SINGLE_CONCEPT
        + "\n"
    ),
    "strengths": (
        _COMMON_NO_NEXT_PHASE
        + "- 必须为 10 个彼此不同的能力优势\n"
        + "- 每个优势需来自用户确认的描述，严禁杜撰\n"
        + _NAMING_SINGLE_CONCEPT
        + "\n"
    ),
    "interests": (
        _COMMON_NO_NEXT_PHASE
        + "- 必须为 3 个核心热爱方向，以名词形式呈现\n"
        + "- 每个热爱需来自用户确认的领域，严禁杜撰\n"
        + _NAMING_SINGLE_CONCEPT
        + "\n"
    ),
    "purpose": (
        _COMMON_NO_NEXT_PHASE
        + "- 使命陈述必须来自用户确认的表达\n"
        + "- 必须为用户为他人提供价值的10个行为或者经历。\n"
        + _NAMING_SINGLE_CONCEPT
        + "\n"
    ),
    "rumination": (
        _COMMON_NO_NEXT_PHASE
        + "- 整合信息需基于前面各阶段用户已确认的内容\n"
        + "- 下一步行动需与用户选择的方向一致\n"
        + _NAMING_SINGLE_CONCEPT
        + "\n"
    ),
}

CONCLUSION_CARD_GOALS: Dict[str, dict] = {
    "values": {
        "name": "价值观结论卡",
        "objective": "沉淀用户最终确认的5个核心价值观词，并保持原词、原顺序",
        "must_capture": [
            "final_keywords_ordered",
            "keyword_user_explanations_optional",
        ],
        "validation": {
            "min_keywords": 5,
            "max_keywords": 5,
            "strict_match_user_confirmed_keywords": True,
        },
    },
    "strengths": {
        "name": "禀赋结论卡",
        "objective": "沉淀用户确认的优势项，并凸显可迁移的能力线索",
        "must_capture": [
            "confirmed_strengths",
            "strength_tags_optional",
        ],
        "validation": {
            "min_keywords": 3,
            "max_keywords": 12,
            "strict_match_user_confirmed_keywords": False,
        },
    },
    "interests": {
        "name": "热忱结论卡",
        "objective": "沉淀用户确认的核心热爱方向，突出投入感和持续性",
        "must_capture": [
            "top_interests",
            "interest_reasons_optional",
        ],
        "validation": {
            "min_keywords": 3,
            "max_keywords": 8,
            "strict_match_user_confirmed_keywords": False,
        },
    },
    "purpose": {
        "name": "使命结论卡",
        "objective": "沉淀用户使命表达与价值整合线索",
        "must_capture": [
            "purpose_statement",
            "supporting_evidence_optional",
        ],
        "validation": {
            "min_keywords": 1,
            "max_keywords": 8,
            "strict_match_user_confirmed_keywords": False,
        },
    },
    "rumination": {
        "name": "沉淀结论卡",
        "objective": "整合多维度信息，形成可执行下一步建议",
        "must_capture": [
            "integration_points",
            "next_actions",
        ],
        "validation": {
            "min_keywords": 1,
            "max_keywords": 10,
            "strict_match_user_confirmed_keywords": False,
        },
    },
}


def get_conclusion_card_goal(step_id: str) -> dict:
    normalized = (step_id or "").strip().lower()
    return CONCLUSION_CARD_GOALS.get(normalized, CONCLUSION_CARD_GOALS["values"])


def get_conclusion_rules(step_id: str) -> str:
    """获取指定阶段的结论卡重要原则（用于提示词注入）"""
    normalized = (step_id or "").strip().lower()
    return CONCLUSION_RULES.get(normalized, CONCLUSION_RULES["values"])


def get_conclusion_rules_and_goals(step_id: str) -> str:
    """获取结论卡规则 + 目标（用于动态注入，包含 objective 与 must_capture）"""
    rules = get_conclusion_rules(step_id)
    goal = get_conclusion_card_goal(step_id)
    objective = goal.get("objective", "")
    must_capture = goal.get("must_capture") or []
    capture_text = "、".join(must_capture) if isinstance(must_capture, list) else str(must_capture)
    goals_block = f"本结论卡目标：{objective}\n必须覆盖：{capture_text}" if objective else ""
    return f"{rules}\n\n{goals_block}".strip() if goals_block else rules


def get_goal_prompt_hint(step_id: str) -> str:
    goal = get_conclusion_card_goal(step_id)
    must_capture = goal.get("must_capture") or []
    capture_text = "、".join(must_capture) if isinstance(must_capture, list) else str(must_capture)
    return (
        f"本结论卡目标：{goal.get('objective', '')}\n"
        f"必须覆盖的信息：{capture_text}\n"
        "请避免泛化抒情，优先输出可核对的结构化要点。"
    )
