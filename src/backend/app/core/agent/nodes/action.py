"""
行动节点：调用工具
"""
from typing import Dict
from app.core.agent.state import AgentState
from app.core.agent.tools import ToolRegistry


async def action_node(state: AgentState) -> AgentState:
    """
    行动节点：根据推理结果调用工具
    
    Args:
        state: 当前状态
    
    Returns:
        更新后的状态
    """
    try:
        reasoning = state.get("context", {}).get("reasoning", {})
        action = reasoning.get("action", "respond")
        
        if action == "use_tool":
            tool_name = reasoning.get("tool_name")
            tool_input = reasoning.get("tool_input", {})
            
            if not tool_name:
                state["error"] = "工具名称未指定"
                state["should_continue"] = False
                return state
            
            # 从工具注册表获取工具
            tool = ToolRegistry.get_tool(tool_name)
            if not tool:
                state["error"] = f"工具不存在: {tool_name}"
                state["should_continue"] = False
                return state
            
            # 调用工具
            tool_result = await tool.execute(tool_input, state)
            
            # 更新状态
            state["tools_used"].append(tool_name)
            state["tool_results"].append({
                "tool": tool_name,
                "input": tool_input,
                "output": tool_result
            })
            
            # 存储到context
            state["context"]["last_tool_result"] = tool_result
        
        elif action == "respond":
            # 直接使用推理结果中的回答
            response = reasoning.get("response", "")
            state["final_response"] = response
            state["should_continue"] = False
        
        elif action == "guide":
            # 引导用户
            guide_content = reasoning.get("response", "")
            state["final_response"] = guide_content
            state["should_continue"] = False
        
        return state
    
    except Exception as e:
        state["error"] = f"行动节点错误: {str(e)}"
        state["should_continue"] = False
        return state
