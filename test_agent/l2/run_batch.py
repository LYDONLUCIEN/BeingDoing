#!/usr/bin/env python3
"""
L2 批量场景执行器（MVP）

能力：
- 批量发现 scenario 文件（yaml/yml/json）
- 逐个调用 run_scenario.py 执行
- 输出批量汇总报告
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _collect_scenarios(target: Path) -> List[Path]:
    if target.is_file():
        return [target]
    if not target.is_dir():
        return []
    out: List[Path] = []
    for ext in ("*.yaml", "*.yml", "*.json"):
        out.extend(sorted(target.glob(ext)))
    return out


def _run_one(scenario_file: Path, dry_run: bool, engine: str) -> Dict[str, object]:
    root = _project_root()
    cmd = [
        sys.executable,
        str(root / "test_agent" / "l2" / "run_scenario.py"),
        "--scenario",
        str(scenario_file),
        "--engine",
        engine,
    ]
    if dry_run:
        cmd.append("--dry-run")
    proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True)
    return {
        "scenario": str(scenario_file),
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch-run L2 scenarios.")
    parser.add_argument(
        "--scenarios-dir",
        default="test_agent/scenarios/generated",
        help="场景目录或单个场景文件，默认 test_agent/scenarios/generated",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅打印将执行的命令")
    parser.add_argument("--filter", default="", help="按文件名关键词过滤（不区分大小写）")
    parser.add_argument("--fail-fast", action="store_true", help="遇到首个失败立即停止")
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="遇到失败继续（默认行为，显式开启便于脚本可读）",
    )
    parser.add_argument(
        "--engine",
        choices=["replay", "playwright", "auto"],
        default="auto",
        help="执行引擎：replay / playwright / auto",
    )
    args = parser.parse_args()

    root = _project_root()
    target = Path(args.scenarios_dir)
    if not target.is_absolute():
        target = (root / target).resolve()

    scenarios = _collect_scenarios(target)
    if args.filter.strip():
        kw = args.filter.strip().lower()
        scenarios = [s for s in scenarios if kw in s.name.lower()]
    if not scenarios:
        raise SystemExit(f"未找到可执行场景: {target}")

    if args.fail_fast and args.continue_on_error:
        raise SystemExit("--fail-fast 与 --continue-on-error 不能同时使用")

    print(f"[L2-BATCH] scenarios={len(scenarios)}")
    results: List[Dict[str, object]] = []
    stop_early = False
    for i, s in enumerate(scenarios, start=1):
        print(f"[L2-BATCH] ({i}/{len(scenarios)}) {s}")
        ret = _run_one(s, dry_run=args.dry_run, engine=args.engine)
        results.append(ret)
        if ret["stdout"]:
            print(ret["stdout"])
        if ret["stderr"]:
            print(ret["stderr"])
        if int(ret["exit_code"]) != 0 and args.fail_fast and not args.dry_run:
            stop_early = True
            print("[L2-BATCH] fail-fast: first failure encountered, stopping.")
            break

    passed = sum(1 for x in results if int(x["exit_code"]) == 0)
    failed = len(results) - passed
    summary = {
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "stopped_early": stop_early,
        "dry_run": bool(args.dry_run),
        "filter": args.filter or None,
        "engine": args.engine,
        "results": [
            {"scenario": x["scenario"], "exit_code": x["exit_code"]}
            for x in results
        ],
    }
    reports_dir = root / "test_agent" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = reports_dir / f"l2_batch_{ts}.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[L2-BATCH] summary={out}")
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, ensure_ascii=False, indent=2))
    if failed > 0 and not args.dry_run:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

