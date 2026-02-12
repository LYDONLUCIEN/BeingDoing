"""
LangGraph 状态图：思考链（reasoning → action → observation）循环，
结束后可选进入 user_agent 节点，将思考结果转为用户可见 messages。
"""
from typing import Optional, Any, Dict
from langgraph.graph import StateGraph, END
from app.core.agent.state import AgentState
from app.core.agent.config import AgentRunConfig, DEFAULT_RUN_CONFIG
from app.core.agent.nodes import (
    action_node,
    observation_node,
    guide_node,
)
# v2.4: 切换到新的reasoning节点（支持逐题引导）
from app.core.agent.nodes.reasoning_v2 import reasoning_node
from app.core.agent.nodes.user_agent import user_agent_node
from app.core.agent.tools import ToolRegistry, SearchTool, GuideTool, ExampleTool


def make_should_continue(max_iterations: int = 10):
    """供测试或外部构造条件边使用。"""
    def should_continue(state: AgentState) -> str:
        if state.get("error"):
            return "end"
        if not state.get("should_continue", False):
            return "end"
        if state.get("iteration_count", 0) >= max_iterations:
            return "end"
        context = state.get("context", {}) or {}
        current_step = state.get("current_step", "unknown")
        step_rounds = context.get("step_rounds", {})
        step_round_count = step_rounds.get(current_step, 0)
        max_rounds_per_step = context.get("limits", {}).get("max_rounds_per_step", 5)
        if step_round_count >= max_rounds_per_step:
            return "end"
        return "continue"
    return should_continue


def create_agent_graph(config: Optional[AgentRunConfig] = None):
    """
    创建智能体状态图（可配置）。
    - config.use_user_agent_node=True（默认）：observation 结束 → user_agent → END，用户可见 messages 由 user_agent 写入
    - config.use_user_agent_node=False：observation 结束 → END（仅思考链，适合调试或流式后续处理）
    """
    config = config or DEFAULT_RUN_CONFIG
    should_continue = make_should_continue(config.max_iterations)

    ToolRegistry.register(SearchTool())
    ToolRegistry.register(GuideTool())
    ToolRegistry.register(ExampleTool())

    if StateGraph is None:
        raise ImportError("LangGraph未安装，请运行: pip install langgraph")

    graph = StateGraph(AgentState)
    graph.add_node("reasoning", reasoning_node)
    graph.add_node("action", action_node)
    graph.add_node("observation", observation_node)
    graph.add_node("guide", guide_node)
    graph.add_node("user_agent", user_agent_node)

    graph.set_entry_point("reasoning")
    graph.add_edge("reasoning", "action")
    graph.add_edge("action", "observation")

    if config.use_user_agent_node:
        graph.add_conditional_edges(
            "observation",
            should_continue,
            {
                "continue": "reasoning",
                "end": "user_agent",
            }
        )
        graph.add_edge("user_agent", END)
    else:
        graph.add_conditional_edges(
            "observation",
            should_continue,
            {
                "continue": "reasoning",
                "end": END,
            }
        )

    return graph.compile()


def create_initial_state(
    user_input: str,
    current_step: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    stream_queue: Optional[Any] = None,
    question_progress: Optional[Dict] = None,
    force_regenerate_card: bool = False,
) -> AgentState:
    """
    创建初始状态（含双轨 messages / inner_messages 与 logs）。
    current_step 默认从 domain 读取，便于单点维护。
    stream_queue 非空时 reasoning 节点使用 chat_stream 并往该队列推块，供 SSE 端点真流式输出。
    question_progress: 从持久化存储加载的题目进度，跨请求保持状态。
    force_regenerate_card: 强制重新生成答题卡（用于"继续讨论"后的首次消息）。
    """
    from app.core.llmapi import LLMMessage
    from app.domain import DEFAULT_CURRENT_STEP

    if current_step is None:
        current_step = DEFAULT_CURRENT_STEP

    state: AgentState = AgentState(
        messages=[],
        inner_messages=[],
        logs=[],
        context={},
        current_step=current_step,
        tools_used=[],
        tool_results=[],
        user_input=user_input,
        user_id=user_id,
        session_id=session_id,
        iteration_count=0,
        should_continue=True,
        final_response=None,
        error=None,
    )
    if stream_queue is not None:
        state["stream_queue"] = stream_queue
    if question_progress is not None:
        state["question_progress"] = question_progress
    if force_regenerate_card:
        state["force_regenerate_card"] = force_regenerate_card
    return state