"""子步 3 表格操作处理。

表格操作（选「无」、填假设）现在作为 user 消息通过 /message/stream 发给 AI，
AI 自行判断回复并输出 ROW_STATE_JSON 推进 cursor。
本模块保留辅助函数供其他模块引用，不再生成 side effect。
"""
from __future__ import annotations

from typing import Any, Dict

HYP_FIELD = "用户确认的假设"


def row_hyp(row: Dict[str, Any]) -> str:
    return str(row.get(HYP_FIELD) or "").strip()


def row_fields_line(row: Dict[str, Any]) -> str:
    passion = str(row.get("热爱") or "").strip()
    strength = str(row.get("优势") or "").strip()
    return f"热爱：{passion or '（未填）'} / 优势：{strength or '（未填）'}"
