"""
锚点摘要提炼：按 goals + 可扩展字段生成结构化摘要，供 llm_messages 使用。

写入时机：结论卡首次展示、每次弹出结论卡、step 提交、每 20 轮。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.llmapi import LLMMessage
from app.core.llmapi.factory import get_default_llm_provider
from app.domain.conclusion_card_goals import get_conclusion_card_goal
from app.utils.report_registry import ReportRegistry, STEP_IDS

logger = logging.getLogger(__name__)

ANCHOR_EXTENSIBLE_FIELDS = ["personality", "style", "conflicts"]
"""可扩展锚点字段：用户性格、表达风格、冲突矛盾点等"""


def _build_anchor_prompt(
    phase: str,
    conv_text: str,
    dimension_conclusion: Optional[Dict] = None,
    prior_anchor: Optional[Dict] = None,
    round_count: Optional[int] = None,
) -> str:
    goal = get_conclusion_card_goal(phase)
    objective = goal.get("objective", "")
    must_capture = goal.get("must_capture") or []

    prior_hint = ""
    if prior_anchor and prior_anchor.get("goals"):
        prior_hint = f"""

【重要】已有锚点摘要，若本轮对话与之前相比变化不大，不必过度摘要，可适度沿用已有内容。仅在确有重要新增信息时更新。"""

    round_hint = ""
    if round_count is not None and round_count >= 20:
        round_hint = f"\n\n本轮为第 {round_count} 轮对话，请提炼此前对话的关键信息形成锚点。"

    conclusion_hint = ""
    if dimension_conclusion:
        kw = dimension_conclusion.get("keywords") or []
        summary = dimension_conclusion.get("summary") or dimension_conclusion.get("ai_summary", "")
        conclusion_hint = f"""

【本阶段已产出结论】
关键词：{', '.join(kw) if isinstance(kw, list) else kw}
摘要：{summary}
请将以上结论纳入 goals 部分。"""

    return f"""基于以下对话，生成结构化锚点摘要。{prior_hint}{conclusion_hint}{round_hint}

本阶段目标：{objective}
必须覆盖：{', '.join(must_capture) if must_capture else '无'}

请输出 JSON，格式：
{{
  "goals": "本阶段已沉淀的核心结论与目标达成情况（1-3句话）",
  "personality": "用户的性格或沟通特点（简短）",
  "style": "用户的文字表达风格（简短）",
  "conflicts": "用户提及的矛盾、冲突或待澄清点（若有则写，无则空字符串）"
}}

若某些字段无足够信息可留空字符串。只输出 JSON，不要其他内容。

