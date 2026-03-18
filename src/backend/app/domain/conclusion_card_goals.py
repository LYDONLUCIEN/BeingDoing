"""
结论卡目标配置（可扩展）。

该配置独立于主对话提示词，用于约束不同 step 的结论卡输出重点。
"""

from typing import Dict


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


def get_goal_prompt_hint(step_id: str) -> str:
    goal = get_conclusion_card_goal(step_id)
    must_capture = goal.get("must_capture") or []
    capture_text = "、".join(must_capture) if isinstance(must_capture, list) else str(must_capture)
    return (
        f"本结论卡目标：{goal.get('objective', '')}\n"
        f"必须覆盖的信息：{capture_text}\n"
        "请避免泛化抒情，优先输出可核对的结构化要点。"
    )
