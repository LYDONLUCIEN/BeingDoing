#!/usr/bin/env python3
"""
将旧版 simple 存储迁移到 report 目录结构。

目标结构：
data/simple/reports/{report_id}/
  - record.json
  - {step_id}__{session_id}.json

说明：
- 默认 dry-run，不会写文件
- --apply 才执行写入
- 执行前会自动备份 data/simple 到 data/backups/simple-migrate-<ts>
"""
from __future__ import annotations

import argparse
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from app.utils.report_registry import ReportRegistry, STEP_IDS
from app.utils.simple_activation_manager import get_simple_base_dir


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path, default):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8") or "null")
    except (OSError, json.JSONDecodeError):
        return default


def normalize_step_from_file(stem: str) -> Optional[str]:
    key = (stem or "").strip().lower()
    if not key:
        return None
    base = key.split("__", 1)[0]
    if base in {"main_flow", "all_flow", "refinement", "filter", "combine", "combination"}:
        return "rumination"
    if base in {"values", "strengths", "interests", "purpose", "rumination"}:
        return base
    return None


def normalize_session_from_file(stem: str, default_session_id: str) -> str:
    # values__t_123_xxx => t_123_xxx
    parts = (stem or "").split("__", 1)
    if len(parts) == 2 and parts[1].strip():
        return parts[1].strip()
    return default_session_id


def ensure_message_schema(data: dict) -> dict:
    msgs = data.get("messages") or []
    normalized = []
    for i, m in enumerate(msgs):
        role = (m or {}).get("role") or "assistant"
        item = dict(m or {})
        if not item.get("message_id"):
            if item.get("id"):
                item["message_id"] = str(item.get("id"))
            else:
                item["message_id"] = f"msg_{i+1}"
        # 保留旧 id，新增 message_id 作为标准字段
        item.setdefault("id", item["message_id"])
        item.setdefault("created_at", now_iso())
        item.setdefault("agent_id", "coach" if role == "assistant" else None)
        item.setdefault("event", "assistant_reply" if role == "assistant" else "user_message")
        normalized.append(item)
    data["messages"] = normalized
    meta = data.setdefault("metadata", {})
    meta.setdefault("updated_at", now_iso())
    meta.setdefault("migrated_at", now_iso())
    return data


def build_report_id(activation_code: str, user_id: str) -> str:
    # 稳定 ID，便于重复迁移时结果可复现
    ns = uuid.UUID("11111111-2222-3333-4444-555555555555")
    raw = f"{activation_code.upper()}::{user_id}"
    return str(uuid.uuid5(ns, raw))


