"""
用户滥用检测与处置核心服务。

状态机：正常 → 任一规则首次触发 → warned（429 + 站内信 + 邮件）→
之后再次触发任一规则 → frozen（403 + revoke 激活码 + 通知超管）→ admin 裁决恢复。

设计要点：
- 冻结态走模块级内存 dict（_frozen_users）做热路径门控，同步零 DB 开销；
  服务启动时从 DB 加载（main.py startup 调 load_frozen_users），freeze/unfreeze 同步双写。
- record_and_check_* 对「异常错误」一律放行（fail-open，记日志），
  只有明确命中阈值才 raise 429/403 —— DB 抖动不能阻断主聊天流程。
- 通知/邮件全部尽力而为：失败只记日志，不影响状态机推进。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.abuse import AbuseEvent, AbuseState
from app.models.database import AsyncSessionLocal
from app.models.feedback import Notification
from app.models.llm_usage import LlmUsageLog
from app.models.user import User
from app.services import abuse_config
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)

# ── 冻结态内存缓存（user_id → {rule, frozen_at, code}）──────────────────
_frozen_users: Dict[str, Dict[str, Any]] = {}


def _utcnow() -> datetime:
    """UTC naive 时间（与 abuse_events.created_at 的存储/比较口径一致）"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def is_frozen(user_id: str) -> Optional[Dict[str, Any]]:
    """同步查询用户是否处于冻结态（纯内存，供写端点门控热路径使用）。"""
    if not user_id:
        return None
    return _frozen_users.get(user_id)


def build_frozen_exception(rule: Optional[str] = None) -> HTTPException:
    """冻结态 403 异常（detail 为 JSON 字符串，前端按 type 识别）。"""
    return HTTPException(
        status_code=403,
        detail=json.dumps(
            {
                "type": "abuse_frozen",
                "rule": rule,
                "message": "账号存在异常操作，聊天功能已冻结，请联系管理员",
            },
            ensure_ascii=False,
        ),
    )


def build_warning_exception(rule: Optional[str] = None) -> HTTPException:
    """警告态 429 异常（detail 为 JSON 字符串，前端按 type 识别）。"""
    return HTTPException(
        status_code=429,
        detail=json.dumps(
            {
                "type": "abuse_warning",
                "rule": rule,
                "message": "操作过于频繁，请稍后再试；持续异常操作将导致账号功能被冻结",
            },
            ensure_ascii=False,
        ),
    )


async def load_frozen_users() -> int:
    """服务启动时从 DB 加载全部冻结用户到内存。失败只记日志，不阻断启动。"""
    try:
        async with AsyncSessionLocal() as db:
            rows = (
                (await db.execute(select(AbuseState).where(AbuseState.status == "frozen")))
                .scalars()
                .all()
            )
        _frozen_users.clear()
        for s in rows:
            _frozen_users[s.user_id] = {
                "rule": s.frozen_rule,
                "frozen_at": s.frozen_at.isoformat() if s.frozen_at else None,
                "code": s.frozen_activation_code,
            }
        if rows:
            logger.info("abuse: 已加载 %d 个冻结用户到内存", len(rows))
        return len(rows)
    except Exception as e:
        logger.warning("abuse: 加载冻结用户失败（不影响启动）: %s", e)
        return 0


# ── 通知与邮件（全部尽力而为）─────────────────────────────────────────


async def _notify_user(
    db: AsyncSession, user_id: str, ntype: str, title: str, content: str
) -> None:
    """给用户发站内信（失败只记日志）。"""
    try:
        db.add(Notification(user_id=user_id, type=ntype, title=title, content=content))
        await db.commit()
    except Exception as e:
        logger.warning("abuse: 用户站内信发送失败 user=%s type=%s: %s", user_id, ntype, e)
        try:
            await db.rollback()
        except Exception:
            pass


