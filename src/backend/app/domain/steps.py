"""
流程步骤定义：与 flowchart 一致，单点维护。
API、会话、智能体默认步、问题/引导分类映射均从此读取。
"""
from typing import List, Dict, Any

# 默认当前步骤（与流程图第一步一致）
DEFAULT_CURRENT_STEP = "values_exploration"

# 流程步骤列表（顺序、id、名称、描述），供 /formula/flowchart 与前端展示
FLOW_STEPS: List[Dict[str, Any]] = [
    {"id": "values_exploration", "name": "探索重要的事（价值观）", "description": "了解你认为重要的事", "order": 1},
    {"id": "strengths_exploration", "name": "探索擅长的事（才能）", "description": "了解你的优势和才能", "order": 2},
    {"id": "interests_exploration", "name": "探索喜欢的事（热情）", "description": "了解你的兴趣和热情", "order": 3},
    {"id": "combination", "name": "组合分析", "description": "将三个要素进行组合分析", "order": 4},
    {"id": "refinement", "name": "精炼结果", "description": "精炼和验证最终结果", "order": 5},
]

# 步骤 id -> 问题/知识分类（values/strengths/interests），供 question_service、guide_tool 等使用
STEP_TO_CATEGORY: Dict[str, str] = {
    "values_exploration": "values",
    "strengths_exploration": "strengths",
    "interests_exploration": "interests",
}

# 仅「探索类」步骤 id 列表（用于工具 enum、引导问题等）
EXPLORATION_STEP_IDS: List[str] = [
    "values_exploration",
    "strengths_exploration",
    "interests_exploration",
]
