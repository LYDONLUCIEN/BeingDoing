"""
语音配置
"""
from app.config.settings import settings


class AudioConfig:
    """语音配置类"""
    
    # 语音功能开关
    AUDIO_MODE: bool = settings.AUDIO_MODE
    
    # ASR提供商
    ASR_PROVIDER: str = settings.ASR_PROVIDER
    
    # TTS提供商
    TTS_PROVIDER: str = settings.TTS_PROVIDER
    
    @classmethod
    def is_audio_enabled(cls) -> bool:
        """检查语音功能是否启用"""
        return cls.AUDIO_MODE
