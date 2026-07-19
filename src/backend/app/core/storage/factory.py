"""
Storage 工厂

单例缓存，避免每次请求都重建 OSS Auth/Bucket。
若 OSS 未配置（开发环境），返回 None，调用方需处理。
"""
from functools import lru_cache
from typing import Optional

from app.config.settings import settings
from app.core.storage.base import BaseStorage
from app.core.storage.oss_provider import OSSProvider


@lru_cache(maxsize=1)
def get_storage() -> Optional[BaseStorage]:
    """
    返回全局 Storage 实例。

    若 OSS_ACCESS_KEY_ID 等关键配置缺失，返回 None
    （开发环境可能不配 OSS，调用方判断 None 后优雅降级）。
    """
    if not settings.OSS_ACCESS_KEY_ID or not settings.OSS_BUCKET_NAME:
        return None
    return OSSProvider.from_settings()
