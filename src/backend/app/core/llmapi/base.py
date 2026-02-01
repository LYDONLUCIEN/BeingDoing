"""
LLM API基础接口
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, AsyncIterator
from pydantic import BaseModel


class LLMMessage(BaseModel):
    """LLM消息模型"""
    role: str  # system, user, assistant
    content: str


class LLMResponse(BaseModel):
    """LLM响应模型"""
    content: str
    model: str
    usage: Optional[Dict] = None  # token使用情况
    finish_reason: Optional[str] = None


class LLMError(Exception):
    """LLM相关错误"""
    pass


class BaseLLMProvider(ABC):
    """LLM Provider基础类"""
    
    def __init__(self, model: str, api_key: Optional[str] = None, **kwargs):
        """
        初始化LLM Provider
        
        Args:
            model: 模型名称
            api_key: API密钥
            **kwargs: 其他配置参数
        """
        self.model = model
        self.api_key = api_key
        self.config = kwargs
    
    @abstractmethod
    async def chat(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """
        发送聊天请求
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            **kwargs: 其他参数
        
        Returns:
            LLM响应
        """
        pass
    
    @abstractmethod
    async def chat_stream(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        发送流式聊天请求
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            **kwargs: 其他参数
        
        Yields:
            流式响应文本片段
        """
        pass
    
    @abstractmethod
    async def count_tokens(self, text: str) -> int:
        """
        计算文本的token数量
        
        Args:
            text: 文本内容
        
        Returns:
            token数量
        """
        pass
    
    @abstractmethod
    async def estimate_cost(
        self,
        messages: List[LLMMessage],
        response_tokens: Optional[int] = None
    ) -> Dict[str, float]:
        """
        估算成本
        
        Args:
            messages: 消息列表
            response_tokens: 响应token数（如果已知）
        
        Returns:
            成本信息字典（包含input_cost, output_cost, total_cost等）
        """
        pass
