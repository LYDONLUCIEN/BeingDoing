"""
业务领域层：流程步骤、提示词等与「找到真正想做的事」相关的领域知识集中在此。
专业人士只需改此目录下的 steps 与 prompts，无需到其他文件查找。
"""
from app.domain.steps import (
    FLOW_STEPS,
    DEFAULT_CURRENT_STEP,
    STEP_TO_CATEGORY,
    EXPLORATION_STEP_IDS,
)

__all__ = [
    "FLOW_STEPS",
    "DEFAULT_CURRENT_STEP",
    "STEP_TO_CATEGORY",
    "EXPLORATION_STEP_IDS",
]
