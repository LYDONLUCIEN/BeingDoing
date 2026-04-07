"""
Rumination 筛选表格：列定义与 table_widget 载荷构建。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _cols_step1() -> List[Dict[str, Any]]:
    return [
        {"key": "id", "label": "id"},
        {"key": "热爱", "label": "热爱"},
        {"key": "优势", "label": "优势"},
        {
            "key": "优势标记",
            "label": "优势标记",
            "options": ["有充实感，与成功有关", "有充实感", "不确定"],
        },
    ]


def _cols_step2() -> List[Dict[str, Any]]:
    return [
        {"key": "id", "label": "id"},
        {"key": "热爱", "label": "热爱"},
        {"key": "优势", "label": "优势"},
        {"key": "匹配性", "label": "匹配性", "options": ["匹配", "不匹配"]},
        {"key": "匹配原因", "label": "匹配原因"},
    ]


def _cols_step345() -> List[Dict[str, Any]]:
    """假设1–3 仅作行内数据供下拉选项使用，不单独占列（对齐产品文档：一列「假设」选择）。"""
    return [
        {"key": "id", "label": "id"},
        {"key": "热爱", "label": "热爱"},
        {"key": "优势", "label": "优势"},
        {"key": "匹配性", "label": "匹配性"},
        {"key": "用户确认的假设", "label": "假设"},
    ]


def _cols_step6(values_keywords: List[str]) -> List[Dict[str, Any]]:
    base: List[Dict[str, Any]] = [
        {"key": "id", "label": "id"},
        {"key": "用户确认的假设", "label": "用户确认的假设"},
    ]
    if values_keywords:
        base.append(
            {
                "key": "工作目的",
                "label": "工作目的",
                "options": list(values_keywords) + ["都不符合", "其他"],
            }
        )
    else:
        base.append(
            {
                "key": "工作目的",
                "label": "工作目的",
                "options": ["待定", "其他"],
            }
        )
    return base


def _cols_step7() -> List[Dict[str, Any]]:
    return [
        {"key": "id", "label": "id"},
        {"key": "用户确认的假设", "label": "用户确认的假设"},
        {"key": "工作目的", "label": "工作目的"},
        {
            "key": "激情标记",
            "label": "激情标记",
            "options": ["忍不住想做", "应该做"],
        },
    ]


def _cols_step8() -> List[Dict[str, Any]]:
    return [
        {"key": "id", "label": "id"},
        {"key": "用户确认的假设", "label": "用户确认的假设"},
        {"key": "激情标记", "label": "激情标记"},
        {"key": "现实标记", "label": "现实标记", "options": ["现在", "未来"]},
    ]


def _cols_step9() -> List[Dict[str, Any]]:
    return [
        {"key": "id", "label": "id"},
        {"key": "用户确认的假设", "label": "用户确认的假设"},
    ]


GUIDE_TEXT: Dict[int, str] = {
    1: "请在本页填完所有行的「优势标记」后，点击确认进入下一步（整表一次提交）。",
    2: "请在本页检查并修改所有行的「匹配性」后，点击确认进入下一步（整表一次提交）。",
    3: "请在「假设」列选择：带「个人事业」或「职业路径」色块标签的两条推荐之一，或选「待定」「其他」并自填。整表确认后进入下一轮。",
    4: "未确认的行请在「假设」列从两条推荐（标签区分个人事业 / 职业路径）中选一条，或选「待定」「其他」。整表一次确认。",
    5: "最后一轮：在「假设」列确认个人事业向、职业路径向推荐或「待定」「其他」；无法抉择可选「待定」。",
    6: "请为各行选择价值观标签、选「都不符合」「待定」或「其他」并填写后整表确认。",
    7: "请在本页为各行选择「忍不住想做」或「应该做」后整表确认。",
    8: "请在本页为各行选择「现在」或「未来」后整表确认。",
    9: "可在本页合并相似项、修改文字；整表确认后完成筛选，进入最终选择。",
}


EDITABLE_COLS: Dict[int, List[str]] = {
    1: ["优势标记"],
    2: ["匹配性"],
    3: ["用户确认的假设"],
    4: ["用户确认的假设"],
    5: ["用户确认的假设"],
    6: ["工作目的"],
    7: ["激情标记"],
    8: ["现实标记"],
    9: ["用户确认的假设"],
}


def columns_for_step(step: int, values_keywords: List[str]) -> List[Dict[str, Any]]:
    if step == 1:
        return _cols_step1()
    if step == 2:
        return _cols_step2()
    if step in (3, 4, 5):
        return _cols_step345()
    if step == 6:
        return _cols_step6(values_keywords if values_keywords else ["（未解析到价值观，请填自定义）"])
    if step == 7:
        return _cols_step7()
    if step == 8:
        return _cols_step8()
    if step == 9:
        return _cols_step9()
    return _cols_step1()


def build_table_widget_payload(
    step: int,
    rows: List[dict],
    values_keywords: List[str],
    *,
    single_row_mode: bool = False,
    row_cursor: int = 0,
    total_rows: int = 0,
) -> Optional[Dict[str, Any]]:
    """构建 table_widget 的 card_payload；无行时返回 None。"""
    if not rows:
        return None
    cols = columns_for_step(step, values_keywords)
    guide = GUIDE_TEXT.get(step, "")
    if single_row_mode and total_rows > 0:
        guide = f"第 {min(row_cursor + 1, total_rows)}/{total_rows} 行。{guide}"
    return {
        "columns": cols,
        "rows": rows,
        "editableCols": EDITABLE_COLS.get(step, []),
        "guideText": guide,
        "step": step,
        "singleRowMode": single_row_mode,
        "rowCursor": row_cursor,
        "totalRows": total_rows,
    }


def slice_rows_for_display(
    table: List[Dict[str, Any]],
    cursor: int,
    *,
    single_row_mode: bool,
) -> tuple[List[Dict[str, Any]], int, int]:
    """返回 (展示用 rows, cursor, total)。单行模式只返回一行。"""
    n = len(table)
    if n == 0:
        return [], 0, 0
    c = max(0, min(cursor, n - 1))
    if single_row_mode:
        return [dict(table[c])], c, n
    return [dict(r) for r in table], c, n
