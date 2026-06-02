#!/usr/bin/env python3
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
    for ext in ("*.feature", "*.yaml", "*.yml", "*.json"):
        out.extend(sorted(target.rglob(ext)))
    return out


def _run_one(
    scenario_file: Path,
    engine: str,
    base_url: str,
    backend_url: str,
    timeout_ms: int,
    headless: str,
    dry_run: bool,
) -> Dict[str, object]:
    root = _project_root()
    cmd = [
        sys.executable,
        str(root / "test_agent" / "pipelines" / "run_l3.py"),
        "--scenario",
        str(scenario_file),
        "--engine",
        engine,
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
    if dry_run:
        return {
            "scenario": str(scenario_file),
            "exit_code": 0,
            "stdout": f"[L3-BATCH] dry-run command={' '.join(cmd)}\n",
            "stderr": "",
        }
    proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True)
    return {
        "scenario": str(scenario_file),
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch-run L3 scenarios.")
    parser.add_argument(
        "--scenarios-dir",
        default="test_agent/adapters/beingdoing/scenarios/l3",
        help="场景目录或单个场景文件",
    )
    parser.add_argument("--filter", default="", help="按文件名关键词过滤（不区分大小写）")
    parser.add_argument("--fail-fast", action="store_true", help="遇到首个失败立即停止")
    parser.add_argument("--dry-run", action="store_true", help="仅打印将执行命令，不执行")
    parser.add_argument(
        "--engine",
        choices=["local", "playwright"],
        default="local",
        help="执行引擎",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:3000", help="playwright 前端地址")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000", help="playwright 后端地址")
    parser.add_argument("--timeout-ms", type=int, default=30000, help="playwright 动作超时")
    parser.add_argument("--headless", choices=["true", "false"], default="true", help="playwright 是否无头")
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

    print(f"[L3-BATCH] scenarios={len(scenarios)} engine={args.engine}")
    results: List[Dict[str, object]] = []
    stopped_early = False
    for i, s in enumerate(scenarios, start=1):
        print(f"[L3-BATCH] ({i}/{len(scenarios)}) {s}")
        ret = _run_one(
            scenario_file=s,
            engine=args.engine,
            base_url=args.base_url,
            backend_url=args.backend_url,
            timeout_ms=args.timeout_ms,
            headless=args.headless,
            dry_run=args.dry_run,
        )
        results.append(ret)
        if ret["stdout"]:
            print(ret["stdout"])
        if ret["stderr"]:
            print(ret["stderr"])
        if int(ret["exit_code"]) != 0 and args.fail_fast and not args.dry_run:
            stopped_early = True
            print("[L3-BATCH] fail-fast: first failure encountered, stopping.")
            break

    passed = sum(1 for x in results if int(x["exit_code"]) == 0)
    failed = len(results) - passed
    summary = {
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "stopped_early": stopped_early,
        "dry_run": bool(args.dry_run),
        "engine": args.engine,
        "filter": args.filter or None,
        "results": [{"scenario": x["scenario"], "exit_code": x["exit_code"]} for x in results],
    }
    reports_dir = root / "test_agent" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = reports_dir / f"l3_batch_{ts}.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[L3-BATCH] summary={out}")
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, ensure_ascii=False, indent=2))
    if failed > 0 and not args.dry_run:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
