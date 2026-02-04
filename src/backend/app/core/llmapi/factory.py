"""
LLM Provider工厂
"""
from typing import Optional
from app.core.llmapi.base import BaseLLMProvider
from app.core.llmapi.openai_provider import OpenAIProvider
from app.config.settings import settings


def create_llm_provider(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> BaseLLMProvider:
    """
    创建LLM Provider实例（从 .env / 环境变量读取配置）
    
    Args:
        provider: Provider类型（openai | deepseek），None则从配置读取
        model: 模型名称，None则从配置读取
        api_key: API密钥，None则从配置读取（按provider选择OPENAI_API_KEY或DEEPSEEK_API_KEY）
        base_url: API 地址；openai 默认用 settings.LLM_BASE_URL，deepseek 默认 https://api.deepseek.com
    
    Returns:
        LLM Provider实例
    """
    # 统一默认 provider / model
    provider = (provider or settings.LLM_PROVIDER or "openai").lower()
    model = model or settings.LLM_MODEL or "gpt-4"

    if provider == "openai":
        # OpenAI 默认使用 OPENAI_API_KEY 和可选的 LLM_BASE_URL
        final_api_key = api_key or settings.OPENAI_API_KEY
        final_base_url = base_url or settings.LLM_BASE_URL
        return OpenAIProvider(model=model, api_key=final_api_key, base_url=final_base_url)

    if provider == "deepseek":
        # DeepSeek 永远优先使用 DEEPSEEK_API_KEY，避免误用 OPENAI_API_KEY
        final_api_key = api_key or settings.DEEPSEEK_API_KEY
        final_base_url = base_url or settings.LLM_BASE_URL or "https://api.deepseek.com"
        final_model = model or "deepseek-chat"
        return OpenAIProvider(model=final_model, api_key=final_api_key, base_url=final_base_url)

    raise ValueError(f"不支持的LLM Provider: {provider}")


def get_default_llm_provider() -> BaseLLMProvider:
    """
    获取默认LLM Provider
    
    Returns:
        默认LLM Provider实例
    """
    return create_llm_provider()
