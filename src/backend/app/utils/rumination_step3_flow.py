"""子步 3 表格操作副作用：选「无」逐行跳过、填假设后主动确认提示。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.utils.rumination_ops import is_rumination_step3_positive_hypothesis

HYP_FIELD = "用户确认的假设"


def _row_hyp(row: Dict[str, Any]) -> str:
    return str(row.get(HYP_FIELD) or "").strip()


def _row_fields_line(row: Dict[str, Any]) -> str:
    passion = str(row.get("热爱") or "").strip()
    strength = str(row.get("优势") or "").strip()
    return f"热爱：{passion or '（未填）'} / 优势：{strength or '（未填）'}"


def build_step3_skip_message(
    next_row_1based: Optional[int],
    next_row: Optional[Dict[str, Any]],
) -> str:
    """选「无」后插入右侧的固定短句（非 LLM）。"""
    if next_row_1based and next_row:
        fields = _row_fields_line(next_row)
        return (
            f"好的，这条我们先跳过。请看左侧第 {next_row_1based} 行（{fields}），"
            f"我们继续聊这一行的假设。"
        )
    return "好的，这条我们先跳过。左侧全部行已处理完毕，确认无误后可点表格「确认」进入下一步。"


def build_step3_confirm_prompt(row_1based: int, row: Dict[str, Any]) -> str:
    """填假设后主动追问（固定模板，用户须在对话中文字确认）。"""
    fields = _row_fields_line(row)
    hyp = _row_hyp(row)
    preview = hyp if len(hyp) <= 48 else hyp[:45] + "..."
    return (
        f"我看到你在左侧第 {row_1based} 行（{fields}）填入了假设：「{preview}」。"
        f"请在这里用一句话确认这是否符合你的想法；确认后我会带你进入下一行。"
    )


def apply_step3_table_trigger(
    *,
    existing_prog: Dict[str, Any],
    merged_table: List[Dict[str, Any]],
    trigger: Optional[str],
) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
    """
    处理 step3 表格显式触发（none / hypothesis_commit）。

    Returns:
        (side_effect, new_cursor) — new_cursor 仅 skip 时递增。
    """
    if not trigger or not merged_table:
        return None, None

    cur = int(existing_prog.get("filter_row_cursor") or 0)
    if cur < 0 or cur >= len(merged_table):
        return None, None

    row = merged_table[cur]
    if not isinstance(row, dict):
        return None, None

    hyp = _row_hyp(row)

    if trigger == "none":
        if hyp != "无":
            return None, None
        new_cursor = cur + 1
        next_row = merged_table[new_cursor] if new_cursor < len(merged_table) else None
        message = build_step3_skip_message(
            new_cursor + 1 if next_row else None,
            next_row if isinstance(next_row, dict) else None,
        )
        return (
            {
                "type": "skip_row",
                "message": message,
                "from_row": cur,
                "to_row": new_cursor,
            },
            new_cursor,
        )

    if trigger == "hypothesis_commit":
        if not is_rumination_step3_positive_hypothesis(hyp):
            return None, None
        message = build_step3_confirm_prompt(cur + 1, row)
        return (
            {
                "type": "confirm_prompt",
                "message": message,
                "row": cur,
            },
            None,
        )

    return None, None
