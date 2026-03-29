"""
Rumination 阶段进度存储

存储于 data/simple/reports/{report_id}/rumination_progress.json
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

MAIN_SECTIONS = ("opening", "review", "filter", "final_choice", "recommend", "end")
FILTER_STEPS = tuple(range(1, 10))  # 1-9

DEFAULT_PROGRESS: Dict[str, Any] = {
    "schema_version": 1,
    "main_section": "opening",
    "review_sub_index": 0,
    "filter_step": 0,
    "filter_row_cursor": 0,
    "hypothesis_round": 1,
    "filter_table": None,
    "filter_early_terminated": False,
    "filter_terminate_reason": None,
}


def _rumination_progress_file(reports_root: Path, report_id: str) -> Path:
    return reports_root / report_id / "rumination_progress.json"


def _normalize_loaded(data: Dict[str, Any]) -> Dict[str, Any]:
    out = {**DEFAULT_PROGRESS, **data}
    out["main_section"] = out.get("main_section") or "opening"
    out["review_sub_index"] = int(out.get("review_sub_index", 0))
    out["filter_step"] = int(out.get("filter_step", 0))
    out["filter_row_cursor"] = int(out.get("filter_row_cursor", 0))
    out["hypothesis_round"] = max(1, min(3, int(out.get("hypothesis_round", 1))))
    out["schema_version"] = int(out.get("schema_version", 1))
    if "filter_early_terminated" not in data:
        out["filter_early_terminated"] = False
    if "filter_terminate_reason" not in data:
        out["filter_terminate_reason"] = None
    return out


def load_rumination_progress(reports_root: Path, report_id: str) -> Dict[str, Any]:
    """加载 rumination 进度，不存在则返回默认值。"""
    path = _rumination_progress_file(reports_root, report_id)
    if not path.is_file():
        return dict(DEFAULT_PROGRESS)
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
        if not isinstance(data, dict):
            return dict(DEFAULT_PROGRESS)
        return _normalize_loaded(data)
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return dict(DEFAULT_PROGRESS)


def save_rumination_progress(
    reports_root: Path,
    report_id: str,
    main_section: Optional[str] = None,
    review_sub_index: Optional[int] = None,
    filter_step: Optional[int] = None,
    filter_table: Optional[Any] = None,
    filter_row_cursor: Optional[int] = None,
    hypothesis_round: Optional[int] = None,
    filter_early_terminated: Optional[bool] = None,
    filter_terminate_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """保存 rumination 进度，未传字段保持原值。"""
    current = load_rumination_progress(reports_root, report_id)
    if main_section is not None:
        current["main_section"] = main_section
    if review_sub_index is not None:
        current["review_sub_index"] = max(0, min(3, review_sub_index))
    if filter_step is not None:
        current["filter_step"] = max(0, min(9, filter_step))
    if filter_table is not None:
        current["filter_table"] = filter_table
    if filter_row_cursor is not None:
        current["filter_row_cursor"] = max(0, filter_row_cursor)
    if hypothesis_round is not None:
        current["hypothesis_round"] = max(1, min(3, hypothesis_round))
    if filter_early_terminated is not None:
        current["filter_early_terminated"] = bool(filter_early_terminated)
    if filter_terminate_reason is not None:
        current["filter_terminate_reason"] = filter_terminate_reason

    path = _rumination_progress_file(reports_root, report_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current
