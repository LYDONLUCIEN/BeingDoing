"""
存储 Provider 的统一接口契约

所有 Provider（OSS、S3、Minio、本地）都要实现这个接口。
调用方只面向 BaseStorage，不直接接触具体 SDK。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class StorageObject:
    """上传后返回的元信息"""
    key: str               # 对象 key（如 feedbacks/temp/uuid.png）
    size_bytes: int
    content_type: str
    url: str               # 可访问的 URL（公开 Bucket=持久 URL，私有 Bucket=签名 URL）


class BaseStorage(ABC):
    """对象存储统一接口"""

    @abstractmethod
    async def upload(
        self,
        data: bytes,
        key: str,
        content_type: str,
    ) -> StorageObject:
        """上传字节流。返回 StorageObject。"""
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """删除对象。不存在视为成功（幂等）。"""
        ...

    @abstractmethod
    async def generate_signed_url(self, key: str, expires: int = 3600) -> str:
        """
        生成有时效的签名 URL（私有 Bucket 给前端临时访问用）。
        expires 单位为秒。
        """
        ...

    @abstractmethod
    async def download(self, key: str) -> bytes:
        """下载对象的字节内容。"""
        ...
