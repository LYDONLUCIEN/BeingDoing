"""
缓存配置 - Graph缓存和上下文记忆的配置参数
"""
from pydantic_settings import BaseSettings
from pathlib import Path


class CacheSettings(BaseSettings):
    """缓存配置类"""

    # ===== Graph 缓存配置 =====
    # 是否启用 Graph 缓存（默认启用）
    GRAPH_CACHE_ENABLED: bool = True

    # Graph 缓存过期时间（分钟），默认 15 分钟
    GRAPH_CACHE_TTL_MINUTES: int = 15

    # 最大缓存 session 数量，默认 20
    GRAPH_CACHE_MAX_SIZE: int = 20

    # Graph 缓存清理间隔（分钟），默认 5 分钟
    GRAPH_CACHE_CLEANUP_INTERVAL_MINUTES: int = 5

    # ===== 上下文记忆配置 =====
    # 是否启用完整的上下文加载（默认启用）
    FULL_CONTEXT_ENABLED: bool = True

    # 上下文压缩阈值（对话轮数），超过后开始压缩
    CONTEXT_COMPRESS_AFTER_ROUNDS: int = 5

    # 压缩后保留的最新消息数
    CONTEXT_KEEP_LATEST_MESSAGES: int = 3

    # 上下文最大 token 预算（用于判断是否需要进一步压缩）
    CONTEXT_MAX_TOKEN_BUDGET: int = 8000

    # ===== 新的对话分类配置 =====
    # all_flow.json: 完整对话（原文 + AI 思考过程）
    # main_flow.json: 用户可见的咨询对话
    # note.json: AI 总结的结论性内容
    CONVERSATION_DIR: str = "data/conversations"
    ALL_FLOW_FILENAME: str = "all_flow.json"
    MAIN_FLOW_FILENAME: str = "main_flow.json"
    NOTE_FILENAME: str = "note.json"

    class Config:
        env_file = ".env"
        base_dir = Path(__file__).resolve().parents[2]
        env_file = base_dir / ".env"
        case_sensitive = True


# 全局缓存配置实例
cache_settings = CacheSettings()
