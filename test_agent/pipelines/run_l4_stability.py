#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _parse_report_path(stdout: str) -> str:
    for line in stdout.splitlines():
        if line.startswith("[L4] report="):
            return line.split("=", 1)[1].strip()
    return ""


def _run_once(
    root: Path,
    task: str,
    engine: str,
    bridge_mode: str,
    base_url: str,
    backend_url: str,
    timeout_ms: int,
    headless: str,
    report_dir: str,
) -> Dict[str, Any]:
    cmd = [
        sys.executable,
        str(root / "test_agent" / "pipelines" / "run_l4.py"),
        "--task",
        task,
        "--engine",
        engine,
        "--bridge-mode",
        bridge_mode,
        "--report-dir",
        report_dir,
    ]
    if engine == "playwright":
        cmd.extend(
            [
                "--base-url",
                base_url,
                "--backend-url",
                backend_url,
                "--timeout-ms",
                str(timeout_ms),
                "--headless",
                headless,
            ]
        )
    proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True)
    report_path = _parse_report_path(proc.stdout)
    report_data: Dict[str, Any] = {}
    if report_path:
        rp = Path(report_path)
        if rp.is_file():
            report_data = json.loads(rp.read_text(encoding="utf-8") or "{}")
    return {
        "command": " ".join(f'"{c}"' if " " in c else c for c in cmd),
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "report_path": report_path or None,
        "report": report_data,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="L4 稳定性验收（默认 3 次，至少 2 次通过）")
    parser.add_argument("--task", required=True, help="L4 TaskSpec YAML 路径")
    parser.add_argument("--runs", type=int, default=3, help="重复执行次数（默认 3）")
    parser.add_argument("--min-pass", type=int, default=2, help="最少通过次数（默认 2）")
    parser.add_argument("--engine", choices=["local", "playwright"], default="local")
    parser.add_argument("--bridge-mode", choices=["stub", "cli"], default="stub")
    parser.add_argument("--base-url", default="http://127.0.0.1:3000")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--headless", choices=["true", "false"], default="true")
    parser.add_argument("--report-dir", default="test_agent/reports")
    args = parser.parse_args()

    root = _project_root()
    task = args.task
    if not Path(task).is_absolute():
        task = str((root / task).resolve())
    report_dir = args.report_dir
    if not Path(report_dir).is_absolute():
        report_dir = str((root / report_dir).resolve())

    print(
        f"[L4-STABILITY] task={task} runs={args.runs} min_pass={args.min_pass} "
        f"engine={args.engine} bridge={args.bridge_mode}"
    )
    records: List[Dict[str, Any]] = []
    for i in range(1, args.runs + 1):
        print(f"[L4-STABILITY] run {i}/{args.runs}")
        rec = _run_once(
            root=root,
            task=task,
            engine=args.engine,
            bridge_mode=args.bridge_mode,
            base_url=args.base_url,
            backend_url=args.backend_url,
            timeout_ms=args.timeout_ms,
            headless=args.headless,
            report_dir=report_dir,
        )
        records.append(rec)
        if rec["stdout"]:
            print(rec["stdout"])
        if rec["stderr"]:
            print(rec["stderr"])

    pass_count = 0
    failure_classified = True
    for rec in records:
        report = rec.get("report") if isinstance(rec.get("report"), dict) else {}
        status = str(report.get("status") or "")
        if status in {"passed", "passed_with_risk"}:
            pass_count += 1
        timeline = report.get("timeline") if isinstance(report.get("timeline"), list) else []
        for item in timeline:
            if not isinstance(item, dict):
                continue
            if str(item.get("status") or "") != "fail":
                continue
            ft = str(item.get("failure_type") or "").strip()
            if not ft:
                failure_classified = False
                break

    accepted = pass_count >= args.min_pass and failure_classified
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(report_dir) / f"l4_stability_{ts}.json"
    summary = {
        "task": task,
        "runs": args.runs,
        "min_pass": args.min_pass,
        "pass_count": pass_count,
        "failure_classified": failure_classified,
        "accepted": accepted,
        "engine": args.engine,
        "bridge_mode": args.bridge_mode,
        "records": [
            {
                "exit_code": x.get("exit_code"),
                "report_path": x.get("report_path"),
                "status": (x.get("report") or {}).get("status"),
            }
            for x in records
        ],
    }
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[L4-STABILITY] report={out_path}")
    print(
        json.dumps(
            {
                "accepted": accepted,
                "pass_count": pass_count,
                "failure_classified": failure_classified,
            },
            ensure_ascii=False,
        )
    )
    if not accepted:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
