"""折扣券默认有效期运行时配置。

admin 在支付管理页可调整折扣券默认有效期（天），即时生效、无需重启，
只影响之后新创建的券（存量券 expires_at 不动）。配置持久化在
data/coupon_config.json；非法/缺失时回退 DEFAULT_COUPON_TTL_DAYS。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from app.utils.data_paths import get_project_data_dir

logger = logging.getLogger(__name__)

DEFAULT_COUPON_TTL_DAYS = 90
MIN_TTL_DAYS = 1
MAX_TTL_DAYS = 3650  # 对齐激活码 batch-create 的 ttl_days 上限
_CONFIG_FILENAME = "coupon_config.json"

# mtime 缓存：避免每次创建券都读盘；文件被改写后 mtime 变化即失效
_cache_days: Optional[int] = None
_cache_mtime: Optional[float] = None


def _config_path() -> Path:
    return get_project_data_dir() / _CONFIG_FILENAME


def _is_valid(days: object) -> bool:
    return isinstance(days, int) and not isinstance(days, bool) and MIN_TTL_DAYS <= days <= MAX_TTL_DAYS


def get_default_ttl_days() -> int:
    """当前生效的默认有效期天数（运行时配置 > 默认 90）。异常时回退默认。"""
    global _cache_days, _cache_mtime
    path = _config_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        _cache_days, _cache_mtime = None, None
        return DEFAULT_COUPON_TTL_DAYS
    if _cache_mtime == mtime and _cache_days is not None:
        return _cache_days
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        days = (data or {}).get("default_ttl_days")
        if _is_valid(days):
            _cache_days, _cache_mtime = days, mtime
            return days
        logger.warning("折扣券默认有效期配置非法（%r），回退 %d 天", days, DEFAULT_COUPON_TTL_DAYS)
    except Exception:
        logger.exception("折扣券默认有效期配置读取失败: %s", path)
    _cache_days, _cache_mtime = None, None
    return DEFAULT_COUPON_TTL_DAYS


def set_default_ttl_days(days: int) -> None:
    """写入运行时默认有效期（仅接受 1-3650 的整数）。"""
    if not _is_valid(days):
        raise ValueError(
            f"非法有效期天数: {days!r}（须为 {MIN_TTL_DAYS}-{MAX_TTL_DAYS} 的整数）"
        )
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"default_ttl_days": days}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    global _cache_days, _cache_mtime
    _cache_days, _cache_mtime = None, None
    logger.info("折扣券默认有效期已调整: %d 天", days)
