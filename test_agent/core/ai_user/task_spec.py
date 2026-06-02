from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass(slots=True)
class PersonaSpec:
    age: int | None = None
    role: str = ""
    style: str = ""
    constraints: List[str] = field(default_factory=list)


@dataclass(slots=True)
class BudgetSpec:
    max_steps: int = 40
    max_turns: int = 12
    max_runtime_sec: int = 900
    llm_max_tokens_per_turn: int = 200


@dataclass(slots=True)
class ScoringSpec:
    completion_weight: float = 0.4
    consistency_weight: float = 0.3
    ux_risk_weight: float = 0.3


@dataclass(slots=True)
class TaskSpec:
    task_id: str
    goal: str
    persona: PersonaSpec = field(default_factory=PersonaSpec)
    golden_qa: Dict[str, Any] = field(default_factory=dict)
    budget: BudgetSpec = field(default_factory=BudgetSpec)
    scoring: ScoringSpec = field(default_factory=ScoringSpec)
    stop_conditions: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "TaskSpec":
        task_id = str(raw.get("task_id") or "").strip()
        goal = str(raw.get("goal") or "").strip()
        if not task_id:
            raise ValueError("TaskSpec 缺少 task_id")
        if not goal:
            raise ValueError("TaskSpec 缺少 goal")

        persona_raw = raw.get("persona") if isinstance(raw.get("persona"), dict) else {}
        budget_raw = raw.get("budget") if isinstance(raw.get("budget"), dict) else {}
        scoring_raw = raw.get("scoring") if isinstance(raw.get("scoring"), dict) else {}

        persona = PersonaSpec(
            age=persona_raw.get("age") if isinstance(persona_raw.get("age"), int) else None,
            role=str(persona_raw.get("role") or "").strip(),
            style=str(persona_raw.get("style") or "").strip(),
            constraints=[str(x).strip() for x in persona_raw.get("constraints", []) if str(x).strip()],
        )
        budget = BudgetSpec(
            max_steps=int(budget_raw.get("max_steps", 40)),
            max_turns=int(budget_raw.get("max_turns", 12)),
            max_runtime_sec=int(budget_raw.get("max_runtime_sec", 900)),
            llm_max_tokens_per_turn=int(budget_raw.get("llm_max_tokens_per_turn", 200)),
        )
        scoring = ScoringSpec(
            completion_weight=float(scoring_raw.get("completion_weight", 0.4)),
            consistency_weight=float(scoring_raw.get("consistency_weight", 0.3)),
            ux_risk_weight=float(scoring_raw.get("ux_risk_weight", 0.3)),
        )
        stop_conditions = [x for x in raw.get("stop_conditions", []) if isinstance(x, dict)]

        return cls(
            task_id=task_id,
            goal=goal,
            persona=persona,
            golden_qa=raw.get("golden_qa") if isinstance(raw.get("golden_qa"), dict) else {},
            budget=budget,
            scoring=scoring,
            stop_conditions=stop_conditions,
        )

    @classmethod
    def from_yaml(cls, path: Path) -> "TaskSpec":
        try:
            import yaml  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError("缺少 PyYAML，请先安装：pip install pyyaml") from exc
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError("TaskSpec YAML 顶层必须是对象")
        return cls.from_dict(raw)
