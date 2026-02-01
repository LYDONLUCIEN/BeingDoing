"""
ASR Provider工厂
"""
from typing import Optional
from app.core.asr.base import BaseASRProvider
from app.core.asr.openai_whisper_provider import OpenAIWhisperProvider
from app.config.settings import settings
from app.config.audio_config import get_audio_config


def create_asr_provider(
    provider: Optional[str] = None,
    api_key: Optional[str] = None
) -> BaseASRProvider:
    """
    创建ASR Provider实例
    
    Args:
        provider: Provider类型（openai等），None则从配置读取
        api_key: API密钥，None则从配置读取
    
    Returns:
        ASR Provider实例
    """
    # 检查音频模式
    audio_config = get_audio_config()
    if not audio_config.get("audio_mode", False):
        raise ValueError("音频模式未启用，无法创建ASR Provider")
    
    # 从配置获取默认值
    if provider is None:
        provider = settings.ASR_PROVIDER or "openai"
    
    if api_key is None:
        api_key = settings.OPENAI_WHISPER_API_KEY or settings.OPENAI_API_KEY
    
    # 根据provider类型创建实例
    if provider.lower() == "openai":
        return OpenAIWhisperProvider(api_key=api_key)
    else:
        raise ValueError(f"不支持的ASR Provider: {provider}")


def get_default_asr_provider() -> Optional[BaseASRProvider]:
    """
    获取默认ASR Provider（如果音频模式启用）
    
    Returns:
        默认ASR Provider实例，如果音频模式未启用则返回None
    """
    try:
        return create_asr_provider()
    except ValueError:
        return None
