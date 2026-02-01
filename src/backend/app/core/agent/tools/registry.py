"""
工具注册表
"""
from typing import Dict, Optional
from app.core.agent.tools.base import BaseAgentTool


class ToolRegistry:
    """工具注册表（单例）"""
    
    _instance = None
    _tools: Dict[str, BaseAgentTool] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def register(cls, tool: BaseAgentTool):
        """
        注册工具
        
        Args:
            tool: 工具实例
        """
        cls._tools[tool.name] = tool
    
    @classmethod
    def get_tool(cls, name: str) -> Optional[BaseAgentTool]:
        """
        获取工具
        
        Args:
            name: 工具名称
        
        Returns:
            工具实例，如果不存在则返回None
        """
        return cls._tools.get(name)
    
    @classmethod
    def list_tools(cls) -> Dict[str, BaseAgentTool]:
        """
        列出所有工具
        
        Returns:
            工具字典
        """
        return cls._tools.copy()
    
    @classmethod
    def clear(cls):
        """清空所有工具（主要用于测试）"""
        cls._tools.clear()
