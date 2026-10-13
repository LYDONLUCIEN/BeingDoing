"""Rumination v4 只读导出工具(沉淀仅 v4,见 ADR-0025;2026-10-13)。

背景:导出的可读产物(md / stats / tables / summary)此前只覆盖旧七步表格协议
与 {step}__{session}.json 会话文件;v4 的对话只以 raw/rumination_v4_progress.json
原样附带,导致「人读的导出里缺失第五轮」。本模块提供 v4 状态的只读构建函数:

  - load_v4_progress(report_id, registry) -> Optional[dict]
      原样读取 rumination_v4_progress.json;不存在/损坏返回 None
  - has_v4_content(state) -> bool
      是否有实质内容(任一 combo 或已提交终选),用于 md 章节取舍
  - build_v4_block(state) -> dict
      结构化 combos 区块(rumination_tables.json 的 "v4" 键)
  - compute_v4_message_stats(state) -> Optional[dict]
      聚合全部 combo 对话的消息统计(stats.json 用;无对话返回 None)

只读:不从旧矩阵/旧七步合成 combo 或终选,数据完全取自原生 v4 快照。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from app.utils.helpers import parse_iso_to_utc
from app.utils.report_registry import ReportRegistry

logger = logging.getLogger(__name__)

# 活跃时长会话超时阈值(与 batch_export_service.SESSION_GAP_MAX_SECONDS 同口径)
SESSION_GAP_MAX_SECONDS = 1800


def load_v4_progress(report_id: str, registry: Optional[ReportRegistry] = None) -> Optional[dict]:
    """原样读取 rumination_v4_progress.json;不存在/损坏返回 None。"""
    if registry is None:
        registry = ReportRegistry()
    path = registry.reports_root / report_id / "rumination_v4_progress.json"
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8") or "{}")
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def has_v4_content(state: dict) -> bool:
    """v4 状态是否有实质内容(任一 combo 或已提交终选)。"""
    if not isinstance(state, dict):
        return False
    if state.get("combo_sessions"):
        return True
    return bool((state.get("final_selection") or {}).get("submitted"))


def _selected_ids(state: dict) -> List[str]:
    ids = (state.get("final_selection") or {}).get("selected_combo_ids") or []
    return [str(x) for x in ids if x]


def build_v4_block(state: dict) -> Dict[str, Any]:
    """结构化 v4 区块(rumination_tables.json 的 "v4" 键)。

    原样呈现 combo 与终选,不补全缺失字段语义。
    """
    combos = state.get("combo_sessions") or []
    selected = set(_selected_ids(state))
    return {
        "schema_version": state.get("schema_version"),
        "combo_count": len(combos),
        "final_selection": state.get("final_selection"),
        "combos": [
            {
                "combo_id": c.get("combo_id"),
                "passion": c.get("passion"),
                "strengths": c.get("strengths") or [],
                "status": c.get("status"),
                "user_skipped": bool(c.get("user_skipped")),
                "is_final_selected": c.get("combo_id") in selected,
                "message_count": len(c.get("messages") or []),
                "created_at": c.get("created_at"),
                "updated_at": c.get("updated_at"),
                "conclusion_card": c.get("conclusion_card"),
                "balance_analysis": c.get("balance_analysis"),
            }
            for c in combos
            if isinstance(c, dict)
        ],
    }


def _duration_seconds(timestamps: List[str]) -> int:
    """活跃会话时长(秒):相邻消息间隔累加,超过 30min 的段不计入(跨天离开)。"""
    if len(timestamps) < 2:
        return 0
    try:
        pts = [parse_iso_to_utc(ts) for ts in timestamps if isinstance(ts, str) and ts]
        if len(pts) < 2:
            return 0
        pts.sort()
        total = 0
        for i in range(1, len(pts)):
            gap = (pts[i] - pts[i - 1]).total_seconds()
            if 0 < gap <= SESSION_GAP_MAX_SECONDS:
                total += gap
        return int(total)
    except (ValueError, TypeError):
        return 0


def compute_v4_message_stats(state: dict) -> Optional[Dict[str, Any]]:
    """聚合全部 combo 对话的消息统计;无任何对话返回 None。

    v4 消息字段为 {role, content, ts}(无 token_usage / created_at)。
    """
    combos = [c for c in (state.get("combo_sessions") or []) if isinstance(c, dict)]
    ai_chars = 0
    user_chars = 0
    msg_counts: Dict[str, int] = {}
    timestamps: List[str] = []
    total_msgs = 0
    per_combo: List[Dict[str, Any]] = []

    for c in combos:
        msgs = c.get("messages") or []
        n = 0
        for m in msgs:
            if not isinstance(m, dict):
                continue
            n += 1
            role = m.get("role") or "unknown"
            msg_counts[role] = msg_counts.get(role, 0) + 1
            text = m.get("content")
            text = text if isinstance(text, str) else ("" if text is None else str(text))
            if role == "assistant":
                ai_chars += len(text)
            elif role == "user":
                user_chars += len(text)
            ts = m.get("ts")
            if isinstance(ts, str) and ts:
                timestamps.append(ts)
        total_msgs += n
        if n:
            per_combo.append(
                {
                    "combo_id": c.get("combo_id"),
                    "passion": c.get("passion"),
                    "status": c.get("status"),
                    "message_count": n,
                }
            )

    if total_msgs == 0:
        return None

    timestamps.sort()
    duration = _duration_seconds(timestamps)
    return {
        "combo_count": len(combos),
        "message_count": total_msgs,
        "message_count_by_role": msg_counts,
        "ai_chars": ai_chars,
        "user_chars": user_chars,
        "total_dialogue_chars": ai_chars + user_chars,
        "duration_seconds": duration,
        "first_message_at": timestamps[0] if timestamps else None,
        "last_message_at": timestamps[-1] if timestamps else None,
        "per_combo": per_combo,
    }
