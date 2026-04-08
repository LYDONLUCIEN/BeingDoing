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


def _cols_step7_final() -> List[Dict[str, Any]]:
    """终步子表：多选 1–3 行（行内 __pick + rowSelectionMode，前端整行点选，不单独展示选择列）。"""
    return [
        {"key": "id", "label": "id"},
        {"key": "用户确认的假设", "label": "方向假设"},
    ]


GUIDE_TEXT: Dict[int, str] = {
    1: "请在本页填完所有行的「优势标记」后，点击确认进入下一步（整表一次提交）。",
    2: "请在本页检查并修改所有行的「匹配性」后，点击确认进入下一步（整表一次提交）。",
    3: "请在「假设」列选择：带「个人事业」或「职业路径」色块标签的两条推荐之一，或选「暂未选定」「其他」并自填。若暂不选定可点确认，我会给出引导；至少一行需为有效假设后才能进入价值观筛选。",
    4: "请为各行选择价值观标签、选「都不符合」「待定」或「其他」并填写后整表确认。",
    5: "请在本页为各行选择「忍不住想做」或「应该做」后整表确认。",
    6: "请在本页为各行选择「现在」或「未来」后整表确认。",
    7: "请点击 1–3 行整行选择最认同的方向（至少 1 行、最多 3 行），再点「确认」在右侧生成结论卡；在结论卡上最终确认后将进入下一阶段。",
}


EDITABLE_COLS: Dict[int, List[str]] = {
    1: ["优势标记"],
    2: ["匹配性"],
    3: ["用户确认的假设"],
    4: ["工作目的"],
    5: ["激情标记"],
    6: ["现实标记"],
    7: [],
}


def columns_for_step(step: int, values_keywords: List[str]) -> List[Dict[str, Any]]:
    if step == 1:
        return _cols_step1()
    if step == 2:
        return _cols_step2()
    if step == 3:
        return _cols_step345()
    if step == 4:
        return _cols_step6(values_keywords if values_keywords else ["（未解析到价值观，请填自定义）"])
    if step == 5:
        return _cols_step7()
    if step == 6:
        return _cols_step8()
    if step == 7:
        return _cols_step7_final()
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
    payload: Dict[str, Any] = {
        "columns": cols,
        "rows": rows,
        "editableCols": EDITABLE_COLS.get(step, []),
        "guideText": guide,
        "step": step,
        "singleRowMode": single_row_mode,
        "rowCursor": row_cursor,
        "totalRows": total_rows,
    }
    if step == 7:
        payload["rowSelectionMode"] = "multi"
        payload["rowSelectionMin"] = 1
        payload["rowSelectionMax"] = 3
    return payload


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
