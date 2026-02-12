"""
题目隐藏目标配置：每道题的引导目标、需提取的信息、轮数控制。

AI 咨询师在对话中参考这些目标来决定挖掘方向和深度，但不应直接告知用户。
question_id 是全局顺序 ID（values 1-30, strengths 31-60, interests 61-90），
helper 函数会自动转换为 per-category question_number。
"""
from typing import Dict, Optional

# 类型说明：每个 goal 是一个 dict
# {
#   "goal": str,              # 这道题要帮用户理清的核心信息
#   "extract": list[str],     # 需要从用户回答中提取的关键信息
#   "max_turns": int,         # 最多对话轮数
#   "min_turns": int,         # 最少对话轮数（低于此轮数不触发 answer_card）
#   "sufficiency_hints": list[str],  # 判断充分性的关键词提示
# }

# ────────────────────────────────────────────
# 价值观（values）前5题目标
# ────────────────────────────────────────────
VALUES_GOALS: Dict[int, dict] = {
    1: {
        "goal": "通过用户敬佩的人的特征，反推出用户核心价值观",
        "extract": ["具体的人物", "让用户震撼的特征", "这些特征对应的价值观"],
        "max_turns": 5,
        "min_turns": 2,
        "sufficiency_hints": ["因为", "震撼", "特征", "价值", "重要", "佩服", "敬佩"],
    },
    2: {
        "goal": "找出对用户影响最大的人及其影响方式，揭示用户认同的价值取向",
        "extract": ["影响最大的人", "具体的影响行为或言论", "这种影响如何塑造了用户"],
        "max_turns": 5,
        "min_turns": 2,
        "sufficiency_hints": ["影响", "因为", "改变", "学到", "行为", "说过"],
    },
    3: {
        "goal": "通过对父亲生活方式的认同与反对，发现用户继承或反叛的价值观",
        "extract": ["喜欢父亲的哪些方面", "不喜欢的方面", "与自己价值观的关系"],
        "max_turns": 5,
        "min_turns": 2,
        "sufficiency_hints": ["喜欢", "不喜欢", "父亲", "像", "不想", "影响"],
    },
    4: {
        "goal": "通过对母亲生活方式的认同与反对，发现用户继承或反叛的价值观",
        "extract": ["喜欢母亲的哪些方面", "不喜欢的方面", "与自己价值观的关系"],
        "max_turns": 5,
        "min_turns": 2,
        "sufficiency_hints": ["喜欢", "不喜欢", "母亲", "像", "不想", "影响"],
    },
    5: {
        "goal": "通过用户希望被如何评价，揭示最深层的人生追求和价值观",
        "extract": ["希望被评价的关键词", "这些评价背后的价值取向", "用户的人生追求"],
        "max_turns": 5,
        "min_turns": 2,
        "sufficiency_hints": ["希望", "评价", "记住", "觉得", "重要", "人生"],
    },
}

# ────────────────────────────────────────────
# 才能（strengths）前5题目标
# ────────────────────────────────────────────
STRENGTHS_GOALS: Dict[int, dict] = {
    1: {
        "goal": "发现用户在什么领域能自然运用高效方法，揭示实践型才能",
        "extract": ["用高效方法的具体场景", "别人觉得难但用户觉得轻松的事", "这种才能的表现"],
        "max_turns": 5,
        "min_turns": 2,
        "sufficiency_hints": ["比如", "工作中", "自然而然", "轻松", "方法", "习惯"],
    },
    2: {
        "goal": "发现用户的领导和组织统筹能力",
        "extract": ["掌控全局的具体经历", "组织活动的体验", "什么时候感到厌烦"],
        "max_turns": 5,
        "min_turns": 2,
        "sufficiency_hints": ["组织", "带领", "活动", "安排", "负责", "管理"],
    },
    3: {
        "goal": "发现用户在人才配置和团队协作方面的才能",
        "extract": ["组建或配置团队的经历", "如何识别他人的优势", "团队合作中的角色"],
        "max_turns": 5,
        "min_turns": 2,
        "sufficiency_hints": ["团队", "合作", "搭配", "人", "互补", "配合"],
    },
    4: {
        "goal": "了解用户的自我改善驱动力和学习成长模式",
        "extract": ["主动改善的具体领域", "学习新技能的经历", "改善过程中的感受"],
        "max_turns": 5,
        "min_turns": 2,
        "sufficiency_hints": ["学习", "改善", "提升", "不足", "努力", "成长"],
    },
    5: {
        "goal": "发现用户的问题解决能力和分析思维",
        "extract": ["解决过的具体问题", "发现问题根源的方式", "没有问题时的状态"],
        "max_turns": 5,
        "min_turns": 2,
        "sufficiency_hints": ["问题", "解决", "发现", "原因", "分析", "处理"],
    },
}

