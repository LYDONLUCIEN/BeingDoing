"""
Rumination 阶段进度存储

存储于 data/simple/reports/{report_id}/rumination_progress.json
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

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
    # 每步表格：initial=该步首次生成；submitted=用户确认后（用于回退查看，不删行）
    "filter_step_snapshots": {},
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
    raw_snap = out.get("filter_step_snapshots")
    out["filter_step_snapshots"] = raw_snap if isinstance(raw_snap, dict) else {}
    return out


def max_reached_filter_step(snapshots: Any) -> int:
    """有已提交表格的最高 filter_step（1–9），无则 0。"""
    if not isinstance(snapshots, dict):
        return 0
    m = 0
    for k, v in snapshots.items():
        try:
            sk = int(str(k))
        except (TypeError, ValueError):
            continue
        if isinstance(v, dict) and v.get("submitted") is not None:
            m = max(m, sk)
    return m


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
    filter_step_snapshots: Optional[Dict[str, Any]] = None,
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
    if filter_step_snapshots is not None:
        current["filter_step_snapshots"] = filter_step_snapshots

    path = _rumination_progress_file(reports_root, report_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(
            json.dumps(current, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except (TypeError, ValueError, OSError) as e:
        logger.exception("rumination_progress 写入失败: %s", e)
        raise
    return current
