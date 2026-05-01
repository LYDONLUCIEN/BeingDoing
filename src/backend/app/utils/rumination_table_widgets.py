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
    ]


def _cols_step345() -> List[Dict[str, Any]]:
    """假设1–2 仅作行内数据供下拉选项使用，不单独占列（一列「假设」选择两条推荐之一或自填）。"""
    return [
        {"key": "id", "label": "id"},
        {"key": "热爱", "label": "热爱"},
        {"key": "优势", "label": "优势"},
        {"key": "匹配性", "label": "匹配性"},
        {"key": "用户确认的假设", "label": "假设"},
    ]


def _cols_step6(values_keywords: List[str], values_source: str = "") -> List[Dict[str, Any]]:
    """Step 4 列定义：包含「工作目的」下拉。

    降级策略：
      - source 为 confirmed_card / report_anchor / prior_text 时使用正常关键词选项。
      - source 为 none 或 values_keywords 为空时，仅提供「自定义」让用户自填，
        并在 guideText 中提示降级原因（由调用方在 guide 层处理）。
    """
    base: List[Dict[str, Any]] = [
        {"key": "id", "label": "id"},
        {"key": "用户确认的假设", "label": "用户确认的假设"},
    ]
    if values_keywords:
        base.append(
            {
                "key": "工作目的",
                "label": "工作目的",
                "options": list(values_keywords) + ["都不符合", "自定义"],
            }
        )
    else:
        # 降级：无任何关键词来源时，仅允许自填
        base.append(
            {
                "key": "工作目的",
                "label": "工作目的",
                "options": ["自定义"],
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
    1: "请审阅下表中的「优势标记」，确认后点击「确认」进入下一步。",
    2: "判断标准参考——匹配：热爱与优势能够互相增强，结合起来让你感到充实且方向清晰；不匹配：两者难以协同，或结合后反而消耗精力。请逐行审阅并修改「匹配性」，确认后点击「确认」进入下一步。",
    3: "请在「假设」列选择：「个人事业」或「职业路径」两条推荐之一，或选「无」「自定义」并自填。可点单元格旁图标重新生成推荐。至少一行需为有效假设后才能进入价值观筛选。",
    4: "请为各行选择价值观标签（若多个价值观同样重要，可先选一个最具代表性的，或选「自定义」将多个一并填写）、选「都不符合」或「自定义」并填写后整表确认。",
    5: "请在本页为各行选择「忍不住想做」或「应该做」后整表确认。",
    6: "请在本页为各行选择「现在」或「未来」后整表确认。",
    7: "请在以下表格中整行选择最认同的方向（至少 1 行、最多 3 行），再点「确认」在右侧生成结论卡；在结论卡上最终确认后将进入下一阶段。",
}


EDITABLE_COLS: Dict[int, List[str]] = {
    1: [],
    2: ["匹配性"],
    3: ["用户确认的假设"],
    4: ["工作目的"],
    5: ["激情标记"],
    6: ["现实标记"],
    7: [],
}


def columns_for_step(step: int, values_keywords: List[str], values_source: str = "") -> List[Dict[str, Any]]:
    if step == 1:
        return _cols_step1()
    if step == 2:
        return _cols_step2()
    if step == 3:
        return _cols_step345()
    if step == 4:
        return _cols_step6(values_keywords if values_keywords else [], values_source=values_source)
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
    values_source: str = "",
) -> Optional[Dict[str, Any]]:
    """构建 table_widget 的 card_payload；无行时返回 None。

    Args:
        values_source: 价值观关键词来源标签（confirmed_card / report_anchor / prior_text / none），
                       供前端展示来源信息与降级提示。
    """
    if not rows:
        return None
    display_rows: List[dict] = list(rows)
    if step == 3:
        from app.utils.rumination_hypothesis_service import ensure_row_has_pair_hypotheses

        patched: List[dict] = []
        for i, r in enumerate(rows):
            row = dict(r)
            passion = str(row.get("热爱") or "")
            strength = str(row.get("优势") or "")
            ensure_row_has_pair_hypotheses(
                row, passion=passion, strength=strength, row_index=i
            )
            patched.append(row)
        display_rows = patched
    cols = columns_for_step(step, values_keywords, values_source=values_source)
    guide = GUIDE_TEXT.get(step, "")
    # step 4 降级提示：无价值观关键词来源时，引导用户自填
    if step == 4 and values_source == "none":
        degradation_hint = (
            "当前暂未解析到您的价值观关键词，请在「工作目的」列选择「自定义」手动填写。"
        )
        guide = f"{degradation_hint}\n{guide}" if guide else degradation_hint
    if single_row_mode and total_rows > 0:
        guide = f"第 {min(row_cursor + 1, total_rows)}/{total_rows} 行。{guide}"
    payload: Dict[str, Any] = {
        "columns": cols,
        "rows": display_rows,
        "editableCols": EDITABLE_COLS.get(step, []),
        "guideText": guide,
        "step": step,
        "singleRowMode": single_row_mode,
        "rowCursor": row_cursor,
        "totalRows": total_rows,
    }
    # step 4 附带价值观来源标签，供前端展示与降级处理
    if step == 4:
        payload["valuesSource"] = values_source
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
