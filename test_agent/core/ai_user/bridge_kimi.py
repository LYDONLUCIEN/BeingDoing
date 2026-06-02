from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List

from test_agent.core.ai_user.task_spec import TaskSpec


@dataclass(slots=True)
class KimiBridgeConfig:
    mode: str = "stub"  # stub | cli
    cli_command: str = "kimi"
    timeout_sec: int = 60


class KimiBridge:
    """
    L4 决策桥接层。

    - stub: 无外部依赖，返回稳定可复现动作
    - cli: 尝试调用本地 kimi CLI，要求输出 JSON
    """

    def __init__(self, config: KimiBridgeConfig | None = None) -> None:
        self.config = config or KimiBridgeConfig()

    def propose_action(
        self,
        task_spec: TaskSpec,
        observation: Dict[str, Any],
        timeline: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if self.config.mode == "cli":
            return self._propose_by_cli(task_spec=task_spec, observation=observation, timeline=timeline)
        return self._propose_by_stub(task_spec=task_spec, observation=observation, timeline=timeline)

    def _propose_by_stub(
        self,
        task_spec: TaskSpec,
        observation: Dict[str, Any],
        timeline: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        turn = len(timeline) + 1
        if turn == 1:
            return {"action": "goto", "params": {"url": "/explore/chat/values"}, "thought": "先进入价值观阶段页面"}
        if turn >= task_spec.budget.max_turns:
            return {"action": "stop", "params": {"reason": "turn_budget_reached"}, "thought": "达到轮次上限，停止"}

        persona_hint = task_spec.persona.style or "表达简洁"
        text = f"我是测试用户，第{turn}轮回答。{persona_hint}，围绕目标：{task_spec.goal[:20]}"
        return {"action": "chat_send", "params": {"text": text}, "thought": "继续推进目标达成"}

    def _propose_by_cli(
        self,
        task_spec: TaskSpec,
        observation: Dict[str, Any],
        timeline: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        prompt = self._build_prompt(task_spec=task_spec, observation=observation, timeline=timeline)
        proc = subprocess.run(
            [self.config.cli_command, "chat", "--json"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=self.config.timeout_sec,
            check=False,
        )
        if proc.returncode != 0:
            return {
                "action": "chat_send",
                "params": {"text": "请继续"},
                "thought": f"kimi cli failed: rc={proc.returncode}",
                "bridge_error": proc.stderr.strip(),
                "failure_type": "env_unavailable",
            }
        try:
            output = json.loads(proc.stdout.strip() or "{}")
            action = output.get("action")
            params = output.get("params")
            if not isinstance(action, str) or not isinstance(params, dict):
                raise ValueError("invalid action payload")
            return {
                "action": action,
                "params": params,
                "thought": str(output.get("thought") or ""),
                "raw_llm": output,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "action": "chat_send",
                "params": {"text": "请继续"},
                "thought": "解析 kimi JSON 失败，回退默认动作",
                "bridge_error": str(exc),
                "raw_text": proc.stdout.strip(),
                "failure_type": "llm_invalid_json",
            }

    def _build_prompt(
        self,
        task_spec: TaskSpec,
        observation: Dict[str, Any],
        timeline: List[Dict[str, Any]],
    ) -> str:
        payload = {
            "role": "test_user_agent",
            "task": {
                "task_id": task_spec.task_id,
                "goal": task_spec.goal,
                "persona": {
                    "role": task_spec.persona.role,
                    "style": task_spec.persona.style,
                    "constraints": task_spec.persona.constraints,
                },
            },
            "observation": observation,
            "recent_timeline": timeline[-6:],
            "output_schema": {
                "action": "goto|click|fill|chat_send|wait_for|stop",
                "params": {},
                "thought": "string",
            },
        }
        return json.dumps(payload, ensure_ascii=False)
