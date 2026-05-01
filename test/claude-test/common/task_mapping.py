"""Task ID → 测试文件映射 + 人工评审判定规则"""
from __future__ import annotations

from typing import FrozenSet, Dict, Set

# ── Task ID → 测试文件映射 ──────────────────────────────────────────
TASK_ID_TO_TEST_FILE: Dict[str, str] = {
    # 第一批（原始 14 个 Task ID）
    "S-02": "backend/test_table_widgets.py",
    "P-06": "backend/test_table_widgets.py",
    "U-04": "backend/test_table_widgets.py",
    "P-05": "backend/test_table_widgets.py",
    "U-07": "backend/test_table_widgets.py",
    "S-03": "backend/test_rumination_ops.py",
    "S-09": "backend/test_rumination_ops.py",
    "P-04": "backend/test_neg_gate.py",
    "S-07": "backend/test_neg_gate.py",
    "P-07": "backend/test_neg_gate.py",
    "O-01": "backend/test_opening_chain.py",
    "P-08": "backend/test_prompt_strings.py",
    "P-03": "backend/test_prompt_strings.py",
    "P-02": "backend/test_prompt_strings.py",
    # 第二批第一批后端（8 个 Task ID）
    "O-03": "backend/test_activation_security.py",
    "O-04": "backend/test_survey_user_dimension.py",
    "O-05": "backend/test_conversation_dedup.py",
    "S-04": "backend/test_survey_user_dimension.py",
    "S-05": "backend/test_journey_resume.py",
    "S-06": "backend/test_journey_resume.py",
    "S-08": "backend/test_rumination_recall.py",
    "S-10": "backend/test_rumination_recall.py",
    # 第二批第二批后端（1 个 Task ID）
    "S-01": "backend/test_completion_flow.py",
    # 第三批（3 个 Task ID — 源码 cross-check + 后端 API 测试）
    "O-02": "backend/test_login_redirect.py",
    "O-06": "backend/test_cross_device_sync.py",
    "U-06": "backend/test_dropdown_naming.py",
}

# ── 需人工评审的 Task ID（视觉/LLM 输出质量/交互体验） ─────────────
HUMAN_REVIEWED_IDS: FrozenSet[str] = frozenset({
    "U-01",  # 表头透明 — 视觉
    "U-02",  # 气泡显示 — 视觉
    "U-03",  # 列宽 — 视觉
    "U-05",  # hover 样式 — 视觉
    "U-08",  # 点赞颜色 — 视觉+溯源
})

# ── 人工评审关键词（描述中包含这些词则标记为 human_reviewed） ──────
HUMAN_REVIEW_KEYWORDS: Set[str] = {
    "模型推理质量",
    "视觉效果",
    "精致",
    "裁切",
    "穿透",
    "彩色填充",
    "反馈明显",
    "闪烁",
}

# ── 前端 / E2E 关联 Task ID（当前标记为 automated 但暂无实现） ─────
FRONTEND_TASK_IDS: FrozenSet[str] = frozenset(set())
E2E_TASK_IDS: FrozenSet[str] = frozenset(set())


def classify_item(task_ids: list[str], description: str) -> str:
    """判定测试项类型：automated | human_reviewed"""
    # 任一 task ID 在人工评审集合中
    if any(tid in HUMAN_REVIEWED_IDS for tid in task_ids):
        return "human_reviewed"
    # 描述包含人工评审关键词
    for kw in HUMAN_REVIEW_KEYWORDS:
        if kw in description:
            return "human_reviewed"
    return "automated"


def get_test_file(task_ids: list[str]) -> str | None:
    """返回第一个有映射的 task ID 对应的测试文件"""
    for tid in task_ids:
        if tid in TASK_ID_TO_TEST_FILE:
            return TASK_ID_TO_TEST_FILE[tid]
    return None


def resolve_test_type(test_file: str | None) -> str:
    """从测试文件路径推断测试类型"""
    if not test_file:
        return "unknown"
    if test_file.startswith("backend/"):
        return "backend"
    if test_file.startswith("frontend/"):
        return "frontend"
    if test_file.startswith("e2e/"):
        return "e2e"
    return "unknown"
