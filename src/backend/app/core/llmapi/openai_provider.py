"""
OpenAI LLM Provider实现
"""
import asyncio
from typing import List, Dict, Optional, AsyncIterator
from openai import AsyncOpenAI
from app.core.llmapi.base import BaseLLMProvider, LLMMessage, LLMResponse, LLMError
from app.config.settings import settings
import tiktoken


class OpenAIProvider(BaseLLMProvider):
    """OpenAI Provider实现"""
    
    # 模型价格（每1000 tokens，美元）
    PRICING = {
        "gpt-4": {"input": 0.03, "output": 0.06},
        "gpt-4-turbo": {"input": 0.01, "output": 0.03},
        "gpt-4-turbo-preview": {"input": 0.01, "output": 0.03},
        "gpt-3.5-turbo": {"input": 0.0015, "output": 0.002},
        "gpt-3.5-turbo-16k": {"input": 0.003, "output": 0.004},
    }
    
    def __init__(self, model: str, api_key: Optional[str] = None, base_url: Optional[str] = None, **kwargs):
        """
        初始化OpenAI Provider（也支持兼容接口如 DeepSeek）
        
        Args:
            model: 模型名称（如 gpt-4, deepseek-chat）
            api_key: API密钥
            base_url: 可选，API 地址（如 https://api.deepseek.com）
            **kwargs: 其他配置
        """
        super().__init__(model, api_key, **kwargs)
        key = api_key or settings.OPENAI_API_KEY or ""
        client_kwargs = dict(
            api_key=key,
            timeout=kwargs.get("timeout", 60.0),
            max_retries=kwargs.get("max_retries", 3),
        )
        if base_url:
            client_kwargs["base_url"] = base_url
        self.client = AsyncOpenAI(**client_kwargs)
        self._encoding = None
    
    def _get_encoding(self):
        """获取tiktoken编码器（延迟加载）"""
        if self._encoding is None:
            try:
                # 根据模型选择编码器
                if "gpt-4" in self.model:
                    self._encoding = tiktoken.encoding_for_model("gpt-4")
                else:
                    self._encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
            except KeyError:
                # 默认使用cl100k_base编码
                self._encoding = tiktoken.get_encoding("cl100k_base")
        return self._encoding
    
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
            temperature: 温度参数（0-2）
            max_tokens: 最大token数
            **kwargs: 其他参数（如top_p, frequency_penalty等）
        
        Returns:
            LLM响应
        """
        try:
            # 转换消息格式
            openai_messages = [
                {"role": msg.role, "content": msg.content}
                for msg in messages
            ]
            
            # 调用OpenAI API
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            
            # 解析响应
            choice = response.choices[0]
            usage = response.usage.model_dump() if response.usage else None
            
            return LLMResponse(
                content=choice.message.content or "",
                model=self.model,
                usage=usage,
                finish_reason=choice.finish_reason
            )
        
        except Exception as e:
            # 错误处理
            raise LLMError(f"OpenAI API调用失败: {str(e)}")
    
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
        try:
            # 转换消息格式
            openai_messages = [
                {"role": msg.role, "content": msg.content}
                for msg in messages
            ]
            
            # 调用OpenAI流式API
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                **kwargs
            )
            
            # 流式返回
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        
        except Exception as e:
            raise LLMError(f"OpenAI流式API调用失败: {str(e)}")
    
    async def count_tokens(self, text: str) -> int:
        """
        计算文本的token数量
        
        Args:
            text: 文本内容
        
        Returns:
            token数量
        """
        encoding = self._get_encoding()
        return len(encoding.encode(text))
    
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
            成本信息字典
        """
        # 获取模型价格
        pricing = self.PRICING.get(self.model, {"input": 0.0, "output": 0.0})
        
        # 计算输入token数
        input_text = "\n".join([f"{msg.role}: {msg.content}" for msg in messages])
        input_tokens = await self.count_tokens(input_text)
        
        # 计算输出token数
        if response_tokens is None:
            # 如果没有提供，估算为输入token的50%
            output_tokens = int(input_tokens * 0.5)
        else:
            output_tokens = response_tokens
        
        # 计算成本（美元）
        input_cost = (input_tokens / 1000) * pricing["input"]
        output_cost = (output_tokens / 1000) * pricing["output"]
        total_cost = input_cost + output_cost
        
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "input_cost": input_cost,
            "output_cost": output_cost,
            "total_cost": total_cost,
            "currency": "USD"
        }


