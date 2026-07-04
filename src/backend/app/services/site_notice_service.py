"""
站内公告服务

职责：
1. list_active: 查询当前生效的公告（时间窗口内 + is_active）
2. admin CRUD: list / get / create / update / delete / toggle

设计要点：
- channels_json 在表里是 Text（JSON 字符串），service 层负责 dict<->str 序列化
- 时间比较用 UTC now，前端展示时自行转时区
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from app.models.database import AsyncSessionLocal
from app.models.site_notice import SiteNotice

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_channels(raw: Optional[str]) -> List[Dict[str, Any]]:
    """channels_json Text -> list[dict]，失败返回 []"""
    if not raw:
        return []
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else []
    except Exception:
        logger.warning("site_notice channels_json 反序列化失败: %s", raw[:80])
        return []


def _serialize(notice: SiteNotice) -> Dict[str, Any]:
    """ORM 对象 -> API 返回 dict"""
    return {
        "id": notice.id,
        "type": notice.type,
        "title": notice.title,
        "content_md": notice.content_md or "",
        "severity": notice.severity,
        "start_at": notice.start_at.isoformat() if notice.start_at else None,
        "end_at": notice.end_at.isoformat() if notice.end_at else None,
        "dismissible": bool(notice.dismissible),
        "is_active": bool(notice.is_active),
        "channels": _parse_channels(notice.channels_json),
        "created_at": notice.created_at.isoformat() if notice.created_at else None,
        "updated_at": notice.updated_at.isoformat() if notice.updated_at else None,
    }


class SiteNoticeService:
    """站内公告服务"""

    @staticmethod
    async def list_active(
        *,
        notice_type: str = "banner",
        now: Optional[datetime] = None,
        limit: int = 1,
    ) -> List[Dict[str, Any]]:
        """查询当前生效的公告

        条件：is_active=True 且 type 匹配 且 当前时间落在 [start_at, end_at] 内
        start_at 为空视为 -∞，end_at 为空视为 +∞
        排序：severity（urgent>warn>info）desc, start_at desc
        """
        n = now or _utcnow()
        severity_order = {"urgent": 3, "warn": 2, "info": 1}

        async with AsyncSessionLocal() as db:
            stmt = select(SiteNotice).where(
                SiteNotice.is_active.is_(True),
                SiteNotice.type == notice_type,
            )
            result = await db.execute(stmt)
            rows = result.scalars().all()

        def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
            """SQLite 取回的 naive datetime 当作 UTC 处理"""
            if dt is None:
                return None
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt

        # 时间窗口过滤（Python 端做，避免 SQLite 时区坑）
        def _in_window(r: SiteNotice) -> bool:
            s, e = _as_utc(r.start_at), _as_utc(r.end_at)
            if s and n < s:
                return False
            if e and n > e:
                return False
            return True

        active = [r for r in rows if _in_window(r)]
        active.sort(
            key=lambda r: (-severity_order.get(r.severity or "info", 0), r.start_at or _utcnow())
        )
        return [_serialize(r) for r in active[:limit]]

    @staticmethod
    async def admin_list(
        *,
        notice_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """admin 分页列表"""
        async with AsyncSessionLocal() as db:
            stmt = select(SiteNotice)
            if notice_type:
                stmt = stmt.where(SiteNotice.type == notice_type)
            if is_active is not None:
                stmt = stmt.where(SiteNotice.is_active.is_(is_active))
            stmt = stmt.order_by(SiteNotice.created_at.desc())

            # 计数
            from sqlalchemy import func as _func

            count_stmt = select(_func.count()).select_from(stmt.subquery())
            total = (await db.execute(count_stmt)).scalar_one()

            # 分页
            stmt = stmt.offset((page - 1) * page_size).limit(page_size)
            rows = (await db.execute(stmt)).scalars().all()

        return {
            "items": [_serialize(r) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    async def admin_get(notice_id: str) -> Optional[Dict[str, Any]]:
        async with AsyncSessionLocal() as db:
            r = await db.get(SiteNotice, notice_id)
            return _serialize(r) if r else None

    @staticmethod
    async def admin_create(payload: Dict[str, Any]) -> Dict[str, Any]:
        async with AsyncSessionLocal() as db:
            row = SiteNotice(
                type=payload.get("type", "banner"),
                title=payload["title"],
                content_md=payload.get("content_md"),
                severity=payload.get("severity", "info"),
                start_at=_to_dt(payload.get("start_at")),
                end_at=_to_dt(payload.get("end_at")),
                dismissible=payload.get("dismissible", True),
                is_active=payload.get("is_active", True),
                channels_json=_channels_to_text(payload.get("channels")),
            )
            db.add(row)
            await db.commit()
            await db.refresh(row)
            return _serialize(row)

    @staticmethod
    async def admin_update(notice_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        async with AsyncSessionLocal() as db:
            row = await db.get(SiteNotice, notice_id)
            if not row:
                return None
            for key in ("type", "title", "content_md", "severity", "dismissible", "is_active"):
                if key in payload:
                    setattr(row, key, payload[key])
            if "start_at" in payload:
                row.start_at = _to_dt(payload["start_at"])
            if "end_at" in payload:
                row.end_at = _to_dt(payload["end_at"])
            if "channels" in payload:
                row.channels_json = _channels_to_text(payload["channels"])
            await db.commit()
            await db.refresh(row)
            return _serialize(row)

    @staticmethod
    async def admin_delete(notice_id: str) -> bool:
        async with AsyncSessionLocal() as db:
            row = await db.get(SiteNotice, notice_id)
            if not row:
                return False
            await db.delete(row)
            await db.commit()
            return True

    @staticmethod
    async def admin_toggle(notice_id: str) -> Optional[Dict[str, Any]]:
        async with AsyncSessionLocal() as db:
            row = await db.get(SiteNotice, notice_id)
            if not row:
                return None
            row.is_active = not row.is_active
            await db.commit()
            await db.refresh(row)
            return _serialize(row)


def _to_dt(value: Optional[str]) -> Optional[datetime]:
    """ISO 字符串 -> datetime，None/空返回 None"""
    if not value:
        return None
    try:
        # 支持 "2026-07-05 04:00" 和 "2026-07-05T04:00:00+08:00"
        if "T" not in value:
            return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        logger.warning("时间解析失败: %s", value)
        return None


def _channels_to_text(channels: Optional[Any]) -> Optional[str]:
    if channels is None:
        return None
    if isinstance(channels, str):
        return channels  # 已是字符串
    try:
        return json.dumps(channels, ensure_ascii=False)
    except Exception:
        return None
