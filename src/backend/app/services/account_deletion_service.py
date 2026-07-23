"""
账户注销 / 到期清除服务

流程：
1. 用户发起注销（request_deletion）：置 is_active=False、deleted_at、deletion_purge_after，
   撤销全部 refresh token，写审计 requested；retention==0 时立即物理清除。
2. 冷存期内用户可通过邮箱验证码恢复（auth_service 中实现，恢复后写审计 recovered）。
3. 后台任务每小时扫描到期账户，purge_expired_accounts 逐个物理清除（purge_account），
   先写审计 purged（含 email，因为用户行马上没了），最后删 users 行。

审计日志：data/account_deletion_audit.jsonl（append-only，每行 JSON）。
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select, update

from app.config.settings import settings
from app.models.database import AsyncSessionLocal
from app.models.email_bounce import EmailBounce
from app.models.feedback import Feedback, Notification
from app.models.llm_model_config import UserLlmModelConfig
from app.models.notification import NotificationRecipient
from app.models.payment import ConsultationBooking
from app.models.refresh_token import RefreshToken
from app.models.rumination_ab import RuminationAbAssignment
from app.models.selection import UserSelection
from app.models.session import Session
from app.models.user import ProjectExperience, User, UserProfile, WorkHistory
from app.utils.data_paths import get_project_data_dir, get_user_data_dir
from app.utils.simple_activation_manager import SimpleActivationManager, get_simple_base_dir

logger = logging.getLogger(__name__)

# ---- 审计事件类型 ----
EVENT_REQUESTED = "requested"  # 用户发起注销
EVENT_RECOVERED = "recovered"  # 用户恢复账户
EVENT_PURGED = "purged"  # 到期物理清除


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _audit_path() -> Path:
    return get_project_data_dir() / "account_deletion_audit.jsonl"


def append_account_deletion_audit(
    event: str,
    user_id: str,
    email: Optional[str] = None,
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    """追加一条账户注销审计日志（JSONL，写入失败只记日志不阻断）。"""
    entry: Dict[str, Any] = {
        "event": event,
        "user_id": user_id,
        "email": email,
        "timestamp": _now().isoformat(),
    }
    if detail:
        entry["detail"] = detail

    p = _audit_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        logger.exception("写入账户注销审计日志失败: user_id=%s event=%s", user_id, event)


class AccountDeletionService:
    """账户注销与到期清除服务"""

    @classmethod
    async def request_deletion(cls, user_id: str) -> datetime:
        """
        标记账户注销：is_active=False + deleted_at/deletion_purge_after +
        撤销全部未撤销 refresh token + 审计 requested。
        retention==0 时同步立即执行物理清除。

        Returns:
            deletion_purge_after（立即清除时为注销当下时间）
        """
        retention = float(getattr(settings, "ACCOUNT_DELETION_RETENTION_DAYS", 30.0) or 0.0)
        now = _now()
        purge_after = now + timedelta(days=retention)

        async with AsyncSessionLocal() as db:
            user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
            if not user:
                raise ValueError("用户不存在")
            user.is_active = False
            user.deleted_at = now
            user.deletion_purge_after = purge_after
            email = user.email

            # 撤销该用户全部未撤销 refresh token
            tokens = (
                (
                    await db.execute(
                        select(RefreshToken).where(
                            RefreshToken.user_id == user_id,
                            RefreshToken.is_revoked.is_(False),
                        )
                    )
                )
                .scalars()
                .all()
            )
            for rec in tokens:
                rec.is_revoked = True
                rec.revoked_at = now
                rec.revoked_reason = "account_deleted"
            await db.commit()

        append_account_deletion_audit(
            EVENT_REQUESTED,
            user_id,
            email,
            detail={"purge_after": purge_after.isoformat()},
        )

        if retention <= 0:
            await cls.purge_account(user_id, email)

        return purge_after

    @classmethod
    async def purge_expired_accounts(cls) -> int:
        """
        扫描 deleted_at 非空且 deletion_purge_after <= now 的用户，逐个物理清除。
        单个用户清除失败只记日志，不影响其余用户。

        Returns:
            成功清除的账户数
        """
        # SQLite 存储为 naive datetime，比较时用 naive UTC（与支付关单逻辑一致）
        now_naive = _now().replace(tzinfo=None)
        async with AsyncSessionLocal() as db:
            rows = (
                (
                    await db.execute(
                        select(User).where(
                            User.deleted_at.isnot(None),
                            User.deletion_purge_after.isnot(None),
                            User.deletion_purge_after <= now_naive,
                        )
                    )
                )
                .scalars()
                .all()
            )
            candidates = [(u.id, u.email) for u in rows]

        purged = 0
        for user_id, email in candidates:
            try:
                await cls.purge_account(user_id, email)
                purged += 1
            except Exception as e:
                logger.exception("账户到期清除失败: user_id=%s err=%s", user_id, e)
        if purged:
            logger.info("账户到期清除完成，共清除 %d 个账户", purged)
        return purged

    @classmethod
    async def purge_account(cls, user_id: str, email: Optional[str] = None) -> None:
        """
        物理清除单个账户（三层）：
        1. 文件删除：data/user/{user_id}/、名下激活码及会话目录、名下报告目录
        2. 物理删除 DB 行（各业务表）
        3. 匿名化保留：consultation_bookings.contact / feedbacks.user_email 清空；
           payment_orders/coupons/subscriptions/analytics_* 原样保留（user_id 是 uuid 不构成 PII）
        先写审计 purged（含 email），最后删 users 行。

        注意：data/backups/、data/simple/reports_archive/、
        data/simple/activation_audit.jsonl 一律不动。
        """
        async with AsyncSessionLocal() as db:
            if email is None:
                user = (
                    await db.execute(select(User).where(User.id == user_id))
                ).scalar_one_or_none()
                if not user:
                    return
                email = user.email

        # 1. 文件删除（先做：失败抛异常时用户行保留，下个周期可重试）
        file_detail = cls._purge_user_files(user_id)

        async with AsyncSessionLocal() as db:
            # 2. 物理删除 DB 行
            # project_experiences 连带 work_history 删除
            wh_ids = select(WorkHistory.id).where(WorkHistory.user_id == user_id)
            await db.execute(
                delete(ProjectExperience).where(ProjectExperience.work_history_id.in_(wh_ids))
            )
            await db.execute(delete(WorkHistory).where(WorkHistory.user_id == user_id))
            await db.execute(delete(UserProfile).where(UserProfile.user_id == user_id))
            await db.execute(delete(Session).where(Session.user_id == user_id))
            await db.execute(delete(UserSelection).where(UserSelection.user_id == user_id))
            await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))
            await db.execute(delete(Notification).where(Notification.user_id == user_id))
            await db.execute(
                delete(NotificationRecipient).where(NotificationRecipient.user_id == user_id)
            )
            await db.execute(
                delete(UserLlmModelConfig).where(UserLlmModelConfig.user_id == user_id)
            )
            await db.execute(
                delete(RuminationAbAssignment).where(RuminationAbAssignment.user_id == user_id)
            )
            email_norm = (email or "").strip().lower()
            if email_norm:
                await db.execute(delete(EmailBounce).where(EmailBounce.email == email_norm))

            # 3. 匿名化保留（行保留，清掉联系方式/邮箱）
            await db.execute(
                update(ConsultationBooking)
                .where(ConsultationBooking.user_id == user_id)
                .values(contact=None)
            )
            await db.execute(
                update(Feedback).where(Feedback.user_id == user_id).values(user_email="")
            )

            # 4. 先写审计 purged（含 email，因为用户行马上没了），最后删 users 行
            append_account_deletion_audit(EVENT_PURGED, user_id, email, detail=file_detail)
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()

        logger.info("账户已物理清除: user_id=%s", user_id)

    @staticmethod
    def _purge_user_files(user_id: str) -> Dict[str, Any]:
        """
        删除用户相关文件，返回删除明细（写入审计 detail）：
        - data/user/{user_id}/ 整个目录
        - activations.json 中 owner_user_id == user_id 的码（只删自己名下的，
          已送出的赠品码 owner 已是别人，不动），并删 data/simple/{session_id}/
        - data/simple/reports/*/record.json 中 user_id 匹配的报告目录
        """
        detail: Dict[str, Any] = {}

        # data/user/{user_id}/
        try:
            user_dir = get_user_data_dir() / user_id
            if user_dir.is_dir():
                shutil.rmtree(user_dir, ignore_errors=True)
                detail["user_dir_removed"] = True
        except OSError as e:
            logger.warning("删除用户目录失败: user_id=%s err=%s", user_id, e)

        # 名下激活码 + 会话目录
        base = get_simple_base_dir()
        removed_codes: List[str] = []
        try:
            mgr = SimpleActivationManager(base_dir=str(base))
            records = mgr._load_all()
            owned = {
                code: rec for code, rec in records.items() if (rec.owner_user_id or "") == user_id
            }
            for code, rec in owned.items():
                sess_dir = base / (rec.session_id or "")
                if rec.session_id and sess_dir.is_dir():
                    shutil.rmtree(sess_dir, ignore_errors=True)
                records.pop(code, None)
                removed_codes.append(code)
            if removed_codes:
                mgr._save_all(records)
        except Exception as e:
            logger.warning("清理名下激活码失败: user_id=%s err=%s", user_id, e)
        detail["activation_codes_removed"] = removed_codes

        # 名下报告目录（按 record.json 的 user_id 匹配）
        removed_reports: List[str] = []
        try:
            reports_root = base / "reports"
            if reports_root.is_dir():
                for d in reports_root.iterdir():
                    if not d.is_dir():
                        continue
                    rf = d / "record.json"
                    if not rf.is_file():
                        continue
                    try:
                        rec_data = json.loads(rf.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError, TypeError):
                        continue
                    if (rec_data.get("user_id") or "") == user_id:
                        shutil.rmtree(d, ignore_errors=True)
                        removed_reports.append(d.name)
        except OSError as e:
            logger.warning("清理名下报告目录失败: user_id=%s err=%s", user_id, e)
        detail["reports_removed"] = removed_reports

        return detail
