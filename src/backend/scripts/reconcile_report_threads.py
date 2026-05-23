#!/usr/bin/env python3
"""
Report 线程一致性体检：对比 record.json session_ids 与磁盘 {phase}__{thread_id}.json。

用法：
  python scripts/reconcile_report_threads.py --dry-run
  python scripts/reconcile_report_threads.py --dirs data/simple/reports
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

STEP_FILE_RE = re.compile(r"^(?P<phase>[a-z_]+)__(?P<thread_id>.+)\.json$")

SKIP_DIRS = {".deleted_threads", ".locks"}


def _scan_disk_threads(report_dir: Path) -> Dict[str, Set[str]]:
    """扫描 report 目录下各 phase 的 thread 文件（不含 .deleted_threads）。"""
    by_phase: Dict[str, Set[str]] = {}
    for p in report_dir.iterdir():
        if not p.is_file() or not p.name.endswith(".json"):
            continue
        m = STEP_FILE_RE.match(p.name)
        if not m:
            continue
        phase = m.group("phase")
        tid = m.group("thread_id")
        by_phase.setdefault(phase, set()).add(tid)
    return by_phase


def reconcile_report(report_dir: Path) -> List[str]:
    record_path = report_dir / "record.json"
    if not record_path.is_file():
        return [f"[skip] 无 record.json: {report_dir}"]

    record = json.loads(record_path.read_text(encoding="utf-8"))
    report_id = record.get("report_id") or report_dir.name
    steps = record.get("steps") or {}
    disk = _scan_disk_threads(report_dir)
    lines: List[str] = []

    for phase, step in steps.items():
        registered: Set[str] = {str(s).strip() for s in (step.get("session_ids") or []) if str(s).strip()}
        on_disk = disk.get(phase, set())
        missing_files = registered - on_disk
        orphan_files = on_disk - registered
        if missing_files:
            lines.append(
                f"[missing] report={report_id} phase={phase} "
                f"session_ids 有但磁盘无: {sorted(missing_files)}"
            )
        if orphan_files:
            lines.append(
                f"[orphan] report={report_id} phase={phase} "
                f"磁盘有但 session_ids 无: {sorted(orphan_files)}"
            )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Report 线程 session_ids 与磁盘文件对账")
    parser.add_argument(
        "--dirs",
        nargs="+",
        default=["data/simple/reports"],
        help="要扫描的 reports 根目录",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅输出报告（当前脚本只读）")
    args = parser.parse_args()

    all_lines: List[str] = []
    for root_str in args.dirs:
        root = Path(root_str)
        if not root.is_dir():
            print(f"[warn] 目录不存在: {root}")
            continue
        for report_dir in sorted(root.iterdir()):
            if not report_dir.is_dir() or report_dir.name in SKIP_DIRS:
                continue
            all_lines.extend(reconcile_report(report_dir))

    if not all_lines:
        print("未发现 session_ids 与磁盘不一致。")
        return 0

    for line in all_lines:
        print(line)
    print(f"\n共 {len(all_lines)} 条不一致。")
    return 1 if all_lines else 0


if __name__ == "__main__":
    raise SystemExit(main())
