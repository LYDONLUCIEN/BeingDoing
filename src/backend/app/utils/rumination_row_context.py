"""
子步 3 逐行对话：从 dimension_conclusions 解析「热爱/优势」标签对应的 keyword_notes。
"""
from __future__ import annotations

from typing import Any, Dict

from app.utils.survey_storage import load_dimension_conclusions


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
