"""
反馈与站内信 service 层冒烟测试

覆盖关键路径：
- create_feedback：插主表 + 关联附件 + 给用户 auto_ack + 给 admin feedback_new
- 上传/删除附件
- 列表/未读数/标记已读
- admin 列表/详情/改状态

不测 OSS 真实上传（OSSProvider 已独立测过），attachment 相关用 mock。
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# 确保能 import app
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src" / "backend"))

from app.models.database import Base
from app.models.feedback import Feedback, FeedbackAttachment, Notification
from app.models.user import User
from app.services import feedback_service


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
async def user_and_admin(db_session):
    """准备一个普通用户 + 一个 super_admin 用户（用 SUPER_ADMIN_USER_IDS 标记）"""
    user = User(
        id="user-001",
        email="user@example.com",
        username="normaluser",
        password_hash="test-hash-not-real",
        is_active=True,
    )
    admin = User(
        id="admin-001",
        email="admin@example.com",
        username="boss",
        password_hash="test-hash-not-real",
        is_active=True,
    )
    db_session.add_all([user, admin])
    await db_session.commit()

    # 通过环境变量配置 admin
    old = os.environ.get("SUPER_ADMIN_USER_IDS")
    os.environ["SUPER_ADMIN_USER_IDS"] = "admin-001"
    # 重新加载 settings
    from importlib import reload
    from app.config import settings as settings_mod
    # 注意：pydantic-settings 已在 import 时读取，需要手动重置或直接 patch
    yield user, admin
    if old is not None:
        os.environ["SUPER_ADMIN_USER_IDS"] = old
    else:
        os.environ.pop("SUPER_ADMIN_USER_IDS", None)


@pytest.mark.asyncio
async def test_create_feedback_basic(db_session, user_and_admin, monkeypatch):
    """创建反馈：插主表 + 给用户发 auto_ack + 给 admin 发 feedback_new"""
    user, admin = user_and_admin

    # patch get_super_admin_user_ids 返回 admin
    monkeypatch.setattr(
        "app.services.feedback_service.get_super_admin_user_ids",
        lambda: ["admin-001"],
    )

    feedback = await feedback_service.create_feedback(
        db=db_session,
        user_id="user-001",
        user_email="user@example.com",
        type_="bug",
        content="点击登录按钮没反应",
        attachment_ids=[],
    )
    await db_session.commit()

    # 1. 反馈落库
    assert feedback.id is not None
    assert feedback.status == "received"
    assert feedback.type == "bug"

    # 2. 用户收到 auto_ack
    from sqlalchemy import select
    user_notifs = (
        await db_session.execute(
            select(Notification).where(
                Notification.user_id == "user-001",
                Notification.type == "feedback_auto_ack",
            )
        )
    ).scalars().all()
    assert len(user_notifs) == 1
    assert "【留言反馈】" in user_notifs[0].title
    assert user_notifs[0].related_feedback_id == feedback.id

    # 3. admin 收到 feedback_new
    admin_notifs = (
        await db_session.execute(
            select(Notification).where(
                Notification.user_id == "admin-001",
                Notification.type == "feedback_new",
            )
        )
    ).scalars().all()
    assert len(admin_notifs) == 1
    assert "user@example.com" in admin_notifs[0].content
    assert "bug" in admin_notifs[0].content


@pytest.mark.asyncio
async def test_create_feedback_invalid_type(db_session, user_and_admin):
    """非法 type 抛 ValueError"""
    with pytest.raises(ValueError, match="类型"):
        await feedback_service.create_feedback(
            db=db_session,
            user_id="user-001",
            user_email="user@example.com",
            type_="xxx",
            content="有效的反馈内容",
            attachment_ids=[],
        )


@pytest.mark.asyncio
async def test_create_feedback_content_too_short(db_session, user_and_admin):
    """content 太短抛 ValueError"""
    with pytest.raises(ValueError, match="长度"):
        await feedback_service.create_feedback(
            db=db_session,
            user_id="user-001",
            user_email="user@example.com",
            type_="bug",
            content="短",
            attachment_ids=[],
        )


@pytest.mark.asyncio
async def test_unread_count_and_list(db_session, user_and_admin, monkeypatch):
    """未读数 + 列表"""
    user, admin = user_and_admin
    monkeypatch.setattr(
        "app.services.feedback_service.get_super_admin_user_ids",
        lambda: ["admin-001"],
    )

    # 提一条反馈 → user 收到 auto_ack
    await feedback_service.create_feedback(
        db=db_session,
        user_id="user-001",
        user_email="user@example.com",
        type_="idea",
        content="希望支持深色模式",
        attachment_ids=[],
    )
    await db_session.commit()

    # 未读 = 1
    count = await feedback_service.get_unread_count(db_session, "user-001")
    assert count == 1

    # 列表
    items, total, unread = await feedback_service.list_notifications(
        db_session, "user-001", page=1, page_size=20
    )
    assert total == 1
    assert unread == 1
    assert len(items) == 1
    assert items[0].type == "feedback_auto_ack"

    # 标记已读
    await feedback_service.mark_read(db_session, "user-001", items[0].id)
    await db_session.commit()
    count_after = await feedback_service.get_unread_count(db_session, "user-001")
    assert count_after == 0


@pytest.mark.asyncio
async def test_mark_read_idempotent(db_session, user_and_admin, monkeypatch):
    """标记已读幂等：重复不报错"""
    user, admin = user_and_admin
    monkeypatch.setattr(
        "app.services.feedback_service.get_super_admin_user_ids",
        lambda: ["admin-001"],
    )
    await feedback_service.create_feedback(
        db=db_session,
        user_id="user-001",
        user_email="user@example.com",
        type_="bug",
        content="测试幂等标记",
        attachment_ids=[],
    )
    await db_session.commit()

    from sqlalchemy import select
    notif = (
        await db_session.execute(
            select(Notification).where(Notification.user_id == "user-001")
        )
    ).scalar_one()

    await feedback_service.mark_read(db_session, "user-001", notif.id)
    first_read_at = notif.read_at
    await feedback_service.mark_read(db_session, "user-001", notif.id)
    assert notif.read_at == first_read_at  # 时间戳不变


@pytest.mark.asyncio
async def test_admin_list_and_filter(db_session, user_and_admin, monkeypatch):
    """管理员列表 + 筛选"""
    user, admin = user_and_admin
    monkeypatch.setattr(
        "app.services.feedback_service.get_super_admin_user_ids",
        lambda: ["admin-001"],
    )

    # 提 2 条 bug + 1 条 idea
    for i, (t, c) in enumerate([
        ("bug", "bug 描述 1 号内容"),
        ("bug", "bug 描述 2 号内容"),
        ("idea", "idea 描述内容"),
    ]):
        await feedback_service.create_feedback(
            db=db_session,
            user_id="user-001",
            user_email="user@example.com",
            type_=t,
            content=c,
            attachment_ids=[],
        )
    await db_session.commit()

    # 全部 = 3
    items, total = await feedback_service.admin_list_feedbacks(
        db_session, type_=None, status_=None, page=1, page_size=20
    )
    assert total == 3

    # 仅 bug = 2
    items, total = await feedback_service.admin_list_feedbacks(
        db_session, type_="bug", status_=None, page=1, page_size=20
    )
    assert total == 2
    assert all(f.type == "bug" for f in items)


@pytest.mark.asyncio
async def test_admin_update_status(db_session, user_and_admin, monkeypatch):
    """改状态：发 feedback_status_changed 通知给用户"""
    user, admin = user_and_admin
    monkeypatch.setattr(
        "app.services.feedback_service.get_super_admin_user_ids",
        lambda: ["admin-001"],
    )

    feedback = await feedback_service.create_feedback(
        db=db_session,
        user_id="user-001",
        user_email="user@example.com",
        type_="bug",
        content="状态变更测试",
        attachment_ids=[],
    )
    await db_session.commit()

    # 改为 done
    updated = await feedback_service.admin_update_status(
        db=db_session,
        feedback_id=feedback.id,
        new_status="done",
        admin_user_id="admin-001",
    )
    await db_session.commit()

    assert updated.status == "done"

    # 用户应该收到状态变更通知（除了 auto_ack）
    from sqlalchemy import select
    status_notifs = (
        await db_session.execute(
            select(Notification).where(
                Notification.user_id == "user-001",
                Notification.type == "feedback_status_changed",
            )
        )
    ).scalars().all()
    assert len(status_notifs) == 1
    assert "处理完毕" in status_notifs[0].title


@pytest.mark.asyncio
async def test_admin_update_status_invalid(db_session, user_and_admin):
    """非法状态抛 ValueError"""
    feedback = Feedback(
        user_id="user-001",
        user_email="user@example.com",
        type="bug",
        content="非法状态测试内容",
        status="received",
    )
    db_session.add(feedback)
    await db_session.commit()

    with pytest.raises(ValueError, match="状态无效"):
        await feedback_service.admin_update_status(
            db=db_session,
            feedback_id=feedback.id,
            new_status="invalid_status",
            admin_user_id="admin-001",
        )


@pytest.mark.asyncio
async def test_delete_attachment_rules(db_session, user_and_admin):
    """删附件：不能删别人的，不能删已关联的"""
    user, admin = user_and_admin

    # user 上传一个附件（不通过 service，直接造数据，避免依赖 OSS）
    att = FeedbackAttachment(
        uploader_user_id="user-001",
        feedback_id=None,
        oss_key="feedbacks/temp/test.png",
        size_bytes=1024,
        content_type="image/png",
    )
    db_session.add(att)
    await db_session.commit()

    # admin 想删 user 的附件 → PermissionError
    with pytest.raises(PermissionError):
        await feedback_service.delete_attachment(db_session, "admin-001", att.id)

    # 关联到某个反馈后，user 自己也删不掉
    feedback = Feedback(
        user_id="user-001",
        user_email="user@example.com",
        type="bug",
        content="附件关联测试内容",
        status="received",
    )
    db_session.add(feedback)
    await db_session.commit()
    att.feedback_id = feedback.id
    await db_session.commit()

    with pytest.raises(ValueError, match="已提交"):
        await feedback_service.delete_attachment(db_session, "user-001", att.id)


@pytest.mark.asyncio
async def test_admin_reply_feedback(db_session, user_and_admin, monkeypatch):
    """admin 回复：通过 EmailService 发送邮件，主题含反馈类型，正文含原始反馈摘要"""
    user, admin = user_and_admin

    feedback = Feedback(
        user_id="user-001",
        user_email="user@example.com",
        type="bug",
        content="点击登录按钮没反应",
        status="in_progress",
    )
    db_session.add(feedback)
    await db_session.commit()

    send_mock = AsyncMock()
    monkeypatch.setattr(
        "app.services.email_service.EmailService.send_email", send_mock
    )

    await feedback_service.admin_reply_feedback(
        db=db_session,
        feedback_id=feedback.id,
        content="您好，该问题已修复，请重试。",
    )

    send_mock.assert_awaited_once()
    kwargs = send_mock.await_args.kwargs
    assert kwargs["to_email"] == "user@example.com"
    assert "问题反馈" in kwargs["subject"]
    assert "该问题已修复" in kwargs["body_text"]
    assert "点击登录按钮没反应" in kwargs["body_text"]  # 附原始反馈


@pytest.mark.asyncio
async def test_admin_reply_feedback_validation(db_session, user_and_admin):
    """回复内容为空 / 反馈不存在 → 抛错"""
    feedback = Feedback(
        user_id="user-001",
        user_email="user@example.com",
        type="idea",
        content="希望支持深色模式",
        status="received",
    )
    db_session.add(feedback)
    await db_session.commit()

    with pytest.raises(ValueError, match="回复内容"):
        await feedback_service.admin_reply_feedback(
            db=db_session, feedback_id=feedback.id, content="   "
        )

    with pytest.raises(LookupError, match="不存在"):
        await feedback_service.admin_reply_feedback(
            db=db_session, feedback_id="not-exist", content="正常回复内容"
        )


# ---------- SLA / 处理人 / 超时扫描（016_feedback_sla_assignee） ----------


def test_calc_due_at_skips_weekends():
    """工作日计算：跳过周六日，截止当天 23:59（北京时间）"""
    from zoneinfo import ZoneInfo

    SH = ZoneInfo("Asia/Shanghai")
    # 2026-07-25 周六（北京 12:00）提交 bug → 周一二三 = 7/29 截止
    now_sat = datetime(2026, 7, 25, 4, 0, tzinfo=timezone.utc)
    due = feedback_service.calc_due_at("bug", now_sat).astimezone(SH)
    assert (due.month, due.day, due.hour) == (7, 29, 23)

    # 同日提交 idea → 5 个工作日 = 7/31 截止
    due_idea = feedback_service.calc_due_at("idea", now_sat).astimezone(SH)
    assert (due_idea.month, due_idea.day) == (7, 31)

    # 2026-07-31 周五提交 bug → 下周一二三 = 8/5 截止
    now_fri = datetime(2026, 7, 31, 2, 0, tzinfo=timezone.utc)
    due_fri = feedback_service.calc_due_at("bug", now_fri).astimezone(SH)
    assert (due_fri.month, due_fri.day) == (8, 5)


@pytest.mark.asyncio
async def test_create_feedback_sets_due_at(db_session, user_and_admin, monkeypatch):
    """创建反馈：due_at 落库 + auto_ack 文案含工作日与节假日提示"""
    monkeypatch.setattr(
        "app.services.feedback_service.get_super_admin_user_ids",
        lambda: ["admin-001"],
    )
    feedback = await feedback_service.create_feedback(
        db=db_session,
        user_id="user-001",
        user_email="user@example.com",
        type_="idea",
        content="希望能支持导出 PDF 报告",
        attachment_ids=[],
    )
    await db_session.commit()

    assert feedback.due_at is not None

    from sqlalchemy import select
    user_notifs = (
        await db_session.execute(
            select(Notification).where(
                Notification.user_id == "user-001",
                Notification.type == "feedback_auto_ack",
            )
        )
    ).scalars().all()
    assert "5 个工作日" in user_notifs[0].content
    assert "法定节假日可能略有延期" in user_notifs[0].content
    assert "邮箱" in user_notifs[0].content


@pytest.mark.asyncio
async def test_admin_update_assignee(db_session, user_and_admin, monkeypatch):
    """指派处理人：只能指派 super_admin，可清除"""
    monkeypatch.setattr(
        "app.services.feedback_service.get_super_admin_user_ids",
        lambda: ["admin-001"],
    )
    feedback = await feedback_service.create_feedback(
        db=db_session,
        user_id="user-001",
        user_email="user@example.com",
        type_="bug",
        content="页面白屏无法使用",
        attachment_ids=[],
    )
    await db_session.commit()
    assert feedback.assignee_id is None

    # 指派给 admin
    updated = await feedback_service.admin_update_assignee(
        db_session, feedback.id, "admin-001"
    )
    assert updated.assignee_id == "admin-001"

    # 非 super_admin 不能指派
    with pytest.raises(ValueError):
        await feedback_service.admin_update_assignee(
            db_session, feedback.id, "user-001"
        )

    # 不存在的用户
    with pytest.raises(ValueError):
        await feedback_service.admin_update_assignee(
            db_session, feedback.id, "ghost-999"
        )

    # 清除
    cleared = await feedback_service.admin_update_assignee(
        db_session, feedback.id, None
    )
    assert cleared.assignee_id is None

    # 不存在的反馈
    with pytest.raises(LookupError):
        await feedback_service.admin_update_assignee(
            db_session, "no-such-id", "admin-001"
        )


@pytest.mark.asyncio
async def test_list_assignees(db_session, user_and_admin, monkeypatch):
    """可指派处理人列表 = super_admin 用户"""
    monkeypatch.setattr(
        "app.services.feedback_service.get_super_admin_user_ids",
        lambda: ["admin-001"],
    )
    users = await feedback_service.list_assignees(db_session)
    assert [u.id for u in users] == ["admin-001"]


@pytest.mark.asyncio
async def test_overdue_scan_notify_and_idempotent(user_and_admin, monkeypatch):
    """超时扫描：过期未完结 → 通知 admin；当天重复扫描不重复通知"""
    from app.models.database import Base
    from app.services import feedback_overdue_scan

    # 独立内存库 + sessionmaker，patch 到扫描模块
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(feedback_overdue_scan, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(
        "app.services.feedback_service.get_super_admin_user_ids",
        lambda: ["admin-001"],
    )

    past = datetime(2026, 7, 20, 0, 0)  # naive UTC，已过期
    future = datetime(2099, 1, 1, 0, 0)
    async with session_factory() as s:
        s.add_all(
            [
                Feedback(
                    id="fb-overdue",
                    user_id="user-001",
                    user_email="user@example.com",
                    type="bug",
                    content="过期未处理的反馈",
                    status="in_progress",
                    due_at=past,
                ),
                Feedback(
                    id="fb-done",
                    user_id="user-001",
                    user_email="user@example.com",
                    type="bug",
                    content="已完结的过期反馈（不应提醒）",
                    status="done",
                    due_at=past,
                ),
                Feedback(
                    id="fb-future",
                    user_id="user-001",
                    user_email="user@example.com",
                    type="idea",
                    content="未到期的反馈（不应提醒）",
                    status="received",
                    due_at=future,
                ),
                Feedback(
                    id="fb-legacy",
                    user_id="user-001",
                    user_email="user@example.com",
                    type="bug",
                    content="存量老数据 due_at 为空（不应提醒）",
                    status="received",
                    due_at=None,
                ),
            ]
        )
        await s.commit()

    stats1 = await feedback_overdue_scan.scan_overdue_feedbacks()
    assert stats1["overdue"] == 1
    assert stats1["notified"] == 1

    from sqlalchemy import select
    async with session_factory() as s:
        notifs = (
            await s.execute(
                select(Notification).where(
                    Notification.type == "feedback_overdue",
                    Notification.related_feedback_id == "fb-overdue",
                )
            )
        ).scalars().all()
        assert len(notifs) == 1
        assert notifs[0].user_id == "admin-001"
        assert "超过承诺处理时限" in notifs[0].content

    # 当天再扫：幂等，不重复通知
    stats2 = await feedback_overdue_scan.scan_overdue_feedbacks()
    assert stats2["notified"] == 0
    assert stats2["skipped_already_notified"] == 1

    await engine.dispose()
