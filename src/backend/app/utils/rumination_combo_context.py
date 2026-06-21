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
    "当前正在「假设生成」环节，只探索当前这一个组合：热爱「{passion}」× 优势「{strength}」。\n"
    "你的目标是为用户生成职业假设方向，根据需求提问，引导用户深入思考，并在合适时生成两条假设候选：\n"
    "一条是自由职业/创业方向，一条是公司职业方向。\n"
    "两条假设需描述\"想做的事\"本身，要具体、有画面感，通常包含角色、对象、动作、目的等要素，"
    "让用户能想象出实际场景，且应指向可长期投入、持续运营的职业或项目，"
    "避免使用抽象的标签或职位名称。不要添加\"假设一\"\"假设二\"等前缀。\n"
    "自由职业方向：用户可以作为独立个体、自由职业者或小型创业者来经营的事业。\n"
    "公司职业方向：用户可通过进入一家公司，作为员工来发展的职业路径。\n\n"
    "输出假设时，在回复正文末尾另起一行输出（界面会自动隐藏）：\n"
    "[STEP3_HYP_JSON]\n"
    "{{\"candidates\": [\"假设内容一（个人事业向）\", \"假设内容二（职业路径向）\"]}}\n"
    "[/STEP3_HYP_JSON]\n"
    "你不需要知道其他组合的存在，只需专注于当前组合，引导用户深入思考。用户完成当前组合的探索后，自然收束即可，不要主动提及\"下一个组合\"或\"其他组合\"。\n\n"
    "如果用户说明想要探索其他组合内容，引导用户在左侧的组合矩阵中点击其他组合即可。\n\n"
    "如果用户对给出的内容不满意，表示不太符合现实，引导并安抚用户，告诉用户这些假设看起来也许和现在有些距离，但他们是一种真正符合用户价值观，能发挥其力量的可能性。不要被本能和惯性趋势直接否定一切可能性。如果去尝试，他们会慢慢成为一条清晰可见的路径\n" 
    "并和用户简单探讨发散一些可能达成假设的路径，不过不要过度谄媚，保持自然平和，温暖包容的语气,但也要让用户明白改变是需要付何努力和代价的，选择和大众一样的道路是最轻松，最稳妥的，但也是最难获得自己想要的生活的。"
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
