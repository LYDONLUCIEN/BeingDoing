#!/usr/bin/env python3
"""
Metadata 字段迁移脚本：将旧结论状态字段迁移到新字段，然后删除旧字段。

旧字段 → 新字段：
  pending_status        → conclusion_state
  pending_conclusion    → conclusion_draft
  dimension_conclusion  → conclusion_final
  pending_last_rejected → conclusion_feedback

用法：
  # 预览模式（不修改文件）
  python scripts/migrate_metadata_fields.py --dry-run

  # 执行迁移
  python scripts/migrate_metadata_fields.py

  # 指定扫描目录
  python scripts/migrate_metadata_fields.py --dirs data/simple/reports data/test/simple
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

OLD_TO_NEW_MAP = {
    "pending_status": "conclusion_state",
    "pending_conclusion": "conclusion_draft",
    "dimension_conclusion": "conclusion_final",
}
# pending_last_rejected 是嵌套结构，特殊处理
OLD_NESTED_FIELD = "pending_last_rejected"
NEW_FEEDBACK_FIELD = "conclusion_feedback"

# pending_status 值映射
STATUS_MAP = {
    "awaiting_confirmation": "pending",
    "confirmed": "confirmed",
    "rejected": "rejected",
    "none": "none",
    "pending": "pending",
}

SKIP_FILENAMES = {
    "record.json",
    "rumination_progress.json",
    "activations.json",
    "activations_recycle_bin.json",
    "profiles.json",
    "activation_bindings.json",
    "note.json",
}


def migrate_metadata(meta: dict) -> tuple[dict, list[str]]:
    """
    迁移单个 metadata dict。返回 (新 meta, 变更描述列表)。
    不修改原 dict，返回新副本。
    """
    changes = []
    new_meta = dict(meta)

    # 1. pending_status → conclusion_state
    old_status = meta.get("pending_status")
    new_state = meta.get("conclusion_state")
    if old_status and not new_state:
        mapped = STATUS_MAP.get(str(old_status).strip().lower(), "none")
        new_meta["conclusion_state"] = mapped
        changes.append(f"pending_status='{old_status}' → conclusion_state='{mapped}'")

    # 2. pending_conclusion → conclusion_draft
    old_draft = meta.get("pending_conclusion")
    new_draft = meta.get("conclusion_draft")
    if isinstance(old_draft, dict) and not isinstance(new_draft, dict):
        new_meta["conclusion_draft"] = old_draft
        changes.append("pending_conclusion → conclusion_draft")

    # 3. dimension_conclusion → conclusion_final
    old_final = meta.get("dimension_conclusion")
    new_final = meta.get("conclusion_final")
    if isinstance(old_final, dict) and not isinstance(new_final, dict):
        new_meta["conclusion_final"] = old_final
        changes.append("dimension_conclusion → conclusion_final")

    # 4. pending_last_rejected.feedback → conclusion_feedback
    old_rejected = meta.get(OLD_NESTED_FIELD)
    new_feedback = meta.get(NEW_FEEDBACK_FIELD)
    if isinstance(old_rejected, dict) and not new_feedback:
        fb = old_rejected.get("feedback", "")
        if fb:
            new_meta[NEW_FEEDBACK_FIELD] = fb
            changes.append(f"pending_last_rejected.feedback → conclusion_feedback")

    # 5. 推断 conclusion_state（如果仍为空）
    if not new_meta.get("conclusion_state"):
        if meta.get("thread_completed") and (
            new_meta.get("conclusion_final") or new_meta.get("dimension_conclusion")
        ):
            new_meta["conclusion_state"] = "confirmed"
            changes.append("inferred conclusion_state='confirmed' from thread_completed")
        elif new_meta.get("conclusion_draft") or new_meta.get("pending_conclusion"):
            new_meta["conclusion_state"] = "pending"
            changes.append("inferred conclusion_state='pending' from draft")
        elif new_meta.get("conclusion_feedback"):
            new_meta["conclusion_state"] = "rejected"
            changes.append("inferred conclusion_state='rejected' from feedback")

    # 6. 删除旧字段
    removed = []
    for old_key in [
        "pending_status",
        "pending_conclusion",
        "dimension_conclusion",
        OLD_NESTED_FIELD,
    ]:
        if old_key in new_meta:
            del new_meta[old_key]
            removed.append(old_key)
    if removed:
        changes.append(f"removed old fields: {', '.join(removed)}")

    return new_meta, changes


def process_file(filepath: Path, dry_run: bool) -> dict:
    """处理单个对话 JSON 文件。返回统计信息。"""
    result = {"path": str(filepath), "status": "skipped", "changes": []}

    try:
        raw = filepath.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError) as e:
        result["status"] = "error"
        result["error"] = str(e)
        return result

    meta = data.get("metadata")
    if not isinstance(meta, dict):
        return result

    # 检查是否有旧字段
    has_old = any(
        meta.get(k)
        for k in ["pending_status", "pending_conclusion", "dimension_conclusion", OLD_NESTED_FIELD]
    )
    if not has_old:
        return result

    new_meta, changes = migrate_metadata(meta)
    if not changes:
        return result

    result["changes"] = changes
    result["status"] = "migrated" if not dry_run else "would_migrate"

    if not dry_run:
        data["metadata"] = new_meta
        filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    return result


def scan_and_migrate(dirs: list[str], dry_run: bool) -> list[dict]:
    """扫描目录并迁移所有对话文件。"""
    results = []
    for d in dirs:
        base = Path(d)
        if not base.is_dir():
            print(f"  [WARN] Directory not found: {d}")
            continue
        for root, _, files in os.walk(base):
            for f in files:
                if not f.endswith(".json"):
                    continue
                if f in SKIP_FILENAMES:
                    continue
                fp = Path(root) / f
                result = process_file(fp, dry_run)
                if result["status"] != "skipped":
                    results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser(description="Migrate old metadata fields to new format")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview changes without modifying files"
    )
    parser.add_argument(
        "--dirs",
        nargs="+",
        default=[
            "data/simple/reports",
            "data/test/simple",
            "data/backups",
            "test/backend/fixtures",
        ],
        help="Directories to scan",
    )
    args = parser.parse_args()

    # 项目根目录 = 包含 data/ 的那一层
    repo_root = PROJECT_ROOT.parent.parent  # scripts -> backend -> src -> repo_root
    os.chdir(repo_root)

    mode = "DRY RUN" if args.dry_run else "LIVE"
    print(f"\n{'='*60}")
    print(f"  Metadata Migration ({mode})")
    print(f"  Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print(f"  Scanning: {', '.join(args.dirs)}")
    print(f"{'='*60}\n")

    results = scan_and_migrate(args.dirs, args.dry_run)

    migrated = [r for r in results if r["status"] in ("migrated", "would_migrate")]
    errors = [r for r in results if r["status"] == "error"]

    for r in migrated:
        print(f"  [{r['status'].upper()}] {r['path']}")
        for c in r["changes"]:
            print(f"    - {c}")

    for r in errors:
        print(f"  [ERROR] {r['path']}: {r.get('error', 'unknown')}")

    print(f"\n{'='*60}")
    print(
        f"  Summary: {len(migrated)} files {'would be ' if args.dry_run else ''}migrated, {len(errors)} errors"
    )
    print(f"{'='*60}\n")

    if args.dry_run and migrated:
        print("  Run without --dry-run to apply changes.\n")


if __name__ == "__main__":
    main()