async def _notify_super_admins(db: AsyncSession, title: str, content: str) -> None:
    """给所有 super_admin 发站内信（失败只记日志）。"""
    try:
        from app.services.feedback_service import _get_super_admin_ids  # 延迟导入避免环

        admin_ids = await _get_super_admin_ids(db)
        if not admin_ids:
            logger.warning("abuse: 未找到 super_admin，跳过冻结告警通知")
            return
        for admin_id in admin_ids:
            db.add(
                Notification(
                    user_id=admin_id,
                    type="abuse_frozen_admin",
                    title=title,
                    content=content,
                )
            )
        await db.commit()
    except Exception as e:
        logger.warning("abuse: 超管站内信发送失败: %s", e)
        try:
            await db.rollback()
        except Exception:
            pass


async def _get_user_email(db: AsyncSession, user_id: str) -> Optional[str]:
    try:
        return (await db.execute(select(User.email).where(User.id == user_id))).scalar_one_or_none()
    except Exception:
        return None


async def _send_user_email(db: AsyncSession, user_id: str, subject: str, body: str) -> None:
    """给用户发邮件（未配置 SMTP / 用户无邮箱 / 发送失败都只记日志）。"""
    try:
        email = await _get_user_email(db, user_id)
        if not email:
            return
        await EmailService.send_email(to_email=email, subject=subject, body_text=body)
    except Exception as e:
        logger.warning("abuse: 邮件发送失败 user=%s subject=%s: %s", user_id, subject, e)


# ── 状态机推进 ───────────────────────────────────────────────────────


def _revoke_activation_code(code: Optional[str]) -> None:
    """revoke 激活码（失败只记日志，不阻断冻结）。"""
    if not code:
        return
    try:
        from app.utils.simple_activation_manager import get_activation_manager_for_code

        manager = get_activation_manager_for_code(code)
        changed = manager.update_status(
            [code], "revoked", actor={"user_id": "system", "note": "abuse_freeze"}
        )
        logger.info("abuse: revoke 激活码 %s，changed=%d", code, changed)
    except Exception as e:
        logger.warning("abuse: revoke 激活码失败 code=%s: %s", code, e)


async def _escalate(
    db: AsyncSession,
    user_id: str,
    rule: str,
    detail: Dict[str, Any],
    activation_code: Optional[str],
) -> None:
    """状态机推进：已 frozen → 403；已 warned → 冻结并 403；否则 → 警告并 429。"""
    state = (
        await db.execute(select(AbuseState).where(AbuseState.user_id == user_id))
    ).scalar_one_or_none()
    now = _utcnow()

    # 已冻结：直接 403（防御性——正常路径在门控处已被内存拦截）
    if state is not None and state.status == "frozen":
        raise build_frozen_exception(rule)

    # 已警告 → 冻结
    if state is not None and state.status == "warned":
        state.status = "frozen"
        state.frozen_at = now
        state.frozen_rule = rule
        state.frozen_activation_code = activation_code
        await db.commit()
        _frozen_users[user_id] = {
            "rule": rule,
            "frozen_at": now.isoformat(),
            "code": activation_code,
        }
        _revoke_activation_code(activation_code)

        username = await _get_username(db, user_id)
        email = await _get_user_email(db, user_id)
        await _notify_user(
            db,
            user_id,
            "abuse_frozen",
            "账号功能已被冻结",
            "系统检测到您的账号持续存在异常操作，聊天功能已被冻结。"
            "如有疑问请联系管理员（openlife.lab@outlook.com）。",
        )
        await _send_user_email(
            db,
            user_id,
            "【寻路·OpenLife】账号功能已被冻结",
            "您好，\n\n系统检测到您的账号持续存在异常操作，聊天功能已被冻结。\n"
            "如有疑问请联系管理员（openlife.lab@outlook.com）。\n",
        )
        await _notify_super_admins(
            db,
            "用户滥用已被自动冻结",
            f"用户 {user_id}（username={username}，email={email}）"
            f"再次触发滥用规则 {rule}，已自动冻结。\n"
            f"触发详情：{json.dumps(detail, ensure_ascii=False)}\n"
            f"已 revoke 激活码：{activation_code or '（无）'}\n"
            "请前往管理后台「滥用检测」页裁决是否恢复。",
        )
        logger.warning("abuse: 用户已冻结 user=%s rule=%s code=%s", user_id, rule, activation_code)
        raise build_frozen_exception(rule)

    # 首次触发 → 警告
    if state is None:
        state = AbuseState(user_id=user_id, status="warned", warned_at=now, warned_rule=rule)
        db.add(state)
    else:
        state.status = "warned"
        state.warned_at = now
        state.warned_rule = rule
    await db.commit()
    await _notify_user(
        db,
        user_id,
        "abuse_warning",
        "操作频率异常提醒",
        "系统检测到您的账号操作过于频繁（如短时间内大量发送消息或反复删除对话）。"
        "请稍后再试；持续异常操作将导致账号功能被冻结。",
    )
    await _send_user_email(
        db,
        user_id,
        "【寻路·OpenLife】操作频率异常提醒",
        "您好，\n\n系统检测到您的账号操作过于频繁，请稍后再试。\n"
        "持续异常操作将导致账号功能被冻结。\n",
    )
    logger.info("abuse: 用户已警告 user=%s rule=%s", user_id, rule)
    raise build_warning_exception(rule)


