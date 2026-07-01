"""
管理员调试沙箱：从正式激活码 Fork 独立存储目录，便于在隔离环境中继续对话测试。

目录结构：
  源数据（只读）：data/simple/
  沙箱数据（写入）：data/test/simple/sandboxes/{fork_id}/
    reports/{report_id}/      # 与正式环境相同的 report 布局
    {activation_session_id}/  # 问卷 basic_info、prior_context 等
"""

from __future__ import annotations

import json
import logging
import random
import shutil
import string
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.utils.report_registry import ReportRegistry
from app.utils.helpers import parse_iso_to_utc
from app.utils.simple_activation_manager import (
    ActivationRecord,
    ActivationStatus,
    SimpleActivationManager,
    get_simple_base_dir,
    get_simple_test_base_dir,
)

logger = logging.getLogger(__name__)

SANDBOX_CODE_PREFIX = "SBX"
SANDBOX_RETENTION_DAYS = 15
AUDIT_LOG_FILENAME = "sandbox_fork_audit.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sandbox_audit_path() -> Path:
    return get_simple_test_base_dir() / AUDIT_LOG_FILENAME


def append_fork_audit(entry: Dict[str, Any]) -> None:
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    p = _sandbox_audit_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(line)


def _generate_sandbox_code(
    manager: SimpleActivationManager, extra_records: Optional[Dict[str, Any]] = None
) -> str:
    records = manager.list_activations()
    extra = extra_records or {}
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(200):
        suffix = "".join(random.choices(alphabet, k=8))
        code = f"{SANDBOX_CODE_PREFIX}{suffix}"
        if code not in records and code not in extra:
            return code
    raise RuntimeError("无法生成唯一沙箱激活码")


def find_main_report_for_activation(activation_code: str) -> Optional[Dict[str, Any]]:
    """
    在正式 data/simple 根下查找与激活码匹配的报告 record。
    优先匹配激活码归属用户的 user_id；否则取该激活码下任意一条报告。
    """
    code_u = (activation_code or "").strip().upper()
    if not code_u:
        return None
    registry = ReportRegistry(base_dir=str(get_simple_base_dir()))
    manager = SimpleActivationManager(base_dir=str(get_simple_base_dir()))
    act = manager.get_activation(code_u)
    if act and act.owner_user_id:
        got = registry.get_by_activation_user(code_u, act.owner_user_id)
        if got:
            return got
    for rec in registry.list_reports():
        if (rec.get("activation_code") or "").strip().upper() == code_u:
            return rec
    return None


def _conversation_json_message_count(path: Path) -> int:
    """对话 JSON 文件中 messages 条数。"""
    if not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
        return len(data.get("messages") or [])
    except (OSError, json.JSONDecodeError, TypeError):
        return 0


def merge_legacy_session_dir_into_report_dir(
    legacy_session_dir: Path,
    dst_report_dir: Path,
) -> Dict[str, Any]:
    """
    将 data/simple/{源激活码 session_id}/ 下遗留的「阶段__线程.json」并入报告目录。

    历史数据可能只写在该目录而未出现在 reports/{report_id}/；不合并则 Fork 后丢对话。
    规则：目标无文件则拷贝；目标已有则保留消息更多的一侧。
    """
    merged: List[str] = []
    replaced: List[str] = []
    skipped: List[str] = []
    if not legacy_session_dir.is_dir():
        return {"merged": merged, "replaced": replaced, "skipped": skipped}

    skip_names = {"basic_info.json", "record.json"}
    for src in sorted(legacy_session_dir.glob("*.json")):
        if src.name in skip_names:
            continue
        if "__" not in src.stem:
            continue
        dst = dst_report_dir / src.name
        dst_report_dir.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            shutil.copy2(src, dst)
            merged.append(src.name)
            continue
        c_src = _conversation_json_message_count(src)
        c_dst = _conversation_json_message_count(dst)
        if c_src > c_dst:
            shutil.copy2(src, dst)
            replaced.append(src.name)
        else:
            skipped.append(src.name)

    return {"merged": merged, "replaced": replaced, "skipped": skipped}


def _sandbox_expired_ts(rec: ActivationRecord) -> bool:
    raw = getattr(rec, "sandbox_expires_at", None) or ""
    if not raw:
        return False
    try:
        exp = parse_iso_to_utc(raw)
        return datetime.now(timezone.utc) > exp
    except ValueError:
        return False


