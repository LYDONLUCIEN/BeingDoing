from typing import Dict, Any, Tuple

from langchain_core.runnables import RunnableConfig

from new_agent.graph.state import AgentState


async def record_event(
    state: AgentState,
    config: RunnableConfig,
    payload: Dict[str, Any],
) -> Tuple[AgentState, str]:
    """
    极简数据库记录工具（占位实现）。

    设计目标：
    - 对上层节点暴露一个统一的写入接口；
    - 当前仅把记录附加到 state["db_records_written"]，方便后续替换为真实 DB 调用。

    Args:
        state: 当前会话状态
        config: 运行配置（预留，将来可用于传递 DB 连接 / trace 等）
        payload: 要写入的结构化记录，如：
            {
                "user_id": "...",
                "session_id": "...",
                "stage": "analysis",
                "summary": "...",
                "raw_input": "..."
            }

    Returns:
        (更新后的 state, 字符串说明)
    """
    records = state.get("db_records_written", [])
    records.append(payload)
    state["db_records_written"] = records

    # 实际项目中，可以在这里调用 ORM / SQL / 外部服务写入真正数据库

    return state, "记录已写入占位 DB（实际实现待接入）"

