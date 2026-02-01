"""
LangGraph状态图定义
"""
from langgraph.graph import StateGraph, END
from app.core.agent.state import AgentState
from app.core.agent.nodes import reasoning_node, action_node, observation_node, guide_node
from app.core.agent.tools import ToolRegistry, SearchTool, GuideTool, ExampleTool


def should_continue(state: AgentState) -> str:
    """
    判断是否继续循环
    
    Args:
        state: 当前状态
    
    Returns:
        下一个节点名称
    """
    # 检查错误
    if state.get("error"):
        return "end"
    
    # 检查是否应该继续
    if not state.get("should_continue", False):
        return "end"
    
    # 检查迭代次数（防止无限循环）
    max_iterations = 10
    if state.get("iteration_count", 0) >= max_iterations:
        return "end"
    
    # 继续循环
    return "continue"


def create_agent_graph():
    """
    创建智能体状态图
    
    Returns:
        LangGraph状态图
    """
    # 注册工具
    ToolRegistry.register(SearchTool())
    ToolRegistry.register(GuideTool())
    ToolRegistry.register(ExampleTool())
    
    # 检查LangGraph是否可用
    if StateGraph is None:
        raise ImportError("LangGraph未安装，请运行: pip install langgraph")
    
    # 创建状态图
    graph = StateGraph(AgentState)
    
    # 添加节点
    graph.add_node("reasoning", reasoning_node)
    graph.add_node("action", action_node)
    graph.add_node("observation", observation_node)
    graph.add_node("guide", guide_node)
    
    # 设置入口点
    graph.set_entry_point("reasoning")
    
    # 添加边
    graph.add_edge("reasoning", "action")
    graph.add_edge("action", "observation")
    
    # 条件边：根据should_continue决定是否继续
    graph.add_conditional_edges(
        "observation",
        should_continue,
        {
            "continue": "reasoning",  # 继续循环
            "end": END  # 结束
        }
    )
    
    # 编译图
    app = graph.compile()
    
    return app


def create_initial_state(
    user_input: str,
    current_step: str = "values_exploration",
    user_id: Optional[str] = None,
    session_id: Optional[str] = None
) -> AgentState:
    """
    创建初始状态
    
    Args:
        user_input: 用户输入
        current_step: 当前步骤
        user_id: 用户ID
        session_id: 会话ID
    
    Returns:
        初始状态
    """
    from app.core.llmapi import LLMMessage
    
    return AgentState(
        messages=[],
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
        error=None
    )
