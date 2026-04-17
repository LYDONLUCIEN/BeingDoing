"""
沉淀终步确认后的会话尾巴：短链固定结语 vs 正常 LLM 结语。

与 HTTP 路由解耦，仅依赖 conv_manager / llm 抽象，便于测试与复用。
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from app.domain.rumination_prompt_strings import RUMINATION_SHORTPATH_SKIP_CLOSING_FIXED_ZH
from app.domain.rumination_step_guidance import build_rumination_closing_epilogue_messages

logger = logging.getLogger(__name__)

NormalizeUsageFn = Callable[[Optional[dict]], dict]


async def append_post_table_finalize_message(
    *,
    llm: Any,
    conv_manager: Any,
    report_session_id: str,
    category: str,
    logical_session_id: str,
    via_short_path: bool,
    selected_summary: str,
    normalize_token_usage: NormalizeUsageFn,
) -> None:
    """
    在终步表格提交成功、且 next_action 为 finalize 时，向会话追加一条助手消息。

    - via_short_path: progress.filter_early_terminated 在进入终步保存前为 True。
    - 否则且 selected_summary 非空：调用 LLM 生成结语（非流式，与单次 submit 同请求）。
    """
    if via_short_path:
        body = RUMINATION_SHORTPATH_SKIP_CLOSING_FIXED_ZH
        await conv_manager.append_message(
            session_id=report_session_id,
            category=category,
            message={
                "role": "assistant",
                "content": body,
                "session_id": logical_session_id,
                "step_id": "rumination",
                "agent_id": "coach",
                "event": "rumination_closing_shortpath_fixed",
                "token_usage": normalize_token_usage(None),
            },
        )
        return

    summary = (selected_summary or "").strip()
    if not summary:
        return

    try:
        msgs = build_rumination_closing_epilogue_messages(summary)
        cresp = await llm.chat(msgs, temperature=0.6, max_tokens=450)
        ctext = (cresp.content or "").strip()
        if not ctext:
            return
        usage = getattr(cresp, "usage", None)
        await conv_manager.append_message(
            session_id=report_session_id,
            category=category,
            message={
                "role": "assistant",
                "content": ctext,
                "session_id": logical_session_id,
                "step_id": "rumination",
                "agent_id": "coach",
                "event": "rumination_closing_epilogue",
                "token_usage": normalize_token_usage(usage if isinstance(usage, dict) else None),
            },
        )
    except Exception as e:
        logger.warning("rumination closing epilogue skipped: %s", e)
