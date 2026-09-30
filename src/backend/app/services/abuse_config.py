"""滥用检测运行时配置。

admin 在后台可调整检测开关与各硬阈值，即时生效、无需重启。
配置持久化在 data/abuse_config.json；非法/缺失字段回退默认值。

模式完全对齐 app/services/coupon_config.py：mtime 缓存、非法回退默认、写文件清缓存。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from app.utils.data_paths import get_project_data_dir

logger = logging.getLogger(__name__)

# 默认硬阈值（与产品确认口径一致）
DEFAULTS: Dict[str, Any] = {
    "enabled": True,  # 总开关
    "msg_per_minute": 10,  # 1 分钟内用户消息条数
    "msg_per_hour": 360,  # 1 小时内用户消息条数
    "msg_per_day": 1000,  # 1 天内用户消息条数
    "token_lifetime": 5_000_000,  # 单用户累计 token（聚合 llm_usage_logs）
    "thread_delete_per_phase": 3,  # 同一 phase 累计删除对话次数（不限窗口）
}

# 阈值合法范围（均为正整数，上限防误配成天量导致永不触发）
MIN_THRESHOLD = 1
MAX_THRESHOLD = 10_000_000

_CONFIG_FILENAME = "abuse_config.json"

# 阈值键（enabled 是 bool，单独校验）
_THRESHOLD_KEYS = (
    "msg_per_minute",
    "msg_per_hour",
    "msg_per_day",
    "token_lifetime",
    "thread_delete_per_phase",
)

# mtime 缓存：避免每次消息都读盘；文件被改写后 mtime 变化即失效
_cache_config: Optional[Dict[str, Any]] = None
_cache_mtime: Optional[float] = None


def _config_path() -> Path:
    return get_project_data_dir() / _CONFIG_FILENAME


def _is_valid_threshold(value: object) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and MIN_THRESHOLD <= value <= MAX_THRESHOLD
    )


def _sanitize(data: object) -> Dict[str, Any]:
    """把文件里读到的 dict 清洗成完整配置：非法/缺失字段回退默认。"""
    cfg = dict(DEFAULTS)
    if not isinstance(data, dict):
        return cfg
    enabled = data.get("enabled")
    if isinstance(enabled, bool):
        cfg["enabled"] = enabled
    for key in _THRESHOLD_KEYS:
        value = data.get(key)
        if _is_valid_threshold(value):
            cfg[key] = value
        elif value is not None:
            logger.warning("滥用检测配置项 %s 非法（%r），回退默认 %d", key, value, DEFAULTS[key])
    return cfg


def get_config() -> Dict[str, Any]:
    """当前生效配置（运行时配置 > 默认值）。异常时回退全默认。"""
    global _cache_config, _cache_mtime
    path = _config_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        _cache_config, _cache_mtime = None, None
        return dict(DEFAULTS)
    if _cache_mtime == mtime and _cache_config is not None:
        return dict(_cache_config)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        cfg = _sanitize(data)
        _cache_config, _cache_mtime = cfg, mtime
        return dict(cfg)
    except Exception:
        logger.exception("滥用检测配置读取失败: %s", path)
    _cache_config, _cache_mtime = None, None
    return dict(DEFAULTS)


def set_config(partial: Dict[str, Any]) -> Dict[str, Any]:
    """部分更新运行时配置（只接受已知键；阈值须为 1-10_000_000 的整数）。

    Returns:
        更新后的完整生效配置。

    Raises:
        ValueError: 存在非法字段值。
    """
    if not isinstance(partial, dict):
        raise ValueError("配置必须是对象")
    unknown = set(partial) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"未知配置项: {', '.join(sorted(unknown))}")

    cfg = get_config()
    for key, value in partial.items():
        if key == "enabled":
            if not isinstance(value, bool):
                raise ValueError(f"enabled 必须是布尔值: {value!r}")
            cfg["enabled"] = value
        else:
            if not _is_valid_threshold(value):
                raise ValueError(
                    f"非法阈值 {key}={value!r}（须为 {MIN_THRESHOLD}-{MAX_THRESHOLD} 的整数）"
                )
            cfg[key] = value

    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    global _cache_config, _cache_mtime
    _cache_config, _cache_mtime = None, None
    logger.info("滥用检测配置已调整: %s", cfg)
    return dict(cfg)
