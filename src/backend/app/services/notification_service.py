"""
通知邮件群发服务

职责：
1. create_task: 创建任务 + 展开收件人列表落库 → 返回 task_id
2. run_batch: BackgroundTasks 回调，循环发送，每发一封更新状态 + task 进度
3. get_status / list_tasks: 查询进度和历史
4. recover_interrupted: 启动时扫描 status='running' 标记为 interrupted

设计要点：
- 进度落 SQLite（notification_tasks + notification_recipients），重启不丢
- SMTP 限流：每封之间 sleep 1 秒（163 邮箱限频）
- 失败重试 1 次：第一封失败 → 间隔 2 秒再试一次
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from app.models.database import AsyncSessionLocal
from app.models.notification import NotificationRecipient, NotificationTask
from app.models.user import User, UserProfile
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)


class NotificationService:
    """通知邮件群发服务"""

    # SMTP 限流间隔（秒），163 邮箱建议每秒 ≤1 封
    SMTP_INTERVAL_SECONDS: float = 1.0
    # 失败重试间隔（秒）
    RETRY_INTERVAL_SECONDS: float = 2.0

    # ─── 创建任务 ───────────────────────────────────────────────

    @classmethod
    async def create_task(
        cls,
        subject: str,
        body: str,
        user_filter: Optional[Dict[str, Any]] = None,
    ) -> str:
        """创建群发任务：落 task 记录 + 展开收件人列表落库

        Args:
            subject: 邮件主题
            body: 邮件正文
            user_filter: 收件人筛选条件
                - is_active: Optional[bool] 按是否活跃筛选
                - profile_completed: Optional[bool] 按 profile 完成度筛选
                - created_after: Optional[str] ISO 时间，注册时间下界

        Returns:
            task_id: 新建任务 ID

        Raises:
            ValueError: 筛选后收件人为空
        """
        user_filter = user_filter or {}
        filter_json_str = json.dumps(user_filter, ensure_ascii=False)

        # 查询符合条件的收件人（必须有 email）
        recipients = await cls._query_recipients(user_filter)
        if not recipients:
            raise ValueError("筛选后收件人为空，无法创建群发任务")

        async with AsyncSessionLocal() as db:
            now = datetime.now(timezone.utc)
            task = NotificationTask(
                subject=subject,
                body=body,
                filter_json=filter_json_str,
                total=len(recipients),
                sent=0,
                failed=0,
                status="pending",
                created_at=now,
                updated_at=now,
            )
            db.add(task)
            await db.flush()  # 拿到 task_id

            # 批量插入收件人明细
            recipient_rows = [
                NotificationRecipient(
                    task_id=task.task_id,
                    user_id=user_id,
                    email=email,
                    status="pending",
                    created_at=now,
                )
                for user_id, email in recipients
            ]
            db.add_all(recipient_rows)
            await db.commit()
            return task.task_id

    @classmethod
    async def _query_recipients(
        cls, user_filter: Dict[str, Any]
    ) -> List[tuple[Optional[str], str]]:
        """按筛选条件查询收件人列表（user_id, email）。

        只返回 email 非空的用户。profile_completed 筛选需 join user_profiles。
        支持两种互斥模式：
        - user_filter.user_ids 非空：按显式 user_id 列表收件（手动勾选模式）
        - 其他字段：按条件筛选（is_active/profile_completed/created_after）
        """
        base = select(User.id, User.email).where(User.email.isnot(None))

        # 手动勾选模式：显式 user_id 列表优先，忽略其他筛选
        user_ids = user_filter.get("user_ids")
        if user_ids:
            base = base.where(User.id.in_(list(user_ids)))
        else:
            # 条件筛选模式
            if user_filter.get("profile_completed") is not None:
                base = base.join(UserProfile, UserProfile.user_id == User.id).where(
                    UserProfile.profile_completed == user_filter["profile_completed"]
                )
            if user_filter.get("is_active") is not None:
                base = base.where(User.is_active == user_filter["is_active"])
            if user_filter.get("created_after"):
                try:
                    dt_after = datetime.fromisoformat(str(user_filter["created_after"]))
                    base = base.where(User.created_at >= dt_after)
                except ValueError:
                    logger.warning("invalid created_after filter: %s", user_filter["created_after"])

        async with AsyncSessionLocal() as db:
            result = await db.execute(base)
            rows = result.all()
            # 过滤空 email 字符串
            return [(r[0], r[1]) for r in rows if r[1]]

    # ─── 后台发送 ───────────────────────────────────────────────

    @classmethod
    async def run_batch(cls, task_id: str) -> None:
        """后台批量发送回调（由 BackgroundTasks 调用）

        流程：
        1. 标记 task → running，记录 started_at
        2. 取所有 status='pending' 的收件人
        3. 逐个发送，每发一封：更新 recipient 状态 + task 进度计数
        4. 每封间隔 SMTP_INTERVAL_SECONDS，失败重试 1 次
        5. 全部发完 → 标记 completed/interrupted（中途异常）
        """
        # 标记 running
        await cls._mark_running(task_id)

        try:
            async with AsyncSessionLocal() as db:
                # 锁定 pending 收件人（同一任务不会被并发发送，这里简单查）
                result = await db.execute(
                    select(NotificationRecipient)
                    .where(
                        NotificationRecipient.task_id == task_id,
                        NotificationRecipient.status == "pending",
                    )
                    .order_by(NotificationRecipient.id.asc())
                )
                pending = list(result.scalars().all())

            for recipient in pending:
                # 二次确认任务未被打断（重启恢复会改成 interrupted）
                if await cls._is_interrupted(task_id):
                    logger.info("task %s interrupted, stop sending", task_id)
                    return

                ok, err = await cls._send_one_with_retry(recipient.email, task_id)
                await cls._update_recipient_and_progress(
                    task_id=task_id,
                    recipient_id=recipient.id,
                    success=ok,
                    error_msg=err,
                )
                # SMTP 限流
                await asyncio.sleep(cls.SMTP_INTERVAL_SECONDS)

            # 全部发完，标记 completed
            await cls._mark_completed(task_id)
        except Exception as e:
            logger.exception("run_batch failed for task %s: %s", task_id, e)
            await cls._mark_interrupted(task_id)

    @classmethod
    async def _send_one_with_retry(cls, to_email: str, task_id: str) -> tuple[bool, Optional[str]]:
        """发送单封邮件，失败重试 1 次。

        Returns:
            (success, error_msg)
        """
        # 通过 task 取 subject/body（每次查避免持有 db 连接）
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(NotificationTask.subject, NotificationTask.body).where(
                    NotificationTask.task_id == task_id
                )
            )
            row = result.first()
            if not row:
                return False, "task not found"
            subject, body = row[0], row[1]

        last_err: Optional[str] = None
        for attempt in range(2):  # 最多 2 次（初次 + 1 次重试）
            try:
                await EmailService.send_email(to_email=to_email, subject=subject, body_text=body)
                return True, None
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                logger.warning(
                    "send to %s failed (attempt %d/2): %s",
                    to_email,
                    attempt + 1,
                    last_err,
                )
                if attempt == 0:
                    await asyncio.sleep(cls.RETRY_INTERVAL_SECONDS)
        return False, last_err

    @classmethod
    async def _update_recipient_and_progress(
        cls,
        task_id: str,
        recipient_id: int,
        success: bool,
        error_msg: Optional[str],
    ) -> None:
        """更新单个收件人状态 + task 进度计数（原子）"""
        async with AsyncSessionLocal() as db:
            if success:
                await db.execute(
                    update(NotificationRecipient)
                    .where(NotificationRecipient.id == recipient_id)
                    .values(status="sent")
                )
                await db.execute(
                    update(NotificationTask)
                    .where(NotificationTask.task_id == task_id)
                    .values(sent=NotificationTask.sent + 1, updated_at=datetime.now(timezone.utc))
                )
            else:
                await db.execute(
                    update(NotificationRecipient)
                    .where(NotificationRecipient.id == recipient_id)
                    .values(status="failed", error_msg=error_msg)
                )
                await db.execute(
                    update(NotificationTask)
                    .where(NotificationTask.task_id == task_id)
                    .values(
                        failed=NotificationTask.failed + 1, updated_at=datetime.now(timezone.utc)
                    )
                )
            await db.commit()

    @classmethod
    async def _mark_running(cls, task_id: str) -> None:
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(NotificationTask)
                .where(NotificationTask.task_id == task_id)
                .values(
                    status="running",
                    started_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()

    @classmethod
    async def _mark_completed(cls, task_id: str) -> None:
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(NotificationTask)
                .where(NotificationTask.task_id == task_id)
                .values(
                    status="completed",
                    finished_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()

    @classmethod
    async def _mark_interrupted(cls, task_id: str) -> None:
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(NotificationTask)
                .where(NotificationTask.task_id == task_id)
                .values(
                    status="interrupted",
                    finished_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()

    @classmethod
    async def _is_interrupted(cls, task_id: str) -> bool:
        """检查任务是否被外部标记为非 running（如重启恢复改成了 interrupted）"""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(NotificationTask.status).where(NotificationTask.task_id == task_id)
            )
            status = result.scalar_one_or_none()
            return status not in ("running",)

    # ─── 查询接口 ───────────────────────────────────────────────

    @classmethod
    async def get_status(cls, task_id: str) -> Optional[Dict[str, Any]]:
        """查询单个任务的进度详情

        Returns:
            {
                task_id, subject, body, filter, total, sent, failed, status,
                created_at, started_at, finished_at,
                recipients: [{email, status, error_msg}]
            }
            未找到返回 None
        """
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(NotificationTask).where(NotificationTask.task_id == task_id)
            )
            task = result.scalar_one_or_none()
            if not task:
                return None

            rec_result = await db.execute(
                select(NotificationRecipient)
                .where(NotificationRecipient.task_id == task_id)
                .order_by(NotificationRecipient.id.asc())
            )
            recipients = rec_result.scalars().all()

            return {
                "task_id": task.task_id,
                "subject": task.subject,
                "body": task.body,
                "filter": json.loads(task.filter_json) if task.filter_json else {},
                "total": task.total,
                "sent": task.sent,
                "failed": task.failed,
                "status": task.status,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "finished_at": task.finished_at.isoformat() if task.finished_at else None,
                "recipients": [
                    {
                        "email": r.email,
                        "user_id": r.user_id,
                        "status": r.status,
                        "error_msg": r.error_msg,
                    }
                    for r in recipients
                ],
            }

    @classmethod
    async def list_tasks(cls, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """分页查询历史任务列表

        Returns:
            {items: [{task_id, subject, total, sent, failed, status, created_at, finished_at}],
             total, page, page_size}
        """
        async with AsyncSessionLocal() as db:
            count_q = select(func.count()).select_from(NotificationTask)
            total = (await db.execute(count_q)).scalar() or 0

            offset = (page - 1) * page_size
            list_q = (
                select(NotificationTask)
                .order_by(NotificationTask.created_at.desc())
                .offset(offset)
                .limit(page_size)
            )
            result = await db.execute(list_q)
            tasks = result.scalars().all()

            return {
                "items": [
                    {
                        "task_id": t.task_id,
                        "subject": t.subject,
                        "total": t.total,
                        "sent": t.sent,
                        "failed": t.failed,
                        "status": t.status,
                        "created_at": t.created_at.isoformat() if t.created_at else None,
                        "finished_at": t.finished_at.isoformat() if t.finished_at else None,
                    }
                    for t in tasks
                ],
                "total": total,
                "page": page,
                "page_size": page_size,
            }

    # ─── 重启恢复 ───────────────────────────────────────────────

    @classmethod
    async def recover_interrupted(cls) -> int:
        """启动时扫描所有 status='running' 的任务，标记为 interrupted

        服务异常退出时，running 任务的中途进度已落库，但发送线程已死。
        改成 interrupted 后，admin 可在 UI 上看到并手动重发失败/未发的收件人。

        Returns:
            interrupted_count: 被标记的任务数
        """
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(NotificationTask.task_id).where(NotificationTask.status == "running")
            )
            task_ids = [r[0] for r in result.all()]
            if not task_ids:
                return 0

            await db.execute(
                update(NotificationTask)
                .where(NotificationTask.task_id.in_(task_ids))
                .values(
                    status="interrupted",
                    finished_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()
            logger.info("recovered %d interrupted notification tasks: %s", len(task_ids), task_ids)
            return len(task_ids)
