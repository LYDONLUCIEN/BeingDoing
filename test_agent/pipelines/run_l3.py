#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = _project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from test_agent.adapters.beingdoing.adapter import BeingDoingAdapter
from test_agent.core.bdd.executor import BddExecutor, PlaywrightActionExecutor
from test_agent.core.bdd.parser_gherkin import parse_feature_file
from test_agent.core.bdd.parser_yaml import parse_yaml_scenario


def _normalize_steps_from_feature(path: Path) -> tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    parsed = parse_feature_file(path)
    scenario_id = parsed.scenario_id or path.stem
    steps = [{"keyword": s.keyword, "text": s.text} for s in parsed.steps]
    metadata = {"feature": parsed.feature, "scenario": parsed.scenario}
    return scenario_id, steps, metadata


def _normalize_steps_from_yaml(path: Path) -> tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    parsed = parse_yaml_scenario(path)
    steps = [{"keyword": s.keyword, "text": s.text, "raw": s.raw} for s in parsed.steps]
    metadata = {"title": parsed.title}
    return parsed.scenario_id, steps, metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one L3 BDD scenario.")
    parser.add_argument("--scenario", required=True, help="feature/yaml/json 场景文件")
    parser.add_argument("--report-dir", default="test_agent/reports", help="报告输出目录")
    parser.add_argument("--dry-run", action="store_true", help="仅解析并打印步骤，不执行")
    parser.add_argument("--engine", choices=["local", "playwright"], default="local", help="动作执行引擎")
    parser.add_argument("--base-url", default="http://127.0.0.1:3000", help="playwright 前端地址")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000", help="playwright 后端地址")
    parser.add_argument("--activation-code", default="", help="可选：激活码（用于 deep link/savepoint）")
    parser.add_argument("--thread-id", default="", help="可选：线程 ID（用于 deep link）")
    parser.add_argument("--savepoint-id", default="", help="可选：savepoint ID（会先自动 load）")
    parser.add_argument("--headless", choices=["true", "false"], default="true", help="playwright 是否无头")
    parser.add_argument("--timeout-ms", type=int, default=30000, help="playwright 动作超时")
    args = parser.parse_args()

    root = _project_root()
    scenario_path = Path(args.scenario)
    if not scenario_path.is_absolute():
        scenario_path = (root / scenario_path).resolve()
    if not scenario_path.is_file():
        raise SystemExit(f"场景文件不存在: {scenario_path}")

    suffix = scenario_path.suffix.lower()
    if suffix == ".feature":
        scenario_id, steps, metadata = _normalize_steps_from_feature(scenario_path)
    elif suffix in {".yaml", ".yml", ".json"}:
        scenario_id, steps, metadata = _normalize_steps_from_yaml(scenario_path)
    else:
        raise SystemExit("仅支持 .feature/.yaml/.yml/.json")

    if args.dry_run:
        print(
            json.dumps(
                {"scenario_id": scenario_id, "steps": steps, "metadata": metadata},
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    adapter = BeingDoingAdapter()
    pw_executor = None
    if args.engine == "playwright":
        pw_executor = PlaywrightActionExecutor(
            project_root=root,
            base_url=args.base_url,
            backend_url=args.backend_url,
            activation_code=args.activation_code or None,
            thread_id=args.thread_id or None,
            savepoint_id=args.savepoint_id or None,
            headless=args.headless == "true",
            timeout_ms=args.timeout_ms,
        )
    executor = BddExecutor(adapter=adapter, playwright_executor=pw_executor, engine=args.engine)
    result = executor.run(scenario_id=scenario_id, steps=steps)
    result.metadata.update(metadata)
    result.metadata.update(
        {
            "engine": args.engine,
            "base_url": args.base_url if args.engine == "playwright" else None,
            "backend_url": args.backend_url if args.engine == "playwright" else None,
        }
    )
    report = result.to_dict()

    report_dir = Path(args.report_dir)
    if not report_dir.is_absolute():
        report_dir = (root / report_dir).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"l3_{scenario_id}_{ts}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[L3] scenario={scenario_id}")
    print(f"[L3] status={result.status}")
    print(f"[L3] report={report_path}")
    print(json.dumps({"run_id": result.run_id, "duration_ms": result.duration_ms}, ensure_ascii=False))
    if result.status != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