对话内容：
---
{conv_text[:6000]}
---"""


async def refine_and_save_anchor(
    report_id: str,
    phase: str,
    category: str,
    conv_manager: Any,
    base_dir: str,
    dimension_conclusion: Optional[Dict] = None,
    prior_anchor: Optional[Dict] = None,
    round_count: Optional[int] = None,
    vip_level: int = 1,
) -> Optional[Dict]:
    """
    提炼锚点摘要并写入 record.json 的 steps.{phase}.anchor_summary。

    Args:
        report_id: 报告 ID
        phase: 阶段（values/strengths/interests/purpose）
        category: 存储 category，即 phase__session_id
        conv_manager: ConversationFileManager 实例
        base_dir: reports 根目录
        dimension_conclusion: 当前结论卡内容（若有）
        prior_anchor: 已有锚点（用于「变化不大则不过度摘要」）
        round_count: 当前轮数（每 20 轮触发时传入）

    Returns:
        生成的锚点摘要 dict，失败返回 None
    """
    if phase not in STEP_IDS or phase == "rumination":
        return None

    try:
        conv_data = await conv_manager.get_conversation_data(report_id, category)
        messages = conv_data.get("messages", []) or []
    except Exception as e:
        logger.warning("context_refiner: get_conversation_data failed: %s", e)
        return None

    conv_text = "\n\n".join(
        f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages[-40:]
    )
    if not conv_text.strip():
        return None

    prompt = _build_anchor_prompt(phase, conv_text, dimension_conclusion, prior_anchor, round_count)

    try:
        llm = get_default_llm_provider(vip_level=vip_level)
        resp = await llm.chat([LLMMessage(role="user", content=prompt)], temperature=0.2)
        text = (resp.content or "").strip()
    except Exception as e:
        logger.exception("context_refiner: LLM failed: %s", e)
        return None

    try:
        text_clean = text
        if "```json" in text:
            text_clean = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text_clean = text.split("```")[1].split("```")[0].strip()
        anchor = json.loads(text_clean)
        if not isinstance(anchor, dict):
            anchor = {"goals": str(anchor)}
    except json.JSONDecodeError:
        logger.warning("context_refiner: invalid JSON, using raw as goals: %s", text[:200])
        anchor = {"goals": text[:1000], "personality": "", "style": "", "conflicts": ""}

    for k in ANCHOR_EXTENSIBLE_FIELDS:
        anchor.setdefault(k, "")

    registry = ReportRegistry(base_dir=base_dir)
    registry.update_step_anchor_summary(report_id, phase, anchor)

    return anchor


def format_anchor_for_prompt(anchor: Optional[Dict]) -> str:
    """将锚点摘要格式化为可插入 llm_messages 的文本"""
    if not anchor or not isinstance(anchor, dict):
        return ""
    parts = []
    if anchor.get("goals"):
        parts.append(f"[本阶段要点] {anchor['goals']}")
    for k in ANCHOR_EXTENSIBLE_FIELDS:
        v = anchor.get(k)
        if v and isinstance(v, str) and v.strip():
            label = {"personality": "性格特点", "style": "表达风格", "conflicts": "矛盾/待澄清"}.get(k, k)
            parts.append(f"[{label}] {v.strip()}")
    return "\n".join(parts) if parts else ""


def load_anchor_for_phase(report_id: str, phase: str, base_dir: str) -> Optional[Dict]:
    """从 record.json 加载指定阶段的锚点摘要"""
    registry = ReportRegistry(base_dir=base_dir)
    record = registry.get_report_by_id(report_id)
    if not record:
        return None
    step = (record.get("steps") or {}).get(phase) or {}
    return step.get("anchor_summary")


# ---------------------------------------------------------------------------
# Rumination per-step anchor（沉淀筛选阶段，按子步独立生成摘要）
# ---------------------------------------------------------------------------

_RUMINATION_STEP_OBJECTIVES = {
    1: "确认用户的热爱领域与核心优势，生成热爱×优势组合表",
    2: "分析热爱与优势的匹配性，用户确认或修改匹配结果",
    3: "为每个热爱+优势组合生成并确认具体假设方向",
    4: "用价值观过滤假设，判断每个假设的工作目的",
    5: "用激情过滤假设，区分「忍不住想做」与「应该做」",
    6: "用现实性过滤假设，区分「现在可做」与「未来再做」",
    7: "最终选择并确认要投入的核心假设",
}


async def refine_and_save_rumination_step_anchor(
    report_id: str,
    filter_step: int,
    category: str,
    conv_manager: Any,
    vip_level: int = 1,
) -> Optional[str]:
    """为 rumination 的单个子步生成摘要，存入对话文件 metadata.step_anchors。

    Args:
        report_id: 报告 ID
        filter_step: 当前子步（1-7）
        category: 对话文件 category（rumination__{thread_id}）
        conv_manager: ConversationFileManager 实例
        vip_level: 用户 VIP 等级

    Returns:
        生成的摘要文本（goals），失败返回 None
    """
    if not (1 <= filter_step <= 7):
        return None

    try:
        conv_data = await conv_manager.get_conversation_data(report_id, category)
        messages = conv_data.get("messages") or []
    except Exception as e:
        logger.warning("rumination_anchor: get_conversation_data failed: %s", e)
        return None

    # 只取当前 step 的消息
    step_msgs = [m for m in messages if int(m.get("filter_step") or 0) == filter_step]
    if not step_msgs:
        return None

    conv_text = "\n\n".join(
        f"{m.get('role', 'user')}: {m.get('content', '')}" for m in step_msgs[-30:]
    )
    if not conv_text.strip():
        return None

    objective = _RUMINATION_STEP_OBJECTIVES.get(filter_step, "完成筛选子步")

    prompt = f"""基于以下对话，生成该筛选子步的摘要（2-4句话）。

子步：第 {filter_step} 步
目标：{objective}

请只输出摘要文本，不要 JSON 或其他格式。如果对话内容很少，可以简短总结。

对话内容：
---
{conv_text[:4000]}
---"""

    try:
        llm = get_default_llm_provider(vip_level=vip_level)
        resp = await llm.chat([LLMMessage(role="user", content=prompt)], temperature=0.2)
        text = (resp.content or "").strip()
    except Exception as e:
        logger.exception("rumination_anchor: LLM failed step=%d: %s", filter_step, e)
        return None

    if not text:
        return None

    # 清理可能的 markdown 包裹
    if "```" in text:
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else parts[0]
        text = text.strip()

    # 存入对话文件 metadata.step_anchors
    try:
        await conv_manager.update_metadata(
            report_id,
            category,
            {"step_anchor_" + str(filter_step): text},
        )
    except Exception as e:
        logger.warning("rumination_anchor: save failed step=%d: %s", filter_step, e)

    logger.info("rumination_anchor: saved step=%d len=%d", filter_step, len(text))
    return text


async def load_rumination_step_anchors(
    report_id: str,
    category: str,
    conv_manager: Any,
) -> Dict[str, str]:
    """从对话文件 metadata 中加载所有 rumination 子步 anchor。

    Returns:
        {"1": "摘要...", "2": "摘要...", ...}
    """
    try:
        conv_data = await conv_manager.get_conversation_data(report_id, category)
        meta = conv_data.get("metadata") or {}
    except Exception:
        return {}
    anchors = {}
    for k, v in meta.items():
        if k.startswith("step_anchor_") and isinstance(v, str) and v.strip():
            step_num = k.replace("step_anchor_", "")
            if step_num.isdigit():
                anchors[step_num] = v.strip()
    return anchors
