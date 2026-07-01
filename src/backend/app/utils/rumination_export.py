"""
Rumination 导出数据组装工具

供两个消费方复用：
  1. 批量导出（batch_export_service）—— 产出 rumination_tables.json / summary.json / raw
  2. admin 会话详情接口 —— step_id=rumination 时追加 rumination_tables + 按 step 切片的对话

三个核心函数：
  - build_rumination_tables(report_id) -> dict
      组装 prerequisites(4 phase keywords) + steps[1-7](status/row_count/columns/rows) + combo
  - build_summary(report_id) -> dict
      汇总 report_final_conclusion + 5 phase 的 conclusion_final
  - slice_conversation_by_step(messages) -> dict[str, list] | {"_unified": list}
      按 filter_step 切分 rumination 对话；老数据无法切片则整段单列
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.utils.report_registry import ReportRegistry, STEP_IDS
from app.utils.rumination_progress import (
    FILTER_STEPS,
    load_rumination_progress,
)

logger = logging.getLogger(__name__)

# 前置 4 个 phase（rumination 之前的阶段），keywords 取自各自 conclusion_final
PREREQUISITE_PHASES = ("values", "strengths", "interests", "purpose")

# 5 个 phase 全集（summary.json 用）
ALL_PHASES = ("values", "strengths", "interests", "purpose", "rumination")

# 按 step 切片对话时，MD 详情渲染只保留这些角色的消息（与 batch_export 的 MD_ROLES_KEEP 对齐）
SLICE_ROLES_KEEP = {"user", "assistant", "conclusion_card"}


def _load_step_session_json(registry: ReportRegistry, report_id: str, step_id: str) -> Optional[dict]:
    """读取某 phase 的 selected_session 对应的源 JSON；无则 None。"""
    record = registry.get_report_by_id(report_id)
    if not record:
        return None
    step = (record.get("steps") or {}).get(step_id) or {}
    selected = step.get("selected_session_id")
    session_ids = step.get("session_ids") or []
    chosen = selected or (session_ids[-1] if session_ids else None)
    if not chosen:
        return None
    file = registry.get_step_session_file(report_id, step_id, chosen)
    if not file.is_file():
        return None
    try:
        return json.loads(file.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return None


def _extract_keywords(conclusion_final: Any) -> List[str]:
    """从 conclusion_final 里提取 keywords 列表；无则空。"""
    if not isinstance(conclusion_final, dict):
        return []
    kw = conclusion_final.get("keywords")
    if isinstance(kw, list):
        return [str(x) for x in kw if x]
    return []


def build_prerequisites(registry: ReportRegistry, report_id: str) -> Dict[str, List[str]]:
    """提取 rumination 之前 4 个 phase 的 keywords 作为前置结论。

    返回 {phase: [keyword, ...]}；某 phase 缺失则空列表。
    """
    prereq: Dict[str, List[str]] = {}
    for phase in PREREQUISITE_PHASES:
        raw = _load_step_session_json(registry, report_id, phase)
        cf = ((raw.get("metadata") or {}) if raw else {}).get("conclusion_final")
        prereq[phase] = _extract_keywords(cf)
    return prereq


def _classify_step_status(snap: Optional[dict], key_exists: bool = True) -> str:
    """根据 filter_step_snapshots[step] 判定 status。

    四态：
      submitted       —— 正常提交，有行
      submitted_empty —— 正常提交但 0 行
      skipped         —— skipped=true 或有 initial 但 submitted=None（触达未提交）
      not_reached     —— key 不存在，或快照完全为空（无 skipped/initial/submitted）
    """
    if not key_exists or not isinstance(snap, dict) or not snap:
        return "not_reached"
    if snap.get("skipped") is True:
        return "skipped"
    submitted = snap.get("submitted")
    if submitted is None:
        # 有 initial（AI 生成过）但用户没提交 → 跳过；快照若连 initial 都没有则视为未触及
        return "skipped" if snap.get("initial") is not None else "not_reached"
    return "submitted" if len(submitted) > 0 else "submitted_empty"


def _extract_columns(rows: List[dict]) -> List[str]:
    """从 submitted 行里提取列名（保持首次出现的顺序，去掉 id 列）。"""
    cols: List[str] = []
    seen = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        for k in row.keys():
            if k in ("id", "ID") or k in seen:
                continue
            seen.add(k)
            cols.append(k)
    return cols


def build_rumination_tables(report_id: str, registry: Optional[ReportRegistry] = None) -> Dict[str, Any]:
    """组装 rumination_tables.json 的完整结构。

    结构见设计文档：
      {
        report_id,
        prerequisites: {values/strengths/interests/purpose: [keywords]},
        steps: {1..7: {status, row_count, columns, rows}},
        combo_matrix: [...] | null,
        combo_conclusions: {...} | null
      }
    """
    if registry is None:
        registry = ReportRegistry()
    record = registry.get_report_by_id(report_id)

    # 前置结论
    prerequisites = build_prerequisites(registry, report_id)

    # rumination 进度
    reports_root = registry.reports_root
    progress = load_rumination_progress(reports_root, report_id)
    snapshots = progress.get("filter_step_snapshots") or {}

    steps: Dict[str, Dict[str, Any]] = {}
    for step in FILTER_STEPS:  # 1..7
        sk = str(step)
        key_exists = sk in snapshots
        snap = snapshots.get(sk)
        status = _classify_step_status(snap, key_exists=key_exists)
        submitted = (snap or {}).get("submitted") if isinstance(snap, dict) else None
        rows = submitted if isinstance(submitted, list) else []
        steps[sk] = {
            "status": status,
            "row_count": len(rows),
            "columns": _extract_columns(rows),
            "rows": rows,
        }

    combo_matrix = progress.get("combo_matrix")
    combo_conclusions = progress.get("combo_conclusions")

    return {
        "report_id": report_id,
        "prerequisites": prerequisites,
        "steps": steps,
        "combo_matrix": combo_matrix if isinstance(combo_matrix, list) and combo_matrix else None,
        "combo_conclusions": combo_conclusions if isinstance(combo_conclusions, dict) and combo_conclusions else None,
    }


def build_summary(report_id: str, registry: Optional[ReportRegistry] = None) -> Dict[str, Any]:
    """组装 summary.json：纯结论汇总。

    结构：
      {
        report_id,
        report_final_conclusion,
        phases: {phase: {conclusion_final}}  # rumination 额外带 combo_conclusions
      }
    """
    if registry is None:
        registry = ReportRegistry()
    record = registry.get_report_by_id(report_id) or {}
    report_final = record.get("final_conclusion")

    phases: Dict[str, Dict[str, Any]] = {}
    for phase in ALL_PHASES:
        raw = _load_step_session_json(registry, report_id, phase)
        cf = ((raw.get("metadata") or {}) if raw else {}).get("conclusion_final")
        entry: Dict[str, Any] = {"conclusion_final": cf}
        if phase == "rumination":
            progress = load_rumination_progress(registry.reports_root, report_id)
            cc = progress.get("combo_conclusions")
            entry["combo_conclusions"] = cc if isinstance(cc, dict) and cc else None
        phases[phase] = entry

    return {
        "report_id": report_id,
        "report_final_conclusion": report_final,
        "phases": phases,
    }


def load_raw_rumination_progress(report_id: str, registry: Optional[ReportRegistry] = None) -> Optional[dict]:
    """原样读取 rumination_progress.json（供 raw/ 产物）；不存在返回 None。"""
    if registry is None:
        registry = ReportRegistry()
    path = registry.reports_root / report_id / "rumination_progress.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return None


def slice_conversation_by_step(messages: List[dict]) -> Dict[str, List[dict]]:
    """把 rumination 会话消息按 filter_step 切片。

    归属规则（前向填充）：
      - 有 filter_step 的消息归该 step
      - 无 filter_step 的消息（如 step 开场引导语）归到「之后第一个有 filter_step 的消息」所属的 step

    老数据完全无 filter_step 时，所有消息整段归到 "_unified" key。

    返回 {step_str: [msg, ...]}，step_str 形如 "1".."7"，或 "_unified"。
    仅保留 user/assistant/conclusion_card 角色（与 md 渲染一致）。
    """
    if not isinstance(messages, list) or not messages:
        return {}

    # 先扫描是否有任何消息带 filter_step
    has_any_step = any(isinstance(m, dict) and m.get("filter_step") is not None for m in messages)
    if not has_any_step:
        # 老数据：整段单列
        unified = [m for m in messages if isinstance(m, dict) and (m.get("role") in SLICE_ROLES_KEEP)]
        return {"_unified": unified} if unified else {}

    # 前向填充：逐条确定归属 step
    # 第一遍：为每条消息打 step 标签；无 filter_step 的先用「下一个有 step 的」填充
    n = len(messages)
    labels: List[Optional[int]] = [None] * n
    # 正向扫描记录已知的下一个 step
    next_step: Optional[int] = None
    for i in range(n - 1, -1, -1):
        m = messages[i]
        if not isinstance(m, dict):
            continue
        fs = m.get("filter_step")
        if isinstance(fs, (int, float)):
            next_step = int(fs)
        if next_step is not None:
            labels[i] = next_step

    # 按标签分组
    grouped: Dict[str, List[dict]] = {}
    for i, m in enumerate(messages):
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role not in SLICE_ROLES_KEEP:
            continue
        # conclusion_card 也保留（md 里有用）；但 admin 切片里 assistant/user 为主
        label = labels[i]
        if label is None:
            # 开头几条没有后续 step 标注（极端情况），归到 _unified 兜底
            grouped.setdefault("_unified", []).append(m)
        else:
            grouped.setdefault(str(label), []).append(m)
    return grouped
