#!/usr/bin/env python3
"""
将无 Owner 但已激活的激活码数据迁移到 data/backups。

无 Owner = 无 owner_user_id 且无 owner_email
已激活 = status 为 ACTIVE 或 EXPIRED（曾被使用过）

迁移内容：
- data/simple/{session_id}/ 整个目录 -> data/backups/no-owner-activations-{ts}/{code}__{session_id}/
- activations.json 中对应记录 -> 备份到 manifest，并从主文件移除

默认 dry-run，--apply 才执行。
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from app.utils.simple_activation_manager import get_simple_base_dir


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path, default):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8") or "null")
    except (OSError, json.JSONDecodeError):
        return default


def migrate(dry_run: bool) -> dict:
    base = get_simple_base_dir()
    data_root = base.parent  # data/
    backups_root = data_root / "backups"
    activations_file = base / "activations.json"

    activations = load_json(activations_file, {}) or {}
    to_backup = []
    for code, rec in activations.items():
        if not isinstance(rec, dict):
            continue
        owner_uid = (rec.get("owner_user_id") or "").strip()
        owner_email = (rec.get("owner_email") or "").strip()
        status = (rec.get("status") or "").strip().lower()
        session_id = (rec.get("session_id") or "").strip()
        if owner_uid or owner_email:
            continue
        if status not in ("active", "expired"):
            continue
        to_backup.append({
            "code": code,
            "session_id": session_id,
            "record": rec,
        })

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_dir = backups_root / f"no-owner-activations-{ts}"
    manifest = {
        "migrated_at": now_iso(),
        "reason": "no_owner_but_activated",
        "count": len(to_backup),
        "activations": [],
        "dirs_moved": [],
    }

    if dry_run:
        for item in to_backup:
            manifest["activations"].append({
                "code": item["code"],
                "session_id": item["session_id"],
            })
            sess_dir = base / item["session_id"]
            if sess_dir.exists() and sess_dir.is_dir():
                manifest["dirs_moved"].append(str(sess_dir))
        return {"dry_run": True, "to_backup": len(to_backup), "manifest": manifest}

    backup_dir.mkdir(parents=True, exist_ok=True)
    new_activations = dict(activations)
    for item in to_backup:
        code = item["code"]
        session_id = item["session_id"]
        manifest["activations"].append({
            "code": code,
            "session_id": session_id,
            "record": item["record"],
        })
        sess_dir = base / session_id
        if session_id and sess_dir.exists() and sess_dir.is_dir():
            dst = backup_dir / f"{code}__{session_id}"
            shutil.copytree(sess_dir, dst, dirs_exist_ok=True)
            shutil.rmtree(sess_dir, ignore_errors=True)
            manifest["dirs_moved"].append(str(sess_dir))
        new_activations.pop(code, None)

    manifest_file = backup_dir / "manifest.json"
    manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    activations_file.write_text(
        json.dumps(new_activations, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"backup_dir": str(backup_dir), "removed": len(to_backup), "manifest": manifest}


def main():
    parser = argparse.ArgumentParser(description="迁移无 Owner 激活码数据到 backups")
    parser.add_argument("--apply", action="store_true", help="执行迁移，否则仅 dry-run")
    args = parser.parse_args()
    result = migrate(dry_run=not args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
