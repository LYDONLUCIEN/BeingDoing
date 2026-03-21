#!/usr/bin/env python3
"""
将 basic_info 从 data/simple/{session_id}/ 迁移到 data/user/{user_id}/。

同一用户多份时按 BASIC_INFO_MERGE_STRATEGY 合并：A=最新 B=并集 C=交集。
默认 dry-run，--apply 才执行。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

from app.utils.simple_activation_manager import get_simple_base_dir
from app.utils.data_paths import get_user_data_dir
from app.utils.survey_storage import (
    load_basic_info,
    save_basic_info_by_user,
    merge_basic_info_sources,
)
from app.utils.admin_config import get_basic_info_merge_strategy


def load_json(path: Path, default):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8") or "null")
    except (OSError, json.JSONDecodeError):
        return default


def migrate(dry_run: bool) -> dict:
    base = get_simple_base_dir()
    activations = load_json(base / "activations.json", {}) or {}
    user_data_root = get_user_data_dir()
    user_data_root.mkdir(parents=True, exist_ok=True)

    user_to_sources: Dict[str, List[tuple[str, dict]]] = {}
    for code, rec in activations.items():
        if not isinstance(rec, dict):
            continue
        owner_uid = (rec.get("owner_user_id") or "").strip()
        owner_email = (rec.get("owner_email") or "").strip()
        user_id = owner_uid or owner_email
        if not user_id:
            continue
        session_id = (rec.get("session_id") or "").strip()
        if not session_id:
            continue
        sess_dir = base / session_id
        if not sess_dir.is_dir():
            continue
        basic_path = sess_dir / "basic_info.json"
        if not basic_path.is_file():
            continue
        data = load_basic_info(session_id, str(base))
        if not data:
            continue
        user_to_sources.setdefault(user_id, []).append((code, data))

    strategy = get_basic_info_merge_strategy()
    stats = {"users": 0, "written": 0}
    for user_id, sources in user_to_sources.items():
        if not sources:
            continue
        stats["users"] += 1
        merged = merge_basic_info_sources([s[1] for s in sources], strategy)
        if not merged:
            continue
        if not dry_run:
            save_basic_info_by_user(user_id, merged)
        stats["written"] += 1
    return {"dry_run": dry_run, "strategy": strategy, **stats}


def main():
    parser = argparse.ArgumentParser(description="迁移 basic_info 到用户级")
    parser.add_argument("--apply", action="store_true", help="执行迁移")
    args = parser.parse_args()
    result = migrate(dry_run=not args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
