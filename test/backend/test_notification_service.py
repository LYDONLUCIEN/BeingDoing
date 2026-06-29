"""
通知邮件群发服务测试

测试场景：
1. mock SMTP → 3 用户 → 全部成功（sent=3, failed=0, status=completed）
2. 1 个邮箱故意失败 → failed=1, 其余成功
3. 模拟重启恢复：手动把 status 改 running → recover_interrupted → 标记 interrupted

使用独立的 in-memory SQLite + monkeypatch 替换 AsyncSessionLocal，避免污染主库。
SMTP 通过 monkeypatch EmailService.send_email 实现 mock。
"""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from app.models.database import Base
from app.models.notification import NotificationRecipient, NotificationTask
from app.models.user import User, UserProfile
from app.services import notification_service as ns_mod
from app.services.notification_service import NotificationService
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# ─── 测试专用引擎 + 会话工厂 ──────────────────────────────────

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
_TestSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def _setup_db(monkeypatch):
    """每个测试前：建表 + 插测试用户 + 替换 AsyncSessionLocal

    autouse 确保所有测试都用测试专用引擎，不碰主库。
    """
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 替换 NotificationService 用的会话工厂
    monkeypatch.setattr(ns_mod, "AsyncSessionLocal", _TestSessionLocal)

    # 插入 3 个测试用户（都有 email）
    async with _TestSessionLocal() as db:
        now = datetime.utcnow()
        users = [
            User(
                id="u1",
                email="alice@test.com",
                username="alice",
                password_hash="x",
                is_active=True,
                created_at=now - timedelta(days=10),
            ),
            User(
                id="u2",
                email="bob@test.com",
                username="bob",
                password_hash="x",
                is_active=True,
                created_at=now - timedelta(days=5),
            ),
            User(
                id="u3",
                email="carol@test.com",
                username="carol",
                password_hash="x",
                is_active=False,
                created_at=now,
            ),
        ]
        # 给 u1 加 profile_completed=True，u2/u3 不加（默认 False）
        profiles = [
            UserProfile(id="p1", user_id="u1", profile_completed=True, created_at=now),
            UserProfile(id="p2", user_id="u2", profile_completed=False, created_at=now),
            UserProfile(id="p3", user_id="u3", profile_completed=False, created_at=now),
        ]
        db.add_all(users)
        db.add_all(profiles)
        await db.commit()

    yield

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
def _fast_smtp(monkeypatch):
    """把 SMTP 间隔改成 0，避免测试真的 sleep"""
    monkeypatch.setattr(NotificationService, "SMTP_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(NotificationService, "RETRY_INTERVAL_SECONDS", 0.0)


# ─── 测试用例 ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_task_expands_recipients_all_users():
    """全选筛选 → 3 个收件人落库"""
    task_id = await NotificationService.create_task(
        subject="测试主题",
        body="测试正文",
        user_filter={},
    )
    assert task_id

    async with _TestSessionLocal() as db:
        task = (
            await db.execute(
                select(NotificationTask).where(NotificationTask.task_id == task_id)
            )
        ).scalar_one()
        assert task.total == 3
        assert task.status == "pending"

        recipients = (
            (
                await db.execute(
                    select(NotificationRecipient).where(
                        NotificationRecipient.task_id == task_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(recipients) == 3


@pytest.mark.asyncio
async def test_create_task_filter_active_only():
    """筛选 is_active=True → 只剩 2 个"""
    task_id = await NotificationService.create_task(
        subject="测试",
        body="正文",
        user_filter={"is_active": True},
    )
    async with _TestSessionLocal() as db:
        task = (
            await db.execute(
                select(NotificationTask).where(NotificationTask.task_id == task_id)
            )
        ).scalar_one()
        assert task.total == 2


@pytest.mark.asyncio
async def test_create_task_filter_profile_completed():
    """筛选 profile_completed=True → 只剩 u1"""
    task_id = await NotificationService.create_task(
        subject="测试",
        body="正文",
        user_filter={"profile_completed": True},
    )
    async with _TestSessionLocal() as db:
        task = (
            await db.execute(
                select(NotificationTask).where(NotificationTask.task_id == task_id)
            )
        ).scalar_one()
        assert task.total == 1


@pytest.mark.asyncio
async def test_create_task_empty_recipients_raises():
    """筛掉所有人 → ValueError"""
    with pytest.raises(ValueError):
        await NotificationService.create_task(
            subject="x",
            body="y",
            user_filter={"is_active": False, "profile_completed": True},  # 无交集
        )


@pytest.mark.asyncio
async def test_run_batch_all_success(monkeypatch):
    """场景1：mock SMTP 3 用户全部成功

    用例：sent=3, failed=0, status=completed，收件人状态全 sent
    """
    send_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.services.notification_service.EmailService.send_email", send_mock
    )

    task_id = await NotificationService.create_task(
        subject="全员通知",
        body="系统维护",
        user_filter={},
    )
    await NotificationService.run_batch(task_id)

    # 校验调用次数
    assert send_mock.await_count == 3

    # 校验进度
    status = await NotificationService.get_status(task_id)
    assert status["status"] == "completed"
    assert status["total"] == 3
    assert status["sent"] == 3
    assert status["failed"] == 0
    assert all(r["status"] == "sent" for r in status["recipients"])


@pytest.mark.asyncio
async def test_run_batch_one_failure(monkeypatch):
    """场景2：bob 邮箱故意失败（其余成功）

    用例：sent=2, failed=1, status=completed
    """

    async def fake_send(to_email, subject, body_text):
        if to_email == "bob@test.com":
            raise RuntimeError("SMTP refused")

    send_mock = AsyncMock(side_effect=fake_send)
    monkeypatch.setattr(
        "app.services.notification_service.EmailService.send_email", send_mock
    )

    task_id = await NotificationService.create_task(
        subject="通知",
        body="正文",
        user_filter={},
    )
    await NotificationService.run_batch(task_id)

    status = await NotificationService.get_status(task_id)
    assert status["status"] == "completed"
    assert status["sent"] == 2
    assert status["failed"] == 1
    # 找到失败的收件人，确认 error_msg 非空
    failed = [r for r in status["recipients"] if r["status"] == "failed"]
    assert len(failed) == 1
    assert failed[0]["email"] == "bob@test.com"
    assert failed[0]["error_msg"]


@pytest.mark.asyncio
async def test_run_batch_marks_running_during_execution(monkeypatch):
    """执行中 task 状态应该是 running（标记后即查）"""
    monkeypatch.setattr(
        "app.services.notification_service.EmailService.send_email",
        AsyncMock(return_value=None),
    )

    task_id = await NotificationService.create_task(
        subject="x", body="y", user_filter={}
    )

    # 在 _mark_running 之后、发送之前插入校验
    original_mark_running = NotificationService._mark_running

    captured = {}

    async def spy_mark_running(tid):
        await original_mark_running(tid)
        # 此时 task 应是 running
        st = await NotificationService.get_status(tid)
        captured["status_after_mark"] = st["status"]

    monkeypatch.setattr(NotificationService, "_mark_running", spy_mark_running)

    await NotificationService.run_batch(task_id)
    assert captured["status_after_mark"] == "running"


@pytest.mark.asyncio
async def test_recover_interrupted_marks_running_tasks():
    """场景3：手动把 status 改 running → recover → interrupted

    模拟服务重启场景：上次运行中被杀，库里的 task 卡在 running。
    """
    # 建一个 running 状态的任务
    task_id = await NotificationService.create_task(
        subject="中断任务", body="正文", user_filter={}
    )
    async with _TestSessionLocal() as db:
        await db.execute(
            update(NotificationTask)
            .where(NotificationTask.task_id == task_id)
            .values(status="running", started_at=datetime.utcnow())
        )
        await db.commit()

    # 执行恢复
    count = await NotificationService.recover_interrupted()
    assert count == 1

    # 校验状态变成 interrupted
    status = await NotificationService.get_status(task_id)
    assert status["status"] == "interrupted"
    assert status["finished_at"] is not None


@pytest.mark.asyncio
async def test_recover_interrupted_no_running_returns_zero():
    """没有 running 任务时 recover 返回 0"""
    await NotificationService.create_task(subject="x", body="y", user_filter={})
    count = await NotificationService.recover_interrupted()
    assert count == 0


@pytest.mark.asyncio
async def test_list_tasks_pagination():
    """list_tasks 分页正确"""
    for i in range(3):
        await NotificationService.create_task(
            subject=f"t{i}", body="body", user_filter={}
        )
    res = await NotificationService.list_tasks(page=1, page_size=2)
    assert res["total"] == 3
    assert len(res["items"]) == 2
    res2 = await NotificationService.list_tasks(page=2, page_size=2)
    assert len(res2["items"]) == 1


@pytest.mark.asyncio
async def test_get_status_not_found_returns_none():
    """查不存在的 task_id → None"""
    res = await NotificationService.get_status("nonexistent-id")
    assert res is None


@pytest.mark.asyncio
async def test_filter_json_persisted(monkeypatch):
    """filter_json 正确持久化，get_status 能还原"""
    monkeypatch.setattr(
        "app.services.notification_service.EmailService.send_email",
        AsyncMock(return_value=None),
    )
    filt = {
        "is_active": True,
        "profile_completed": False,
        "created_after": "2026-01-01",
    }
    task_id = await NotificationService.create_task(
        subject="x", body="y", user_filter=filt
    )
    status = await NotificationService.get_status(task_id)
    assert status["filter"] == filt


@pytest.mark.asyncio
async def test_run_batch_with_retry_eventually_succeeds(monkeypatch):
    """第一次失败、重试成功 → 最终 sent，且调用 2 次"""
    call_count = {"n": 0}

    async def flaky_send(to_email, subject, body_text):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("transient error")
        # 第二次成功

    monkeypatch.setattr(
        "app.services.notification_service.EmailService.send_email", flaky_send
    )

    task_id = await NotificationService.create_task(
        subject="x", body="y", user_filter={"is_active": False}  # 只有 u3
    )
    await NotificationService.run_batch(task_id)

    status = await NotificationService.get_status(task_id)
    assert status["sent"] == 1
    assert status["failed"] == 0
    assert call_count["n"] == 2  # 初次 + 1 次重试
