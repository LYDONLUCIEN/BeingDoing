#!/usr/bin/env python3
"""
L2 最小可用场景执行器（MVP）

用途：
- 读取 YAML/JSON 场景文件
- 提取 seed_fixture + phase/thread/message
- 调用 replay_simple_chat.py 执行一次回放
- 输出结构化执行报告到 test_agent/reports/
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class ScenarioReplayInput:
    scenario_id: str
    seed_report_dir: str
    phase: str
    thread_id: str
    message: str
    savepoint_id: Optional[str] = None


@dataclass
class ScenarioPlaywrightInput:
    scenario_id: str
    scenario_file: str
    base_url: str
    backend_url: str
    activation_code: Optional[str] = None
    thread_id: Optional[str] = None
    savepoint_id: Optional[str] = None


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError as e:
        raise RuntimeError("缺少 PyYAML，请先安装：pip install pyyaml") from e
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("场景文件格式错误：顶层必须是对象")
    return raw


def _load_scenario(path: Path) -> Dict[str, Any]:
    if path.suffix.lower() in {".yaml", ".yml"}:
        return _load_yaml(path)
    if path.suffix.lower() == ".json":
        raw = json.loads(path.read_text(encoding="utf-8") or "{}")
        if not isinstance(raw, dict):
            raise ValueError("JSON 场景文件顶层必须是对象")
        return raw
    raise ValueError("仅支持 .yaml/.yml/.json 场景文件")


def _extract_chat_send_text(s: Dict[str, Any]) -> Optional[str]:
    steps = s.get("steps")
    if not isinstance(steps, list):
        return None
    for step in steps:
        if not isinstance(step, dict):
            continue
        if str(step.get("action") or "").strip() == "chat_send":
            txt = str(step.get("text") or "").strip()
            if txt:
                return txt
    return None


def _extract_input(s: Dict[str, Any]) -> ScenarioReplayInput:
    scenario_id = str(s.get("id") or "unnamed_scenario").strip()
    data = s.get("data") if isinstance(s.get("data"), dict) else {}
    seed_report_dir = str(data.get("fixture_report_dir") or "").strip()
    phase = str(data.get("phase") or "values").strip()
    thread_id = str(data.get("thread_id") or "").strip()
    if not seed_report_dir or not thread_id:
        raise ValueError("场景缺少 data.fixture_report_dir 或 data.thread_id")

    message = (
        _extract_chat_send_text(s)
        or str((s.get("assertions") or {}).get("expected_hint") or "").strip()
        or "请继续"
    )
    savepoint_id = scenario_id if scenario_id.startswith("sp_") else None
    return ScenarioReplayInput(
        scenario_id=scenario_id,
        seed_report_dir=seed_report_dir,
        phase=phase,
        thread_id=thread_id,
        message=message,
        savepoint_id=savepoint_id,
    )


def _extract_playwright_input(s: Dict[str, Any], scenario_file: Path) -> ScenarioPlaywrightInput:
    scenario_id = str(s.get("id") or "unnamed_scenario").strip()
    data = s.get("data") if isinstance(s.get("data"), dict) else {}
    base_url = str(data.get("base_url") or "http://127.0.0.1:3000").strip()
    backend_url = str(data.get("backend_url") or "http://127.0.0.1:8000").strip()
    activation_code = str(data.get("activation_code") or "").strip() or None
    thread_id = str(data.get("thread_id") or "").strip() or None
    savepoint_id = str(data.get("savepoint_id") or "").strip() or None
    return ScenarioPlaywrightInput(
        scenario_id=scenario_id,
        scenario_file=str(scenario_file),
        base_url=base_url,
        backend_url=backend_url,
        activation_code=activation_code,
        thread_id=thread_id,
        savepoint_id=savepoint_id,
    )


def _build_command(inp: ScenarioReplayInput) -> list[str]:
    root = _project_root()
    cmd = [
        sys.executable,
        str(root / "src/backend/scripts/replay_simple_chat.py"),
        "--seed-report-dir",
        inp.seed_report_dir,
        "--phase",
        inp.phase,
        "--thread-id",
        inp.thread_id,
        "--message",
        inp.message,
    ]
    if inp.savepoint_id:
        cmd.extend(["--savepoint-id", inp.savepoint_id])
    return cmd


def _parse_summary(stdout: str) -> Dict[str, Any]:
    m = re.search(r"=== SUMMARY ===\s*(\{[\s\S]*?\})\s*$", stdout.strip())
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}


def _parse_playwright_result(stdout: str) -> Dict[str, Any]:
    m = re.search(r"=== L2_PLAYWRIGHT_RESULT ===\s*(\{[\s\S]*?\})\s*$", stdout.strip())
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}


def main() -> None:
    p = argparse.ArgumentParser(description="Run one L2 scenario via replay script.")
    p.add_argument("--scenario", required=True, help="场景文件路径（yaml/json）")
    p.add_argument("--dry-run", action="store_true", help="仅打印命令，不执行")
    p.add_argument(
        "--engine",
        choices=["replay", "playwright", "auto"],
        default="auto",
        help="执行引擎：replay（默认兼容）或 playwright（真浏览器）",
    )
    args = p.parse_args()

    root = _project_root()
    scenario_path = (root / args.scenario).resolve() if not Path(args.scenario).is_absolute() else Path(args.scenario)
    if not scenario_path.is_file():
        raise SystemExit(f"场景文件不存在: {scenario_path}")

    scenario = _load_scenario(scenario_path)
    scenario_engine = str(scenario.get("engine") or "").strip().lower()
    engine = args.engine
    if engine == "auto":
        engine = "playwright" if scenario_engine == "playwright" else "replay"

    reports_dir = root / "test_agent" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    input_payload: Dict[str, Any] = {}
    if engine == "playwright":
        inp_pw = _extract_playwright_input(scenario, scenario_path)
        cmd = [
            "node",
            str(root / "test_agent" / "l2" / "playwright_runner.mjs"),
            "--scenario",
            inp_pw.scenario_file,
            "--base-url",
            inp_pw.base_url,
            "--backend-url",
            inp_pw.backend_url,
        ]
        if inp_pw.activation_code:
            cmd.extend(["--activation-code", inp_pw.activation_code])
        if inp_pw.thread_id:
            cmd.extend(["--thread-id", inp_pw.thread_id])
        if inp_pw.savepoint_id:
            cmd.extend(["--savepoint-id", inp_pw.savepoint_id])
        scenario_id = inp_pw.scenario_id
        input_payload = inp_pw.__dict__
        out = reports_dir / f"l2_{scenario_id}_{ts}.json"
    else:
        inp = _extract_input(scenario)
        cmd = _build_command(inp)
        scenario_id = inp.scenario_id
        input_payload = inp.__dict__
        out = reports_dir / f"l2_{scenario_id}_{ts}.json"

    pretty = " ".join(f'"{c}"' if " " in c else c for c in cmd)
    print(f"[L2] scenario={scenario_id}")
    print(f"[L2] engine={engine}")
    print(f"[L2] command={pretty}")
    if args.dry_run:
        return

    proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True)
    summary = _parse_playwright_result(proc.stdout) if engine == "playwright" else _parse_summary(proc.stdout)
    report = {
        "scenario_id": scenario_id,
        "scenario_file": str(scenario_path),
        "engine": engine,
        "input": input_payload,
        "command": pretty,
        "exit_code": proc.returncode,
        "summary": summary,
    }
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[L2] report={out}")
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr)
        raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main()

