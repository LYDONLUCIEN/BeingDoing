"""
激活码归属审计日志模块

记录激活码生命周期中的关键事件（归属绑定、权限校验、状态变更等），
以 JSONL 追加写入，供事后审计与排障使用。

日志位置：
  - data/simple/activation_audit.jsonl       （正式激活码）
  - data/test/simple/activation_audit.jsonl   （调试/沙箱激活码）

每条日志包含：
  event              — 事件类型
  at                 — UTC 时间戳
  activation_code    — 激活码
  actor_user_id      — 操作者 user_id
  actor_email        — 操作者 email
  client_ip          — 请求来源 IP（可选，由调用方传入）
  detail             — 事件详情 dict
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.utils.simple_activation_manager import (
    get_simple_base_dir,
    get_simple_test_base_dir,
    _looks_like_debug_activation_code,
)

logger = logging.getLogger(__name__)

_AUDIT_FILENAME = "activation_audit.jsonl"

# ---- 事件类型常量 ----
EVENT_OWNER_CLAIMED = "owner_claimed"               # 首次绑定归属
EVENT_OWNER_VERIFIED = "owner_verified"             # 归属校验通过
EVENT_OWNER_DENIED = "owner_denied"                 # 归属校验拒绝（403）
EVENT_CLAIM_BLOCKED = "claim_blocked"               # 绑定被阻止（已有归属者）
EVENT_STATUS_CHANGED = "status_changed"             # 管理员批量状态变更
EVENT_SOFT_DELETED = "soft_deleted"                 # 软删除到回收站
EVENT_PERMANENT_DELETED = "permanent_deleted"       # 永久删除
EVENT_RESTORED = "restored"                         # 从回收站恢复
EVENT_BATCH_CREATED = "batch_created"               # 批量创建
EVENT_SYNC_FROM_DB = "sync_from_db"                 # 从数据库同步
EVENT_ACCESS = "activation_access"                  # 激活码访问（activate 端点）
EVENT_EXTENDED = "extended_and_activated"           # 延期并自动激活


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _audit_path_for_code(code: Optional[str]) -> Path:
    """根据激活码前缀选择审计日志路径（与激活码存储双根一致）。"""
    if _looks_like_debug_activation_code(code):
        return get_simple_test_base_dir() / _AUDIT_FILENAME
    return get_simple_base_dir() / _AUDIT_FILENAME


def append_activation_audit(
    event: str,
    activation_code: str,
    *,
    actor_user_id: Optional[str] = None,
    actor_email: Optional[str] = None,
    client_ip: Optional[str] = None,
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    """
    追加一条审计日志。

    Parameters
    ----------
    event : str
        事件类型常量（EVENT_OWNER_CLAIMED 等）。
    activation_code : str
        激活码。
    actor_user_id : str, optional
        操作者 user_id。
    actor_email : str, optional
        操作者 email。
    client_ip : str, optional
        请求来源 IP。
    detail : dict, optional
        事件补充信息（如 old_owner、new_owner、status 变更等）。
    """
    entry: Dict[str, Any] = {
        "event": event,
        "at": _now_iso(),
        "activation_code": (activation_code or "").strip().upper(),
        "actor_user_id": actor_user_id,
        "actor_email": actor_email,
    }
    if client_ip:
        entry["client_ip"] = client_ip
    if detail:
        entry["detail"] = detail

    p = _audit_path_for_code(activation_code)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with p.open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        logger.exception("写入激活码审计日志失败: code=%s event=%s", activation_code, event)


def read_audit_logs(
    code: Optional[str] = None,
    limit: int = 200,
    *,
    test_root: bool = False,
) -> list:
    """
    读取审计日志（最近 limit 条）。

    Parameters
    ----------
    code : str, optional
        若提供则过滤指定激活码的日志；否则返回全部。
    limit : int
        最大返回条数（默认 200）。
    test_root : bool
        True 时读取测试根目录日志；False 时根据 code 前缀自动判断。

    Returns
    -------
    list[dict]
        按时间倒序的审计日志条目。
    """
    if test_root:
        p = get_simple_test_base_dir() / _AUDIT_FILENAME
    elif code:
        p = _audit_path_for_code(code)
    else:
        # 无 code 时合并双根
        logs: list[dict] = []
        for root in (get_simple_base_dir(), get_simple_test_base_dir()):
            logs.extend(_read_audit_file(root / _AUDIT_FILENAME))
        logs.sort(key=lambda x: x.get("at", ""), reverse=True)
        return logs[:limit]
    return _read_audit_file(p, code=code, limit=limit)


def _read_audit_file(path: Path, code: Optional[str] = None, limit: int = 200) -> list:
    """从单个 JSONL 文件读取审计日志。"""
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    # 从文件尾部向前扫描（效率优化：大文件不需要全部加载）
    code_upper = (code or "").strip().upper() if code else ""
    results: list[dict] = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if code_upper and entry.get("activation_code", "").upper() != code_upper:
            continue
        results.append(entry)
        if len(results) >= limit:
            break
    return results
