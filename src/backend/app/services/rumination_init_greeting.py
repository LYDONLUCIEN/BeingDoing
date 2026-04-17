"""
沉淀阶段首次进入线程时的开场白生成（LLM + 降级文案）。
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional, Tuple

from app.domain.rumination_step_guidance import build_rumination_entry_init_messages

logger = logging.getLogger(__name__)

NormalizeUsageFn = Callable[[Optional[dict]], dict]

RUMINATION_INIT_FALLBACK_ZH = (
    "已进入最后一轮——沉淀与选择。我们将一起筛选和讨论，帮你确定三个可以尝试的职业发展方向。"
    "你可以先打开左侧表格按步骤操作；若有疑问，随时在右侧告诉我。"
)


async def synthesize_rumination_entry_greeting(
    llm: Any,
    *,
    basic_info: str,
    prior_block: str,
    normalize_token_usage: NormalizeUsageFn,
    temperature: float = 0.65,
    max_tokens: int = 500,
) -> Tuple[str, dict]:
    """
    Returns:
        (reply_text, token_usage_dict)
    """
    msgs = build_rumination_entry_init_messages(basic_info=basic_info, prior_block=prior_block)
    try:
        response = await llm.chat(msgs, temperature=temperature, max_tokens=max_tokens)
        text = (response.content or "").strip()
        usage = getattr(response, "usage", None)
        return (
            text or RUMINATION_INIT_FALLBACK_ZH,
            normalize_token_usage(usage if isinstance(usage, dict) else None),
        )
    except Exception as e:
        logger.warning("rumination init LLM failed: %s", e)
        return RUMINATION_INIT_FALLBACK_ZH, normalize_token_usage(None)
