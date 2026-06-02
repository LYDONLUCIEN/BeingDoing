from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass(slots=True)
class YamlScenarioStep:
    keyword: str
    text: str
    raw: Dict[str, Any]


@dataclass(slots=True)
class YamlScenario:
    scenario_id: str
    title: str
    steps: List[YamlScenarioStep] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


def parse_yaml_scenario(path: Path) -> YamlScenario:
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("缺少 PyYAML，请先安装：pip install pyyaml") from exc

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("YAML 场景格式错误：顶层必须是对象")

    scenario_id = str(raw.get("id") or path.stem).strip()
    title = str(raw.get("title") or scenario_id).strip()
    steps_raw = raw.get("steps")
    if not isinstance(steps_raw, list) or not steps_raw:
        raise ValueError("YAML 场景缺少 steps")

    steps: List[YamlScenarioStep] = []
    for step in steps_raw:
        if not isinstance(step, dict):
            continue
        keyword = str(step.get("keyword") or "When").strip()
        text = str(step.get("text") or "").strip()
        if not text:
            action_name = str(step.get("action") or "").strip()
            if action_name:
                text = f"ACTION::{action_name}"
        steps.append(YamlScenarioStep(keyword=keyword, text=text, raw=step))

    if not steps:
        raise ValueError("YAML 场景中没有可执行步骤")

    return YamlScenario(scenario_id=scenario_id, title=title, steps=steps, raw=raw)
