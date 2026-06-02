from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

StepStatus = Literal["pass", "fail", "skip"]
ScenarioStatus = Literal["pass", "fail"]


@dataclass(slots=True)
class StepResult:
    step_id: str
    keyword: str
    text: str
    status: StepStatus
    duration_ms: int
    action_input: List[Dict[str, Any]] = field(default_factory=list)
    observation_summary: str = ""
    assertions: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass(slots=True)
class ScenarioResult:
    run_id: str
    scenario_id: str
    level: str
    status: ScenarioStatus
    started_at: str
    finished_at: str
    duration_ms: int
    steps: List[StepResult] = field(default_factory=list)
    failure_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def new(cls, run_id: str, scenario_id: str, level: str) -> "ScenarioResult":
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            run_id=run_id,
            scenario_id=scenario_id,
            level=level,
            status="pass",
            started_at=now,
            finished_at=now,
            duration_ms=0,
        )

    def finalize(self) -> None:
        self.finished_at = datetime.now(timezone.utc).isoformat()
        start_dt = datetime.fromisoformat(self.started_at)
        end_dt = datetime.fromisoformat(self.finished_at)
        self.duration_ms = int((end_dt - start_dt).total_seconds() * 1000)
        if any(step.status == "fail" for step in self.steps):
            self.status = "fail"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
