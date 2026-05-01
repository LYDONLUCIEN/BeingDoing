"""
沉淀（rumination）筛选子步：右侧引导语与主对话注入。

- 文案常量见 ``rumination_prompt_strings``；本模块负责上下文快照与 LLMMessage 组装。
- opening_mode：fixed / llm 由 ``STEP_OPENING_MODE`` 控制（当前均为 llm）。

============================================================================
引导语（opening）调用链路说明
============================================================================

沉淀阶段引导语分两层，不可混用：

1. 阶段级引导（step_copy.yaml — 前端弹窗展示）
   - 来源: domain/prompts/templates/step_copy.yaml → rumination.intro_zh
   - 入口: GET /init 返回 step_intro 字段 → get_step_copy("rumination", "intro")
   - 用途: 阶段进入时的欢迎弹窗（前端独立渲染），与对话流无关
   - 特征: 纯静态文案，不包含表格数据，不经过 LLM

2. 首轮对话开场白（entry_init — 对话流首条 assistant 消息）
   - 来源: rumination_prompt_strings.RUMINATION_ENTRY_INIT_SYSTEM_ZH / _USER_TEMPLATE_ZH
   - 入口: POST /init → _simple_init_impl() → synthesize_rumination_entry_greeting()
   - 降级: rumination_init_greeting.RUMINATION_INIT_FALLBACK_ZH（LLM 失败时）
   - 用途: 对话流中第一条 assistant 消息，带个性化信息（basic_info + prior_block）
   - 特征: 由 LLM 动态生成，包含用户上下文

3. 筛选子步引导语（filter step opening — 每个子步进入时）
   - 优先级: 由 STEP_OPENING_MODE 控制
     a) mode="llm"（当前全量）: POST /rumination-step-opening-stream → build_opening_llm_messages()
        - system prompt: STEP_{1..7}_OPENING_SYSTEM_ZH（per-step 专用提示词）
        - user prompt:   OPENING_USER_WITH_TABLE_ZH（标准）/ STEP_4_OPENING_USER_TEMPLATE_ZH（步骤4专用）
     b) mode="fixed":    GET /rumination-step-opening → render_fixed_opening_zh()
        - 模板来源:       STEP_OPENING_FIXED_ZH（固定文案字典）
   - 用途: 进入筛选步骤1-7时右侧对话区的引导语
   - 特征: mode="llm" 时包含表格数据；mode="fixed" 时为格式化后的静态文本

⚠️ 重要边界:
- step_copy.yaml 的 rumination.intro_zh 仅用于阶段弹窗，不应出现在对话流中
- 筛选子步引导语（step 1-7 opening）不应包含 step_copy.yaml 的内容
- 各步骤的 LLM opening system prompt 严格按步骤对应，不可交叉使用
============================================================================
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
    DEEP_CHAT_STEP_SYSTEM_MAP,
    STEP_3_LLM_FAILED_DEEP_CHAT_SYSTEM_ZH,
)

OpeningMode = Literal["fixed", "llm"]

STEP_OPENING_MODE: Dict[int, OpeningMode] = {i: "llm" for i in range(1, 8)}


@dataclass
class RuminationOpeningContext:
    filter_step: int
    row_count: int
    values_keywords: str
    values_source: str
    table_json: str
    rows: List[Any]


def build_opening_context(
    *,
    filter_step: int,
    progress: Dict[str, Any],
    values_list: List[str],
    values_source: str = "",
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
        values_source=values_source or "none",
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
    text = template.format(
        row_count=ctx.row_count,
        values_keywords=ctx.values_keywords,
        table_json=ctx.table_json,
    )
    # step 4 降级：无价值观关键词来源时追加提示
    if step == 4 and ctx.values_source == "none":
        text += "\n\n（当前未解析到您的价值观关键词，请在「工作目的」列选「其他」手动填写。）"
    return text


def build_step_4_opening_llm_messages(ctx: RuminationOpeningContext) -> List[LLMMessage]:
    """第 4 步 user 额外含价值观关键词：行内「工作目的」尚空，关键词列表不在 table_json 中集中呈现。

    当 values_source 为 none 时，在 user 模板中追加降级提示，引导 LLM 提醒用户手动填写。
    """
    user = STEP_4_OPENING_USER_TEMPLATE_ZH.format(
        values_keywords=ctx.values_keywords,
        row_count=ctx.row_count,
        table_json=ctx.table_json,
    )
    # 降级提示：无关键词时提醒 LLM 引导用户自填
    if ctx.values_source == "none":
        user += (
            "\n\n【重要】当前未解析到该用户的价值观关键词列表，下拉框中仅有「其他」选项。"
            "请引导用户在「工作目的」列选「其他」并手动填写他们自己的价值观描述，"
            "不要编造不存在的关键词选项。"
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


def get_deep_chat_step_system(step: int, llm_failed: bool = False) -> str:
    """获取深入聊天阶段的步骤差异化 system 片段。

    每个步骤（2/3/5/6）拥有独立的 system prompt 片段，包含：
    - 步骤专属角色定位与目标
    - 字段上下文模板
    - 逐条处理流程约束
    - 完成与退出约束

    Args:
        step: 当前步骤编号（2/3/5/6）
        llm_failed: LLM 质检是否失败（仅步骤 3 有降级逻辑）

    Returns:
        步骤专属的 system 片段文本；若步骤不在映射中则返回空字符串。
    """
    step = int(step)
    # 步骤 3 LLM 失败时使用降级片段
    if step == 3 and llm_failed:
        return STEP_3_LLM_FAILED_DEEP_CHAT_SYSTEM_ZH
    return DEEP_CHAT_STEP_SYSTEM_MAP.get(step, "")
