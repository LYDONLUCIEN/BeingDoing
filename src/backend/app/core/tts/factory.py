"""
TTS Provider工厂
"""
from typing import Optional
from app.core.tts.base import BaseTTSProvider
from app.core.tts.openai_tts_provider import OpenAITTSProvider
from app.config.settings import settings
from app.config.audio_config import get_audio_config


def create_tts_provider(
    provider: Optional[str] = None,
    api_key: Optional[str] = None
) -> BaseTTSProvider:
    """
    创建TTS Provider实例
    
    Args:
        provider: Provider类型（openai等），None则从配置读取
        api_key: API密钥，None则从配置读取
    
    Returns:
        TTS Provider实例
    """
    # 检查音频模式
    audio_config = get_audio_config()
    if not audio_config.get("audio_mode", False):
        raise ValueError("音频模式未启用，无法创建TTS Provider")
    
    # 从配置获取默认值
    if provider is None:
        provider = settings.TTS_PROVIDER or "openai"
    
    if api_key is None:
        api_key = settings.OPENAI_TTS_API_KEY or settings.OPENAI_API_KEY
    
    # 根据provider类型创建实例
    if provider.lower() == "openai":
        return OpenAITTSProvider(api_key=api_key)
    else:
        raise ValueError(f"不支持的TTS Provider: {provider}")


def get_default_tts_provider() -> Optional[BaseTTSProvider]:
    """
    获取默认TTS Provider（如果音频模式启用）
    
    Returns:
        默认TTS Provider实例，如果音频模式未启用则返回None
    """
    try:
        return create_tts_provider()
    except ValueError:
        return None
