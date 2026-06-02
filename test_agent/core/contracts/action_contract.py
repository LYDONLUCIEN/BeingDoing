from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Protocol


@dataclass(slots=True)
class ActionContract:
    """L3/L4 共享的标准动作描述。"""

    action: str
    params: Dict[str, Any] = field(default_factory=dict)


class ActionExecutorContract(Protocol):
    """动作执行器协议。"""

    def execute_action(self, action: ActionContract, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行动作并返回结构化结果。

        返回值建议字段：
        - status: pass/fail/skip
        - observation: 观察摘要
        - artifacts: 证据路径数组
        - error: 错误信息（可选）
        """
        ...
