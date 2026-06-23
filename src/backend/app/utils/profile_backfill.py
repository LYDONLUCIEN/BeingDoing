"""
启动时一次性回填 user_profiles.profile_completed。

标记文件存在则直接返回;否则扫描 data/user/*/basic_info.json,
对 DB profile_completed=False 但 JSON 有内容的用户,更新为 True。
成功后写标记文件。失败不写标记,下次启动重试。

判定规则复用 app.utils.survey_storage._basic_info_has_content。
"""
import logging
from pathlib import Path

from app.utils.data_paths import get_user_data_dir
from app.utils.survey_storage import load_basic_info_by_user, _basic_info_has_content

logger = logging.getLogger(__name__)
_MARKER_FILENAME = ".profile_backfilled"


def _marker_path() -> Path:
    return get_user_data_dir() / _MARKER_FILENAME


def _write_marker() -> None:
    try:
        _marker_path().write_text("ok", encoding="utf-8")
    except OSError as e:
        logger.warning("profile backfill marker write failed: %s", e)


async def run_profile_backfill_if_needed() -> None:
    """
    启动时调用一次。已回填(标记文件存在)则零成本返回。
    扫描所有用户 basic_info.json,对有内容但 DB profile_completed
    仍为 False 的用户更新为 True。
    """
    if _marker_path().exists():
        return

    from app.models.database import AsyncSessionLocal
    from app.core.database.user_db import UserDB

    user_root = get_user_data_dir()
    if not user_root.exists():
        _write_marker()
        return

    updated = 0
    skipped = 0
    for user_dir in user_root.iterdir():
        if not user_dir.is_dir():
            continue
        user_id = user_dir.name
        try:
            data = load_basic_info_by_user(user_id)
            if not _basic_info_has_content(data):
                skipped += 1
                continue
            async with AsyncSessionLocal() as db:
                user_db = UserDB(db)
                existing = await user_db.get_user_profile(user_id)
                if existing and existing.profile_completed:
                    continue
                await user_db.update_user_profile(
                    user_id=user_id,
                    gender=(data.get("gender") if data else None),
                    profile_completed=True,
                )
                updated += 1
        except Exception as e:
            logger.warning("profile backfill skipped user %s: %s", user_id, e)
            skipped += 1

    _write_marker()
    logger.info("profile backfill done: updated=%d, skipped=%d", updated, skipped)
