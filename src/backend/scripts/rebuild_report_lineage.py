#!/usr/bin/env python3
"""
重建 simple 模式 report 主链路（安全版，默认 dry-run）。

目标链路：
activation_code + user_id -> report_id -> 5 steps -> session_ids

并可选：
- 重建 analytics_chat_turns（从 logs/runs.jsonl 回填）
- 重建 analytics_reports（从重建后的 report 注册表回填）
- 刷新 data/static/admin_dashboard_overview.json

用法：
  python scripts/rebuild_report_lineage.py --dry-run
  python scripts/rebuild_report_lineage.py --apply
  python scripts/rebuild_report_lineage.py --apply --rebuild-analytics --refresh-dashboard
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import delete

from app.models.database import AsyncSessionLocal
from app.models.analytics import AnalyticsChatTurn, AnalyticsReport
from app.services.analytics_service import AnalyticsService
from app.utils.report_registry import STEP_IDS, STEP_ALIASES, ReportRegistry
from app.utils.simple_activation_manager import get_simple_base_dir


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_step_from_stem(stem: str) -> Optional[str]:
    key = (stem or "").strip().lower()
    if not key:
        return None
    # thread 文件：values__t_xxx -> values
    key = key.split("__", 1)[0]
    # 常见历史别名
    if key in {"main_flow", "all_flow", "refinement"}:
        key = "rumination"
    return STEP_ALIASES.get(key)


def load_json(path: Path, default):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8") or "null")
    except (OSError, json.JSONDecodeError):
        return default


def infer_steps_for_session(session_dir: Path) -> Set[str]:
    steps: Set[str] = set()
    if not session_dir.is_dir():
        return steps
    for file in session_dir.glob("*.json"):
        step = normalize_step_from_stem(file.stem)
        if step:
            steps.add(step)
    return steps


@dataclass
class BuildStats:
    activations_total: int = 0
    reports_built: int = 0
    sessions_bound: int = 0
    orphan_sessions: int = 0
    reports_with_owner: int = 0
    reports_with_unknown_owner: int = 0


def build_reports_payload(include_orphans: bool = True) -> Tuple[Dict[str, dict], BuildStats]:
    base_dir = get_simple_base_dir()
    activations_file = base_dir / "activations.json"

    activations = load_json(activations_file, {}) or {}
    existing_registry = ReportRegistry()
    existing_reports = existing_registry.list_reports()

    # 复用已存在 report_id（避免重建后 ID 全变）
    existing_id_by_key: Dict[Tuple[str, str], str] = {}
    for report in existing_reports:
        key = ((report.get("activation_code") or "").strip().upper(), report.get("user_id") or "")
        if key[0] and key[1]:
            existing_id_by_key[key] = report.get("report_id") or ""

    built: Dict[str, dict] = {}
    stats = BuildStats(activations_total=len(activations))
    activation_session_ids: Set[str] = set()

    def get_or_create_report_id(activation_code: str, user_id: str) -> str:
        key = (activation_code, user_id)
        reused = existing_id_by_key.get(key)
        if reused:
            return reused
        return str(uuid.uuid4())

    def ensure_report(activation_code: str, user_id: str, created_at: Optional[str] = None) -> dict:
        report_id = get_or_create_report_id(activation_code, user_id)
        report = built.get(report_id)
        if report:
            return report
        ts = created_at or now_iso()
        report = {
            "report_id": report_id,
            "activation_code": activation_code,
            "user_id": user_id,
            "created_at": ts,
            "updated_at": ts,
            "steps": {
                sid: {"step_id": sid, "session_ids": [], "updated_at": ts}
                for sid in STEP_IDS
            },
            "status": "in_progress",
        }
        built[report_id] = report
        stats.reports_built += 1
        if user_id.startswith("unknown:"):
            stats.reports_with_unknown_owner += 1
        else:
            stats.reports_with_owner += 1
        return report

    def bind_session(report: dict, step_id: str, session_id: str):
        node = report["steps"].setdefault(step_id, {"step_id": step_id, "session_ids": [], "updated_at": now_iso()})
        if session_id not in node["session_ids"]:
            node["session_ids"].append(session_id)
            node["updated_at"] = now_iso()
            report["updated_at"] = now_iso()
            stats.sessions_bound += 1

    # 1) 以 activation 为主，重建 report 主链路
    for code, rec in (activations or {}).items():
        activation_code = (code or "").strip().upper()
        if not activation_code or not isinstance(rec, dict):
            continue
        session_id = (rec.get("session_id") or "").strip()
        owner_user_id = (rec.get("owner_user_id") or "").strip()
        owner_email = (rec.get("owner_email") or "").strip()
        user_id = owner_user_id or owner_email or f"unknown:{activation_code}"
        report = ensure_report(activation_code, user_id, created_at=rec.get("created_at"))

        if not session_id:
            continue
        activation_session_ids.add(session_id)
        session_steps = infer_steps_for_session(base_dir / session_id)
        if not session_steps:
            # 没有文件时，至少按 values 绑定主 session
            session_steps = {"values"}
        for step in session_steps:
            bind_session(report, step, session_id)

    # 2) 可选：把“孤儿 session 目录”也纳入 registry，避免链路断裂
    if include_orphans and base_dir.is_dir():
        for d in base_dir.iterdir():
            if not d.is_dir():
                continue
            sid = d.name
            if sid in activation_session_ids:
                continue
            step_set = infer_steps_for_session(d)
            if not step_set:
                continue
            orphan_code = f"ORPHAN__{sid}"
            orphan_user = f"unknown:orphan:{sid}"
            report = ensure_report(orphan_code, orphan_user)
            for step in step_set:
                bind_session(report, step, sid)
            stats.orphan_sessions += 1

    return built, stats


async def rebuild_analytics_from_reports(reports: List[dict]) -> Dict[str, int]:
    inserted_reports = 0
    async with AsyncSessionLocal() as db:
        # 清空两张核心分析表后重建（likes 不动）
        await db.execute(delete(AnalyticsChatTurn))
        await db.execute(delete(AnalyticsReport))

        seen_sessions: Set[Tuple[str, str]] = set()
        for report in reports:
            activation_code = (report.get("activation_code") or "").strip() or None
            steps = report.get("steps") or {}
            for step_id in STEP_IDS:
                session_ids = ((steps.get(step_id) or {}).get("session_ids")) or []
                for sid in session_ids:
                    key = (activation_code or "", sid)
                    if key in seen_sessions:
                        continue
                    seen_sessions.add(key)
                    db.add(AnalyticsReport(session_id=sid, activation_code=activation_code))
                    inserted_reports += 1

        await db.commit()

    sync_result = await AnalyticsService.sync_from_history()
    return {
        "analytics_reports_inserted": inserted_reports,
        "analytics_chat_turns_synced": int(sync_result.get("synced") or 0),
    }


def backup_files(target_dir: Path, files: List[Path]) -> List[str]:
    target_dir.mkdir(parents=True, exist_ok=True)
    copied: List[str] = []
    for f in files:
        if not f.exists():
            continue
        dst = target_dir / f.name
        if f.is_file():
            shutil.copy2(f, dst)
            copied.append(str(dst))
    return copied


async def main_async(args):
    base_dir = get_simple_base_dir()
    reports_file = base_dir / "reports.json"
    activations_file = base_dir / "activations.json"

    rebuilt, stats = build_reports_payload(include_orphans=not args.no_orphans)
    rebuilt_list = list(rebuilt.values())
    rebuilt_list.sort(key=lambda x: x.get("created_at") or "")
    payload = {r["report_id"]: r for r in rebuilt_list}

    summary = {
        "mode": "dry-run" if not args.apply else "apply",
        "reports_file": str(reports_file),
        "activations_file": str(activations_file),
        "stats": {
            "activations_total": stats.activations_total,
            "reports_built": stats.reports_built,
            "sessions_bound": stats.sessions_bound,
            "orphan_sessions": stats.orphan_sessions,
            "reports_with_owner": stats.reports_with_owner,
            "reports_with_unknown_owner": stats.reports_with_unknown_owner,
        },
    }

    if not args.apply:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print("\n[DRY-RUN] 未写入任何文件。使用 --apply 执行重建。")
        return

    if not args.no_backup:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup_dir = Path(args.backup_dir) if args.backup_dir else (base_dir.parent / "backups" / f"lineage-{ts}")
        copied = backup_files(backup_dir, [reports_file, activations_file])
        summary["backup_dir"] = str(backup_dir)
        summary["backup_files"] = copied

    reports_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["reports_written"] = len(payload)

    if args.rebuild_analytics:
        result = await rebuild_analytics_from_reports(rebuilt_list)
        summary["analytics_rebuild"] = result

    if args.refresh_dashboard:
        dashboard_payload = await AnalyticsService.sync_dashboard_overview_to_static()
        summary["dashboard_refreshed_at"] = dashboard_payload.get("generated_at")

    print(json.dumps(summary, ensure_ascii=False, indent=2))


def parse_args():
    parser = argparse.ArgumentParser(description="重建 report 主链路")
    parser.add_argument("--dry-run", action="store_true", help="仅预览（默认行为）")
    parser.add_argument("--apply", action="store_true", help="实际写入 reports.json")
    parser.add_argument("--rebuild-analytics", action="store_true", help="重建 analytics_report/chat_turn")
    parser.add_argument("--refresh-dashboard", action="store_true", help="刷新 dashboard static 缓存")
    parser.add_argument("--no-orphans", action="store_true", help="不纳入孤儿 session 目录")
    parser.add_argument("--no-backup", action="store_true", help="执行 apply 时不备份")
    parser.add_argument("--backup-dir", type=str, default="", help="自定义备份目录")
    return parser.parse_args()


def main():
    args = parse_args()
    # 默认 dry-run；只有 --apply 才写入
    if not args.apply:
        args.dry_run = True
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()

