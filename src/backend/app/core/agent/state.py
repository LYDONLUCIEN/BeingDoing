"""
智能体状态定义
"""
from typing import TypedDict, List, Dict, Optional, Any
from app.core.llmapi.base import LLMMessage


class AgentState(TypedDict):
    """智能体状态"""
    # 消息历史
    messages: List[LLMMessage]
    
    # 当前上下文
    context: Dict[str, Any]
    
    # 当前步骤
    current_step: str  # values_exploration, strengths_exploration, interests_exploration, combination, refinement
    
    # 已使用的工具
    tools_used: List[str]
    
    # 工具调用结果
    tool_results: List[Dict[str, Any]]
    
    # 用户输入
    user_input: Optional[str]
    
    # 用户ID和会话ID
    user_id: Optional[str]
    session_id: Optional[str]
    
    # 迭代计数（防止无限循环）
    iteration_count: int
    
    # 是否应该继续
    should_continue: bool
    
    # 最终响应
    final_response: Optional[str]
    
    # 错误信息
    error: Optional[str]
