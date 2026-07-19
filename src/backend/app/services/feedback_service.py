"""
反馈与站内信业务服务层

封装跨表事务：
- 创建反馈 + 关联附件 + 发 auto_ack 通知 + 发新反馈通知给所有 admin
- 改 status + 发状态变更通知给用户
- 用户上传/删除附件（孤儿模式）
- 拉通知列表/未读数/标记已读
"""
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.core.storage import get_storage
from app.core.storage.base import BaseStorage
from app.core.storage.oss_provider import generate_object_key
from app.models.feedback import Feedback, FeedbackAttachment, Notification
from app.models.user import User
from app.utils.super_admin import get_super_admin_user_ids

# ---------- 常量 ----------

ALLOWED_TYPES = {"bug", "idea"}
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_CONTENT_TYPE_TO_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
MAX_ATTACHMENT_BYTES = 2 * 1024 * 1024  # 2MB
MAX_ATTACHMENTS_PER_FEEDBACK = 3

AUTO_ACK_TITLE = "【留言反馈】我们已收到您的反馈"
AUTO_ACK_CONTENT = (
    "感谢您的反馈，我们将在 3 天内通过邮箱与您联系。请留意您注册邮箱的邮件。"
)
NEW_FEEDBACK_TITLE_FOR_ADMIN = "【留言反馈】收到一条新反馈"


# ---------- 内部工具 ----------


def _validate_content(content: str) -> None:
    if len(content) < 5 or len(content) > 2000:
        raise ValueError("反馈内容长度必须在 5-2000 字之间")


def _validate_type(t: str) -> None:
    if t not in ALLOWED_TYPES:
        raise ValueError("反馈类型必须是 bug 或 idea")


def _validate_content_type(ct: str) -> None:
    if ct not in ALLOWED_CONTENT_TYPES:
        raise ValueError("仅支持 jpg/png/webp 格式")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _get_super_admin_ids(db: AsyncSession) -> List[str]:
    """获取所有 super_admin 的 user_id（来自 SUPER_ADMIN_USER_IDS/SUPER_ADMIN_EMAILS）"""
    # get_super_admin_user_ids 来自 app.utils.super_admin，读 settings
    ids = get_super_admin_user_ids()
    if ids:
        return ids
    # 兜底：直接查 users 表（若实现支持 is_super_admin 字段或类似）
    # 这里保守返回空，由调用方处理
    return []


# ---------- 核心业务 ----------


async def upload_attachment(
    db: AsyncSession,
    user_id: str,
    file_data: bytes,
    content_type: str,
    size_bytes: int,
) -> FeedbackAttachment:
    """
    用户上传一张截图（孤儿模式，feedback_id 暂为 None）
    """
    _validate_content_type(content_type)
    if size_bytes > MAX_ATTACHMENT_BYTES:
        raise ValueError(f"图片大小不能超过 {MAX_ATTACHMENT_BYTES // (1024 * 1024)}MB")

    storage = get_storage()
    if storage is None:
        raise RuntimeError("OSS 未配置，无法上传附件")

    ext = ALLOWED_CONTENT_TYPE_TO_EXT[content_type]
    oss_key = generate_object_key("feedbacks/temp", ext)
    await storage.upload(file_data, oss_key, content_type)

    att = FeedbackAttachment(
        uploader_user_id=user_id,
        feedback_id=None,
        oss_key=oss_key,
        size_bytes=size_bytes,
        content_type=content_type,
    )
    db.add(att)
    await db.flush()
    return att


async def get_attachment_signed_url(att: FeedbackAttachment) -> str:
    """生成某个附件的签名 URL（1 小时有效）"""
    storage = get_storage()
    if storage is None:
        raise RuntimeError("OSS 未配置")
    return await storage.generate_signed_url(att.oss_key, settings.OSS_SIGNED_URL_EXPIRES)


async def delete_attachment(db: AsyncSession, user_id: str, attachment_id: str) -> None:
    """
    删除附件：只能删自己的 + 未关联反馈的
    """
    result = await db.execute(
        select(FeedbackAttachment).where(FeedbackAttachment.id == attachment_id)
    )
    att = result.scalar_one_or_none()
    if not att:
        raise LookupError("附件不存在")
    if att.uploader_user_id != user_id:
        raise PermissionError("无权操作该附件")
    if att.feedback_id is not None:
        raise ValueError("已提交的反馈截图不能删除")

    # OSS 先删（失败不阻塞 DB 删除，孤儿清理任务会兜底）
    storage = get_storage()
    if storage is not None:
        try:
            await storage.delete(att.oss_key)
        except Exception:
            pass
    await db.delete(att)


