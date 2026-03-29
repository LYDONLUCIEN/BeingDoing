"""
Admin Prompt Lab（sandbox_only）

能力：
- 管理员维护多份提示词配置（profile）
- 每个 profile 支持多版本（versions）
- 将 profile 绑定到调试工作区激活码（ADM/SBX）
- simple-chat 运行时按 activation_code 读取绑定配置
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.utils.simple_activation_manager import get_simple_test_base_dir


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _lab_root() -> Path:
    root = get_simple_test_base_dir() / "admin_prompt_lab"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _profiles_file() -> Path:
    return _lab_root() / "profiles.json"


def _bindings_file() -> Path:
    return _lab_root() / "activation_bindings.json"


def _load_json(file: Path, default: Any) -> Any:
    if not file.is_file():
        return default
    try:
        return json.loads(file.read_text(encoding="utf-8") or "null")
    except (OSError, json.JSONDecodeError, TypeError):
        return default


def _save_json(file: Path, payload: Any) -> None:
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def list_profiles() -> List[Dict[str, Any]]:
    raw = _load_json(_profiles_file(), {"items": []}) or {"items": []}
    items = raw.get("items") if isinstance(raw, dict) else []
    if not isinstance(items, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        versions = item.get("versions") if isinstance(item.get("versions"), list) else []
        out.append(
            {
                "profile_id": item.get("profile_id"),
                "name": item.get("name") or "",
                "description": item.get("description") or "",
                "current_version_id": item.get("current_version_id"),
                "version_count": len(versions),
                "updated_at": item.get("updated_at"),
                "created_at": item.get("created_at"),
            }
        )
    out.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return out


def get_profile(profile_id: str) -> Optional[Dict[str, Any]]:
    pid = (profile_id or "").strip()
    if not pid:
        return None
    raw = _load_json(_profiles_file(), {"items": []}) or {"items": []}
    items = raw.get("items") if isinstance(raw, dict) else []
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        if (item.get("profile_id") or "") == pid:
            return item
    return None


def create_profile(name: str, description: str = "") -> Dict[str, Any]:
    nm = (name or "").strip()
    if not nm:
        raise ValueError("name 不能为空")
    raw = _load_json(_profiles_file(), {"items": []}) or {"items": []}
    items = raw.get("items") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        items = []
    now = _now_iso()
    profile = {
        "profile_id": str(uuid.uuid4()),
        "name": nm,
        "description": (description or "").strip(),
        "created_at": now,
        "updated_at": now,
        "current_version_id": None,
        "versions": [],
    }
    items.append(profile)
    _save_json(_profiles_file(), {"items": items})
    return profile


def add_profile_version(
    profile_id: str,
    *,
    simple_chat_system_prompt_template: str,
    extra_goal_hint: str = "",
    created_by: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    pid = (profile_id or "").strip()
    if not pid:
        raise ValueError("profile_id 不能为空")
    template = (simple_chat_system_prompt_template or "").strip()
    if not template:
        raise ValueError("simple_chat_system_prompt_template 不能为空")

    raw = _load_json(_profiles_file(), {"items": []}) or {"items": []}
    items = raw.get("items") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        raise ValueError("profiles 数据损坏")

    now = _now_iso()
    actor = {
        "user_id": (created_by or {}).get("user_id"),
        "email": (created_by or {}).get("email"),
    }
    version = {
        "version_id": str(uuid.uuid4()),
        "created_at": now,
        "created_by": actor,
        "simple_chat_system_prompt_template": template,
        "extra_goal_hint": (extra_goal_hint or "").strip(),
    }
    target: Optional[Dict[str, Any]] = None
    for item in items:
        if isinstance(item, dict) and (item.get("profile_id") or "") == pid:
            target = item
            break
    if not target:
        raise ValueError("profile 不存在")
    versions = target.get("versions")
    if not isinstance(versions, list):
        versions = []
        target["versions"] = versions
    versions.append(version)
    target["current_version_id"] = version["version_id"]
    target["updated_at"] = now

    _save_json(_profiles_file(), {"items": items})
    return version


def set_current_version(profile_id: str, version_id: str) -> Dict[str, Any]:
    pid = (profile_id or "").strip()
    vid = (version_id or "").strip()
    if not pid or not vid:
        raise ValueError("profile_id/version_id 不能为空")
    raw = _load_json(_profiles_file(), {"items": []}) or {"items": []}
    items = raw.get("items") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        raise ValueError("profiles 数据损坏")

    target: Optional[Dict[str, Any]] = None
    for item in items:
        if isinstance(item, dict) and (item.get("profile_id") or "") == pid:
            target = item
            break
    if not target:
        raise ValueError("profile 不存在")
    versions = target.get("versions")
    if not isinstance(versions, list) or not any((v or {}).get("version_id") == vid for v in versions):
        raise ValueError("version 不存在")
    target["current_version_id"] = vid
    target["updated_at"] = _now_iso()
    _save_json(_profiles_file(), {"items": items})
    return target


def bind_profile_to_activation(
    activation_code: str, profile_id: str, actor: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    code = (activation_code or "").strip().upper()
    pid = (profile_id or "").strip()
    if not code:
        raise ValueError("activation_code 不能为空")
    if not pid:
        raise ValueError("profile_id 不能为空")
    profile = get_profile(pid)
    if not profile:
        raise ValueError("profile 不存在")
    if not profile.get("current_version_id"):
        raise ValueError("profile 尚无可用版本，请先保存版本")

    raw = _load_json(_bindings_file(), {"items": []}) or {"items": []}
    items = raw.get("items") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        items = []
    now = _now_iso()
    actor_info = {"user_id": (actor or {}).get("user_id"), "email": (actor or {}).get("email")}
    found = None
    for item in items:
        if isinstance(item, dict) and (item.get("activation_code") or "").upper() == code:
            found = item
            break
    if found:
        found["profile_id"] = pid
        found["updated_at"] = now
        found["updated_by"] = actor_info
    else:
        items.append(
            {
                "activation_code": code,
                "profile_id": pid,
                "created_at": now,
                "updated_at": now,
                "updated_by": actor_info,
            }
        )
    _save_json(_bindings_file(), {"items": items})
    return {"activation_code": code, "profile_id": pid}


def get_binding_by_activation(activation_code: str) -> Optional[Dict[str, Any]]:
    code = (activation_code or "").strip().upper()
    if not code:
        return None
    raw = _load_json(_bindings_file(), {"items": []}) or {"items": []}
    items = raw.get("items") if isinstance(raw, dict) else []
    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, dict) and (item.get("activation_code") or "").upper() == code:
            return item
    return None


def list_bindings() -> List[Dict[str, Any]]:
    raw = _load_json(_bindings_file(), {"items": []}) or {"items": []}
    items = raw.get("items") if isinstance(raw, dict) else []
    if not isinstance(items, list):
        return []
    out = [x for x in items if isinstance(x, dict)]
    out.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return out


def resolve_simple_chat_prompt_override(
    activation_code: str,
) -> Optional[Tuple[str, str, Dict[str, Any]]]:
    """
    根据 activation_code 返回当前生效的 simple-chat 覆盖配置：
      (template, extra_goal_hint, meta)
    """
    bind = get_binding_by_activation(activation_code)
    if not bind:
        return None
    profile_id = bind.get("profile_id")
    if not profile_id:
        return None
    profile = get_profile(profile_id)
    if not profile:
        return None
    current_vid = profile.get("current_version_id")
    versions = profile.get("versions")
    if not current_vid or not isinstance(versions, list):
        return None
    current = next((v for v in versions if isinstance(v, dict) and v.get("version_id") == current_vid), None)
    if not isinstance(current, dict):
        return None
    template = (current.get("simple_chat_system_prompt_template") or "").strip()
    if not template:
        return None
    extra = (current.get("extra_goal_hint") or "").strip()
    meta = {
        "profile_id": profile_id,
        "profile_name": profile.get("name") or "",
        "version_id": current_vid,
    }
    return template, extra, meta


def export_current_profile_payload(profile_id: str) -> Dict[str, Any]:
    """
    导出 profile 当前生效版本，便于人工回填到代码模板文件。
    """
    profile = get_profile(profile_id)
    if not profile:
        raise ValueError("profile 不存在")
    current_vid = profile.get("current_version_id")
    versions = profile.get("versions")
    if not current_vid or not isinstance(versions, list):
        raise ValueError("profile 尚未设置生效版本")
    current = next((v for v in versions if isinstance(v, dict) and v.get("version_id") == current_vid), None)
    if not isinstance(current, dict):
        raise ValueError("生效版本不存在")
    template = (current.get("simple_chat_system_prompt_template") or "").strip()
    extra_goal_hint = (current.get("extra_goal_hint") or "").strip()
    if not template:
        raise ValueError("当前生效版本模板为空")

    merged_for_copy = template
    if extra_goal_hint:
        merged_for_copy = f"{template}\n\n[管理员调试目标补充]\n{extra_goal_hint}"

    return {
        "profile_id": profile_id,
        "profile_name": profile.get("name") or "",
        "current_version_id": current_vid,
        "template": template,
        "extra_goal_hint": extra_goal_hint,
        "merged_for_copy": merged_for_copy,
        "copied_from": {
            "created_at": current.get("created_at"),
            "created_by": current.get("created_by"),
        },
    }
