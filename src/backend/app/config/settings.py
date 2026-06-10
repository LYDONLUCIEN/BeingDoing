"""
应用配置
"""
from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path
from app.utils.data_paths import get_conversation_dir

class Settings(BaseSettings):
    """应用配置类"""
    
    # 应用配置
    APP_ENV: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "your-secret-key-here-change-in-production"
    # JWT access token 有效期（分钟）
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    # refresh token 有效期（天）
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    # refresh token 轮换（每次 refresh 后签发新 refresh，并废弃旧 refresh）
    REFRESH_TOKEN_ROTATE: bool = True
    # 可选：refresh token 独立密钥（不配置时回退 SECRET_KEY）
    REFRESH_TOKEN_SECRET_KEY: Optional[str] = None
    # refresh cookie 配置（HttpOnly）
    REFRESH_COOKIE_NAME: str = "bd_refresh_token"
    REFRESH_COOKIE_DOMAIN: Optional[str] = None
    REFRESH_COOKIE_PATH: str = "/api/v1/auth"
    REFRESH_COOKIE_SAMESITE: str = "lax"  # lax | strict | none
    # 本地 http 调试建议 False；生产 https 必须 True
    REFRESH_COOKIE_SECURE: bool = False

    # 超级管理员（用于查看调试日志等，仅后端权限控制使用）
    # 说明：
    # - SUPER_ADMIN_USER_IDS：逗号分隔的 user_id 列表，如 "1,2,3"
    # - SUPER_ADMIN_EMAILS：逗号分隔的邮箱列表，如 "a@example.com,b@example.com"
    SUPER_ADMIN_USER_IDS: Optional[str] = None
    SUPER_ADMIN_EMAILS: Optional[str] = None

    # Debug 模式：仅当 DEBUG_MODE=true 且当前用户在 SUPER_ADMIN_USER_IDS/SUPER_ADMIN_EMAILS 内时生效
    # 启用后：可载入过期激活码、解锁全部探索阶段、直接查看报告
    DEBUG_MODE: bool = False

    # Admin 调试特权总开关（生产建议关闭）
    # - 关闭时：常驻工作区、SBX 沙箱等管理员调试特权全部不可用
    # - 开启时：再由各子开关控制具体能力
    ADMIN_DEBUG_POLICY_ENABLED: bool = False
    ADMIN_DEBUG_WORKSPACE_ENABLED: bool = True
    ADMIN_SANDBOX_ENABLED: bool = True
    
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

    # API 池与 VIP 模型（按 vip_level 选择）
    # VIP1 = 基础（DeepSeek），VIP2 = 高级（Kimi/Qwen）
    LLM_VIP1_PROVIDER: str = "deepseek"
    LLM_VIP1_MODEL: Optional[str] = None  # 默认 deepseek-v4-pro
    LLM_VIP2_PROVIDER: str = "kimi"  # kimi | qwen
    KIMI_API_KEY: Optional[str] = None
    KIMI_BASE_URL: Optional[str] = "https://api.moonshot.cn/v1"
    KIMI_MODEL: str = "moonshot-v1-8k"
    QWEN_API_KEY: Optional[str] = None
    QWEN_BASE_URL: Optional[str] = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_MODEL: str = "qwen-plus"

    # 并发限制：同时进行的 LLM 调用数（0=不限制）
    LLM_MAX_CONCURRENT: int = 0

    # 子步 3：AI 回复后若假设已完整则自动 cursor+1（默认关，避免抢跑跳行）
    RUMINATION_STEP3_AUTO_UNLOCK_ENABLED: bool = False

    # 全局思维链开关：控制 v4-pro 等模型是否开启 thinking 模式（默认关，提升响应速度）
    LLM_THINKING_ENABLED: bool = False

    # SMTP 邮件配置（忘记密码验证码）
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 465
    SMTP_USER: Optional[str] = None
    SMTP_PASS: Optional[str] = None
    SMTP_FROM_EMAIL: Optional[str] = None
    SMTP_FROM_NAME: str = "xunlu"
    SMTP_USE_SSL: bool = True
    SMTP_USE_TLS: bool = False
    SMTP_TIMEOUT_SECONDS: int = 20

    # 前端地址（用于邮箱验证链接）
    FRONTEND_URL: str = "http://localhost:3000"
    
    # ASR配置
    ASR_PROVIDER: str = "openai"
    OPENAI_WHISPER_API_KEY: Optional[str] = None
    
    # TTS配置
    TTS_PROVIDER: str = "openai"
    OPENAI_TTS_API_KEY: Optional[str] = None
    
    # 语音功能
    AUDIO_MODE: bool = False
    
    # 引导策略
    GUIDE_IDLE_TIMEOUT: int = 600  # 10分钟（秒）
    GUIDE_QUIET_TIMEOUT: int = 900  # 15分钟（秒）
    GUIDE_SHORT_ANSWER_THRESHOLD: int = 20  # 字数阈值

    # ========== Graph 缓存配置 ==========
    GRAPH_CACHE_ENABLED: bool = True
    GRAPH_CACHE_TTL_MINUTES: int = 15
    GRAPH_CACHE_MAX_SIZE: int = 20
    GRAPH_CACHE_CLEANUP_INTERVAL_MINUTES: int = 5

    # ========== 完整上下文加载配置 ==========
    FULL_CONTEXT_ENABLED: bool = True
    CONTEXT_COMPRESS_AFTER_ROUNDS: int = 5
    CONTEXT_KEEP_LATEST_MESSAGES: int = 3
    CONTEXT_MAX_TOKEN_BUDGET: int = 8000

    # 对话文件存储目录（项目根 data/conversations）
    CONVERSATION_DIR: str = str(get_conversation_dir())

    # basic_info 多源合并策略（迁移时用）：A=最新覆盖 B=并集(非空优先) C=A∩B 交集
    BASIC_INFO_MERGE_STRATEGY: str = "A"

    class Config:
        #env_file = ".env"
        base_dir = Path(__file__).resolve().parents[4]  # 指向 /home/gitclone/BeingDoing
        env_file = base_dir / ".env"
        case_sensitive = True
        extra = "ignore"  # 忽略 .env 中未声明的变量（如 NEXT_PUBLIC_API_URL 供前端使用）


# 全局配置实例
settings = Settings()