async def create_feedback(
    db: AsyncSession,
    user_id: str,
    user_email: str,
    type_: str,
    content: str,
    attachment_ids: List[str],
) -> Feedback:
    """
    创建反馈（事务性）：
    1. 插 feedback
    2. 关联 attachments（回填 feedback_id，校验权限/数量/格式）
    3. 给用户发 auto_ack 通知
    4. 给每个 super_admin 发 feedback_new 通知
    """
    _validate_type(type_)
    _validate_content(content)

    if len(attachment_ids) > MAX_ATTACHMENTS_PER_FEEDBACK:
        raise ValueError(f"最多 {MAX_ATTACHMENTS_PER_FEEDBACK} 张截图")

    # 1. 插 feedback
    feedback = Feedback(
        user_id=user_id,
        user_email=user_email,
        type=type_,
        content=content,
        status="received",
    )
    db.add(feedback)
    await db.flush()  # 拿 id

    # 2. 关联附件
    if attachment_ids:
        result = await db.execute(
            select(FeedbackAttachment).where(
                FeedbackAttachment.id.in_(attachment_ids)
            )
        )
        atts = result.scalars().all()
        for att in atts:
            if att.uploader_user_id != user_id:
                raise PermissionError("附件不属于当前用户")
            if att.feedback_id is not None:
                raise ValueError("附件已关联到其他反馈")
            att.feedback_id = feedback.id
        # 数量校验（防止 attachment_ids 有不存在的 ID 但没匹配上）
        matched = {a.id for a in atts}
        missing = set(attachment_ids) - matched
        if missing:
            raise LookupError(f"附件不存在：{missing}")

    # 3. 给用户发 auto_ack
    user_notif = Notification(
        user_id=user_id,
        type="feedback_auto_ack",
        title=AUTO_ACK_TITLE,
        content=AUTO_ACK_CONTENT,
        read_at=None,
        related_feedback_id=feedback.id,
    )
    db.add(user_notif)

    # 4. 给每个 super_admin 发新反馈通知
    admin_ids = await _get_super_admin_ids(db)
    preview = content if len(content) <= 60 else content[:60] + "…"
    admin_content = (
        f"来自 {user_email} 的 {type_} 反馈：\n\n{preview}\n\n"
        f"请在 admin 后台查看详情，并通过邮件回复用户。"
    )
    for admin_id in admin_ids:
        if admin_id == user_id:
            continue  # 用户本身是 admin，避免自通知
        db.add(
            Notification(
                user_id=admin_id,
                type="feedback_new",
                title=NEW_FEEDBACK_TITLE_FOR_ADMIN,
                content=admin_content,
                read_at=None,
                related_feedback_id=feedback.id,
            )
        )

    await db.flush()
    return feedback


async def admin_list_feedbacks(
    db: AsyncSession,
    type_: Optional[str] = None,
    status_: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[List[Feedback], int]:
    """管理员列表：分页 + 筛选"""
    q = select(Feedback).order_by(Feedback.updated_at.desc())
    if type_:
        q = q.where(Feedback.type == type_)
    if status_:
        q = q.where(Feedback.status == status_)

    # count
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    # page
    q = q.offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(q)).scalars().all()
    return list(items), int(total)


async def admin_get_feedback_detail(
    db: AsyncSession, feedback_id: str
) -> Optional[Tuple[Feedback, List[FeedbackAttachment]]]:
    """管理员拉详情，含所有附件"""
    result = await db.execute(
        select(Feedback).where(Feedback.id == feedback_id)
    )
    feedback = result.scalar_one_or_none()
    if not feedback:
        return None
    att_result = await db.execute(
        select(FeedbackAttachment)
        .where(FeedbackAttachment.feedback_id == feedback_id)
        .order_by(FeedbackAttachment.created_at)
    )
    atts = list(att_result.scalars().all())
    return feedback, atts


async def admin_update_status(
    db: AsyncSession,
    feedback_id: str,
    new_status: str,
    admin_user_id: str,
) -> Feedback:
    """管理员改状态：发 feedback_status_changed 通知给用户"""
    if new_status not in {"received", "in_progress", "done"}:
        raise ValueError("状态无效，应为 received / in_progress / done")

    result = await db.execute(
        select(Feedback).where(Feedback.id == feedback_id)
    )
    feedback = result.scalar_one_or_none()
    if not feedback:
        raise LookupError("反馈不存在")

    old_status = feedback.status
    feedback.status = new_status
    await db.flush()

    if old_status != new_status:
        # 发状态变更通知
        title_map = {
            "in_progress": "【留言反馈】您的反馈处理中",
            "done": "【留言反馈】您的反馈已处理完毕",
            "received": "【留言反馈】您的反馈已重新受理",
        }
        content_map = {
            "in_progress": "管理员已开始处理您的反馈，请留意邮箱。",
            "done": "您的反馈已处理完毕，详情请查看邮件。感谢您的支持！",
            "received": "您的反馈已被重新受理，请留意后续邮件。",
        }
        db.add(
            Notification(
                user_id=feedback.user_id,
                type="feedback_status_changed",
                title=title_map.get(new_status, "【留言反馈】反馈状态已更新"),
                content=content_map.get(new_status, f"反馈状态更新为 {new_status}"),
                read_at=None,
                related_feedback_id=feedback.id,
            )
        )
        await db.flush()

    return feedback


# ---------- 通知查询 ----------


async def get_unread_count(db: AsyncSession, user_id: str) -> int:
    result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
        )
    )
    return int(result.scalar_one())


async def list_notifications(
    db: AsyncSession,
    user_id: str,
    page: int = 1,
    page_size: int = 20,
    unread_only: bool = False,
) -> Tuple[List[Notification], int, int]:
    """
    返回 (items, total, unread_count)
    """
    q = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        q = q.where(Notification.read_at.is_(None))

    total = (
        await db.execute(select(func.count()).select_from(q.subquery()))
    ).scalar_one()

    unread_count = await get_unread_count(db, user_id)

    q = q.order_by(Notification.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)
    items = list((await db.execute(q)).scalars().all())

    return items, int(total), int(unread_count)


async def mark_read(db: AsyncSession, user_id: str, notification_id: str) -> None:
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
    )
    n = result.scalar_one_or_none()
    if not n:
        raise LookupError("通知不存在")
    if n.read_at is None:
        n.read_at = _now()


async def mark_all_read(db: AsyncSession, user_id: str) -> int:
    """全部已读，返回更新行数"""
    result = await db.execute(
        update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=_now())
    )
    return result.rowcount or 0
