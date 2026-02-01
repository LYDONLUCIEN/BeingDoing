"""
推理节点
"""
from typing import Dict
from app.core.agent.state import AgentState
from app.core.llmapi import get_default_llm_provider, LLMMessage


async def reasoning_node(state: AgentState) -> AgentState:
    """
    推理节点：分析用户输入，决定下一步行动
    
    Args:
        state: 当前状态
    
    Returns:
        更新后的状态
    """
    try:
        llm = get_default_llm_provider()
        
        # 构建推理提示词
        system_prompt = """你是一个专业的职业规划助手。你的任务是帮助用户探索他们的价值观、才能和兴趣。

当前步骤：{current_step}
用户输入：{user_input}
已使用的工具：{tools_used}

请分析用户输入，决定下一步应该：
1. 使用工具（如search_tool, guide_tool等）
2. 直接回答用户问题
3. 引导用户继续探索

请以JSON格式返回：
{{
    "action": "use_tool" | "respond" | "guide",
    "tool_name": "工具名称（如果action是use_tool）",
    "tool_input": {{"query": "查询内容"}},
    "response": "直接回答（如果action是respond）",
    "reasoning": "你的推理过程"
}}
"""
        
        # 构建消息
        messages = [
            LLMMessage(
                role="system",
                content=system_prompt.format(
                    current_step=state.get("current_step", "unknown"),
                    user_input=state.get("user_input", ""),
                    tools_used=", ".join(state.get("tools_used", []))
                )
            ),
            LLMMessage(
                role="user",
                content=state.get("user_input", "")
            )
        ]
        
        # 调用LLM
        response = await llm.chat(messages, temperature=0.7)
        
        # 解析响应（简化版，实际应该解析JSON）
        import json
        try:
            reasoning_result = json.loads(response.content)
        except:
            # 如果解析失败，默认直接回答
            reasoning_result = {
                "action": "respond",
                "response": response.content,
                "reasoning": "LLM直接生成回答"
            }
        
        # 更新状态
        state["messages"].append(
            LLMMessage(role="assistant", content=response.content)
        )
        
        # 存储推理结果到context
        state["context"]["reasoning"] = reasoning_result
        
        return state
    
    except Exception as e:
        state["error"] = f"推理节点错误: {str(e)}"
        state["should_continue"] = False
        return state
