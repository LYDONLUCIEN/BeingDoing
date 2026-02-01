"""
工具基类
"""
from abc import ABC, abstractmethod
from typing import Dict, Any
from app.core.agent.state import AgentState


class BaseAgentTool(ABC):
    """智能体工具基类"""
    
    def __init__(self, name: str, description: str):
        """
        初始化工具
        
        Args:
            name: 工具名称
            description: 工具描述
        """
        self.name = name
        self.description = description
    
    @abstractmethod
    async def execute(
        self,
        input_data: Dict[str, Any],
        state: AgentState
    ) -> Dict[str, Any]:
        """
        执行工具
        
        Args:
            input_data: 输入数据
            state: 当前状态
        
        Returns:
            工具执行结果
        """
        pass
    
    def get_schema(self) -> Dict[str, Any]:
        """
        获取工具schema（用于LLM理解工具）
        
        Returns:
            工具schema字典
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self._get_parameters()
        }
    
    @abstractmethod
    def _get_parameters(self) -> Dict[str, Any]:
        """
        获取工具参数定义
        
        Returns:
            参数定义字典
        """
        pass