def migrate(dry_run: bool) -> dict:
    base = get_simple_base_dir()
    reports_root = base / "reports"
    activations = load_json(base / "activations.json", {}) or {}
    old_reports = load_json(base / "reports.json", {}) or {}
    registry = ReportRegistry()

    stats = {
        "activations_total": len(activations),
        "reports_created": 0,
        "conversation_files_written": 0,
        "sessions_bound": 0,
        "skipped_no_session_dir": 0,
        "unknown_owner_reports": 0,
        "orphan_session_dirs": 0,
    }

    # activation -> owner/report
    mapping: Dict[str, dict] = {}
    for code, rec in (activations or {}).items():
        if not isinstance(rec, dict):
            continue
        activation_code = (code or "").strip().upper()
        if not activation_code:
            continue
        owner_uid = (rec.get("owner_user_id") or "").strip()
        owner_email = (rec.get("owner_email") or "").strip()
        user_id = owner_uid or owner_email or f"unknown:{activation_code}"
        if user_id.startswith("unknown:"):
            stats["unknown_owner_reports"] += 1
        report_id = build_report_id(activation_code, user_id)
        mapping[activation_code] = {
            "report_id": report_id,
            "user_id": user_id,
            "session_id": (rec.get("session_id") or "").strip(),
            "created_at": rec.get("created_at") or now_iso(),
        }

    # old reports.json 可补充 step-session 绑定
    old_bindings: Dict[str, Dict[str, List[str]]] = {}
    for report in (old_reports or {}).values():
        if not isinstance(report, dict):
            continue
        code = (report.get("activation_code") or "").strip().upper()
        uid = (report.get("user_id") or "").strip()
        if not code or not uid:
            continue
        report_id = build_report_id(code, uid)
        steps = report.get("steps") or {}
        old_bindings.setdefault(report_id, {})
        for step in STEP_IDS:
            sess = ((steps.get(step) or {}).get("session_ids")) or []
            if sess:
                old_bindings[report_id].setdefault(step, [])
                for s in sess:
                    if s not in old_bindings[report_id][step]:
                        old_bindings[report_id][step].append(s)

    for activation_code, info in mapping.items():
        report_id = info["report_id"]
        user_id = info["user_id"]
        session_id = info["session_id"]
        report_dir = reports_root / report_id

        if not dry_run:
            report = registry.get_by_activation_user(activation_code, user_id)
            if not report:
                report = registry.ensure_report(activation_code=activation_code, user_id=user_id, session_id=session_id or None)
                stats["reports_created"] += 1
            else:
                # 确保存在 values 主会话
                if session_id:
                    registry.bind_session(report["report_id"], "values", session_id)
            report = registry.get_by_activation_user(activation_code, user_id) or report
        else:
            stats["reports_created"] += 1
            report = {
                "report_id": report_id,
                "activation_code": activation_code,
                "user_id": user_id,
                "steps": {k: {"session_ids": []} for k in STEP_IDS},
            }

        # 迁移会话文件：旧 data/simple/{session_id}/*.json
        legacy_dir = base / session_id if session_id else None
        if not session_id or not legacy_dir or not legacy_dir.is_dir():
            stats["skipped_no_session_dir"] += 1
            continue

        for f in legacy_dir.glob("*.json"):
            stem = f.stem
            step_id = normalize_step_from_file(stem)
            if not step_id:
                # 非 step 文件（如 basic_info）写到 report 根目录
                if not dry_run:
                    report_dir.mkdir(parents=True, exist_ok=True)
                    target = report_dir / f.name
                    if not target.exists():
                        target.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
                continue

            sess = normalize_session_from_file(stem, session_id)
            if not dry_run:
                registry.bind_session(report_id, step_id, sess)
                conv_raw = load_json(f, {"messages": [], "metadata": {}})
                conv_data = ensure_message_schema(conv_raw if isinstance(conv_raw, dict) else {"messages": [], "metadata": {}})
                out_file = registry.get_step_session_file(report_id, step_id, sess)
                out_file.parent.mkdir(parents=True, exist_ok=True)
                out_file.write_text(json.dumps(conv_data, ensure_ascii=False, indent=2), encoding="utf-8")
            stats["conversation_files_written"] += 1
            stats["sessions_bound"] += 1

        # 叠加旧 reports.json 的绑定信息
        for step, sess_list in (old_bindings.get(report_id) or {}).items():
            for s in sess_list:
                if dry_run:
                    stats["sessions_bound"] += 1
                    continue
                registry.bind_session(report_id, step, s)
                stats["sessions_bound"] += 1

    # orphan session 目录：没有被 activations 映射到的历史目录
    mapped_session_ids = {((v or {}).get("session_id") or "").strip() for v in mapping.values()}
    for d in base.iterdir():
        if not d.is_dir():
            continue
        if d.name in {"reports"}:
            continue
        sid = d.name
        if sid in mapped_session_ids:
            continue
        stats["orphan_session_dirs"] += 1
        activation_code = f"ORPHAN__{sid}"
        user_id = f"unknown:orphan:{sid}"
        report_id = build_report_id(activation_code, user_id)
        if dry_run:
            stats["reports_created"] += 1
            report = {"report_id": report_id}
        else:
            report = registry.get_by_activation_user(activation_code, user_id)
            if not report:
                report = registry.ensure_report(activation_code=activation_code, user_id=user_id, session_id=sid)
                stats["reports_created"] += 1

        for f in d.glob("*.json"):
            step_id = normalize_step_from_file(f.stem)
            if not step_id:
                if not dry_run:
                    out_dir = base / "reports" / report["report_id"]
                    out_dir.mkdir(parents=True, exist_ok=True)
                    target = out_dir / f.name
                    if not target.exists():
                        target.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
                continue
            logical_session = normalize_session_from_file(f.stem, sid)
            if not dry_run:
                registry.bind_session(report["report_id"], step_id, logical_session)
                conv_raw = load_json(f, {"messages": [], "metadata": {}})
                conv_data = ensure_message_schema(conv_raw if isinstance(conv_raw, dict) else {"messages": [], "metadata": {}})
                out_file = registry.get_step_session_file(report["report_id"], step_id, logical_session)
                out_file.parent.mkdir(parents=True, exist_ok=True)
                out_file.write_text(json.dumps(conv_data, ensure_ascii=False, indent=2), encoding="utf-8")
            stats["conversation_files_written"] += 1
            stats["sessions_bound"] += 1

    return stats


def backup_simple_dir(simple_dir: Path) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_root = simple_dir.parent / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    dst = backup_root / f"simple-migrate-{ts}"
    shutil.copytree(simple_dir, dst)
    return dst


def main():
    parser = argparse.ArgumentParser(description="migrate simple data to report dirs")
    parser.add_argument("--dry-run", action="store_true", help="仅预览（默认）")
    parser.add_argument("--apply", action="store_true", help="执行迁移并写入")
    parser.add_argument("--skip-backup", action="store_true", help="执行 apply 时跳过备份")
    args = parser.parse_args()

    dry_run = not args.apply or args.dry_run
    base = get_simple_base_dir()
    result = {"mode": "dry-run" if dry_run else "apply"}

    if not dry_run and not args.skip_backup:
        backup_dir = backup_simple_dir(base)
        result["backup_dir"] = str(backup_dir)

    stats = migrate(dry_run=dry_run)
    result["stats"] = stats
    result["simple_dir"] = str(base)
    result["reports_dir"] = str(base / "reports")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

