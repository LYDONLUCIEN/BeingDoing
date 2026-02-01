"""
LLM Provider工厂
"""
from typing import Optional
from app.core.llmapi.base import BaseLLMProvider
from app.core.llmapi.openai_provider import OpenAIProvider
from app.config.settings import settings
from app.config.architecture import get_arch_config


def create_llm_provider(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None
) -> BaseLLMProvider:
    """
    创建LLM Provider实例
    
    Args:
        provider: Provider类型（openai等），None则从配置读取
        model: 模型名称，None则从配置读取
        api_key: API密钥，None则从配置读取
    
    Returns:
        LLM Provider实例
    """
    # 从配置获取默认值
    if provider is None:
        provider = settings.LLM_PROVIDER or "openai"
    
    if model is None:
        model = settings.LLM_MODEL or "gpt-4"
    
    if api_key is None:
        api_key = settings.OPENAI_API_KEY
    
    # 根据provider类型创建实例
    if provider.lower() == "openai":
        return OpenAIProvider(model=model, api_key=api_key)
    else:
        raise ValueError(f"不支持的LLM Provider: {provider}")


def get_default_llm_provider() -> BaseLLMProvider:
    """
    获取默认LLM Provider
    
    Returns:
        默认LLM Provider实例
    """
    return create_llm_provider()
