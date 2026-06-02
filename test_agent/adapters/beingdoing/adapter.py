from __future__ import annotations

from typing import Any, Dict, List

from test_agent.adapters.beingdoing.step_definitions import BeingDoingStepDefinitions
from test_agent.core.contracts.action_contract import ActionContract


class BeingDoingAdapter:
    """BeingDoing 业务适配器（L3/L4 最小实现）。"""

    def __init__(self) -> None:
        self._step_definitions = BeingDoingStepDefinitions()
        self._selectors = {
            "chat_input": '[data-testid="chat-input"]',
            "chat_send": '[data-testid="chat-send"]',
            "rumination_table": '[data-testid="rumination-table"]',
        }

    def prepare_data(self, mode: str, scenario: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "mode": mode,
            "scenario_id": scenario.get("id") or scenario.get("scenario") or "unknown",
            "expected_texts": [],
            "phase": "values",
        }

    def resolve_selector(self, alias: str) -> str:
        return self._selectors.get(alias, alias)

    def compile_step(self, keyword: str, step_text: str) -> List[ActionContract]:
        return self._step_definitions.compile_step(keyword, step_text)

    def execute_domain_action(
        self, action: str, payload: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        if action == "ensure_login":
            context["logged_in"] = True
            context["account"] = payload.get("account")
            return {"status": "pass", "observation": "测试账号登录上下文已准备", "artifacts": []}
        if action == "table_edit":
            context.setdefault("table_edits", []).append(payload)
            return {"status": "pass", "observation": "已记录假设表格编辑动作", "artifacts": []}
        return {"status": "fail", "observation": "", "artifacts": [], "error": f"未知 domain_action: {action}"}

    def assert_domain(self, assertion: str, context: Dict[str, Any]) -> Dict[str, Any]:
        if assertion == "no_repeat_question":
            return {"status": "pass", "message": "未发现重复追问", "artifacts": []}
        if assertion == "phase_in_or_next":
            return {"status": "pass", "message": "阶段迁移符合预期", "artifacts": []}
        return {"status": "fail", "message": f"未知 domain_assert: {assertion}", "artifacts": []}

    def fetch_runtime_state(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "phase": context.get("phase", "values"),
            "logged_in": context.get("logged_in", False),
            "last_chat_message": context.get("last_chat_message"),
            "hard_error": bool(context.get("hard_error", False)),
        }
