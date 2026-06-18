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
MAX_FILTER_STEP = 7
FILTER_STEPS = tuple(range(1, MAX_FILTER_STEP + 1))  # 1-7

DEFAULT_PROGRESS: Dict[str, Any] = {
    "schema_version": 3,
    "main_section": "opening",
    "review_sub_index": 0,
    "filter_step": 0,
    "filter_row_cursor": 0,
    "hypothesis_round": 1,
    "filter_table": None,
    # True：跳过 6→8 直达第 9 步（假设轮≤3 行短链，或 6/7/8 筛选 0 行仍带本步填写进终筛）
    "filter_early_terminated": False,
    "filter_terminate_reason": None,
    # 每步表格：initial=该步首次生成；submitted=用户确认后（用于回退查看，不删行）
    "filter_step_snapshots": {},
    # 方案 Q：待提交的表格快照（未写入各步 submitted）
    "pending_table_submit": None,
    # 否定/标记跟进：awaiting_choice | exploring | closed
    "rumination_neg_state": None,
    # 每子步「深入聊聊」闸门首次触发标记：集合，触发的子步号写入；重新填写时仅清除当前步
    "neg_gate_triggered_steps": [],
    # --- v3: 组合矩阵模式 ---
    # filter_step=3 时的子阶段：None=旧版兼容 | "matrix"=组合假设填写 | "discussion"=深度讨论(3b)
    "filter_sub_step": None,
    # {combo_id: {"text": str, "state": "empty"|"confirmed"|"skipped"}}
    "combo_conclusions": {},
    # [{combo_id, passion_idx, strength_idx, passion_name, strength_name}]
    "combo_matrix": None,
    # 用户勾选"不再提示"后为 True
    "combo_completion_modal_dismissed": False,
}


def _rumination_progress_file(reports_root: Path, report_id: str) -> Path:
    return reports_root / report_id / "rumination_progress.json"


def _migrate_progress_v1_to_v2(data: Dict[str, Any]) -> None:
    """将旧版 9 子步快照映射为 7 子步（去掉原 4–5 假设轮）。"""
    if int(data.get("schema_version", 1)) >= 2:
        return
    snaps = data.get("filter_step_snapshots")
    if not isinstance(snaps, dict):
        data["schema_version"] = 2
        return
    new_snaps: Dict[str, Any] = {}
    for k, v in snaps.items():
        try:
            sk = int(str(k))
        except (TypeError, ValueError):
            continue
        if not isinstance(v, dict):
            continue
        if sk in (1, 2, 3):
            new_snaps[str(sk)] = v
        elif sk in (4, 5):
            continue
        elif sk == 6:
            new_snaps["4"] = v
        elif sk == 7:
            new_snaps["5"] = v
        elif sk == 8:
            new_snaps["6"] = v
        elif sk == 9:
            new_snaps["7"] = v
    data["filter_step_snapshots"] = new_snaps
    fs = int(data.get("filter_step") or 0)
    if fs in (4, 5):
        data["filter_step"] = 3
    elif fs == 6:
        data["filter_step"] = 4
    elif fs == 7:
        data["filter_step"] = 5
    elif fs == 8:
        data["filter_step"] = 6
    elif fs >= 9:
        data["filter_step"] = 7
    data["schema_version"] = 2


