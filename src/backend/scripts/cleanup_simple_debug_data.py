#!/usr/bin/env python3
"""
安全清理 data/simple 中已迁移的调试数据（方案 A 第二步）。

使用方式：
1) 先执行迁移脚本（建议）：
   python src/backend/scripts/migrate_simple_debug_data.py --apply
2) 读取 manifest 后再执行清理：
   python src/backend/scripts/cleanup_simple_debug_data.py \
     --manifest data/test/simple/migration_manifests/xxx.json \
     --apply \
     --confirm-manifest-id <manifest_id> \
     --remove-directories

安全保护：
- 默认 dry-run
- --apply + --confirm-manifest-id 双确认才会执行
- 仅删除 manifest 中列出的调试激活码索引项
- 目录删除采用 move 到备份目录（非直接 rm），便于回滚
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


BACKEND_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_ROOT.parent.parent
PROD_SIMPLE_ROOT = PROJECT_ROOT / "data" / "simple"
TEST_SIMPLE_ROOT = PROJECT_ROOT / "data" / "test" / "simple"
DEFAULT_MANIFEST_DIR = TEST_SIMPLE_ROOT / "migration_manifests"
BACKUP_ROOT = PROJECT_ROOT / "data" / "backups"

DEBUG_DIRS = ["sandboxes", "admin_workspaces", "admin_prompt_lab"]
DEBUG_FILES = ["sandbox_fork_audit.jsonl"]


def load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8") or "null")
    except (OSError, json.JSONDecodeError, TypeError):
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _latest_manifest() -> Path | None:
    if not DEFAULT_MANIFEST_DIR.is_dir():
        return None
    files = sorted(DEFAULT_MANIFEST_DIR.glob("migrate-simple-debug-*.json"))
    return files[-1] if files else None


def _require_manifest(path: Path) -> Dict[str, Any]:
    manifest = load_json(path, None)
    if not isinstance(manifest, dict):
        raise ValueError(f"manifest 非法或不存在: {path}")
    if not manifest.get("manifest_id"):
        raise ValueError("manifest 缺少 manifest_id")
    return manifest


def _validate_cross_root(manifest: Dict[str, Any]) -> List[str]:
    warnings: List[str] = []
    test_act = load_json(TEST_SIMPLE_ROOT / "activations.json", {}) or {}
    for code in manifest.get("debug_activation_codes_migrated") or []:
        c = str(code or "").strip().upper()
        if c and c not in test_act:
            warnings.append(f"missing_in_test_activations:{c}")
    for name in DEBUG_DIRS:
        src = PROD_SIMPLE_ROOT / name
        dst = TEST_SIMPLE_ROOT / name
        if src.exists() and not dst.exists():
            warnings.append(f"target_missing_for_dir:{name}")
    return warnings


def _remove_activation_codes(
    codes: List[str],
    *,
    dry_run: bool,
) -> Dict[str, Any]:
    prod_act_file = PROD_SIMPLE_ROOT / "activations.json"
    prod_rb_file = PROD_SIMPLE_ROOT / "activations_recycle_bin.json"
    prod_act = load_json(prod_act_file, {}) or {}
    prod_rb = load_json(prod_rb_file, {}) or {}

    removed_act: List[str] = []
    removed_rb: List[str] = []

    for code in codes:
        c = str(code or "").strip().upper()
        if not c:
            continue
        if c in prod_act:
            removed_act.append(c)
            if not dry_run:
                prod_act.pop(c, None)
        if c in prod_rb:
            removed_rb.append(c)
            if not dry_run:
                prod_rb.pop(c, None)

    if not dry_run:
        save_json(prod_act_file, prod_act)
        save_json(prod_rb_file, prod_rb)

    return {"removed_from_activations": sorted(removed_act), "removed_from_recycle": sorted(removed_rb)}


def _move_debug_paths_to_backup(*, dry_run: bool, backup_dir: Path) -> Dict[str, Any]:
    moved_dirs: List[str] = []
    moved_files: List[str] = []

    for name in DEBUG_DIRS:
        src = PROD_SIMPLE_ROOT / name
        if not src.exists():
            continue
        dst = backup_dir / name
        moved_dirs.append(name)
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))

    for name in DEBUG_FILES:
        src = PROD_SIMPLE_ROOT / name
        if not src.exists():
            continue
        dst = backup_dir / name
        moved_files.append(name)
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))

    return {"moved_dirs": moved_dirs, "moved_files": moved_files}


def run_cleanup(
    *,
    manifest_path: Path,
    apply: bool,
    confirm_manifest_id: str,
    remove_directories: bool,
) -> Dict[str, Any]:
    dry_run = not apply
    manifest = _require_manifest(manifest_path)
    manifest_id = str(manifest.get("manifest_id"))
    warnings = _validate_cross_root(manifest)

    if apply and confirm_manifest_id.strip() != manifest_id:
        raise ValueError("confirm_manifest_id 与 manifest_id 不一致，拒绝执行")

    codes = [str(c).strip().upper() for c in (manifest.get("debug_activation_codes_migrated") or []) if str(c).strip()]
    activation_cleanup = _remove_activation_codes(codes, dry_run=dry_run)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_dir = BACKUP_ROOT / f"simple-debug-cleanup-{ts}"
    moved = {"moved_dirs": [], "moved_files": []}
    if remove_directories:
        moved = _move_debug_paths_to_backup(dry_run=dry_run, backup_dir=backup_dir)

    result = {
        "mode": "dry-run" if dry_run else "apply",
        "manifest_path": str(manifest_path),
        "manifest_id": manifest_id,
        "confirm_manifest_id": confirm_manifest_id,
        "remove_directories": remove_directories,
        "backup_dir": str(backup_dir),
        "warnings": warnings,
        "activation_cleanup": activation_cleanup,
        "path_cleanup": moved,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely cleanup migrated debug data from data/simple.")
    parser.add_argument("--manifest", default="", help="迁移清单路径（默认取最新 manifest）")
    parser.add_argument("--apply", action="store_true", help="执行清理（默认 dry-run）")
    parser.add_argument(
        "--confirm-manifest-id",
        default="",
        help="执行 apply 时必须填写且与 manifest_id 完全一致",
    )
    parser.add_argument(
        "--remove-directories",
        action="store_true",
        help="同时清理 data/simple 下调试目录（移动到 backup，而非直接删除）",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve() if args.manifest else _latest_manifest()
    if not manifest_path:
        raise SystemExit("未找到 manifest，请先执行 migrate_simple_debug_data.py --apply")

    result = run_cleanup(
        manifest_path=manifest_path,
        apply=bool(args.apply),
        confirm_manifest_id=args.confirm_manifest_id or "",
        remove_directories=bool(args.remove_directories),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not args.apply:
        print("\n[提示] 当前为 dry-run。执行时需要 --apply + --confirm-manifest-id。")


if __name__ == "__main__":
    main()

