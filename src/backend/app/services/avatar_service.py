"""
用户头像服务

存储口径（2026-09-17 决策，详见 alembic/versions/021_user_avatar.py）：
- 图片本体：OSS 私有桶，确定性 key = avatars/{user_id}（无扩展名），
  重复上传同 key 覆盖，零孤儿文件，无需清理 job
- DB users.avatar_url：存后端代理 URL（/api/v1/users/{user_id}/avatar?v=<上传时间戳>），
  永久有效；?v= 时间戳用于换头像后击穿浏览器缓存
- 读取：GET /users/{user_id}/avatar 后端代理转发（公开端点，
  CSS background 不带鉴权头也能加载），内容类型由 magic bytes 嗅探
- 压缩（2026-09-17 起）：上传时服务端统一压缩——EXIF 方向校正 → 中心裁剪正方形
  → 缩放到 256px（只缩不放）→ WebP q85，入库体积一般 <50KB，代理加载快
"""
import time
from io import BytesIO
from typing import Tuple

from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage.factory import get_storage
from app.models.user import User

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_AVATAR_BYTES = 5 * 1024 * 1024  # 5MB（原图上限，压缩后远小于此）
AVATAR_SIZE = 256  # 输出边长（正方形，只缩不放）
AVATAR_WEBP_QUALITY = 85


def avatar_oss_key(user_id: str) -> str:
    """头像 OSS key：确定性命名，重复上传同 key 覆盖"""
    return f"avatars/{user_id}"


def compress_avatar(file_data: bytes) -> bytes:
    """
    服务端压缩头像：EXIF 方向校正 → 中心裁剪正方形 → 缩放到 256px（只缩不放）→ WebP q85

    Raises:
        ValueError: 图片无法解析
    """
    try:
        img = Image.open(BytesIO(file_data))
        img = ImageOps.exif_transpose(img)  # 按 EXIF 校正方向（手机照片常见旋转）
        img.load()
    except Exception:
        raise ValueError("无法识别的图片文件")

    # 中心裁剪为正方形（头像展示均为圆形，方形底图即可）
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))

    # 缩放到目标边长（只缩不放，小图保持原尺寸）
    if side > AVATAR_SIZE:
        img = img.resize((AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS)

    # 无透明通道转 RGB（WebP 下更小）
    has_alpha = img.mode in ("RGBA", "LA") or (
        img.mode == "P" and "transparency" in img.info
    )
    img = img.convert("RGBA" if has_alpha else "RGB")

    buf = BytesIO()
    img.save(buf, "WEBP", quality=AVATAR_WEBP_QUALITY, method=6)
    return buf.getvalue()


def detect_content_type(data: bytes) -> str:
    """按 magic bytes 嗅探图片类型（key 无扩展名，代理转发时需要用）"""
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


async def upload_avatar(
    db: AsyncSession,
    user_id: str,
    file_data: bytes,
    content_type: str,
) -> str:
    """
    上传头像：OSS 覆盖写 + 更新 users.avatar_url（代理 URL，带 ?v= 时间戳）

    Returns:
        新的 avatar_url

    Raises:
        ValueError: 格式/大小不合法
        LookupError: 用户不存在
        RuntimeError: OSS 未配置
    """
    ct = (content_type or "").lower()
    if ct not in ALLOWED_CONTENT_TYPES:
        raise ValueError("仅支持 JPG / PNG / WebP 格式的图片")
    if not file_data:
        raise ValueError("文件内容为空")
    if len(file_data) > MAX_AVATAR_BYTES:
        raise ValueError(f"图片大小不能超过 {MAX_AVATAR_BYTES // (1024 * 1024)}MB")

    storage = get_storage()
    if storage is None:
        raise RuntimeError("OSS 未配置，无法上传头像")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise LookupError("用户不存在")

    # 服务端压缩：统一转 WebP 小图，后续代理加载快
    compressed = compress_avatar(file_data)
    await storage.upload(compressed, avatar_oss_key(user_id), "image/webp")

    avatar_url = f"/api/v1/users/{user_id}/avatar?v={int(time.time())}"
    user.avatar_url = avatar_url
    await db.flush()
    return avatar_url


async def download_avatar(user_id: str) -> Tuple[bytes, str]:
    """
    从 OSS 拉取头像字节流（代理转发用）

    Returns:
        (图片字节, content_type)

    Raises:
        LookupError: 头像不存在
        RuntimeError: OSS 未配置
    """
    storage = get_storage()
    if storage is None:
        raise RuntimeError("OSS 未配置")
    try:
        data = await storage.download(avatar_oss_key(user_id))
    except Exception as e:
        raise LookupError("头像不存在") from e
    return data, detect_content_type(data)
