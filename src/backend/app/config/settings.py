"""
应用配置
"""
from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path

class Settings(BaseSettings):
    """应用配置类"""
    
    # 应用配置
    APP_ENV: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "your-secret-key-here-change-in-production"
    # JWT 登录态有效期（分钟），如 60=1 小时内免登录，1440=24 小时
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # 超级管理员（用于查看调试日志等，仅后端权限控制使用）
    # 说明：
    # - SUPER_ADMIN_USER_IDS：逗号分隔的 user_id 列表，如 "1,2,3"
    # - SUPER_ADMIN_EMAILS：逗号分隔的邮箱列表，如 "a@example.com,b@example.com"
    SUPER_ADMIN_USER_IDS: Optional[str] = None
    SUPER_ADMIN_EMAILS: Optional[str] = None
    
    # 数据库
    DATABASE_URL: str = "sqlite+aiosqlite:///./app.db"
    
    # 架构配置（与 app.config.architecture 保持一致）
    ARCHITECTURE_MODE: str = "simple"  # simple | full
    
    # LLM配置
    LLM_PROVIDER: str = "openai"  # openai | deepseek
    OPENAI_API_KEY: Optional[str] = None
    LLM_MODEL: str = "gpt-4"
    # DeepSeek（兼容 OpenAI 接口，需设置 base_url）
    DEEPSEEK_API_KEY: Optional[str] = None
    LLM_BASE_URL: Optional[str] = None  # 如 https://api.deepseek.com
    
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
        #env_file = ".env"
        base_dir = Path(__file__).resolve().parents[4]  # 指向 /home/gitclone/BeingDoing
        env_file = base_dir / ".env"
        case_sensitive = True


# 全局配置实例
settings = Settings()
