"""
阿里云 OSS Provider

基于 oss2 SDK 实现 BaseStorage 接口。
私有 Bucket 模式：所有读访问通过签名 URL。
"""
import uuid
from typing import Optional

import oss2
from oss2.models import PutObjectResult

from app.config.settings import settings
from app.core.storage.base import BaseStorage, StorageObject


class OSSProvider(BaseStorage):
    """阿里云 OSS 实现"""

    def __init__(
        self,
        access_key_id: str,
        access_key_secret: str,
        endpoint: str,
        bucket_name: str,
        public_base_url: Optional[str] = None,
    ):
        if not all([access_key_id, access_key_secret, endpoint, bucket_name]):
            raise ValueError(
                "OSS 配置不完整：需要 OSS_ACCESS_KEY_ID / OSS_ACCESS_KEY_SECRET / "
                "OSS_ENDPOINT / OSS_BUCKET_NAME"
            )
        self._auth = oss2.Auth(access_key_id, access_key_secret)
        self._endpoint = endpoint.rstrip("/")
        self._bucket_name = bucket_name
        self._bucket = oss2.Bucket(self._auth, self._endpoint, bucket_name)
        # 公开 base url（绑了 CDN/域名时用），否则用 OSS 默认域名
        self._public_base_url = (
            public_base_url.rstrip("/") if public_base_url else None
        )

    @classmethod
    def from_settings(cls) -> "OSSProvider":
        """从全局 settings 构造（推荐入口）"""
        return cls(
            access_key_id=settings.OSS_ACCESS_KEY_ID,
            access_key_secret=settings.OSS_ACCESS_KEY_SECRET,
            endpoint=settings.OSS_ENDPOINT,
            bucket_name=settings.OSS_BUCKET_NAME,
            public_base_url=settings.OSS_PUBLIC_BASE_URL,
        )

    def _apply_public_base_url(self, url: str) -> str:
        """如果配了 public_base_url，把签名 URL 的域名替换掉"""
        if not self._public_base_url:
            return url
        # OSS 默认域名形如 https://bucket.endpoint/...
        default_prefix = f"https://{self._bucket_name}.{self._endpoint}/"
        if url.startswith(default_prefix):
            return url.replace(default_prefix, self._public_base_url + "/", 1)
        return url

    async def upload(
        self,
        data: bytes,
        key: str,
        content_type: str,
    ) -> StorageObject:
        # OSS put_object 是同步接口；bytes 量小（截图 ≤2MB），
        # 包在 asyncio thread pool 里太重，直接同步调用即可。
        # 真要做异步，可换 oss2 的异步包装或 aiooss2，但当前规模没必要。
        headers = {"Content-Type": content_type}
        result: PutObjectResult = self._bucket.put_object(key, data, headers=headers)
        return StorageObject(
            key=key,
            size_bytes=len(data),
            content_type=content_type,
            # 上传后立即返回一个签名 URL，方便调用方拿到给前端预览
            url=self._apply_public_base_url(
                self._bucket.sign_url(
                    "GET", key, settings.OSS_SIGNED_URL_EXPIRES
                )
            ),
        )

    async def delete(self, key: str) -> None:
        try:
            self._bucket.delete_object(key)
        except oss2.exceptions.NoSuchKey:
            # 不存在视为成功（幂等）
            pass

    async def generate_signed_url(self, key: str, expires: int = 3600) -> str:
        url = self._bucket.sign_url("GET", key, expires)
        return self._apply_public_base_url(url)

    async def download(self, key: str) -> bytes:
        result = self._bucket.get_object(key)
        return result.read()


def generate_object_key(prefix: str, ext: str) -> str:
    """
    生成 OSS 对象 key（统一命名规范）

    例：generate_object_key("feedbacks/temp", "png")
        → "feedbacks/temp/2026/07/16/uuid.png"
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    date_part = now.strftime("%Y/%m/%d")
    unique = uuid.uuid4().hex
    ext_clean = ext.lstrip(".").lower()
    return f"{prefix.rstrip('/')}/{date_part}/{unique}.{ext_clean}"
