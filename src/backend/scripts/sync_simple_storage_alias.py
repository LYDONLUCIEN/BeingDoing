#!/usr/bin/env python3
"""
为 data/simple 会话目录生成“激活码+session_id”排查别名（软链接）。

用途：
- 保留现有 data/simple/{session_id} 结构不变（不影响运行）
- 额外创建 data/simple/{activation_code}__{session_id} -> {session_id} 的符号链接
- 便于后台人工排查时按激活码快速定位目录

用法：
    python scripts/sync_simple_storage_alias.py
    python scripts/sync_simple_storage_alias.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent.parent  # src/backend/
PROJECT_ROOT = BACKEND_ROOT.parent.parent  # BeingDoing/
SIMPLE_DIR = PROJECT_ROOT / "data" / "simple"
ACTIVATIONS_FILE = SIMPLE_DIR / "activations.json"


def load_activations() -> dict:
    if not ACTIVATIONS_FILE.is_file():
        return {}
    try:
        return json.loads(ACTIVATIONS_FILE.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        return {}


def sync_alias(dry_run: bool = False) -> dict:
    stats = {"total": 0, "linked": 0, "skipped": 0, "missing_source": 0}
    activations = load_activations()
    if not activations:
        return stats

    SIMPLE_DIR.mkdir(parents=True, exist_ok=True)
    for code, rec in activations.items():
        stats["total"] += 1
        session_id = (rec or {}).get("session_id")
        if not session_id:
            stats["skipped"] += 1
            continue
        src = SIMPLE_DIR / session_id
        alias_name = f"{code}__{session_id}"
        dst = SIMPLE_DIR / alias_name

        if not src.exists():
            stats["missing_source"] += 1
            continue
        if dst.exists():
            stats["skipped"] += 1
            continue

        if dry_run:
            print(f"[DRY-RUN] ln -s {src} {dst}")
        else:
            os.symlink(src, dst)
        stats["linked"] += 1
    return stats


def main():
    parser = argparse.ArgumentParser(description="同步 simple 会话目录别名")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入")
    args = parser.parse_args()

    os.chdir(BACKEND_ROOT)
    result = sync_alias(dry_run=args.dry_run)
    prefix = "[DRY-RUN] " if args.dry_run else ""
    print(f"{prefix}总记录: {result['total']}")
    print(f"{prefix}新建别名: {result['linked']}")
    print(f"{prefix}跳过: {result['skipped']}")
    print(f"{prefix}源目录缺失: {result['missing_source']}")


if __name__ == "__main__":
    main()

