"""
领域提示词：对外仅暴露 get_*_prompt(context)，节点直接调用，无需关心 YAML 路径。
"""
from app.domain.prompts.loader import (
    get_reasoning_prompt,
    get_observation_prompt,
    get_guide_prompt,
    get_answer_card_prompt,
)

__all__ = [
    "get_reasoning_prompt",
    "get_observation_prompt",
    "get_guide_prompt",
    "get_answer_card_prompt",
]
