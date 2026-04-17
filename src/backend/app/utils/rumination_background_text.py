"""
沉淀假设生成：拼装「用户背景信息和诉求」纯文本（无 I/O，便于单测与复用）。
"""
from __future__ import annotations

PRIOR_SNIPPET_MAX_DEFAULT = 6000


def compose_hypothesis_user_background(
    *,
    values_hint: str,
    prior_rumination_text: str,
    prior_max_chars: int = PRIOR_SNIPPET_MAX_DEFAULT,
) -> str:
    """
    Args:
        values_hint: 价值观关键词节选（如「、」拼接）。
        prior_rumination_text: 沉淀阶段 prior 全文（由路由层加载后传入）。
        prior_max_chars: prior 截断上限，控制假设 prompt 体积。
    """
    parts: list[str] = []
    vh = (values_hint or "").strip()
    if vh:
        parts.append(f"价值观关键词参考：{vh}")
    pr = (prior_rumination_text or "").strip()
    if pr:
        parts.append(f"前序探索摘要：\n{pr[:prior_max_chars]}")
    return "\n\n".join(parts) if parts else ""
