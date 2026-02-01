"""
配置模块
"""
from app.config.settings import settings
from app.config.architecture import get_arch_config, is_simple_mode, ARCHITECTURE_MODE
from app.config.guide_config import GuideConfig
from app.config.audio_config import AudioConfig

__all__ = [
    "settings",
    "get_arch_config",
    "is_simple_mode",
    "ARCHITECTURE_MODE",
    "GuideConfig",
    "AudioConfig",
]
