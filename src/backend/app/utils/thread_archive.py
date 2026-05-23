"""Thread 对话文件软归档：删除时移入 .deleted_threads，保留 manifest 供审计与排查。"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _deleted_at_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def archive_step_session_file(
    session_file: Path,
    *,
    phase_step: str,
    thread_id: str,
    report_id: str,
    operator_user_id: Optional[str] = None,
    reason: str = "thread_delete",
) -> Optional[Path]:
    """
    将会话文件（及 .lock）移入 reports/{report_id}/.deleted_threads/{phase}/{thread_id}_{ts}/。

    若源文件不存在则仅写 manifest（记录 attempted 路径），返回归档目录或 None。
    """
    deleted_at = _deleted_at_stamp()
    archive_dir = (
        session_file.parent
        / ".deleted_threads"
        / phase_step
        / f"{thread_id}_{deleted_at}"
    )
    archive_dir.mkdir(parents=True, exist_ok=True)

    dest_file = archive_dir / session_file.name
    if session_file.is_file():
        shutil.move(str(session_file), str(dest_file))

    lock_file = session_file.with_suffix(session_file.suffix + ".lock")
    if lock_file.is_file():
        shutil.move(str(lock_file), str(archive_dir / lock_file.name))

    manifest = {
        "report_id": report_id,
        "phase_step": phase_step,
        "thread_id": thread_id,
        "deleted_at": deleted_at,
        "original_path": str(session_file),
        "archived_path": str(dest_file),
        "operator_user_id": operator_user_id,
        "reason": reason,
    }
    (archive_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return archive_dir
