"""
Rumination 假设列：按产品文档一次 LLM 生成两条假设（自由职业向 + 公司职业向），失败时降级为占位。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Tuple

from app.core.llmapi.base import LLMMessage

from app.utils.rumination_ops import fallback_hypotheses

logger = logging.getLogger(__name__)


def _parse_hypothesis_pair(text: str) -> Tuple[str, str]:
    """从模型输出中解析两条字符串（优先 JSON 数组，恰好 2 个元素）。"""
    if not text:
        return "", ""
    s = text.strip()
    try:
        arr = json.loads(s)
        if isinstance(arr, list) and len(arr) >= 2:
            a = str(arr[0]).strip()
            b = str(arr[1]).strip()
            return a, b
    except (json.JSONDecodeError, TypeError):
        pass
    m = re.search(r"\[.*\]", s, re.DOTALL)
    if m:
        try:
            arr = json.loads(m.group(0))
            if isinstance(arr, list) and len(arr) >= 2:
                return str(arr[0]).strip(), str(arr[1]).strip()
        except (json.JSONDecodeError, TypeError):
            pass
    lines = [ln.strip().lstrip("0123456789.-、)） ") for ln in s.splitlines() if ln.strip()]
    if len(lines) >= 2:
        return lines[0], lines[1]
    if len(lines) == 1:
        return lines[0], ""
    return "", ""


# 文档 rumination-prompt.md 中两段「假设生成」原文合并为一次生成任务（输出格式在 system 末约束）
HYPOTHESIS_PAIR_SYSTEM_ZH = (
    "你将根据用户消息中的「热爱」「优势」「匹配说明」以及「用户背景信息和诉求」，在同一回复中完成两项输出。\n\n"
    "【任务一：自由职业导向假设】\n"
    "目前正处于「假设生成」环节。根据以下要求结合用户背景信息和诉求生成一句话的「自由职业导向假设」：\n"
    "为当前组合（热爱：见用户消息，优势：见用户消息）生成一个具体的假设。假设需描述「想做的事」本身，要具体、有画面感，"
    "通常包含角色、对象、动作、目的等要素，让用户能想象出实际场景，且应指向可长期投入、持续运营的职业或项目，"
    "避免使用抽象的标签或职位名称。并可以作为独立个体、自由职业者或小型创业者来经营的事业。\n\n"
    "【任务二：公司职业导向假设】\n"
    "目前正处于「假设生成」环节。根据以下要求结合用户背景信息和诉求生成一句话的「公司职业导向假设」：\n"
    "为当前组合（热爱：见用户消息，优势：见用户消息）生成一个具体的假设。假设需描述「想做的事」本身，要具体、有画面感，"
    "通常包含角色、对象、动作、目的等要素，让用户能想象出实际场景，且应指向可长期投入、持续运营的职业或项目，"
    "避免使用抽象的标签或职位名称。并通过进入一家公司，作为员工来发展的职业路径。\n\n"
    "【输出格式】\n"
    "只输出严格 JSON 数组，恰好 2 个字符串：第一个字符串为任务一的正文，第二个为任务二的正文。"
    "不要输出数组以外的任何说明、标点或 Markdown。"
)

HYPOTHESIS_PAIR_USER_TEMPLATE_ZH = (
    "热爱：{passion}\n"
    "优势：{strength}\n"
    "匹配说明：{match_reason}\n\n"
    "以下是用户背景信息和诉求：\n"
    "{user_background}\n"
)


async def generate_hypothesis_pair_for_row(
    llm: Any,
    *,
    passion: str,
    strength: str,
    match_reason: str = "",
    user_background: str = "",
    row_index: int = 0,
) -> Tuple[str, str]:
    """为单行一次生成两条假设：假设1=自由职业向，假设2=公司职业向。"""
    ub = (user_background or "").strip() or "（暂无额外背景，请仅根据热爱与优势生成。）"
    mr = (match_reason or "").strip() or "（无）"
    user = HYPOTHESIS_PAIR_USER_TEMPLATE_ZH.format(
        passion=passion or "（未填）",
        strength=strength or "（未填）",
        match_reason=mr,
        user_background=ub,
    )
    try:
        resp = await llm.chat(
            [
                LLMMessage(role="system", content=HYPOTHESIS_PAIR_SYSTEM_ZH),
                LLMMessage(role="user", content=user),
            ],
            temperature=0.72,
            max_tokens=500,
        )
        raw = (resp.content or "").strip()
        h1, h2 = _parse_hypothesis_pair(raw)
        if len(h1) >= 4 and len(h2) >= 4:
            return h1[:400], h2[:400]
        fb = fallback_hypotheses(passion, strength, row_index)
        if len(h1) < 4:
            h1 = fb[0] if fb else h1
        if len(h2) < 4:
            h2 = fb[1] if len(fb) > 1 else (fb[0] if fb else h2)
        return h1[:400], h2[:400]
    except Exception as e:
        logger.warning("rumination hypothesis pair LLM failed: %s", e)
    fb = fallback_hypotheses(passion, strength, row_index)
    return (fb[0] if fb else "")[:400], (fb[1] if len(fb) > 1 else fb[0] if fb else "")[:400]


def ensure_row_has_pair_hypotheses(
    row: Dict[str, Any],
    *,
    passion: str,
    strength: str,
    row_index: int = 0,
) -> None:
    """保证假设1、假设2非空；假设3不再使用，置空。"""
    row["假设3"] = ""
    fb = fallback_hypotheses(passion, strength, row_index)
    if not str(row.get("假设1") or "").strip():
        row["假设1"] = fb[0] if fb else ""
    if not str(row.get("假设2") or "").strip():
        row["假设2"] = fb[1] if len(fb) > 1 else (fb[0] if fb else "")


async def fill_hypothesis_columns_for_table(
    llm: Any,
    table: List[Dict[str, Any]],
    *,
    user_background: str = "",
    only_empty_hypothesis_slots: bool = False,
) -> List[Dict[str, Any]]:
    """
    为表中行填充假设1/假设2（一次 LLM 调用生成一对）。

    only_empty_hypothesis_slots=True 时仅处理「用户确认的假设」为空且假设1 为空的行（第二轮）。
    """
    out: List[Dict[str, Any]] = []
    for i, r in enumerate(table):
        row = dict(r)
        passion = str(row.get("热爱") or "")
        strength = str(row.get("优势") or "")
        match_reason = str(row.get("匹配原因") or "")
        confirmed = (row.get("用户确认的假设") or "").strip()
        h1 = (row.get("假设1") or "").strip()

        need_fill = True
        if only_empty_hypothesis_slots:
            need_fill = not confirmed and not h1

        if need_fill:
            p1, p2 = await generate_hypothesis_pair_for_row(
                llm,
                passion=passion,
                strength=strength,
                match_reason=match_reason,
                user_background=user_background,
                row_index=i,
            )
            row["假设1"] = p1
            row["假设2"] = p2
            row["假设3"] = ""
        else:
            row["假设3"] = ""
        ensure_row_has_pair_hypotheses(row, passion=passion, strength=strength, row_index=i)
        out.append(row)
    return out