async def _get_username(db: AsyncSession, user_id: str) -> Optional[str]:
    try:
        return (
            await db.execute(select(User.username).where(User.id == user_id))
        ).scalar_one_or_none()
    except Exception:
        return None


# ── 事件记录与阈值检查 ────────────────────────────────────────────────

# 消息速率窗口规则：(规则名, 窗口秒数)
_MSG_WINDOW_RULES = (
    ("msg_per_minute", 60),
    ("msg_per_hour", 3600),
    ("msg_per_day", 86400),
)


async def _check_message_rules(
    db: AsyncSession, user_id: str, cfg: Dict[str, Any]
) -> Optional[tuple]:
    """聚合检查消息速率与累计 token 规则。返回 (rule, detail) 或 None。"""
    now = _utcnow()
    for rule, window_seconds in _MSG_WINDOW_RULES:
        threshold = cfg.get(rule, abuse_config.DEFAULTS[rule])
        count = int(
            (
                await db.execute(
                    select(func.count(AbuseEvent.id)).where(
                        AbuseEvent.user_id == user_id,
                        AbuseEvent.event_type == "message",
                        AbuseEvent.created_at >= now - timedelta(seconds=window_seconds),
                    )
                )
            ).scalar_one()
        )
        if count > threshold:
            return rule, {"count": count, "threshold": threshold, "window_seconds": window_seconds}

    token_threshold = cfg.get("token_lifetime", abuse_config.DEFAULTS["token_lifetime"])
    total_tokens = int(
        (
            await db.execute(
                select(
                    func.coalesce(
                        func.sum(LlmUsageLog.prompt_tokens + LlmUsageLog.completion_tokens), 0
                    )
                ).where(LlmUsageLog.user_id == user_id)
            )
        ).scalar_one()
        or 0
    )
    if total_tokens > token_threshold:
        return "token_lifetime", {"total_tokens": total_tokens, "threshold": token_threshold}
    return None


async def record_and_check_message(
    user_id: str, activation_code: Optional[str], phase: Optional[str]
) -> None:
    """记录一条用户消息事件并做阈值检查。

    命中阈值时按状态机 raise 429（首次警告）/ 403（冻结）；
    其他一切异常（DB 抖动等）只记日志、放行（fail-open，不阻断主聊天流程）。
    """
    if not user_id:
        return
    cfg = abuse_config.get_config()
    if not cfg.get("enabled", True):
        return
    # 冻结态短路（内存判断，防御性——路由层门控已先行拦截）
    if is_frozen(user_id):
        raise build_frozen_exception((_frozen_users.get(user_id) or {}).get("rule"))
    try:
        await _record_and_check_message_inner(user_id, activation_code, phase, cfg)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("abuse: 消息检查异常（放行）user=%s: %s", user_id, e, exc_info=True)


