"""
维度探索完成配置：各阶段的核心目标与完成判据。
用于 LLM 判断对话是否已达到该维度的探索结论，以及生成结论卡片的引导。
"""
from typing import Dict, Optional

# 每个 phase 的探索目标与完成标准（供 LLM 判断用）
DIMENSION_COMPLETION_CONFIG: Dict[str, dict] = {
    "values": {
        "label": "信念",
        "goal": "发现用户经过收敛的5个核心价值观关键词，并明确优先级排序",
        "completion_criteria": "用户已确认5个价值观关键词及其排序，或明确表示认可当前提炼结果",
        "summary_prompt_hint": "用1-2段话概括用户的5个核心价值观及其含义，突出用户最在意的原则",
    },
    "strengths": {
        "label": "禀赋",
        "goal": "发现用户5个真正不重复的擅长的事，无需刻意努力、自动发生的思维、情感或行动模式。并对每件事完成「有充实感/与成功有关」等标记",
        "completion_criteria": "用户已确认5件擅长的事及其标签，或明确表示认可当前提炼结果",
        "summary_prompt_hint": "用1-2段话概括用户的核心才能与优势，突出做起来轻松自然、他人有反馈的领域",
    },
    "interests": {
        "label": "热忱",
        "goal": "发现用户3件「喜欢的事」（真正感兴趣、好奇，想理解更深层原理的领域，而不是享受单纯的操作），从12件候选中筛选 top3",
        "completion_criteria": "用户已确认 top3 喜欢的事，或明确表示认可当前提炼结果",
        "summary_prompt_hint": "用1-2段话概括用户的热忱所在，突出让用户忘我投入、时间消失的领域",
    },
    "purpose": {
        "label": "使命",
        "goal": "帮助用户用一句话或短语表达其职业使命感——工作对其更深层的意义与目的",
        "completion_criteria": "用户已给出并确认自己的使命宣言，或明确表示认可当前提炼结果",
        "summary_prompt_hint": "用1段话概括用户的使命宣言，结合信念、禀赋、热忱的汇聚之处",
    },
}


def get_dimension_config(phase: str) -> Optional[dict]:
    """获取指定阶段的维度完成配置。interests_goals 视为 interests 的别名（兼容旧数据）。rumination 无结论卡。"""
    normalized = "interests" if phase in ("interests_goals", "goals") else phase
    if normalized == "rumination":
        return None  # rumination 使用不同流程，不触发维度结论卡
    return DIMENSION_COMPLETION_CONFIG.get(normalized) or DIMENSION_COMPLETION_CONFIG.get(
        "values"
    )
