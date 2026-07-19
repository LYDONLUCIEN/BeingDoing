"""
孤儿附件清理任务测试
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src" / "backend"))

from app.models.database import Base
from app.models.feedback import FeedbackAttachment


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_cleanup_old_orphans(db_session, monkeypatch):
    """超过 N 天的孤儿被清理，未超的不动，已关联的不动"""
    from app.services.feedback_orphan_cleanup import cleanup_orphan_attachments

    now = datetime.now(timezone.utc)

    # 1. 老孤儿（8 天前，应被清）
    old_orphan = FeedbackAttachment(
        uploader_user_id="u1",
        feedback_id=None,
        oss_key="feedbacks/temp/old.png",
        size_bytes=100,
        content_type="image/png",
        created_at=now - timedelta(days=8),
    )
    # 2. 新孤儿（1 天前，保留）
    new_orphan = FeedbackAttachment(
        uploader_user_id="u1",
        feedback_id=None,
        oss_key="feedbacks/temp/new.png",
        size_bytes=100,
        content_type="image/png",
        created_at=now - timedelta(days=1),
    )
    # 3. 已关联（即使是老的，也不动）
    attached = FeedbackAttachment(
        uploader_user_id="u1",
        feedback_id="fb-1",
        oss_key="feedbacks/fb-1/attached.png",
        size_bytes=100,
        content_type="image/png",
        created_at=now - timedelta(days=30),
    )
    db_session.add_all([old_orphan, new_orphan, attached])
    await db_session.commit()

    # mock storage 避免真调 OSS
    storage_mock = AsyncMock()
    storage_mock.delete = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.services.feedback_orphan_cleanup.get_storage", lambda: storage_mock
    )
    # patch AsyncSessionLocal 让 service 用我们的 session
    monkeypatch.setattr(
        "app.services.feedback_orphan_cleanup.AsyncSessionLocal",
        lambda: _ctxmgr(db_session),
    )

    stats = await cleanup_orphan_attachments()

    assert stats["scanned"] == 1, "只有 1 个老孤儿符合条件"
    assert stats["deleted_db"] == 1
    assert stats["deleted_oss_ok"] == 1
    storage_mock.delete.assert_called_once_with("feedbacks/temp/old.png")

    # DB 验证：只剩 new_orphan + attached
    result = await db_session.execute(select(FeedbackAttachment))
    remaining = list(result.scalars().all())
    remaining_keys = {a.oss_key for a in remaining}
    assert remaining_keys == {"feedbacks/temp/new.png", "feedbacks/fb-1/attached.png"}


class _ctxmgr:
    """简单的 async context manager 包装，让 fixture session 能被 service 使用"""
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        return False
