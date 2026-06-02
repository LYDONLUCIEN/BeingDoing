from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Protocol

from test_agent.core.contracts.action_contract import ActionContract


@dataclass(slots=True)
class AdapterContext:
    """业务适配器运行上下文。"""

    run_id: str
    scenario_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class AdapterContract(Protocol):
    """
    业务适配器协议。

    core 层仅依赖此接口，不直接耦合具体业务实现。
    """

    def prepare_data(self, mode: str, scenario: Dict[str, Any]) -> Dict[str, Any]:
        ...

    def resolve_selector(self, alias: str) -> str:
        ...

    def compile_step(self, keyword: str, step_text: str) -> List[ActionContract]:
        ...

    def execute_domain_action(
        self, action: str, payload: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        ...

    def assert_domain(self, assertion: str, context: Dict[str, Any]) -> Dict[str, Any]:
        ...

    def fetch_runtime_state(self, context: Dict[str, Any]) -> Dict[str, Any]:
        ...
