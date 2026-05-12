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
    """子步 3：热爱/优势/匹配性 + 「假设」列（显式选「无」或自填，逐行解锁由 rowCursor 控制）。"""
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
    3: (
        "请在右侧与咨询师逐行完成假设探索；当前可编辑行见表下说明。"
        "在「假设」列请先在「无 / 填写假设」中选择：选「无」表示本行跳过；选「填写假设」请填入具体内容。"
        "每行在对话中确认后才会解锁下一行。全部行处理完毕后，点击「确认」进入价值观筛选。"
    ),
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


STEP3_WIDGET_REDACT_KEYS = (
    "热爱",
    "优势",
    "匹配性",
    "用户确认的假设",
    "假设1",
    "假设2",
    "假设3",
    "假设填写方式",
)


def redact_step3_rows_for_widget(rows: List[dict], cursor: int) -> List[dict]:
    """子步 3：索引 > cursor 的行不返回业务字段（仅保留 id）；已解锁行去掉假设1/2/3 出参。

    cursor 可为 len(rows)，表示本步逐行对话已全部完成，此时不再脱敏任何行。
    """
    n = len(rows)
    c = max(0, min(int(cursor), n))
    out: List[dict] = []
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            continue
        if i > c:
            rid = r.get("id", "")
            clean: Dict[str, Any] = {"id": rid}
            for k in STEP3_WIDGET_REDACT_KEYS:
                clean[k] = ""
            out.append(clean)
        else:
            row = {k: v for k, v in r.items() if k not in ("假设1", "假设2", "假设3")}
            row["假设1"] = ""
            row["假设2"] = ""
            row["假设3"] = ""
            out.append(row)
    return out


def build_table_widget_payload(
    step: int,
    rows: List[dict],
    values_keywords: List[str],
    *,
    single_row_mode: bool = False,
    row_cursor: int = 0,
    total_rows: int = 0,
    values_source: str = "",
    hypothesis_row_cursor: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """构建 table_widget 的 card_payload；无行时返回 None。

    Args:
        values_source: 价值观关键词来源标签（confirmed_card / report_anchor / prior_text / none），
                       供前端展示来源信息与降级提示。
    """
    if not rows:
        return None
    display_rows: List[dict] = list(rows)
    total = len(rows)
    eff_cursor = row_cursor
    if step == 3:
        if hypothesis_row_cursor is not None:
            eff_cursor = int(hypothesis_row_cursor)
        eff_cursor = max(0, min(eff_cursor, total))
        display_rows = redact_step3_rows_for_widget(display_rows, eff_cursor)
    cols = columns_for_step(step, values_keywords, values_source=values_source)
    guide = GUIDE_TEXT.get(step, "")
    # step 4 降级提示：无价值观关键词来源时，引导用户自填
    if step == 4 and values_source == "none":
        degradation_hint = (
            "当前暂未解析到您的价值观关键词，请在「工作目的」列选择「自定义」手动填写。"
        )
        guide = f"{degradation_hint}\n{guide}" if guide else degradation_hint
    eff_total = total_rows if total_rows > 0 else total
    if step == 3:
        eff_total = total
        row_cursor = eff_cursor
    if single_row_mode and eff_total > 0:
        guide = f"第 {min(row_cursor + 1, eff_total)}/{eff_total} 行。{guide}"
    if step == 3 and eff_total > 0:
        if row_cursor >= eff_total:
            line_prog = f"已完成全部 {eff_total} 行的对话，请检查表格后点击「确认」进入下一步。"
        else:
            line_prog = (
                f"当前进行第 {row_cursor + 1}/{eff_total} 行（右侧对话同步进行）。"
            )
        guide = f"{line_prog}\n{guide}"
    payload: Dict[str, Any] = {
        "columns": cols,
        "rows": display_rows,
        "editableCols": EDITABLE_COLS.get(step, []),
        "guideText": guide,
        "step": step,
        "singleRowMode": single_row_mode,
        "rowCursor": row_cursor,
        "totalRows": eff_total if eff_total else total,
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
