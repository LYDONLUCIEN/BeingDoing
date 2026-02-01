"""
架构配置
"""
import os
from typing import Dict, Literal

# 架构模式
ARCHITECTURE_MODE: Literal["simple", "full"] = os.getenv("ARCHITECTURE_MODE", "simple")

# 简化架构配置（当前实现）
SIMPLE_ARCH: Dict[str, any] = {
    "use_gateway": False,           # 不使用网关
    "use_vector_db": False,         # 不使用向量数据库
    "use_redis": False,             # 不使用Redis
    "use_celery": False,            # 不使用Celery
    "static_files": "fastapi",      # FastAPI内置静态文件服务
    "vector_store": "memory",       # 内存向量存储
    "cache": "memory",             # 内存缓存
    "database": "sqlite"            # SQLite数据库
}

# 完整架构配置（保留接口，暂不实现）
FULL_ARCH: Dict[str, any] = {
    "use_gateway": True,            # 使用Nginx网关 [保留接口]
    "use_vector_db": True,          # 使用Chroma/FAISS [保留接口]
    "use_redis": True,              # 使用Redis缓存 [保留接口]
    "use_celery": True,             # 使用Celery任务队列 [保留接口]
    "static_files": "nginx",        # Nginx静态文件服务 [保留接口]
    "vector_store": "chroma",       # Chroma向量数据库 [保留接口]
    "cache": "redis",               # Redis缓存 [保留接口]
    "database": "postgresql"        # PostgreSQL数据库 [保留接口]
}


def get_arch_config() -> Dict[str, any]:
    """获取当前架构配置"""
    if ARCHITECTURE_MODE == "full":
        return FULL_ARCH
    return SIMPLE_ARCH


def is_simple_mode() -> bool:
    """判断是否为简化架构"""
    return ARCHITECTURE_MODE == "simple"
