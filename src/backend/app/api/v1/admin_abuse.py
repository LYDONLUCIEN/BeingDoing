"""
Admin 滥用检测管理 API

接口：
- GET  /admin/abuse/config                    读运行时配置（含默认值与合法范围）
- POST /admin/abuse/config                    部分更新运行时配置（即时生效）
- GET  /admin/abuse/users                     处置状态分页列表（warned/frozen 过滤）
- GET  /admin/abuse/users/{user_id}/events    该用户事件流水（倒序分页）
- POST /admin/abuse/users/{user_id}/unfreeze  解冻（恢复激活码 + 清状态 + 站内信）

全部 is_super_admin_user 门控，统一响应 {code, message, data}。
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.v1.auth import get_current_user
from app.models.abuse import AbuseEvent, AbuseState
from app.models.database import AsyncSessionLocal
from app.models.user import User
from app.services import abuse_config, abuse_service
from app.utils.super_admin import is_super_admin_user

router = APIRouter(prefix="/admin", tags=["Admin-Abuse"])


def _ok(data: Any) -> Dict[str, Any]:
    return {"code": 200, "message": "success", "data": data}


def _require_super_admin(current_user: Optional[dict]) -> None:
    if not is_super_admin_user(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")


# ===================== Schemas =====================


class AbuseConfigUpdateRequest(BaseModel):
    """滥用检测配置部分更新（全部可选，只更新传入字段）"""

    enabled: Optional[bool] = Field(None, description="检测总开关")
    msg_per_minute: Optional[int] = Field(None, description="1 分钟内用户消息条数阈值")
    msg_per_hour: Optional[int] = Field(None, description="1 小时内用户消息条数阈值")
    msg_per_day: Optional[int] = Field(None, description="1 天内用户消息条数阈值")
    token_lifetime: Optional[int] = Field(None, description="单用户累计 token 阈值")
    thread_delete_per_phase: Optional[int] = Field(
        None, description="同一 phase 累计删除对话次数阈值"
    )


# ===================== 配置 =====================


@router.get("/abuse/config")
async def get_abuse_config(
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """读滥用检测运行时配置"""
    _require_super_admin(current_user)
    return _ok(
        {
            "config": abuse_config.get_config(),
            "defaults": dict(abuse_config.DEFAULTS),
            "ranges": {
                "min": abuse_config.MIN_THRESHOLD,
                "max": abuse_config.MAX_THRESHOLD,
            },
        }
    )


@router.post("/abuse/config")
async def set_abuse_config(
    payload: AbuseConfigUpdateRequest,
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """部分更新滥用检测配置（即时生效）"""
    _require_super_admin(current_user)
    partial = payload.model_dump(exclude_none=True)
    if not partial:
        raise HTTPException(status_code=400, detail="至少提供一个配置项")
    try:
        cfg = abuse_config.set_config(partial)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _ok({"config": cfg})


# ===================== 用户处置状态 =====================


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


@router.get("/abuse/users")
async def list_abuse_users(
    status: Optional[str] = Query(None, description="warned | frozen；空 = 全部"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """滥用处置状态分页列表（含 24h 消息数与累计删除数聚合）"""
    _require_super_admin(current_user)
    if status is not None and status not in ("warned", "frozen"):
        raise HTTPException(status_code=400, detail="status 仅支持 warned | frozen")

    async with AsyncSessionLocal() as db:
        conds = []
        if status:
            conds.append(AbuseState.status == status)
        total = int(
            (await db.execute(select(func.count(AbuseState.id)).where(*conds))).scalar_one()
        )
        rows = (
            (
                await db.execute(
                    select(AbuseState)
                    .where(*conds)
                    .order_by(AbuseState.updated_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            .scalars()
            .all()
        )

        user_ids = [r.user_id for r in rows]
        user_map: Dict[str, Any] = {}
        if user_ids:
            urows = (
                await db.execute(
                    select(User.id, User.username, User.email).where(User.id.in_(user_ids))
                )
            ).all()
            user_map = {u.id: u for u in urows}

        # 聚合：24h 消息数 + 累计删除数（只查本页用户）
        since_24h = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)
        msg_counts: Dict[str, int] = {}
        del_counts: Dict[str, int] = {}
        if user_ids:
            for row in (
                await db.execute(
                    select(AbuseEvent.user_id, func.count(AbuseEvent.id))
                    .where(
                        AbuseEvent.user_id.in_(user_ids),
                        AbuseEvent.event_type == "message",
                        AbuseEvent.created_at >= since_24h,
                    )
                    .group_by(AbuseEvent.user_id)
                )
            ).all():
                msg_counts[row[0]] = int(row[1])
            for row in (
                await db.execute(
                    select(AbuseEvent.user_id, func.count(AbuseEvent.id))
                    .where(
                        AbuseEvent.user_id.in_(user_ids),
                        AbuseEvent.event_type == "thread_delete",
                    )
                    .group_by(AbuseEvent.user_id)
                )
            ).all():
                del_counts[row[0]] = int(row[1])

        items = [
            {
                "user_id": r.user_id,
                "username": getattr(user_map.get(r.user_id), "username", None),
                "email": getattr(user_map.get(r.user_id), "email", None),
                "status": r.status,
                "warned_at": _iso(r.warned_at),
                "warned_rule": r.warned_rule,
                "frozen_at": _iso(r.frozen_at),
                "frozen_rule": r.frozen_rule,
                "frozen_activation_code": r.frozen_activation_code,
                "messages_24h": msg_counts.get(r.user_id, 0),
                "deletes_total": del_counts.get(r.user_id, 0),
            }
            for r in rows
        ]
    return _ok({"items": items, "total": total})


@router.get("/abuse/users/{user_id}/events")
async def list_abuse_user_events(
    user_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """该用户事件流水（倒序分页）"""
    _require_super_admin(current_user)
    async with AsyncSessionLocal() as db:
        total = int(
            (
                await db.execute(
                    select(func.count(AbuseEvent.id)).where(AbuseEvent.user_id == user_id)
                )
            ).scalar_one()
        )
        rows = (
            (
                await db.execute(
                    select(AbuseEvent)
                    .where(AbuseEvent.user_id == user_id)
                    .order_by(AbuseEvent.created_at.desc(), AbuseEvent.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            .scalars()
            .all()
        )
        items = [
            {
                "id": e.id,
                "event_type": e.event_type,
                "phase": e.phase,
                "detail": e.detail,
                "created_at": _iso(e.created_at),
            }
            for e in rows
        ]
    return _ok({"items": items, "total": total})


@router.post("/abuse/users/{user_id}/unfreeze")
async def unfreeze_abuse_user(
    user_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """解冻用户：恢复被 revoke 的激活码、删除状态行、清内存缓存、发站内信"""
    _require_super_admin(current_user)
    result = await abuse_service.unfreeze_user(
        user_id, actor_user_id=(current_user or {}).get("user_id")
    )
    return _ok(result)
