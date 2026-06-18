"""
组合对话上下文：按 combo_id 隔离消息 + 构建组合专属 system prompt。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def slice_messages_for_combo(
    messages: List[Dict[str, Any]], combo_id: str
) -> List[Dict[str, Any]]:
    """从消息列表中筛选指定 combo_id 的消息。"""
    return [m for m in messages if m.get("combo_id") == combo_id]


# ── 固定模板引导语 ──────────────────────────────────────────────

COMBO_GUIDE_FIRST_TEMPLATE_ZH = (
    "让我们探索第1个组合「{passion} × {strength}」，"
    "你觉得它们结合后可以做什么？"
)

COMBO_GUIDE_TEMPLATE_ZH = (
    "让我们探索「{passion} × {strength}」，"
    "你觉得它们结合后可以做什么？"
)


def build_combo_guide_text(
    passion: str,
    strength: str,
    completed_count: int,
) -> str:
    """生成固定模板引导语。第一个组合（completed_count==0）带序号，后续不带。"""
    if completed_count == 0:
        return COMBO_GUIDE_FIRST_TEMPLATE_ZH.format(
            passion=passion,
            strength=strength,
        )
    return COMBO_GUIDE_TEMPLATE_ZH.format(
        passion=passion,
        strength=strength,
    )


# ── 组合对话 system prompt 追加段 ──────────────────────────────

COMBO_CHAT_SYSTEM_ADDON_ZH = (
    "当前正在「假设生成」环节，探索组合：热爱「{passion}」× 优势「{strength}」。\n"
    "请针对这个组合引导用户思考具体可落地的方向，并在合适时生成两条假设候选：\n"
    "一条是自由职业/创业方向，一条是公司职业方向。\n"
    "使用 [STEP3_HYP_JSON] 协议块输出假设候选。"
)


def build_combo_chat_system_addon(
    passion: str,
    strength: str,
) -> str:
    """构建组合对话的 system prompt 追加段。"""
    return COMBO_CHAT_SYSTEM_ADDON_ZH.format(
        passion=passion or "（未填）",
        strength=strength or "（未填）",
    )


def build_combo_first_message(
    passion: str,
    strength: str,
    completed_count: int,
    combo_id: Optional[str] = None,
) -> Dict[str, Any]:
    """为组合生成首条 assistant 消息（引导语）。"""
    from datetime import datetime, timezone
    return {
        "role": "assistant",
        "content": build_combo_guide_text(passion, strength, completed_count),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "type": "combo_guide",
        "filter_step": 3,
        "combo_id": combo_id,
    }
