#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_pytest_command(pytest_args: List[str], junit_xml: Path | None) -> List[str]:
    cmd = [sys.executable, "-m", "pytest"]
    cmd.extend(pytest_args)
    if junit_xml is not None:
        cmd.extend(["--junitxml", str(junit_xml)])
    return cmd


def main() -> None:
    parser = argparse.ArgumentParser(description="Run L1 deterministic regression via pytest.")
    parser.add_argument(
        "--pytest-target",
        default="test/backend",
        help="pytest 目标（目录/文件/用例表达式）",
    )
    parser.add_argument(
        "--pytest-args",
        default="",
        help='附加 pytest 参数，例如: "-k rumination -q"',
    )
    parser.add_argument("--report-dir", default="test_agent/reports", help="报告输出目录")
    parser.add_argument("--dry-run", action="store_true", help="仅打印命令，不执行")
    args = parser.parse_args()

    root = _project_root()
    report_dir = Path(args.report_dir)
    if not report_dir.is_absolute():
        report_dir = (root / report_dir).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    junit_xml = report_dir / f"l1_pytest_{ts}.xml"
    pytest_args: List[str] = [args.pytest_target]
    if args.pytest_args.strip():
        pytest_args.extend(args.pytest_args.strip().split())
    cmd = _build_pytest_command(pytest_args=pytest_args, junit_xml=junit_xml)
    pretty = " ".join(f'"{c}"' if " " in c else c for c in cmd)
    print(f"[L1] command={pretty}")

    if args.dry_run:
        return

    proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True)
    report = {
        "level": "L1",
        "runner": "pytest",
        "target": args.pytest_target,
        "pytest_args": args.pytest_args or None,
        "exit_code": proc.returncode,
        "passed": proc.returncode == 0,
        "junit_xml": str(junit_xml),
    }
    report_path = report_dir / f"l1_{ts}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[L1] report={report_path}")
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr)
        raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main()
