"""
引导节点：主动引导用户
"""
from app.core.agent.state import AgentState
from app.core.llmapi import get_default_llm_provider, LLMMessage


async def guide_node(state: AgentState) -> AgentState:
    """
    引导节点：主动引导用户继续探索
    
    Args:
        state: 当前状态
    
    Returns:
        更新后的状态
    """
    try:
        llm = get_default_llm_provider()
        
        current_step = state.get("current_step", "unknown")
        user_input = state.get("user_input", "")
        
        system_prompt = """你是一个专业的职业规划助手。用户可能在探索过程中遇到了困难或需要引导。

当前步骤：{current_step}
用户输入：{user_input}

请提供：
1. 鼓励性的引导
2. 具体的建议
3. 相关的示例

请用友好、鼓励的语气回答。
"""
        
        messages = [
            LLMMessage(
                role="system",
                content=system_prompt.format(
                    current_step=current_step,
                    user_input=user_input
                )
            ),
            LLMMessage(
                role="user",
                content="我需要一些引导和帮助"
            )
        ]
        
        response = await llm.chat(messages, temperature=0.8)
        
        # 更新状态
        state["final_response"] = response.content
        state["messages"].append(
            LLMMessage(role="assistant", content=response.content)
        )
        state["should_continue"] = False
        
        return state
    
    except Exception as e:
        state["error"] = f"引导节点错误: {str(e)}"
        state["should_continue"] = False
        return state
