"""
Admin 可配置的运行时配置（覆盖 env 默认值）。
存储于 data/admin_runtime_config.json。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from app.utils.data_paths import get_project_data_dir


def _config_path() -> Path:
    return get_project_data_dir() / "admin_runtime_config.json"


def _load_config() -> Dict[str, Any]:
    path = _config_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return {}


def _save_config(data: Dict[str, Any]) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_admin_config(key: str, default: Any = None) -> Any:
    """获取 admin 配置项，不存在则返回 default"""
    return _load_config().get(key, default)


def set_admin_config(key: str, value: Any) -> None:
    """设置 admin 配置项"""
    data = _load_config()
    data[key] = value
    _save_config(data)


def get_basic_info_merge_strategy() -> str:
    """获取 basic_info 合并策略，admin 配置优先于 env"""
    from app.config.settings import settings

    val = get_admin_config("basic_info_merge_strategy")
    if val and str(val).strip().upper() in ("A", "B", "C"):
        return str(val).strip().upper()
    return (getattr(settings, "BASIC_INFO_MERGE_STRATEGY", None) or "A").strip().upper()
