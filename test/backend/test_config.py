"""
配置模块测试

运行方式：
1. 从项目根目录：pytest test/backend/test_config.py -v
2. 设置PYTHONPATH：$env:PYTHONPATH="src/backend"; pytest test/backend/test_config.py -v
"""
import pytest
from app.config.settings import Settings
from app.config.architecture import get_arch_config, is_simple_mode, ARCHITECTURE_MODE
from app.config.guide_config import GuideConfig
from app.config.audio_config import AudioConfig


def test_settings():
    """测试配置读取"""
    settings = Settings()
    assert settings.APP_ENV is not None
    assert settings.DATABASE_URL is not None


def test_architecture_config():
    """测试架构配置"""
    config = get_arch_config()
    assert "use_gateway" in config
    assert "database" in config
    
    # 当前应该使用简化架构
    assert is_simple_mode() == (ARCHITECTURE_MODE == "simple")


def test_guide_config():
    """测试引导配置"""
    assert GuideConfig.IDLE_TIMEOUT > 0
    assert GuideConfig.QUIET_TIMEOUT > GuideConfig.IDLE_TIMEOUT
    assert GuideConfig.SHORT_ANSWER_THRESHOLD > 0
    
    # 测试超时时间获取
    normal_timeout = GuideConfig.get_timeout(GuideConfig.PREFERENCE_NORMAL)
    quiet_timeout = GuideConfig.get_timeout(GuideConfig.PREFERENCE_QUIET)
    assert quiet_timeout > normal_timeout


def test_audio_config():
    """测试语音配置"""
    assert isinstance(AudioConfig.AUDIO_MODE, bool)
    assert AudioConfig.ASR_PROVIDER is not None
    assert AudioConfig.TTS_PROVIDER is not None
