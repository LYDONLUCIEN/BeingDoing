from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Protocol


@dataclass(slots=True)
class AssertionContract:
    """断言描述，支持通用断言和业务断言。"""

    assertion: str
    params: Dict[str, Any] = field(default_factory=dict)


class AssertionExecutorContract(Protocol):
    """断言执行协议。"""

    def execute_assertion(
        self, assertion: AssertionContract, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        返回结构化断言结果。

        返回值建议字段：
        - status: pass/fail/skip
        - message: 断言说明
        - artifacts: 证据路径数组
        """
        ...
