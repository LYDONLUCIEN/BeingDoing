"""
子步 3 逐行对话：从 dimension_conclusions 解析「热爱/优势」标签对应的 keyword_notes。

沉淀点选表格行发问：build_rumination_row_chat_user_message 包装 user 消息正文。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.domain.rumination_prompt_strings import (
    RUMINATION_ROW_CHAT_STEP3_CURSOR_NOTE_ZH,
    RUMINATION_ROW_CHAT_USER_TEMPLATE_ZH,
    RUMINATION_STEP_TOPIC_ZH,
)
from app.utils.survey_storage import load_dimension_conclusions

_ROW_PROMPT_META_KEYS = frozenset(
    {"__pick", "_rumination_selected", "假设1", "假设2", "假设3", "假设填写方式"}
)


def clean_row_for_row_chat_prompt(row: Dict[str, Any]) -> Dict[str, Any]:
    """去掉表格内部/meta 字段，供行点击包装 prompt 使用。"""
    return {k: v for k, v in row.items() if k not in _ROW_PROMPT_META_KEYS}


def build_rumination_row_chat_user_message(
    *,
    filter_step: int,
    row_index: int,
    user_query: str,
    filter_table: List[Any],
) -> Optional[str]:
    """点选表格行发问时，将用户原文包装为结构化 user 消息（存盘与送 LLM 一致）。"""
    query = (user_query or "").strip()
    if not query:
        return None
    step = max(1, min(7, int(filter_step)))
    idx = int(row_index)
    if not isinstance(filter_table, list) or idx < 0 or idx >= len(filter_table):
        return None
    raw = filter_table[idx]
    if not isinstance(raw, dict):
        return None
    topic = RUMINATION_STEP_TOPIC_ZH.get(step, "")
    row_clean = clean_row_for_row_chat_prompt(raw)
    try:
        row_json = json.dumps(row_clean, ensure_ascii=False)
    except (TypeError, ValueError):
        row_json = str(row_clean)
    text = RUMINATION_ROW_CHAT_USER_TEMPLATE_ZH.format(
        current_step_topic=topic,
        row_id=idx + 1,
        row_json=row_json,
        user_query=query,
    )
    if step == 3:
        text = f"{text}\n\n{RUMINATION_ROW_CHAT_STEP3_CURSOR_NOTE_ZH}"
    return text


def _note_for_label(block: Dict[str, Any], label: str) -> str:
    kws = block.get("keywords") or []
    notes = block.get("keyword_notes") or []
    if not isinstance(kws, list) or not (label or "").strip():
        return ""
    lt = label.strip()
    for i, kw in enumerate(kws):
        if str(kw).strip() == lt:
            if isinstance(notes, list) and i < len(notes):
                return str(notes[i] or "").strip()
            return ""
    return ""


def format_step3_row_context_block(
    report_id: str,
    reports_root: str,
    row: Dict[str, Any],
    *,
    combo_index_1based: int,
    total_combos: int,
    prev_combo_summary: str = "",
) -> str:
    """拼入 system / addon 的当前行上下文（咨询师可见，勿逐字复述给用户）。"""
    store = load_dimension_conclusions(report_id, reports_root)
    passion = str(row.get("热爱") or "").strip()
    strength = str(row.get("优势") or "").strip()
    int_b = store.get("interests") if isinstance(store.get("interests"), dict) else {}
    str_b = store.get("strengths") if isinstance(store.get("strengths"), dict) else {}
    pe = _note_for_label(int_b, passion) or "（结论卡中暂无该关键词的单独说明。）"
    se = _note_for_label(str_b, strength) or "（结论卡中暂无该关键词的单独说明。）"
    prev = (prev_combo_summary or "").strip() or "（无，当前为首个组合。）"
    return (
        "[内部·子步3当前行]\n"
        f"第 {combo_index_1based} 行（共 {total_combos} 行）\n"
        f"上一行摘要：{prev}\n"
        f"热爱：{passion or '（未填）'} / 优势：{strength or '（未填）'}\n"
        f"热爱（解释/用户理解）：{pe}\n"
        f"优势（解释/用户理解）：{se}\n"
    )


def format_step3_next_row_preview(row: Dict[str, Any], next_index_1based: int, total: int) -> str:
    """下一行简要预览，供 AI 在确认当前行后直接过渡提问。"""
    p = str(row.get("热爱") or "").strip() or "（未填）"
    s = str(row.get("优势") or "").strip() or "（未填）"
    return (
        "[内部·子步3下一行预览]\n"
        f"第 {next_index_1based} 行（共 {total} 行）\n"
        f"热爱：{p} / 优势：{s}\n"
        "（仅用于过渡提问参考，不要在用户确认前提前提及此行内容。）"
    )


def summarize_prev_combo_row(prev_row: Dict[str, Any]) -> str:
    """上一行用于提示的短摘要。"""
    p = str(prev_row.get("热爱") or "").strip()
    s = str(prev_row.get("优势") or "").strip()
    h = str(prev_row.get("用户确认的假设") or "").strip()
    if not p and not s:
        return ""
    tail = f"；假设：{h}" if h else ""
    return f"热爱「{p}」× 优势「{s}」{tail}".strip()


def format_step3_confirmed_rows_block(
    rows: list,
    cursor: int,
) -> str:
    """生成已确认行的摘要块，拼入 system 提示让 AI 了解历史进度。

    Args:
        rows: filter_table 全部行。
        cursor: 当前 filter_row_cursor（下一个待处理的行索引）。
                索引 0..cursor-1 的行视为已确认。
    """
    confirmed: list[str] = []
    for i in range(min(cursor, len(rows))):
        row = rows[i] if isinstance(rows[i], dict) else {}
        p = str(row.get("热爱") or "").strip()
        s = str(row.get("优势") or "").strip()
        h = str(row.get("用户确认的假设") or "").strip()
        if not h:
            h = "（未填）"
        elif len(h) > 30:
            h = h[:27] + "..."
        label = f"第{i + 1}行（{p}×{s}）：{h}"
        confirmed.append(label)
    if not confirmed:
        return "[内部·子步3已确认行]\n（无，当前为首个组合。）"
    return "[内部·子步3已确认行]\n" + "\n".join(confirmed)
