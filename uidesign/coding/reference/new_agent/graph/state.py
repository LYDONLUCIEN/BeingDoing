from typing import Annotated, Dict, Any, List, Optional

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    """
    精简版会话状态。

    - messages: 对用户可见的消息（用于前端展示）
    - inner_messages: 供 LLM / Planner 使用的内部消息（通常与 messages 同步，必要时可扩展）
    - logs: 过程日志，前端可用于展示进度
    - session_id: 会话 ID
    - plan: 当前总体规划/思路（由 planner_agent 写入）
    - current_step: 当前执行到的步骤描述
    - context: 结构化上下文（关键信息提取结果等）
    - db_records: 需要写入数据库的记录队列
    - db_records_written: 已写入数据库的记录（用于调试/回溯）
    - notes: 需要写入文件的笔记队列（每条包含 path/content）
    - completed: 会话是否已完成
    """

    messages: Annotated[List[AnyMessage], add_messages]
    inner_messages: Annotated[List[AnyMessage], add_messages]

    logs: List[Dict[str, Any]]
    session_id: str

    plan: Optional[Dict[str, Any]]
    current_step: Optional[str]
    context: Dict[str, Any]

    db_records: List[Dict[str, Any]]
    db_records_written: List[Dict[str, Any]]

    notes: List[Dict[str, Any]]

    completed: bool


def create_initial_state(state: Dict[str, Any]) -> AgentState:
    """
    从任意 dict 构造一个标准的 AgentState，
    保证所有字段都有合理的默认值。
    """
    messages = state.get("messages", [])

    return AgentState(
        messages=messages,
        inner_messages=list(messages),
        logs=state.get("logs", []),
        session_id=state.get("session_id", ""),
        plan=state.get("plan"),
        current_step=state.get("current_step"),
        context=state.get("context", {}),
        db_records=state.get("db_records", []),
        db_records_written=state.get("db_records_written", []),
        notes=state.get("notes", []),
        completed=state.get("completed", False),
    )

