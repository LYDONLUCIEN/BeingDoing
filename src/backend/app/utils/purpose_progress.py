"""
Purpose 阶段经历-价值观匹配进度。

存储位置：对话 thread JSON 文件的 metadata.purpose_progress 字段。
通过 ConversationFileManager.update_metadata 读写。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TARGET_TOTAL = 5

DEFAULT_PROGRESS: Dict[str, Any] = {
    "current_index": 0,
    "confirmed_rows": [],
    "completed": False,
}


def normalize_progress(raw: Any) -> Dict[str, Any]:
    """将 metadata 中读取的 purpose_progress 规范化。"""
    if not isinstance(raw, dict):
        return dict(DEFAULT_PROGRESS)
    out: Dict[str, Any] = {
        "current_index": min(max(0, int(raw.get("current_index", 0))), TARGET_TOTAL),
        "confirmed_rows": _normalize_rows(raw.get("confirmed_rows")),
        "completed": bool(raw.get("completed", False)),
    }
    return out


def _normalize_rows(raw: Any) -> List[Dict[str, Any]]:
    """规范化 confirmed_rows，兼容旧 value 单值格式。"""
    if not isinstance(raw, list):
        return []
    clean: List[Dict[str, Any]] = []
    for item in raw[:TARGET_TOTAL]:
        if not isinstance(item, dict):
            continue
        ex = str(item.get("experience") or "").strip()[:280]
        vals = _coerce_values(item.get("values") or item.get("value"))
        if ex or vals:
            clean.append({"experience": ex, "values": vals})
    return clean


def _coerce_values(raw: Any) -> List[str]:
    """将价值观字段统一转为 list[str]。"""
    if isinstance(raw, list):
        return [str(v).strip() for v in raw if str(v).strip()]
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    return []


def build_progress_injection(progress: Dict[str, Any]) -> str:
    """构建 [内部·使命进度] prompt 注入块。"""
    if progress.get("completed"):
        return "[内部·使命进度] 已完成全部经历匹配（{0}/{0}）。".format(TARGET_TOTAL)

    idx = progress.get("current_index", 0)
    if idx >= TARGET_TOTAL:
        return "[内部·使命进度] 已完成全部经历匹配（{0}/{0}）。".format(TARGET_TOTAL)

    confirmed = progress.get("confirmed_rows") or []
    done = len(confirmed)
    lines = [
        "[内部·使命进度]",
        json.dumps(
            {"current_index": idx, "confirmed_rows": confirmed, "target_total": TARGET_TOTAL},
            ensure_ascii=False,
        ),
        f"当前进度：第 {idx + 1}/{TARGET_TOTAL} 条经历（已完成 {done} 条）。",
        "规则：仅处理 current_index 指向的经历；不得对 confirmed_rows 中的经历重新提问或重新匹配。",
        "用户确认后：将 current_index +1 并将该行追加到 confirmed_rows；若用户要求修改已确认经历，更新对应行 values 并调整 current_index。",
        "每次回复末尾的 STATE_JSON 中须包含 purpose_progress 字段（与当前进度一致），即使未推进也须回传。",
    ]
    return "\n".join(lines)


def apply_progress_update(
    progress: Dict[str, Any],
    new_progress: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """从 STATE_JSON 的 purpose_progress 字段合并更新到当前进度。

    不限制 current_index 方向（允许前进和回退）。
    """
    if not isinstance(new_progress, dict):
        return progress

    out = dict(progress)
    new_idx = new_progress.get("current_index")
    if isinstance(new_idx, (int, float)):
        out["current_index"] = min(max(0, int(new_idx)), TARGET_TOTAL)

    new_rows = new_progress.get("confirmed_rows")
    if isinstance(new_rows, list):
        out["confirmed_rows"] = _normalize_rows(new_rows)

    new_completed = new_progress.get("completed")
    if isinstance(new_completed, bool):
        out["completed"] = new_completed

    return out


def progress_to_experience_value_rows(progress: Dict[str, Any]) -> List[Dict[str, Any]]:
    """将 confirmed_rows 转为结论卡用的 experience_value_rows 格式。"""
    confirmed = progress.get("confirmed_rows") or []
    return [
        {"experience": r.get("experience", ""), "values": list(r.get("values", []))}
        for r in confirmed
        if r.get("experience") or r.get("values")
    ]