def fork_activation_from_source(
    source_activation_code: str,
    admin_user: Dict[str, Any],
) -> Tuple[ActivationRecord, Dict[str, Any]]:
    """
    从正式激活码复制报告与问卷目录到 sandboxes/{fork_id}/，并注册新激活码（归属管理员）。

    Returns:
        (新 ActivationRecord, 摘要信息 dict)
    """
    source_manager = SimpleActivationManager(base_dir=str(get_simple_base_dir()))
    target_manager = SimpleActivationManager(base_dir=str(get_simple_test_base_dir()))
    src_code = (source_activation_code or "").strip().upper()
    if not src_code:
        raise ValueError("请提供源激活码")

    src_act = source_manager.get_activation(src_code)
    if not src_act:
        raise ValueError("源激活码不存在")

    if getattr(src_act, "is_sandbox", False):
        raise ValueError("不允许从沙箱再次 Fork")

    report = find_main_report_for_activation(src_code)
    if not report or not report.get("report_id"):
        raise ValueError("未找到该激活码对应的报告数据，无法 Fork")

    src_report_id = report["report_id"]
    main_base = get_simple_base_dir()
    test_base = get_simple_test_base_dir()
    src_report_dir = main_base / "reports" / src_report_id
    if not src_report_dir.is_dir():
        raise ValueError(f"报告目录不存在: {src_report_id}")

    fork_id = str(uuid.uuid4())
    sandbox_rel = f"sandboxes/{fork_id}"
    sandbox_base = test_base / sandbox_rel
    if sandbox_base.exists():
        raise ValueError("沙箱目录冲突，请重试")

    new_report_id = str(uuid.uuid4())
    new_session_id = str(uuid.uuid4())
    new_code = _generate_sandbox_code(
        target_manager, extra_records=source_manager.list_activations()
    )

    dst_report_dir = sandbox_base / "reports" / new_report_id
    dst_report_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_report_dir, dst_report_dir)

    # 合并遗留目录中的对话文件（与 migrate 脚本同源路径，避免只克隆 reports 时丢线程）
    legacy_merge = merge_legacy_session_dir_into_report_dir(
        main_base / src_act.session_id,
        dst_report_dir,
    )

    # 重写 record.json（除身份与 fork 元数据外保持源 record 全量：各 step 进度、threads、锚点等）
    record_file = dst_report_dir / "record.json"
    if not record_file.is_file():
        shutil.rmtree(sandbox_base, ignore_errors=True)
        raise ValueError("Fork 后缺少 record.json")

    try:
        record_data = json.loads(record_file.read_text(encoding="utf-8") or "{}")
    except (json.JSONDecodeError, OSError):
        shutil.rmtree(sandbox_base, ignore_errors=True)
        raise ValueError("record.json 解析失败")

    admin_uid = (admin_user or {}).get("user_id") or ""
    admin_email = (admin_user or {}).get("email")
    if not admin_uid:
        shutil.rmtree(sandbox_base, ignore_errors=True)
        raise ValueError("管理员 user_id 缺失")

    now = _now_iso()
    expires_dt = datetime.now(timezone.utc) + timedelta(days=SANDBOX_RETENTION_DAYS)
    expires_iso = expires_dt.isoformat()

    record_data["report_id"] = new_report_id
    record_data["activation_code"] = new_code
    record_data["user_id"] = admin_uid
    # 保留源端 updated_at / created_at，便于对照调试（仅补充 fork 元数据）
    record_data.setdefault("created_at", record_data.get("created_at") or now)
    record_data["forked_from_activation_code"] = src_code
    record_data["forked_at"] = now
    record_data["is_sandbox_fork"] = True

    record_file.write_text(
        json.dumps(record_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 复制问卷 / prior 等：data/simple/{源 activation session_id}/
    src_sess_dir = main_base / src_act.session_id
    dst_sess_dir = sandbox_base / new_session_id
    if src_sess_dir.is_dir():
        shutil.copytree(src_sess_dir, dst_sess_dir)

    # 新激活记录（已绑定管理员，无需再 claim）
    new_rec = ActivationRecord(
        code=new_code,
        session_id=new_session_id,
        mode=src_act.mode or "combined",
        created_at=now,
        expires_at=expires_iso,
        last_activity_at=now,
        status=ActivationStatus.ACTIVE,
        owner_user_id=admin_uid,
        owner_email=admin_email,
        claimed_at=now,
        vip_level=getattr(src_act, "vip_level", 1) or 1,
        is_sandbox=True,
        sandbox_root=sandbox_rel,
        fork_id=fork_id,
        forked_from_code=src_code,
        forked_at=now,
        forked_by_user_id=admin_uid,
        sandbox_expires_at=expires_iso,
        source="admin_sandbox_fork",
        workspace_kind="fork",
        workspace_root=sandbox_rel,
    )

    target_manager.put_activation(new_rec)

    summary = {
        "sandbox_activation_code": new_code,
        "fork_id": fork_id,
        "sandbox_root": sandbox_rel,
        "report_id": new_report_id,
        "session_id": new_session_id,
        "source_activation_code": src_code,
        "source_report_id": src_report_id,
        "sandbox_expires_at": expires_iso,
        "retention_days": SANDBOX_RETENTION_DAYS,
        "legacy_merge_merged_files": legacy_merge.get("merged") or [],
        "legacy_merge_replaced_files": legacy_merge.get("replaced") or [],
        "legacy_merge_skipped_files": legacy_merge.get("skipped") or [],
    }

    append_fork_audit(
        {
            "event": "fork_created",
            "at": now,
            "fork_id": fork_id,
            "sandbox_code": new_code,
            "source_code": src_code,
            "admin_user_id": admin_uid,
            "admin_email": admin_email,
        }
    )
    logger.info("sandbox fork created: %s from %s", new_code, src_code)
    return new_rec, summary


def delete_sandbox_by_code(
    activation_code: str, admin_user: Optional[Dict[str, Any]] = None
) -> bool:
    """删除沙箱磁盘目录并从 activations.json 移除记录。"""
    manager = SimpleActivationManager(base_dir=str(get_simple_test_base_dir()))
    code = (activation_code or "").strip().upper()
    if not code:
        return False
    rec = manager.get_activation(code)
    if not rec:
        return False
    if not getattr(rec, "is_sandbox", False):
        raise ValueError("该激活码不是沙箱，拒绝按沙箱逻辑删除")

    main_base = get_simple_test_base_dir()
    root = getattr(rec, "sandbox_root", None) or ""
    if root:
        full = main_base / root
        if full.is_dir():
            shutil.rmtree(full, ignore_errors=True)

    manager.remove_activation_code(code)

    append_fork_audit(
        {
            "event": "sandbox_deleted",
            "at": _now_iso(),
            "sandbox_code": code,
            "fork_id": getattr(rec, "fork_id", None),
            "admin_user_id": (admin_user or {}).get("user_id"),
            "admin_email": (admin_user or {}).get("email"),
        }
    )
    return True


def list_sandboxes() -> List[Dict[str, Any]]:
    manager = SimpleActivationManager(base_dir=str(get_simple_test_base_dir()))
    out: List[Dict[str, Any]] = []
    for code, rec in manager.list_activations().items():
        if not getattr(rec, "is_sandbox", False):
            continue
        expired = _sandbox_expired_ts(rec)
        out.append(
            {
                "activation_code": rec.code,
                "fork_id": rec.fork_id,
                "sandbox_root": rec.sandbox_root,
                "session_id": rec.session_id,
                "forked_from_code": rec.forked_from_code,
                "forked_at": rec.forked_at,
                "forked_by_user_id": rec.forked_by_user_id,
                "sandbox_expires_at": rec.sandbox_expires_at,
                "status": rec.status,
                "expired": expired,
                "created_at": rec.created_at,
                "expires_at": rec.expires_at,
            }
        )
    out.sort(key=lambda x: x.get("forked_at") or "", reverse=True)
    return out


def purge_expired_sandboxes() -> int:
    """删除已超过 sandbox_expires_at 的沙箱（数据与激活记录）。"""
    manager = SimpleActivationManager(base_dir=str(get_simple_test_base_dir()))
    removed = 0
    for code, rec in list(manager.list_activations().items()):
        if not getattr(rec, "is_sandbox", False):
            continue
        if not _sandbox_expired_ts(rec):
            continue
        try:
            delete_sandbox_by_code(code, admin_user=None)
            removed += 1
        except ValueError:
            continue
    return removed


def assert_sandbox_not_expired(rec: ActivationRecord) -> None:
    """若沙箱已过期则抛 ValueError（供 API 层转 HTTP）。"""
    if getattr(rec, "is_sandbox", False) and _sandbox_expired_ts(rec):
        raise ValueError("沙箱已超过保留期限，请重新 Fork 或等待自动清理完成")