def _migrate_progress_v2_to_v3(data: Dict[str, Any]) -> None:
    """v2→v3：为 filter_step=3 的旧数据构建 combo_matrix 和 combo_conclusions。

    规则：
    - 已提交的 step3 快照（submitted）→ filter_sub_step="discussion"
    - 未提交但有 filter_table → filter_sub_step="matrix"
    - filter_step != 3 的数据不做任何变更。
    """
    if int(data.get("schema_version", 2)) >= 3:
        return
    fs = int(data.get("filter_step", 0))
    if fs != 3:
        return

    # v3 新字段默认值
    data.setdefault("filter_sub_step", None)
    data.setdefault("combo_conclusions", {})
    data.setdefault("combo_matrix", None)
    data.setdefault("combo_completion_modal_dismissed", False)

    # 已提交 step3 → 直接进入 discussion 模式
    snapshots = data.get("filter_step_snapshots") or {}
    snap3 = snapshots.get("3") or {}
    if isinstance(snap3, dict) and snap3.get("submitted"):
        data["filter_sub_step"] = "discussion"
        submitted_rows = snap3.get("submitted") or []
        if isinstance(submitted_rows, list):
            conclusions: Dict[str, Dict[str, str]] = {}
            for r in submitted_rows:
                if not isinstance(r, dict):
                    continue
                p = str(r.get("热爱") or "")
                s = str(r.get("优势") or "")
                h = str(r.get("用户确认的假设") or "").strip()
                if not p or not s:
                    continue
                cid = _build_combo_id_from_table(submitted_rows, p, s)
                if not cid:
                    continue
                if h and h not in ("无", "待定", "暂未选定"):
                    conclusions[cid] = {"text": h, "state": "confirmed"}
                else:
                    conclusions[cid] = {"text": h, "state": "skipped"}
            data["combo_conclusions"] = conclusions
        data["schema_version"] = 3
        return

    # 有 filter_table 但未提交 → matrix 模式
    ft = data.get("filter_table")
    if isinstance(ft, list) and ft:
        data["filter_sub_step"] = "matrix"
        matrix = _build_combo_matrix_from_table(ft)
        data["combo_matrix"] = matrix
        conclusions: Dict[str, Dict[str, str]] = {}
        for r in ft:
            if not isinstance(r, dict):
                continue
            p = str(r.get("热爱") or "")
            s = str(r.get("优势") or "")
            h = str(r.get("用户确认的假设") or "").strip()
            if not p or not s:
                continue
            cid = _build_combo_id_from_table(ft, p, s)
            if not cid:
                continue
            if h and h not in ("无", "待定", "暂未选定"):
                conclusions[cid] = {"text": h, "state": "confirmed"}
            else:
                conclusions[cid] = {"text": "", "state": "empty"}
        data["combo_conclusions"] = conclusions
        data["schema_version"] = 3
        return

    data["schema_version"] = 3


def _build_combo_id_from_table(table: list, passion: str, strength: str) -> str:
    """从表格行中查找热爱/优势的索引位置，构建 combo_id。"""
    passions_seen: list[str] = []
    for r in table:
        if not isinstance(r, dict):
            continue
        p = str(r.get("热爱") or "").strip()
        if p and p not in passions_seen:
            passions_seen.append(p)
    strengths_seen: list[str] = []
    for r in table:
        if not isinstance(r, dict):
            continue
        s = str(r.get("优势") or "").strip()
        if s and s not in strengths_seen:
            strengths_seen.append(s)
    p_idx = passions_seen.index(passion) if passion in passions_seen else -1
    s_idx = strengths_seen.index(strength) if strength in strengths_seen else -1
    if p_idx < 0 or s_idx < 0:
        return ""
    return f"{p_idx}{s_idx}"


def _build_combo_matrix_from_table(table: list) -> list:
    """从已有表格行构建 combo_matrix 列表。"""
    passions_seen: list[str] = []
    for r in table:
        if not isinstance(r, dict):
            continue
        p = str(r.get("热爱") or "").strip()
        if p and p not in passions_seen:
            passions_seen.append(p)
    strengths_seen: list[str] = []
    for r in table:
        if not isinstance(r, dict):
            continue
        s = str(r.get("优势") or "").strip()
        if s and s not in strengths_seen:
            strengths_seen.append(s)
    matrix = []
    for pi, p in enumerate(passions_seen[:3]):
        for si, s in enumerate(strengths_seen[:5]):
            matrix.append({
                "combo_id": f"{pi}{si}",
                "passion_idx": pi,
                "strength_idx": si,
                "passion_name": p,
                "strength_name": s,
            })
    return matrix


