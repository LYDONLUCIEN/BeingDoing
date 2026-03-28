"""
超级管理员判定工具：
- 统一处理 user_id / email 的配置解析
- 邮箱比较大小写不敏感
- 对输入和配置做 trim 归一化
"""

from typing import Any, Dict, Optional, Set

from app.config.settings import settings


def normalize_email(value: Optional[str]) -> str:
    """邮箱归一化：去首尾空格 + 小写。"""
    return (value or "").strip().lower()


def _normalize_user_id(value: Optional[str]) -> str:
    return (value or "").strip()


def _parse_csv_set(raw: Optional[str], *, lowercase: bool = False) -> Set[str]:
    vals = set()
    for item in (raw or "").split(","):
        v = item.strip()
        if not v:
            continue
        vals.add(v.lower() if lowercase else v)
    return vals


def is_super_admin_user(user: Optional[Dict[str, Any]]) -> bool:
    """按配置判断用户是否 super_admin。"""
    if not user:
        return False

    user_ids = _parse_csv_set(getattr(settings, "SUPER_ADMIN_USER_IDS", None), lowercase=False)
    emails = _parse_csv_set(getattr(settings, "SUPER_ADMIN_EMAILS", None), lowercase=True)

    user_id = _normalize_user_id(str(user.get("user_id") or ""))
    if user_id and user_id in user_ids:
        return True

    email = normalize_email(str(user.get("email") or ""))
    if email and email in emails:
        return True

    return False
