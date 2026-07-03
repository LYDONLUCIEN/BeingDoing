"""
Admin 退信黑名单管理 API

接口：
- GET    /admin/bounces          分页列表（支持 email 模糊搜、status/source 过滤）
- POST   /admin/bounces          手动添加（email + 备注，去重）
- DELETE /admin/bounces/{email}  解封（status=unblocked，记录保留）
- POST   /admin/bounces/scan     手动触发一次 IMAP 扫描
- GET    /admin/bounces/stats    统计：总 blocked 数、今日新增数

全部 _is_super_admin 守卫。
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field

from app.api.v1.auth import get_current_user
from app.models.database import AsyncSessionLocal
from app.models.email_bounce import EmailBounce
from app.services.bounce_scanner import BounceScanner
from app.utils.super_admin import is_super_admin_user
from sqlalchemy import func, select

from datetime import datetime, timezone, timedelta

router = APIRouter(prefix="/admin/bounces", tags=["Admin-Bounces"])


def _is_super_admin(user: Optional[dict]) -> bool:
    return is_super_admin_user(user)


# ─── 请求 / 响应模型 ──────────────────────────────────────


class AddBounceRequest(BaseModel):
    """手动添加黑名单请求"""
    email: EmailStr
    reason: Optional[str] = Field(None, max_length=500, description="拉黑原因")
    notes: Optional[str] = Field(None, max_length=500, description="备注")


class BounceItem(BaseModel):
    email: str
    bounce_type: str
    status: str
    bounce_count: int
    last_bounce_at: Optional[str] = None
    reason: Optional[str] = None
    source: str
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class BounceListResponse(BaseModel):
    items: List[BounceItem]
    total: int
    page: int
    page_size: int


class BounceStatsResponse(BaseModel):
    blocked_total: int
    unblocked_total: int
    added_today: int
    by_source: Dict[str, int]


# ─── 路由 ────────────────────────────────────────────────


@router.get("")
async def list_bounces(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: Optional[str] = Query(None, description="按 email 模糊搜索"),
    status: Optional[str] = Query(None, description="blocked | unblocked"),
    source: Optional[str] = Query(None, description="auto | manual"),
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """分页查询黑名单列表"""
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")

    async with AsyncSessionLocal() as db:
        # 基础查询
        base = select(EmailBounce)
        count_base = select(func.count()).select_from(EmailBounce)

        if q:
            like = f"%{q.lower()}%"
            base = base.where(func.lower(EmailBounce.email).like(like))
            count_base = count_base.where(func.lower(EmailBounce.email).like(like))
        if status:
            base = base.where(EmailBounce.status == status)
            count_base = count_base.where(EmailBounce.status == status)
        if source:
            base = base.where(EmailBounce.source == source)
            count_base = count_base.where(EmailBounce.source == source)

        total = (await db.execute(count_base)).scalar() or 0

        offset = (page - 1) * page_size
        rows = (
            await db.execute(
                base.order_by(EmailBounce.updated_at.desc()).offset(offset).limit(page_size)
            )
        ).scalars().all()

        return {
            "items": [_to_dict(r) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }


@router.post("")
async def add_bounce(
    payload: AddBounceRequest,
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """手动添加邮箱到黑名单

    - 严格 email 校验（pydantic EmailStr）
    - 重复添加：已存在则更新 status=blocked，并合并 notes
    """
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")

    em = payload.email.lower().strip()
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        existing = (
            await db.execute(select(EmailBounce).where(EmailBounce.email == em))
        ).scalar_one_or_none()

        if existing:
            # 已存在：合并更新
            existing.status = "blocked"
            existing.source = "manual"
            existing.bounce_type = "hard"
            existing.last_bounce_at = now
            if payload.reason:
                existing.reason = payload.reason
            if payload.notes:
                old_notes = existing.notes or ""
                existing.notes = (old_notes + "\n" + payload.notes) if old_notes else payload.notes
            existing.updated_at = now
            await db.commit()
            return {"email": em, "action": "updated", "item": _to_dict(existing)}

        # 新增
        row = EmailBounce(
            email=em,
            bounce_type="hard",
            status="blocked",
            bounce_count=1,
            last_bounce_at=now,
            reason=payload.reason,
            source="manual",
            notes=payload.notes,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        await db.commit()
        return {"email": em, "action": "created", "item": _to_dict(row)}


@router.delete("/{email}")
async def unblock_bounce(
    email: str,
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """解封邮箱（status=unblocked，记录保留）

    下次扫描如果再退信，hard 会重新 block；soft 继续累计。
    """
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")

    em = email.lower().strip()
    async with AsyncSessionLocal() as db:
        existing = (
            await db.execute(select(EmailBounce).where(EmailBounce.email == em))
        ).scalar_one_or_none()
        if not existing:
            raise HTTPException(status_code=404, detail="该邮箱不在黑名单记录中")

        existing.status = "unblocked"
        existing.updated_at = datetime.now(timezone.utc)
        await db.commit()
        return {"email": em, "status": "unblocked"}


@router.post("/scan")
async def trigger_scan(
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """手动触发一次 IMAP 扫描

    同步等待结果返回（扫描可能耗时 5-30 秒）。
    """
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")

    result = await BounceScanner.scan_once()
    return result


@router.get("/stats")
async def get_stats(
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """统计信息"""
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    async with AsyncSessionLocal() as db:
        blocked_total = (
            await db.execute(
                select(func.count()).select_from(EmailBounce).where(
                    EmailBounce.status == "blocked"
                )
            )
        ).scalar() or 0

        unblocked_total = (
            await db.execute(
                select(func.count()).select_from(EmailBounce).where(
                    EmailBounce.status == "unblocked"
                )
            )
        ).scalar() or 0

        added_today = (
            await db.execute(
                select(func.count()).select_from(EmailBounce).where(
                    EmailBounce.created_at >= today_start
                )
            )
        ).scalar() or 0

        # 按 source 分组
        source_rows = (
            await db.execute(
                select(EmailBounce.source, func.count()).group_by(EmailBounce.source)
            )
        ).all()
        by_source = {r[0]: r[1] for r in source_rows}

        return {
            "blocked_total": blocked_total,
            "unblocked_total": unblocked_total,
            "added_today": added_today,
            "by_source": by_source,
        }


# ─── 工具函数 ────────────────────────────────────────────


def _to_dict(row: EmailBounce) -> Dict[str, Any]:
    return {
        "email": row.email,
        "bounce_type": row.bounce_type,
        "status": row.status,
        "bounce_count": row.bounce_count,
        "last_bounce_at": row.last_bounce_at.isoformat() if row.last_bounce_at else None,
        "reason": row.reason,
        "source": row.source,
        "notes": row.notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
