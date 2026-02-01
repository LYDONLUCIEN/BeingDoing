"""
应用配置
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """应用配置类"""
    
    # 应用配置
    APP_ENV: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "your-secret-key-here-change-in-production"
    
    # 数据库
    DATABASE_URL: str = "sqlite+aiosqlite:///./app.db"
    
    # LLM配置
    LLM_PROVIDER: str = "openai"
    OPENAI_API_KEY: Optional[str] = None
    LLM_MODEL: str = "gpt-4"
    
    # ASR配置
    ASR_PROVIDER: str = "openai"
    OPENAI_WHISPER_API_KEY: Optional[str] = None
    
    # TTS配置
    TTS_PROVIDER: str = "openai"
    OPENAI_TTS_API_KEY: Optional[str] = None
    
    # 语音功能
    AUDIO_MODE: bool = False
    
    # ASR配置
    ASR_PROVIDER: str = "openai"
    OPENAI_WHISPER_API_KEY: Optional[str] = None
    
    # TTS配置
    TTS_PROVIDER: str = "openai"
    OPENAI_TTS_API_KEY: Optional[str] = None
    
    # 引导策略
    GUIDE_IDLE_TIMEOUT: int = 600  # 10分钟（秒）
    GUIDE_QUIET_TIMEOUT: int = 900  # 15分钟（秒）
    GUIDE_SHORT_ANSWER_THRESHOLD: int = 20  # 字数阈值
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# 全局配置实例
settings = Settings()
