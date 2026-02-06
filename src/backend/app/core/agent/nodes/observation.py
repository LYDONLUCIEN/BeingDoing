"""
观察节点：处理工具结果
"""
from app.core.agent.state import AgentState
from app.core.llmapi import get_default_llm_provider, LLMMessage


async def observation_node(state: AgentState) -> AgentState:
    """
    观察节点：处理工具调用结果，决定是否继续
    
    Args:
        state: 当前状态
    
    Returns:
        更新后的状态
    """
    try:
        # 获取最后一个工具结果
        tool_results = state.get("tool_results", [])
        if not tool_results:
            state["should_continue"] = False
            return state
        
        last_result = tool_results[-1]
        tool_output = last_result.get("output", {})
        
        # 使用LLM分析工具结果
        llm = get_default_llm_provider()
        
        system_prompt = """你是一个专业的职业规划助手。你刚刚使用工具获取了一些信息。

工具结果：
{tool_output}

请分析这个结果，决定：
1. 是否需要继续使用其他工具
2. 是否可以给出最终回答

请以JSON格式返回：
{{
    "should_continue": true | false,
    "next_action": "use_tool" | "respond",
    "analysis": "你的分析",
    "response": "如果should_continue为false，提供最终回答"
}}
"""
        
        messages = [
            LLMMessage(
                role="system",
                content=system_prompt.format(tool_output=str(tool_output))
            ),
            LLMMessage(
                role="user",
                content="请分析工具结果并决定下一步行动"
            )
        ]
        
        response = await llm.chat(messages, temperature=0.7)
        
        # 解析响应
        import json
        try:
            observation_result = json.loads(response.content)
        except:
            observation_result = {
                "should_continue": False,
                "response": response.content
            }
        
        # 更新状态
        state["context"]["observation"] = observation_result
        state["should_continue"] = observation_result.get("should_continue", False)
        
        if not state["should_continue"]:
            state["final_response"] = observation_result.get("response", response.content)
        
        return state
    
    except Exception as e:
        state["error"] = f"观察节点错误: {str(e)}"
        state["should_continue"] = False
        return state
