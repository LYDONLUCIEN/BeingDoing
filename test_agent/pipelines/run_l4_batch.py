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


def _collect_tasks(target: Path) -> List[Path]:
    if target.is_file():
        return [target]
    if not target.is_dir():
        return []
    return sorted(target.rglob("*.yaml"))


def _run_one(
    task_file: Path,
    bridge_mode: str,
    engine: str,
    base_url: str,
    backend_url: str,
    timeout_ms: int,
    headless: str,
    report_dir: Path,
    dry_run: bool,
) -> Dict[str, object]:
    root = _project_root()
    cmd = [
        sys.executable,
        str(root / "test_agent" / "pipelines" / "run_l4.py"),
        "--task",
        str(task_file),
        "--bridge-mode",
        bridge_mode,
        "--engine",
        engine,
        "--report-dir",
        str(report_dir),
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
            "task": str(task_file),
            "exit_code": 0,
            "stdout": f"[L4-BATCH] dry-run command={' '.join(cmd)}\n",
            "stderr": "",
        }
    proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True)
    return {
        "task": str(task_file),
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch-run L4 TaskSpec scenarios.")
    parser.add_argument(
        "--tasks-dir",
        default="test_agent/adapters/beingdoing/scenarios/l4",
        help="L4 task 目录或单文件",
    )
    parser.add_argument("--filter", default="", help="按文件名关键词过滤（不区分大小写）")
    parser.add_argument("--bridge-mode", choices=["stub", "cli"], default="stub", help="L4 bridge 模式")
    parser.add_argument("--engine", choices=["local", "playwright"], default="local", help="L4 执行引擎")
    parser.add_argument("--base-url", default="http://127.0.0.1:3000", help="playwright 前端地址")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000", help="playwright 后端地址")
    parser.add_argument("--timeout-ms", type=int, default=30000, help="playwright 超时")
    parser.add_argument("--headless", choices=["true", "false"], default="true", help="playwright 是否无头")
    parser.add_argument("--report-dir", default="test_agent/reports", help="报告输出目录")
    parser.add_argument("--fail-fast", action="store_true", help="遇到首个失败立即停止")
    parser.add_argument("--dry-run", action="store_true", help="仅打印将执行命令，不执行")
    args = parser.parse_args()

    root = _project_root()
    target = Path(args.tasks_dir)
    if not target.is_absolute():
        target = (root / target).resolve()
    tasks = _collect_tasks(target)
    if args.filter.strip():
        kw = args.filter.strip().lower()
        tasks = [t for t in tasks if kw in t.name.lower()]
    if not tasks:
        raise SystemExit(f"未找到可执行任务: {target}")

    report_dir = Path(args.report_dir)
    if not report_dir.is_absolute():
        report_dir = (root / report_dir).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"[L4-BATCH] tasks={len(tasks)} bridge_mode={args.bridge_mode} engine={args.engine} dry_run={args.dry_run}"
    )
    results: List[Dict[str, object]] = []
    stopped_early = False
    for i, task in enumerate(tasks, start=1):
        print(f"[L4-BATCH] ({i}/{len(tasks)}) {task}")
        ret = _run_one(
            task_file=task,
            bridge_mode=args.bridge_mode,
            engine=args.engine,
            base_url=args.base_url,
            backend_url=args.backend_url,
            timeout_ms=args.timeout_ms,
            headless=args.headless,
            report_dir=report_dir,
            dry_run=args.dry_run,
        )
        results.append(ret)
        if ret["stdout"]:
            print(ret["stdout"])
        if ret["stderr"]:
            print(ret["stderr"])
        if int(ret["exit_code"]) != 0 and args.fail_fast and not args.dry_run:
            stopped_early = True
            print("[L4-BATCH] fail-fast: first failure encountered, stopping.")
            break

    passed = sum(1 for x in results if int(x["exit_code"]) == 0)
    failed = len(results) - passed
    summary = {
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "stopped_early": stopped_early,
        "dry_run": bool(args.dry_run),
        "bridge_mode": args.bridge_mode,
        "engine": args.engine,
        "filter": args.filter or None,
        "results": [{"task": x["task"], "exit_code": x["exit_code"]} for x in results],
    }
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = report_dir / f"l4_batch_{ts}.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[L4-BATCH] summary={out}")
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, ensure_ascii=False, indent=2))
    if failed > 0 and not args.dry_run:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
