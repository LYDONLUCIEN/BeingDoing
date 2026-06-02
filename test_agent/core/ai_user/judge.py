from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from test_agent.core.ai_user.task_spec import TaskSpec


@dataclass(slots=True)
class JudgeSignals:
    completion: bool = False
    consistency: bool = True
    ux_risk: List[str] = field(default_factory=list)


class L4Judge:
    """L4 规则判定器（首版：纯规则，避免 LLM 判题漂移）。"""

    def evaluate(
        self,
        task_spec: TaskSpec,
        timeline: List[Dict[str, Any]],
        runtime_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        signals = JudgeSignals()

        if runtime_state.get("hard_error"):
            signals.consistency = False
            signals.ux_risk.append("runtime_error")

        if any(str(item.get("status") or "").lower() == "fail" for item in timeline):
            signals.consistency = False
            for item in timeline:
                if str(item.get("status") or "").lower() != "fail":
                    continue
                ft = str(item.get("failure_type") or "runtime_error")
                if ft not in signals.ux_risk:
                    signals.ux_risk.append(ft)

        # completion: 当前阶段已进入目标后续阶段，或达到至少 2 轮并有有效用户输入
        phase = str(runtime_state.get("phase") or "")
        if phase and phase in {"talents", "interests"}:
            signals.completion = True
        elif len([t for t in timeline if t.get("action") == "chat_send"]) >= 2:
            signals.completion = True

        for item in timeline:
            duration_ms = int(item.get("duration_ms") or 0)
            if duration_ms > 10000:
                signals.ux_risk.append(f"slow_response:{duration_ms}ms")
                break

        score = self._score(task_spec=task_spec, signals=signals)
        status = "passed" if signals.completion and signals.consistency else "passed_with_risk"
        if not signals.consistency:
            status = "failed"

        return {
            "status": status,
            "score": score,
            "signals": {
                "completion": signals.completion,
                "consistency": signals.consistency,
                "ux_risk": signals.ux_risk,
            },
        }

    def _score(self, task_spec: TaskSpec, signals: JudgeSignals) -> float:
        completion = 1.0 if signals.completion else 0.0
        consistency = 1.0 if signals.consistency else 0.0
        risk_penalty = 0.0 if not signals.ux_risk else 0.3
        score = (
            completion * task_spec.scoring.completion_weight
            + consistency * task_spec.scoring.consistency_weight
            + max(0.0, 1.0 - risk_penalty) * task_spec.scoring.ux_risk_weight
        )
        return round(score, 4)
