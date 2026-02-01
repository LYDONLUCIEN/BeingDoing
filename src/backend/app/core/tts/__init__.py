"""
TTS (Text-to-Speech) API模块
"""
from app.core.tts.base import BaseTTSProvider, TTSResponse, TTSError
from app.core.tts.openai_tts_provider import OpenAITTSProvider
from app.core.tts.factory import create_tts_provider, get_default_tts_provider

__all__ = [
    "BaseTTSProvider",
    "TTSResponse",
    "TTSError",
    "OpenAITTSProvider",
    "create_tts_provider",
    "get_default_tts_provider",
]
