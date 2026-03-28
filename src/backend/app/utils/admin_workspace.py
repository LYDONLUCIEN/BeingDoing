"""
管理员常驻调试工作区：
- 每个 super_admin 绑定一个长期可复用的激活码
- 数据目录隔离在 data/simple/admin_workspaces/{admin_user_id}/
- 与 SBX Fork 并行，不替代既有 Fork 机制
"""

from __future__ import annotations

import random
import re
import string
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Tuple

from app.utils.simple_activation_manager import (
    ActivationRecord,
    ActivationStatus,
    SimpleActivationManager,
    get_simple_base_dir,
)


RESIDENT_CODE_PREFIX = "ADM"
RESIDENT_TTL_DAYS = 3650  # 10 年，近似长期有效


def _safe_workspace_owner(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return "admin"
    normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value)
    return normalized[:80] or "admin"


def _generate_resident_code(manager: SimpleActivationManager) -> str:
    records = manager.list_activations()
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(200):
        suffix = "".join(random.choices(alphabet, k=8))
        code = f"{RESIDENT_CODE_PREFIX}{suffix}"
        if code not in records:
            return code
    raise RuntimeError("无法生成唯一管理员工作区激活码")


def _owner_match(rec: ActivationRecord, user: Dict[str, Any]) -> bool:
    user_id = (user.get("user_id") or "").strip()
    email = (user.get("email") or "").strip()
    if user_id and rec.owner_user_id == user_id:
        return True
    if email and rec.owner_email == email:
        return True
    return False


def _ensure_workspace_dir(workspace_root: str) -> Path:
    base = get_simple_base_dir()
    root = (base / workspace_root).resolve()
    (root / "reports").mkdir(parents=True, exist_ok=True)
    return root


def ensure_admin_resident_workspace(admin_user: Dict[str, Any]) -> Tuple[ActivationRecord, bool]:
    """
    确保当前管理员存在常驻工作区激活码。

    Returns:
        (record, created)
    """
    manager = SimpleActivationManager()
    records = manager.list_activations()

    # 1) 优先复用已存在的 resident workspace
    for rec in records.values():
        if rec.workspace_kind != "resident":
            continue
        if rec.status == ActivationStatus.DELETED.value:
            continue
        if not _owner_match(rec, admin_user):
            continue
        workspace_root = (rec.workspace_root or "").strip()
        if workspace_root:
            _ensure_workspace_dir(workspace_root)
        return rec, False

    # 2) 创建新的 resident workspace
    owner_user_id = (admin_user.get("user_id") or "").strip()
    owner_email = (admin_user.get("email") or "").strip()
    if not owner_user_id and not owner_email:
        raise ValueError("管理员身份缺失，无法创建常驻工作区")

    owner_key = owner_user_id or owner_email
    workspace_root = f"admin_workspaces/{_safe_workspace_owner(owner_key)}"
    _ensure_workspace_dir(workspace_root)

    now = datetime.utcnow()
    now_iso = now.isoformat() + "Z"
    expires_iso = (now + timedelta(days=RESIDENT_TTL_DAYS)).isoformat() + "Z"
    code = _generate_resident_code(manager)

    rec = ActivationRecord(
        code=code,
        session_id=str(uuid.uuid4()),
        mode="combined",
        created_at=now_iso,
        expires_at=expires_iso,
        last_activity_at=now_iso,
        status=ActivationStatus.ACTIVE.value,
        owner_user_id=owner_user_id or None,
        owner_email=owner_email or None,
        claimed_at=now_iso,
        source="admin_resident_workspace",
        vip_level=1,
        is_sandbox=False,
        workspace_kind="resident",
        workspace_root=workspace_root,
    )
    manager.put_activation(rec)
    return rec, True