def _normalize_loaded(data: Dict[str, Any]) -> Dict[str, Any]:
    out = {**DEFAULT_PROGRESS, **data}
    out["main_section"] = out.get("main_section") or "opening"
    out["review_sub_index"] = int(out.get("review_sub_index", 0))
    out["filter_row_cursor"] = int(out.get("filter_row_cursor", 0))
    out["hypothesis_round"] = max(1, min(3, int(out.get("hypothesis_round", 1))))
    _migrate_progress_v1_to_v2(out)
    _migrate_progress_v2_to_v3(out)
    out["schema_version"] = max(int(out.get("schema_version", 3)), 3)
    out["filter_step"] = max(0, min(MAX_FILTER_STEP, int(out.get("filter_step", 0))))
    if "filter_early_terminated" not in data:
        out["filter_early_terminated"] = False
    if "filter_terminate_reason" not in data:
        out["filter_terminate_reason"] = None
    raw_snap = out.get("filter_step_snapshots")
    out["filter_step_snapshots"] = raw_snap if isinstance(raw_snap, dict) else {}
    if "pending_table_submit" not in data:
        out["pending_table_submit"] = None
    if "rumination_neg_state" not in data:
        out["rumination_neg_state"] = None
    # neg_gate_triggered_steps: 确保为列表，兼容旧数据
    raw_triggered = out.get("neg_gate_triggered_steps")
    if not isinstance(raw_triggered, list):
        out["neg_gate_triggered_steps"] = []
    else:
        out["neg_gate_triggered_steps"] = [int(x) for x in raw_triggered if isinstance(x, (int, float, str))]
    # v3 字段已由 DEFAULT_PROGRESS + _migrate_progress_v2_to_v3 处理，无需额外 setdefault
    return out


def max_reached_filter_step(snapshots: Any) -> int:
    """有已提交表格的最高 filter_step（1–7），无则 0。"""
    if not isinstance(snapshots, dict):
        return 0
    m = 0
    for k, v in snapshots.items():
        try:
            sk = int(str(k))
        except (TypeError, ValueError):
            continue
        if sk > MAX_FILTER_STEP:
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
        current["filter_step"] = max(0, min(MAX_FILTER_STEP, filter_step))
        # 进入 step3 时，如果 sub_step 是 discussion（旧残留），重置为 matrix
        if filter_step == 3 and current.get("filter_sub_step") == "discussion":
            current["filter_sub_step"] = "matrix"
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


def merge_rumination_progress_fields(
    reports_root: Path, report_id: str, updates: Dict[str, Any]
) -> Dict[str, Any]:
    """合并写入任意进度字段（如 pending_table_submit / rumination_neg_state）。"""
    current = load_rumination_progress(reports_root, report_id)
    for k, v in updates.items():
        current[k] = v
    path = _rumination_progress_file(reports_root, report_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(current, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return current


def is_neg_gate_triggered(progress: Dict[str, Any], step: int) -> bool:
    """检查指定子步的「深入聊聊」闸门是否已经触发过。"""
    triggered: list = progress.get("neg_gate_triggered_steps") or []
    return step in triggered


def mark_neg_gate_triggered(
    reports_root: Path, report_id: str, step: int
) -> Dict[str, Any]:
    """标记某子步闸门已触发（幂等：已存在则不重复写入）。"""
    current = load_rumination_progress(reports_root, report_id)
    triggered: list = current.get("neg_gate_triggered_steps") or []
    if step not in triggered:
        triggered.append(step)
        current["neg_gate_triggered_steps"] = triggered
        path = _rumination_progress_file(reports_root, report_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(current, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    return current


def clear_neg_gate_triggered_step(
    reports_root: Path, report_id: str, step: int
) -> Dict[str, Any]:
    """清除某子步的闸门触发标记（重新填写时调用）。"""
    current = load_rumination_progress(reports_root, report_id)
    triggered: list = current.get("neg_gate_triggered_steps") or []
    if step in triggered:
        triggered = [s for s in triggered if s != step]
        current["neg_gate_triggered_steps"] = triggered
        path = _rumination_progress_file(reports_root, report_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(current, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    return current


def clear_neg_gate_triggered_from_step(reports_root: Path, report_id: str, from_step: int) -> Dict[str, Any]:
    """清除指定步骤及所有后续步骤的闸门触发标记（回到某步重新填写时调用）。"""
    current = load_rumination_progress(reports_root, report_id)
    triggered: list = current.get("neg_gate_triggered_steps") or []
    steps_to_clear = {s for s in triggered if isinstance(s, int) and s >= from_step}
    if steps_to_clear:
        triggered = [s for s in triggered if s not in steps_to_clear]
        current["neg_gate_triggered_steps"] = triggered
        path = _rumination_progress_file(reports_root, report_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(current, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    return current
