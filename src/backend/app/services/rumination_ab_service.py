"""
Rumination v3/v4 分组判定服务

职责：
- resolve_rumination_version: 返回某 report 应走的版本（v3/v4）
  - 首次：按配置（强制 v3/v4 或按比例随机）分配，写入 rumination_ab_assignments
  - 后续：直接读已有记录（幂等，保证同 report 版本稳定）

日志：分配时打印 version / source / ratio，便于后台统计。
"""
from __future__ import annotations

import logging
import random
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.rumination_ab import RuminationAbAssignment

logger = logging.getLogger(__name__)


async def _get_existing(db: AsyncSession, report_id: str) -> Optional[RuminationAbAssignment]:
    result = await db.execute(
        select(RuminationAbAssignment).where(RuminationAbAssignment.report_id == report_id)
    )
    return result.scalar_one_or_none()


def _decide_version() -> tuple[str, str, Optional[float]]:
    """根据 settings 决定版本与来源。返回 (version, source, ratio_at_assignment)。"""
    mode = (settings.RUMINATION_VERSION_MODE or "ab").strip().lower()
    if mode == "v3":
        return "v3", "forced", None
    if mode == "v4":
        return "v4", "forced", None
    # ab（含未知值兜底为 ab）
    ratio = settings.RUMINATION_AB_V4_RATIO
    try:
        ratio_val = float(ratio)
    except (TypeError, ValueError):
        ratio_val = 0.5
    # 钳到 [0.0, 1.0]
    ratio_val = max(0.0, min(1.0, ratio_val))
    version = "v4" if random.random() < ratio_val else "v3"
    return version, "ab", ratio_val


async def resolve_rumination_version(
    db: AsyncSession,
    report_id: str,
    user_id: Optional[str],
) -> Dict[str, Any]:
    """返回 {version, source, assigned_at, ratio_at_assignment}。

    规则：
    - 首次：按配置决策（强制 v3/v4 或 ab 随机），写入记录。
    - 后续 + 配置是 ab：尊重已有记录（版本稳定，AB 实验不被重复采样）。
    - 后续 + 配置是强制（v3/v4）：若已有记录与当前强制配置不一致，覆盖之。
      这样运营把配置改成强制 v3/v4 时，老用户会跟着切版本。
      （数据安全由 v3/v4 文件物理隔离保证，切版本不会丢数据。）
    并发：report_id 唯一约束冲突时重读，保证幂等。
    """
    mode = (settings.RUMINATION_VERSION_MODE or "ab").strip().lower()
    is_forced = mode in ("v3", "v4")

    # 1. 先查已有
    existing = await _get_existing(db, report_id)

    # 2. 已有 + ab 模式 → 直接返回（版本稳定）
    if existing and not is_forced:
        return {
            "version": existing.version,
            "source": existing.source,
            "assigned_at": existing.created_at.isoformat() if existing.created_at else None,
            "ratio_at_assignment": existing.ratio_at_assignment,
        }

    # 3. 决策当前应有版本
    version, source, ratio = _decide_version()

    # 4. 已有 + 强制模式且版本一致 → 直接返回（无需写）
    if existing and existing.version == version and existing.source == source:
        return {
            "version": existing.version,
            "source": existing.source,
            "assigned_at": existing.created_at.isoformat() if existing.created_at else None,
            "ratio_at_assignment": existing.ratio_at_assignment,
        }

    # 5. 已有 + 强制模式且版本不一致 → 覆盖（运营切版本）
    if existing:
        old_version = existing.version
        existing.version = version
        existing.source = source
        existing.ratio_at_assignment = ratio
        existing.user_id = user_id or existing.user_id
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            logger.warning("rumination_version override failed report=%s", report_id)
            return {
                "version": old_version,
                "source": "forced",
                "assigned_at": existing.created_at.isoformat() if existing.created_at else None,
                "ratio_at_assignment": existing.ratio_at_assignment,
            }
        logger.info(
            "rumination_version_overridden report=%s user=%s old=%s new=%s source=%s",
            report_id, user_id, old_version, version, source,
        )
        return {
            "version": version,
            "source": source,
            "assigned_at": existing.created_at.isoformat() if existing.created_at else None,
            "ratio_at_assignment": ratio,
        }

    # 6. 无已有记录 → 新建
    row = RuminationAbAssignment(
        report_id=report_id,
        user_id=user_id,
        version=version,
        source=source,
        ratio_at_assignment=ratio,
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        # 并发：另一请求已写入，回滚后重读
        await db.rollback()
        existing = await _get_existing(db, report_id)
        if existing:
            return {
                "version": existing.version,
                "source": existing.source,
                "assigned_at": existing.created_at.isoformat() if existing.created_at else None,
                "ratio_at_assignment": existing.ratio_at_assignment,
            }
        logger.warning(
            "rumination_version assignment lost after conflict report=%s version=%s",
            report_id, version,
        )
        return {
            "version": version,
            "source": source,
            "assigned_at": None,
            "ratio_at_assignment": ratio,
        }

    logger.info(
        "rumination_version_assigned report=%s user=%s version=%s source=%s ratio=%s",
        report_id, user_id, version, source, ratio,
    )
    return {
        "version": version,
        "source": source,
        "assigned_at": row.created_at.isoformat() if row.created_at else None,
        "ratio_at_assignment": ratio,
    }
