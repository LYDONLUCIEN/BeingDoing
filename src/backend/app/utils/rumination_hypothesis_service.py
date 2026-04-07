"""
Rumination 假设列：调用 LLM 生成三条职业假设，失败时降级为占位文案。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from app.core.llmapi.base import LLMMessage

from app.utils.rumination_ops import fallback_hypotheses

logger = logging.getLogger(__name__)


def _parse_hypothesis_list(text: str) -> List[str]:
    """从模型输出中解析 3 条字符串。"""
    if not text:
        return []
    s = text.strip()
    # 优先整段 JSON 数组
    try:
        arr = json.loads(s)
        if isinstance(arr, list):
            out = [str(x).strip() for x in arr if str(x).strip()]
            return out[:3]
    except (json.JSONDecodeError, TypeError):
        pass
    m = re.search(r"\[.*\]", s, re.DOTALL)
    if m:
        try:
            arr = json.loads(m.group(0))
            if isinstance(arr, list):
                out = [str(x).strip() for x in arr if str(x).strip()]
                return out[:3]
        except (json.JSONDecodeError, TypeError):
            pass
    lines = [ln.strip().lstrip("0123456789.-、)） ") for ln in s.splitlines() if ln.strip()]
    return [x for x in lines if x][:3]


async def generate_three_hypotheses_for_row(
    llm: Any,
    *,
    passion: str,
    strength: str,
    match_reason: str = "",
    values_hint: str = "",
    row_index: int = 0,
) -> List[str]:
    """
    为单行生成三条短假设（中文，单一方向表述，避免并列堆砌）。
    """
    system = (
        "你是职业规划师助理。根据用户的热爱、优势生成三条不同的、可落地的职业方向假设。"
        "每条一句，15-40 字，中文；不要编号外的多余解释。"
        "输出严格 JSON 数组，恰好 3 个字符串，例如 [\"...\",\"...\",\"...\"]。"
    )
    user = (
        f"热爱：{passion}\n优势：{strength}\n匹配说明：{match_reason or '（无）'}\n"
        f"价值观参考：{values_hint or '（无）'}"
    )
    try:
        resp = await llm.chat(
            [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user)],
            temperature=0.75,
            max_tokens=400,
        )
        raw = (resp.content or "").strip()
        got = _parse_hypothesis_list(raw)
        if len(got) >= 3:
            return got[:3]
        if len(got) > 0:
            fb = fallback_hypotheses(passion, strength, row_index)
            while len(got) < 3:
                got.append(fb[len(got) % 3])
            return got[:3]
    except Exception as e:
        logger.warning("rumination hypothesis LLM failed: %s", e)
    return list(fallback_hypotheses(passion, strength, row_index))


async def generate_two_hypotheses_for_row(
    llm: Any,
    *,
    passion: str,
    strength: str,
    match_reason: str = "",
    values_hint: str = "",
    row_index: int = 0,
) -> tuple[str, str]:
    """
    为单行生成两条假设：假设1=个人事业向，假设2=职业路径向；假设3 由调用方清空。
    """
    sys_freelance = (
        "目前处于「个人事业」向假设生成。根据热爱与优势生成一句具体假设（15-45 字），"
        "描述可独立经营、自由职业或小型创业的方向，有画面感。"
        "只输出一句正文，不要引号、编号或前后缀说明。"
    )
    sys_company = (
        "目前处于「职业路径」向假设生成。根据热爱与优势生成一句具体假设（15-45 字），"
        "描述可通过进入公司、担任某类岗位发展的路径，有画面感。"
        "只输出一句正文，不要引号、编号或前后缀说明。"
    )
    user_common = (
        f"热爱：{passion}\n优势：{strength}\n匹配说明：{match_reason or '（无）'}\n"
        f"价值观参考：{values_hint or '（无）'}"
    )

    async def _one_line(system: str) -> str:
        try:
            resp = await llm.chat(
                [
                    LLMMessage(role="system", content=system),
                    LLMMessage(role="user", content=user_common),
                ],
                temperature=0.72,
                max_tokens=160,
            )
            raw = (resp.content or "").strip()
            line = raw.split("\n")[0].strip().strip('"“”')
            return line[:220] if line else ""
        except Exception as e:
            logger.warning("rumination two-hypo single LLM failed: %s", e)
            return ""

    h1 = await _one_line(sys_freelance)
    h2 = await _one_line(sys_company)
    if len(h1) < 4 or len(h2) < 4:
        fb = fallback_hypotheses(passion, strength, row_index)
        if len(h1) < 4:
            h1 = fb[0] if fb else h1
        if len(h2) < 4:
            h2 = fb[1] if len(fb) > 1 else fb[0] if fb else h2
    return h1, h2


async def fill_hypothesis_columns_for_table(
    llm: Any,
    table: List[Dict[str, Any]],
    *,
    values_hint: str = "",
    only_empty_hypothesis_slots: bool = False,
) -> List[Dict[str, Any]]:
    """
    为表中行填充 假设1/假设2/假设3。
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
            hyps = await generate_three_hypotheses_for_row(
                llm,
                passion=passion,
                strength=strength,
                match_reason=match_reason,
                values_hint=values_hint,
                row_index=i,
            )
            row["假设1"] = hyps[0] if len(hyps) > 0 else ""
            row["假设2"] = hyps[1] if len(hyps) > 1 else ""
            row["假设3"] = hyps[2] if len(hyps) > 2 else ""
        out.append(row)
    return out
