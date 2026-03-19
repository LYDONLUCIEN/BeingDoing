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


def _rumination_progress_file(reports_root: Path, report_id: str) -> Path:
    return reports_root / report_id / "rumination_progress.json"


def load_rumination_progress(reports_root: Path, report_id: str) -> Dict[str, Any]:
    """加载 rumination 进度，不存在则返回默认值。"""
    path = _rumination_progress_file(reports_root, report_id)
    if not path.is_file():
        return {
            "main_section": "opening",
            "review_sub_index": 0,
            "filter_step": 0,
            "filter_table": None,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
        if not isinstance(data, dict):
            return {"main_section": "opening", "review_sub_index": 0, "filter_step": 0, "filter_table": None}
        return {
            "main_section": data.get("main_section") or "opening",
            "review_sub_index": int(data.get("review_sub_index", 0)),
            "filter_step": int(data.get("filter_step", 0)),
            "filter_table": data.get("filter_table"),
        }
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return {"main_section": "opening", "review_sub_index": 0, "filter_step": 0, "filter_table": None}


def save_rumination_progress(
    reports_root: Path,
    report_id: str,
    main_section: Optional[str] = None,
    review_sub_index: Optional[int] = None,
    filter_step: Optional[int] = None,
    filter_table: Optional[Any] = None,
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

    path = _rumination_progress_file(reports_root, report_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current