async def _record_and_check_message_inner(
    user_id: str, activation_code: Optional[str], phase: Optional[str], cfg: Dict[str, Any]
) -> None:
    async with AsyncSessionLocal() as db:
        db.add(
            AbuseEvent(
                user_id=user_id,
                event_type="message",
                phase=(phase or None),
                created_at=_utcnow(),
            )
        )
        await db.flush()  # 让本次事件计入窗口聚合
        triggered = await _check_message_rules(db, user_id, cfg)
        if not triggered:
            await db.commit()
            return
        rule, detail = triggered
        # 事件与状态机在同一事务里落库后再推进
        await _escalate(db, user_id, rule, detail, activation_code)


async def record_and_check_thread_delete(
    user_id: str, activation_code: Optional[str], phase: Optional[str]
) -> None:
    """记录一次删除对话事件并检查同 phase 累计删除阈值。

    命中阈值时按状态机 raise 429/403；其他异常 fail-open。
    注意：调用点删除动作已完成，escalate 抛错不回滚删除（产品口径可接受）。
    """
    if not user_id:
        return
    cfg = abuse_config.get_config()
    if not cfg.get("enabled", True):
        return
    if is_frozen(user_id):
        raise build_frozen_exception((_frozen_users.get(user_id) or {}).get("rule"))
    try:
        await _record_and_check_thread_delete_inner(user_id, activation_code, phase, cfg)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("abuse: 删除检查异常（放行）user=%s: %s", user_id, e, exc_info=True)


async def _record_and_check_thread_delete_inner(
    user_id: str, activation_code: Optional[str], phase: Optional[str], cfg: Dict[str, Any]
) -> None:
    threshold = cfg.get("thread_delete_per_phase", abuse_config.DEFAULTS["thread_delete_per_phase"])
    async with AsyncSessionLocal() as db:
        db.add(
            AbuseEvent(
                user_id=user_id,
                event_type="thread_delete",
                phase=(phase or None),
                created_at=_utcnow(),
            )
        )
        await db.flush()
        count = int(
            (
                await db.execute(
                    select(func.count(AbuseEvent.id)).where(
                        AbuseEvent.user_id == user_id,
                        AbuseEvent.event_type == "thread_delete",
                        AbuseEvent.phase == (phase or None),
                    )
                )
            ).scalar_one()
        )
        if count <= threshold:
            await db.commit()
            return
        await _escalate(
            db,
            user_id,
            "thread_delete_per_phase",
            {"count": count, "threshold": threshold, "phase": phase},
            activation_code,
        )


# ── admin 解冻 ───────────────────────────────────────────────────────


async def unfreeze_user(user_id: str, actor_user_id: Optional[str] = None) -> Dict[str, Any]:
    """解冻用户：恢复被 revoke 的激活码、删除状态行、清内存、发站内信。

    Returns:
        {"user_id": ..., "status": "normal", "restored_code": Optional[str]}
    """
    restored_code: Optional[str] = None
    async with AsyncSessionLocal() as db:
        state = (
            await db.execute(select(AbuseState).where(AbuseState.user_id == user_id))
        ).scalar_one_or_none()

        if state is not None and state.status == "frozen" and state.frozen_activation_code:
            code = state.frozen_activation_code
            try:
                from app.utils.simple_activation_manager import (
                    get_activation_manager_for_code,
                )

                manager = get_activation_manager_for_code(code)
                rec = manager.get_activation(code)
                if rec is not None and getattr(rec, "status", None) == "revoked":
                    manager.update_status(
                        [code],
                        "active",
                        actor={"user_id": actor_user_id or "system", "note": "abuse_unfreeze"},
                    )
                    restored_code = code
            except Exception as e:
                logger.warning("abuse: 解冻恢复激活码失败 user=%s code=%s: %s", user_id, code, e)

        if state is not None:
            await db.delete(state)
            await db.commit()

        await _notify_user(
            db,
            user_id,
            "abuse_unfrozen",
            "账号已解冻",
            "您的账号聊天功能已恢复正常，可以继续使用。请注意保持正常使用频率。",
        )

    _frozen_users.pop(user_id, None)
    logger.info("abuse: 用户已解冻 user=%s restored_code=%s", user_id, restored_code)
    return {"user_id": user_id, "status": "normal", "restored_code": restored_code}
