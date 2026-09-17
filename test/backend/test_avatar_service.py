"""
用户头像 service 层测试

覆盖关键路径：
- upload_avatar：格式/大小校验、压缩（方形 256px WebP）、OSS 覆盖写、
  users.avatar_url 更新（带 ?v= 时间戳）
- download_avatar：正常拉取 + content_type 嗅探、头像不存在、OSS 未配置

不测 OSS 真实上传，storage 相关用 mock（与 test_feedback_service.py 同口径）。
"""
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# 确保能 import app
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src" / "backend"))

from app.models.database import Base
from app.models.user import User
from app.services import avatar_service

def make_image(fmt: str = "PNG", size=(800, 600), mode: str = "RGB") -> bytes:
    """生成真实图片字节（PIL 压缩链路需要能解析的图）"""
    buf = BytesIO()
    Image.new(mode, size, (200, 30, 30)).save(buf, fmt)
    return buf.getvalue()


PNG_BYTES = make_image("PNG")
JPEG_BYTES = make_image("JPEG")
WEBP_BYTES = make_image("WEBP")


@pytest_asyncio.fixture
async def db_session():
    """内存 SQLite 异步 session，每个测试独立"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def user(db_session):
    u = User(
        id="user-avatar-001",
        email="avatar@example.com",
        username="avataruser",
        password_hash="test-hash-not-real",
        is_active=True,
    )
    db_session.add(u)
    await db_session.commit()
    return u


def _mock_storage():
    storage = AsyncMock()
    storage.upload = AsyncMock()
    storage.download = AsyncMock(return_value=PNG_BYTES)
    return storage


@pytest.mark.asyncio
async def test_upload_avatar_success(db_session, user):
    """上传成功：压缩为 WebP 后 OSS 覆盖写，avatar_url 带 ?v= 时间戳"""
    storage = _mock_storage()
    with patch("app.services.avatar_service.get_storage", return_value=storage):
        url = await avatar_service.upload_avatar(
            db_session, user.id, PNG_BYTES, "image/png"
        )

    assert url.startswith(f"/api/v1/users/{user.id}/avatar?v=")
    args = storage.upload.await_args
    assert args.args[1] == f"avatars/{user.id}"
    assert args.args[2] == "image/webp"
    # 压缩产物是 WebP 且远小于原图
    assert args.args[0][:4] == b"RIFF" and args.args[0][8:12] == b"WEBP"
    assert len(args.args[0]) < len(PNG_BYTES)
    await db_session.refresh(user)
    assert user.avatar_url == url


@pytest.mark.asyncio
async def test_compress_avatar_square_256_webp():
    """大图压缩：中心裁剪正方形 + 缩到 256px + WebP"""
    compressed = avatar_service.compress_avatar(make_image("JPEG", size=(1024, 600)))
    img = Image.open(BytesIO(compressed))
    assert img.format == "WEBP"
    assert img.size == (256, 256)
    assert len(compressed) < 50 * 1024  # 一般 <50KB


@pytest.mark.asyncio
async def test_compress_avatar_small_image_no_upscale():
    """小图只裁剪不放大"""
    compressed = avatar_service.compress_avatar(make_image("PNG", size=(120, 80)))
    img = Image.open(BytesIO(compressed))
    assert img.size == (80, 80)


def test_compress_avatar_invalid_image():
    with pytest.raises(ValueError, match="无法识别"):
        avatar_service.compress_avatar(b"not-an-image")


@pytest.mark.asyncio
async def test_upload_avatar_overwrites_same_key(db_session, user):
    """重复上传：OSS key 不变（覆盖写），avatar_url 的 ?v= 可区分"""
    storage = _mock_storage()
    with patch("app.services.avatar_service.get_storage", return_value=storage):
        url1 = await avatar_service.upload_avatar(db_session, user.id, PNG_BYTES, "image/png")
        url2 = await avatar_service.upload_avatar(db_session, user.id, JPEG_BYTES, "image/jpeg")

    keys = [c.args[1] for c in storage.upload.await_args_list]
    assert keys == [f"avatars/{user.id}", f"avatars/{user.id}"]
    assert url1.split("?")[0] == url2.split("?")[0]


@pytest.mark.asyncio
async def test_upload_avatar_rejects_bad_type(db_session, user):
    with patch("app.services.avatar_service.get_storage", return_value=_mock_storage()):
        with pytest.raises(ValueError, match="仅支持"):
            await avatar_service.upload_avatar(db_session, user.id, b"data", "image/gif")


@pytest.mark.asyncio
async def test_upload_avatar_rejects_oversize(db_session, user):
    big = b"\x89PNG" + b"\x00" * (avatar_service.MAX_AVATAR_BYTES)
    with patch("app.services.avatar_service.get_storage", return_value=_mock_storage()):
        with pytest.raises(ValueError, match="不能超过"):
            await avatar_service.upload_avatar(db_session, user.id, big, "image/png")


@pytest.mark.asyncio
async def test_upload_avatar_oss_not_configured(db_session, user):
    with patch("app.services.avatar_service.get_storage", return_value=None):
        with pytest.raises(RuntimeError, match="OSS 未配置"):
            await avatar_service.upload_avatar(db_session, user.id, PNG_BYTES, "image/png")


@pytest.mark.asyncio
async def test_download_avatar_sniffs_content_type(user):
    storage = _mock_storage()
    for data, expected in [
        (PNG_BYTES, "image/png"),
        (JPEG_BYTES, "image/jpeg"),
        (WEBP_BYTES, "image/webp"),
    ]:
        storage.download = AsyncMock(return_value=data)
        with patch("app.services.avatar_service.get_storage", return_value=storage):
            raw, ct = await avatar_service.download_avatar(user.id)
        assert raw == data
        assert ct == expected
        storage.download.assert_awaited_once_with(f"avatars/{user.id}")


@pytest.mark.asyncio
async def test_download_avatar_not_found(user):
    storage = _mock_storage()
    storage.download = AsyncMock(side_effect=Exception("NoSuchKey"))
    with patch("app.services.avatar_service.get_storage", return_value=storage):
        with pytest.raises(LookupError, match="头像不存在"):
            await avatar_service.download_avatar(user.id)


@pytest.mark.asyncio
async def test_download_avatar_oss_not_configured(user):
    with patch("app.services.avatar_service.get_storage", return_value=None):
        with pytest.raises(RuntimeError, match="OSS 未配置"):
            await avatar_service.download_avatar(user.id)
