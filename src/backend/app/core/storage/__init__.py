"""
对象存储抽象层

对外暴露 `get_storage()` 返回统一接口 BaseStorage。
首期实现：OSSProvider（阿里云 OSS）。

未来要支持 S3/Minio/本地磁盘，新增 Provider 并切换即可。
"""
from app.core.storage.base import BaseStorage, StorageObject
from app.core.storage.factory import get_storage

__all__ = ["BaseStorage", "StorageObject", "get_storage"]
