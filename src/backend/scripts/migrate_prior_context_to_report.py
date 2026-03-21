#!/usr/bin/env python3
"""
将 prior_context 从 data/simple/{session_id}/ 迁移到 reports/{report_id}/。

需先有 report（由 migrate_simple_to_report_dirs 或正常使用产生）。
默认 dry-run，--apply 才执行。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 确保 app 可导入（可从项目根或 src/backend 执行）
_script_dir = Path(__file__).resolve().parent
_backend = _script_dir.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))
import json
import shutil
from pathlib import Path
from typing import Dict

from app.utils.simple_activation_manager import get_simple_base_dir
from app.utils.report_registry import ReportRegistry

_PRIOR_FILENAME = "prior_context_{phase}.txt"
PHASES = ["values", "strengths", "interests", "purpose", "rumination"]


def load_json(path: Path, default):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8") or "null")
    except (OSError, json.JSONDecodeError):
        return default


def migrate(dry_run: bool) -> dict:
    base = get_simple_base_dir()
    reports_root = base / "reports"
    activations = load_json(base / "activations.json", {}) or {}
    registry = ReportRegistry(base_dir=str(base))

    user_to_code_sess: Dict[str, list] = {}
    for code, rec in activations.items():
        if not isinstance(rec, dict):
            continue
        owner = (rec.get("owner_user_id") or rec.get("owner_email") or "").strip()
        if not owner:
            continue
        sess = (rec.get("session_id") or "").strip()
        if not sess:
            continue
        user_to_code_sess.setdefault(owner, []).append((code, sess))

    copied = 0
    for user_id, pairs in user_to_code_sess.items():
        for activation_code, session_id in pairs:
            report = registry.get_by_activation_user(activation_code, user_id)
            if not report or not report.get("report_id"):
                continue
            report_id = report["report_id"]
            sess_dir = base / session_id
            if not sess_dir.is_dir():
                continue
            report_dir = reports_root / report_id
            for phase in PHASES:
                src = sess_dir / _PRIOR_FILENAME.format(phase=phase)
                if not src.is_file():
                    continue
                dst = report_dir / _PRIOR_FILENAME.format(phase=phase)
                if not dry_run:
                    report_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                copied += 1
    return {"dry_run": dry_run, "prior_files_copied": copied}


def main():
    parser = argparse.ArgumentParser(description="迁移 prior_context 到 report 目录")
    parser.add_argument("--apply", action="store_true", help="执行迁移")
    args = parser.parse_args()
    result = migrate(dry_run=not args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