# ────────────────────────────────────────────
# 兴趣/热情（interests）前5题目标
# ────────────────────────────────────────────
INTERESTS_GOALS: Dict[int, dict] = {
    1: {
        "goal": "了解用户对动物/自然相关领域的兴趣深度",
        "extract": ["对该领域的具体兴趣点", "投入的时间和精力", "带来的满足感"],
        "max_turns": 4,
        "min_turns": 2,
        "sufficiency_hints": ["喜欢", "兴趣", "感觉", "投入", "满足", "开心"],
    },
    2: {
        "goal": "了解用户对花卉/植物相关领域的兴趣深度",
        "extract": ["对该领域的具体兴趣点", "投入的时间和精力", "带来的满足感"],
        "max_turns": 4,
        "min_turns": 2,
        "sufficiency_hints": ["喜欢", "兴趣", "感觉", "投入", "满足", "开心"],
    },
    3: {
        "goal": "了解用户对农业相关领域的兴趣深度",
        "extract": ["对该领域的具体兴趣点", "投入的时间和精力", "带来的满足感"],
        "max_turns": 4,
        "min_turns": 2,
        "sufficiency_hints": ["喜欢", "兴趣", "感觉", "投入", "满足", "开心"],
    },
    4: {
        "goal": "了解用户对林业相关领域的兴趣深度",
        "extract": ["对该领域的具体兴趣点", "投入的时间和精力", "带来的满足感"],
        "max_turns": 4,
        "min_turns": 2,
        "sufficiency_hints": ["喜欢", "兴趣", "感觉", "投入", "满足", "开心"],
    },
    5: {
        "goal": "了解用户对宇宙/天文相关领域的兴趣深度",
        "extract": ["对该领域的具体兴趣点", "投入的时间和精力", "带来的满足感"],
        "max_turns": 4,
        "min_turns": 2,
        "sufficiency_hints": ["喜欢", "兴趣", "感觉", "投入", "满足", "开心"],
    },
}

# 按 category 索引
QUESTION_GOALS: Dict[str, Dict[int, dict]] = {
    "values": VALUES_GOALS,
    "strengths": STRENGTHS_GOALS,
    "interests": INTERESTS_GOALS,
}

# 每个 category 的默认目标（当具体题目没有配置时使用）
DEFAULT_GOALS: Dict[str, dict] = {
    "values": {
        "goal": "帮助用户发现和表达隐含的价值观",
        "extract": ["用户提到的关键词", "背后体现的价值取向", "具体的例子或经历"],
        "max_turns": 5,
        "min_turns": 2,
        "sufficiency_hints": ["因为", "比如", "例如", "感觉", "觉得", "体验", "经历", "让我", "的时候"],
    },
    "strengths": {
        "goal": "帮助用户识别和确认自身才能与优势",
        "extract": ["用户擅长的具体事情", "做起来轻松自然的体验", "他人的反馈"],
        "max_turns": 5,
        "min_turns": 2,
        "sufficiency_hints": ["擅长", "轻松", "自然", "比如", "经历", "别人说", "反馈"],
    },
    "interests": {
        "goal": "帮助用户确认对该领域的兴趣程度和热情来源",
        "extract": ["兴趣的具体表现", "投入的时间和精力", "获得的满足感"],
        "max_turns": 4,
        "min_turns": 2,
        "sufficiency_hints": ["喜欢", "兴趣", "投入", "满足", "开心", "享受", "好奇"],
    },
}


def _question_id_to_number(category: str, question_id: int) -> int:
    """
    将全局 question_id 转换为 per-category question_number。
    Values: id 1-30  → number = id
    Strengths: id 31-60 → number = id - 30
    Interests: id 61-90 → number = id - 60
    如果 id 不在预期范围，返回 id 本身（兼容）。
    """
    if category == "values":
        return question_id
    elif category == "strengths":
        return question_id - 30 if question_id > 30 else question_id
    elif category == "interests":
        return question_id - 60 if question_id > 60 else question_id
    return question_id


def get_question_goal(category: str, question_id: int) -> Optional[dict]:
    """
    获取指定题目的隐藏目标配置。

    Args:
        category: 问题类别 (values/strengths/interests)
        question_id: 全局题目 ID

    Returns:
        目标配置 dict，如果具体题目没有配置则返回 category 默认目标
    """
    if not category:
        return None

    question_number = _question_id_to_number(category, question_id)
    category_goals = QUESTION_GOALS.get(category, {})

    if question_number in category_goals:
        return category_goals[question_number]

    return DEFAULT_GOALS.get(category)
