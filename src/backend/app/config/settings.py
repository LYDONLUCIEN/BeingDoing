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
    # VIP1 = 基础（DeepSeek），VIP2 = 高级
    # P-A 起（ADR-0008）：试用码 vip_level=1、完整码 vip_level=2，两档均配置为 DeepSeek
    LLM_VIP1_PROVIDER: str = "deepseek"
    LLM_VIP1_MODEL: Optional[str] = None  # 默认 deepseek-v4-pro
    LLM_VIP2_PROVIDER: str = "deepseek"  # deepseek | kimi | qwen（当前默认 deepseek）
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

    # Rumination 版本切换：'v3'（强制 v3）| 'v4'（强制 v4）| 'ab'（按比例随机，默认）
    RUMINATION_VERSION_MODE: str = "ab"
    # AB 模式下分配到 v4 的概率（0.0~1.0，默认 0.5）
    RUMINATION_AB_V4_RATIO: float = 0.5

    # 全局思维链开关：控制 v4-pro 等模型是否开启 thinking 模式（默认关，提升响应速度）
    LLM_THINKING_ENABLED: bool = False

    # LLM 模型配置加密密钥（admin 后台存的 api_key 用 Fernet 加密）
    # 为空时回退 SECRET_KEY；轮换会让历史密文不可解密，需重新填写 api_key
    MODEL_CONFIG_ENC_KEY: Optional[str] = None

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

    # 退信扫描（IMAP）配置——用于群发邮件后识别不可达邮箱
    # 默认复用 SMTP 账号；163 邮箱需在后台单独开启 IMAP 服务并生成授权码
    BOUNCE_IMAP_HOST: Optional[str] = None       # 例：imap.163.com
    BOUNCE_IMAP_PORT: int = 993
    BOUNCE_IMAP_USER: Optional[str] = None       # 不填则回退 SMTP_USER
    BOUNCE_IMAP_PASS: Optional[str] = None       # 不填则回退 SMTP_PASS
    # 定时扫描 cron（本地时间，5 字段）
    BOUNCE_SCAN_CRON: str = "0 3 * * *"          # 默认每日 03:00
    BOUNCE_SCAN_LOOKBACK_HOURS: int = 48          # 每次扫描回看窗口，watermark 丢失时兜底
    BOUNCE_SCAN_SOFT_THRESHOLD: int = 3           # soft 累计次数阈值，达到升级为 blocked

    # 反馈附件孤儿清理 cron（本地时间，5 字段）
    # 用户上传截图后未提交反馈（feedback_id IS NULL）超 N 天的附件，DB 记录 + OSS 对象都删
    FEEDBACK_ORPHAN_CLEANUP_CRON: str = "0 4 * * *"  # 默认每日 04:00
    FEEDBACK_ORPHAN_CLEANUP_DAYS: int = 7             # 超过 7 天未关联反馈视为孤儿

    # 反馈超时扫描 cron（本地时间，5 字段）
    # 扫描 due_at 已过且未完结的反馈，站内信提醒所有 super_admin（当天幂等）
    FEEDBACK_OVERDUE_SCAN_CRON: str = "0 9 * * *"  # 默认每日 09:00

    # ========== 支付模块（计划见 tasks/payment-module-plan.md）==========
    # 旧商品：全程激活码（单一 SKU，已下架；配置保留供历史订单展示）
    ACTIVATION_CODE_PRICE: int = 9900  # 99 元
    ACTIVATION_CODE_TTL_DAYS: int = 180
    # 套餐商品化（P-B，ADR-0008，金额单位：分）
    QUARTERLY_PRICE: int = 6900  # 单人激活码 69 元
    ANNUAL_PRICE: int = 9900  # 三人包 99 元
    RENEWAL_QUARTERLY_PRICE: int = 2300  # 季度码延期 23 元
    RENEWAL_ANNUAL_PRICE: int = 3300  # 年度码延期 33 元
    CONSULTATION_PRICE: int = 29800  # 报告解读咨询 298 元
    QUARTERLY_DAYS: int = 90  # 季度时长（天）
    ANNUAL_DAYS: int = 365  # 年度时长（天）
    # 折扣券：券池空时邮件发券按此面额（分）自动创建
    DEFAULT_COUPON_AMOUNT: int = 5000  # 50 元
    # 订单：pending 超时关单时间（分钟）
    ORDER_TIMEOUT_MINUTES: int = 30
    # 会员（P3 预留，本期不开放）
    MEMBERSHIP_ENABLED: bool = False
    # 账户注销：冷存保留天数（float，支持 0.01 这种小数值；0=注销时立即物理清除）
    ACCOUNT_DELETION_RETENTION_DAYS: float = 30.0
    MEMBERSHIP_MONTHLY_PRICE: int = 1500  # 15 元
    MEMBERSHIP_LIFETIME_PRICE: int = 29900  # 299 元
    MEMBER_DISCOUNT_PERCENT: int = 85  # 8.5 折

    # ========== 支付渠道（P2 预留，未配置时支付接口不可用）==========
    # 微信支付 V3
    WECHAT_MCH_ID: str = ""
    WECHAT_APP_ID: str = ""
    WECHAT_API_V3_KEY: str = ""
    WECHAT_PRIVATE_KEY_PATH: str = ""
    WECHAT_CERT_SERIAL_NO: str = ""
    WECHAT_NOTIFY_URL: str = ""
    # 支付宝
    ALIPAY_APP_ID: str = ""
    ALIPAY_PRIVATE_KEY_PATH: str = ""
    ALIPAY_PUBLIC_KEY_PATH: str = ""
    ALIPAY_NOTIFY_URL: str = ""
    ALIPAY_RETURN_URL: str = ""  # 电脑网站支付同步回跳地址（前端支付结果页）
    # 网关：正式 https://openapi.alipay.com/gateway.do；沙箱切 openapi-sandbox
    ALIPAY_GATEWAY: str = "https://openapi.alipay.com/gateway.do"

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

    # ========== 对象存储（阿里云 OSS，用于反馈截图等）==========
    OSS_ACCESS_KEY_ID: Optional[str] = None
    OSS_ACCESS_KEY_SECRET: Optional[str] = None
    OSS_ENDPOINT: Optional[str] = None  # 如 oss-cn-shanghai.aliyuncs.com
    OSS_BUCKET_NAME: Optional[str] = None
    OSS_PUBLIC_BASE_URL: Optional[str] = None  # 可选，绑定 CDN/域名后填
    # 签名 URL 有效期（秒），用户查看截图时用
    OSS_SIGNED_URL_EXPIRES: int = 3600

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
