"""
沉淀（rumination）筛选子步：右侧引导语与主对话注入。

- 文案常量见 ``rumination_prompt_strings``；本模块负责上下文快照与 LLMMessage 组装。
- opening_mode：fixed / llm 由 ``STEP_OPENING_MODE`` 控制（当前均为 llm）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from app.core.llmapi.base import LLMMessage

from app.domain.rumination_prompt_strings import (
    OPENING_USER_WITH_TABLE_ZH,
    RUMINATION_CLOSING_EPILOGUE_SYSTEM_ZH,
    RUMINATION_CLOSING_EPILOGUE_USER_TEMPLATE_ZH,
    RUMINATION_CLOSING_USER_SUMMARY_IN_PROMPT_MAX,
    RUMINATION_ENTRY_INIT_PRIOR_MAX_CHARS,
    RUMINATION_ENTRY_INIT_SYSTEM_ZH,
    RUMINATION_ENTRY_INIT_USER_TEMPLATE_ZH,
    RUMINATION_OPENING_TABLE_JSON_MAX_LEN,
    STEP_1_OPENING_SYSTEM_ZH,
    STEP_2_OPENING_SYSTEM_ZH,
    STEP_3_OPENING_SYSTEM_ZH,
    STEP_4_OPENING_SYSTEM_ZH,
    STEP_4_OPENING_USER_TEMPLATE_ZH,
    STEP_5_OPENING_SYSTEM_ZH,
    STEP_6_OPENING_SYSTEM_ZH,
    STEP_7_OPENING_SYSTEM_ZH,
    STEP_OPENING_FIXED_ZH,
    RUMINATION_CHAT_STEP_ADDON_EN,
    RUMINATION_CHAT_STEP_ADDON_ZH,
)

OpeningMode = Literal["fixed", "llm"]

STEP_OPENING_MODE: Dict[int, OpeningMode] = {i: "llm" for i in range(1, 8)}


@dataclass
class RuminationOpeningContext:
    filter_step: int
    row_count: int
    values_keywords: str
    table_json: str
    rows: List[Any]


def build_opening_context(
    *,
    filter_step: int,
    progress: Dict[str, Any],
    values_list: List[str],
) -> RuminationOpeningContext:
    """从 progress 快照读取当前子步表格，供固定文案格式化或 LLM 提示词使用。"""
    step = max(1, min(7, int(filter_step)))
    snapshots = progress.get("filter_step_snapshots") or {}
    sk = str(step)
    ent = snapshots.get(sk) or {}
    rows = ent.get("submitted")
    if rows is None:
        rows = ent.get("initial")
    if not isinstance(rows, list):
        rows = []
    if not rows and int(progress.get("filter_step") or 0) == step:
        ft = progress.get("filter_table")
        if isinstance(ft, list):
            rows = ft

    if (
        step == 2
        and int(progress.get("filter_step") or 0) == 2
        and isinstance(progress.get("filter_table"), list)
        and (progress.get("filter_table") or [])
    ):
        rows = list(progress["filter_table"])

    row_count = len(rows)
    values_keywords = "、".join(values_list[:12]) if values_list else ""
    try:
        table_json = json.dumps(rows, ensure_ascii=False) if rows else "[]"
    except (TypeError, ValueError):
        table_json = "[]"
    max_len = RUMINATION_OPENING_TABLE_JSON_MAX_LEN
    if len(table_json) > max_len:
        table_json = table_json[:max_len] + "…（已截断）"

    return RuminationOpeningContext(
        filter_step=step,
        row_count=row_count,
        values_keywords=values_keywords or "（暂无关键词，可引导用户依表头选择）",
        table_json=table_json,
        rows=rows,
    )


def get_opening_mode(filter_step: int) -> OpeningMode:
    step = max(1, min(7, int(filter_step)))
    return STEP_OPENING_MODE.get(step, "fixed")


def render_fixed_opening_zh(filter_step: int, ctx: RuminationOpeningContext) -> str:
    step = max(1, min(7, int(filter_step)))
    template = STEP_OPENING_FIXED_ZH.get(step, "")
    if not template:
        return "请查看左侧表格，按提示完成本步选择后点击「确认」。"
    return template.format(
        row_count=ctx.row_count,
        values_keywords=ctx.values_keywords,
        table_json=ctx.table_json,
    )


def build_step_4_opening_llm_messages(ctx: RuminationOpeningContext) -> List[LLMMessage]:
    """第 4 步 user 额外含价值观关键词：行内「工作目的」尚空，关键词列表不在 table_json 中集中呈现。"""
    user = STEP_4_OPENING_USER_TEMPLATE_ZH.format(
        values_keywords=ctx.values_keywords,
        row_count=ctx.row_count,
        table_json=ctx.table_json,
    )
    return [
        LLMMessage(role="system", content=STEP_4_OPENING_SYSTEM_ZH),
        LLMMessage(role="user", content=user),
    ]


def _opening_user_standard(ctx: RuminationOpeningContext) -> str:
    return OPENING_USER_WITH_TABLE_ZH.format(row_count=ctx.row_count, table_json=ctx.table_json)


def build_opening_llm_messages(filter_step: int, ctx: RuminationOpeningContext) -> List[LLMMessage]:
    """按子步组装 LLM 消息（opening_mode=llm）。"""
    step = max(1, min(7, int(filter_step)))
    builders = {
        1: (STEP_1_OPENING_SYSTEM_ZH, _opening_user_standard(ctx)),
        2: (STEP_2_OPENING_SYSTEM_ZH, _opening_user_standard(ctx)),
        3: (STEP_3_OPENING_SYSTEM_ZH, _opening_user_standard(ctx)),
        5: (STEP_5_OPENING_SYSTEM_ZH, _opening_user_standard(ctx)),
        6: (STEP_6_OPENING_SYSTEM_ZH, _opening_user_standard(ctx)),
        7: (STEP_7_OPENING_SYSTEM_ZH, _opening_user_standard(ctx)),
    }
    if step == 4:
        return build_step_4_opening_llm_messages(ctx)
    if step in builders:
        sys_t, usr = builders[step]
        return [
            LLMMessage(role="system", content=sys_t),
            LLMMessage(role="user", content=usr),
        ]
    raise ValueError(f"rumination opening llm not implemented for step {step}")


def build_rumination_closing_epilogue_messages(selected_summary: str) -> List[LLMMessage]:
    summary = (selected_summary or "").strip() or "（用户已完成方向点选）"
    user = RUMINATION_CLOSING_EPILOGUE_USER_TEMPLATE_ZH.format(
        selected_summary=summary[:RUMINATION_CLOSING_USER_SUMMARY_IN_PROMPT_MAX]
    )
    return [
        LLMMessage(role="system", content=RUMINATION_CLOSING_EPILOGUE_SYSTEM_ZH),
        LLMMessage(role="user", content=user),
    ]


def build_rumination_entry_init_messages(*, basic_info: str, prior_block: str) -> List[LLMMessage]:
    bi = (basic_info or "").strip() or "（暂无）"
    pr = (prior_block or "").strip() or "（暂无）"
    user = RUMINATION_ENTRY_INIT_USER_TEMPLATE_ZH.format(
        basic_info=bi,
        prior_block=pr[:RUMINATION_ENTRY_INIT_PRIOR_MAX_CHARS],
    )
    return [
        LLMMessage(role="system", content=RUMINATION_ENTRY_INIT_SYSTEM_ZH),
        LLMMessage(role="user", content=user),
    ]


def get_rumination_chat_step_addon(filter_step: int, locale: str = "zh") -> str:
    step = max(1, min(7, int(filter_step)))
    loc = (locale or "zh").strip().lower()
    if loc.startswith("en"):
        text = RUMINATION_CHAT_STEP_ADDON_EN.get(step, "")
    else:
        text = RUMINATION_CHAT_STEP_ADDON_ZH.get(step, "")
    return (text or "").strip()
