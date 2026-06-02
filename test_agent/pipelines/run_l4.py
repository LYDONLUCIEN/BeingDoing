#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = _project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from test_agent.core.ai_user.agent_loop import L4AgentLoop
from test_agent.core.ai_user.bridge_kimi import KimiBridge, KimiBridgeConfig
from test_agent.core.ai_user.task_spec import TaskSpec


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one L4 AI user task.")
    parser.add_argument("--task", required=True, help="L4 TaskSpec YAML 路径")
    parser.add_argument("--bridge-mode", choices=["stub", "cli"], default="stub")
    parser.add_argument("--engine", choices=["local", "playwright"], default="local", help="L4 执行引擎")
    parser.add_argument("--base-url", default="http://127.0.0.1:3000", help="playwright 前端地址")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000", help="playwright 后端地址")
    parser.add_argument("--activation-code", default="", help="可选：激活码")
    parser.add_argument("--thread-id", default="", help="可选：线程 ID")
    parser.add_argument("--savepoint-id", default="", help="可选：savepoint ID")
    parser.add_argument("--headless", choices=["true", "false"], default="true", help="playwright 是否无头")
    parser.add_argument("--timeout-ms", type=int, default=30000, help="playwright 超时")
    parser.add_argument("--report-dir", default="test_agent/reports", help="报告输出目录")
    args = parser.parse_args()

    root = _project_root()
    task_path = Path(args.task)
    if not task_path.is_absolute():
        task_path = (root / task_path).resolve()
    if not task_path.is_file():
        raise SystemExit(f"TaskSpec 文件不存在: {task_path}")

    task_spec = TaskSpec.from_yaml(task_path)
    report_dir = Path(args.report_dir)
    if not report_dir.is_absolute():
        report_dir = (root / report_dir).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    artifacts_dir = report_dir / "artifacts" / f"{task_spec.task_id}_{ts}"
    bridge = KimiBridge(config=KimiBridgeConfig(mode=args.bridge_mode))
    loop = L4AgentLoop(
        bridge=bridge,
        runtime_engine=args.engine,
        runtime_options={
            "base_url": args.base_url,
            "backend_url": args.backend_url,
            "activation_code": args.activation_code,
            "thread_id": args.thread_id,
            "savepoint_id": args.savepoint_id,
            "headless": args.headless == "true",
            "timeout_ms": args.timeout_ms,
        },
        project_root=root,
    )
    result = loop.run(task_spec=task_spec, artifacts_dir=artifacts_dir)

    report_path = report_dir / f"l4_{task_spec.task_id}_{ts}.json"
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[L4] task={task_spec.task_id}")
    print(f"[L4] engine={args.engine} bridge={args.bridge_mode}")
    print(f"[L4] status={result['status']} score={result['score']}")
    print(f"[L4] report={report_path}")
    if result["status"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
