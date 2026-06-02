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


def _run_cmd(cmd: List[str], cwd: Path) -> Dict[str, object]:
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    return {
        "command": " ".join(f'"{c}"' if " " in c else c for c in cmd),
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run L1/L2/L3/L4 in a unified pipeline.")
    parser.add_argument(
        "--profile",
        choices=["custom", "nightly"],
        default="custom",
        help="执行预设：custom（按参数）/ nightly（L2+L3+L4 夜跑推荐）",
    )
    parser.add_argument(
        "--levels",
        default="l1,l2,l3",
        help="要执行的层级，逗号分隔：l1,l2,l3,l4",
    )
    parser.add_argument("--report-dir", default="test_agent/reports", help="总报告输出目录")
    parser.add_argument("--fail-fast", action="store_true", help="任一层失败后立即停止")
    parser.add_argument("--dry-run", action="store_true", help="仅打印将执行命令，不执行")
    parser.add_argument(
        "--l1-target",
        default="test/backend",
        help="L1 pytest target",
    )
    parser.add_argument(
        "--l1-args",
        default="",
        help="L1 额外 pytest 参数",
    )
    parser.add_argument(
        "--l2-scenarios-dir",
        default="test_agent/scenarios/generated",
        help="L2 场景目录",
    )
    parser.add_argument(
        "--l2-engine",
        choices=["replay", "playwright", "auto"],
        default="auto",
        help="L2 引擎",
    )
    parser.add_argument(
        "--l3-scenarios-dir",
        default="test_agent/adapters/beingdoing/scenarios/l3",
        help="L3 场景目录",
    )
    parser.add_argument(
        "--l3-engine",
        choices=["local", "playwright"],
        default="local",
        help="L3 引擎",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:3000", help="L2/L3 playwright 前端地址")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000", help="L2/L3 playwright 后端地址")
    parser.add_argument("--timeout-ms", type=int, default=30000, help="L3 playwright 超时")
    parser.add_argument("--headless", choices=["true", "false"], default="true", help="L3 playwright 是否无头")
    parser.add_argument(
        "--l4-tasks-dir",
        default="test_agent/adapters/beingdoing/scenarios/l4",
        help="L4 task 目录",
    )
    parser.add_argument(
        "--l4-bridge-mode",
        choices=["stub", "cli"],
        default="stub",
        help="L4 bridge 模式",
    )
    parser.add_argument(
        "--l4-engine",
        choices=["local", "playwright"],
        default="local",
        help="L4 执行引擎",
    )
    args = parser.parse_args()

    if args.profile == "nightly":
        # Nightly 默认：L2 + L3 + L4，收集更多风险信号，不做 fail-fast。
        args.levels = "l2,l3,l4"
        nightly_l2_generated = _project_root() / "test_agent" / "scenarios" / "generated"
        generated_has_cases = False
        if nightly_l2_generated.exists():
            for ext in ("*.yaml", "*.yml", "*.json"):
                if any(nightly_l2_generated.glob(ext)):
                    generated_has_cases = True
                    break
        args.l2_scenarios_dir = (
            "test_agent/scenarios/generated"
            if generated_has_cases
            else "test_agent/scenarios/l2"
        )
        args.l2_engine = "auto"
        args.l3_scenarios_dir = "test_agent/adapters/beingdoing/scenarios/l3"
        args.l3_engine = "local"
        args.l4_tasks_dir = "test_agent/adapters/beingdoing/scenarios/l4"
        args.l4_bridge_mode = "stub"
        args.l4_engine = "local"
        if args.fail_fast:
            print("[PIPELINE] profile=nightly: overriding --fail-fast to false")
            args.fail_fast = False

    root = _project_root()
    selected_levels = [x.strip().lower() for x in args.levels.split(",") if x.strip()]
    supported = {"l1", "l2", "l3", "l4"}
    invalid = [x for x in selected_levels if x not in supported]
    if invalid:
        raise SystemExit(f"不支持的 levels: {invalid}，仅支持 {sorted(supported)}")

    report_dir = Path(args.report_dir)
    if not report_dir.is_absolute():
        report_dir = (root / report_dir).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    plan: List[Dict[str, object]] = []
    if "l1" in selected_levels:
        cmd = [
            sys.executable,
            str(root / "test_agent" / "l1" / "run_l1.py"),
            "--pytest-target",
            args.l1_target,
            "--report-dir",
            str(report_dir),
        ]
        if args.l1_args.strip():
            cmd.extend(["--pytest-args", args.l1_args])
        if args.dry_run:
            cmd.append("--dry-run")
        plan.append({"level": "l1", "cmd": cmd})

    if "l2" in selected_levels:
        cmd = [
            sys.executable,
            str(root / "test_agent" / "l2" / "run_batch.py"),
            "--scenarios-dir",
            args.l2_scenarios_dir,
            "--engine",
            args.l2_engine,
        ]
        if args.dry_run:
            cmd.append("--dry-run")
        plan.append({"level": "l2", "cmd": cmd})

    if "l3" in selected_levels:
        cmd = [
            sys.executable,
            str(root / "test_agent" / "pipelines" / "run_l3_batch.py"),
            "--scenarios-dir",
            args.l3_scenarios_dir,
            "--engine",
            args.l3_engine,
        ]
        if args.l3_engine == "playwright":
            cmd.extend(
                [
                    "--base-url",
                    args.base_url,
                    "--backend-url",
                    args.backend_url,
                    "--timeout-ms",
                    str(args.timeout_ms),
                    "--headless",
                    args.headless,
                ]
            )
        if args.dry_run:
            cmd.append("--dry-run")
        plan.append({"level": "l3", "cmd": cmd})

    if "l4" in selected_levels:
        cmd = [
            sys.executable,
            str(root / "test_agent" / "pipelines" / "run_l4_batch.py"),
            "--tasks-dir",
            args.l4_tasks_dir,
            "--bridge-mode",
            args.l4_bridge_mode,
            "--engine",
            args.l4_engine,
            "--report-dir",
            str(report_dir),
        ]
        if args.l4_engine == "playwright":
            cmd.extend(
                [
                    "--base-url",
                    args.base_url,
                    "--backend-url",
                    args.backend_url,
                    "--timeout-ms",
                    str(args.timeout_ms),
                    "--headless",
                    args.headless,
                ]
            )
        if args.dry_run:
            cmd.append("--dry-run")
        plan.append({"level": "l4", "cmd": cmd})

    print(f"[PIPELINE] levels={selected_levels} dry_run={args.dry_run}")
    results: List[Dict[str, object]] = []
    stopped_early = False
    for item in plan:
        level = str(item["level"])
        cmd = item["cmd"] if isinstance(item.get("cmd"), list) else []
        print(f"[PIPELINE] running {level}")
        ret = _run_cmd(cmd=cmd, cwd=root)
        results.append({"level": level, **ret})
        if ret["stdout"]:
            print(ret["stdout"])
        if ret["stderr"]:
            print(ret["stderr"])
        if int(ret["exit_code"]) != 0 and args.fail_fast and not args.dry_run:
            stopped_early = True
            print("[PIPELINE] fail-fast: stop on first failed level.")
            break

    failed_levels = [x["level"] for x in results if int(x["exit_code"]) != 0]
    summary = {
        "profile": args.profile,
        "levels": selected_levels,
        "total_levels": len(results),
        "failed_levels": failed_levels,
        "passed": len(failed_levels) == 0,
        "stopped_early": stopped_early,
        "dry_run": bool(args.dry_run),
        "results": [
            {
                "level": x["level"],
                "exit_code": x["exit_code"],
                "command": x["command"],
            }
            for x in results
        ],
    }
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_path = report_dir / f"all_levels_{ts}.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[PIPELINE] summary={summary_path}")
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, ensure_ascii=False, indent=2))
    if failed_levels and not args.dry_run:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
