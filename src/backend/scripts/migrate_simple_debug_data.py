#!/usr/bin/env python3
"""
迁移 simple 调试数据到独立测试根目录。

目标：
- 将 data/simple 下的非业务调试数据迁移到 data/test/simple
- 保持真实用户业务数据留在 data/simple

迁移范围：
- sandboxes/
- admin_workspaces/
- admin_prompt_lab/
- sandbox_fork_audit.jsonl
- activations.json 中调试激活码记录（SBX/ADM/is_sandbox/workspace_kind=fork|resident）
- activations_recycle_bin.json 中对应调试记录

安全策略：
- 默认 dry-run（不写入）
- --apply 才执行
- 每次执行写入 manifest（可用于后续清理脚本二次确认）
"""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


BACKEND_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_ROOT.parent.parent
PROD_SIMPLE_ROOT = PROJECT_ROOT / "data" / "simple"
TEST_SIMPLE_ROOT = PROJECT_ROOT / "data" / "test" / "simple"
MANIFEST_DIR = TEST_SIMPLE_ROOT / "migration_manifests"

DEBUG_DIRS = ["sandboxes", "admin_workspaces", "admin_prompt_lab"]
DEBUG_AUDIT_FILES = ["sandbox_fork_audit.jsonl"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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


def is_debug_activation_record(code: str, rec: Dict[str, Any]) -> bool:
    c = (code or "").strip().upper()
    if c.startswith("SBX") or c.startswith("ADM"):
        return True
    if bool((rec or {}).get("is_sandbox")):
        return True
    kind = str((rec or {}).get("workspace_kind") or "").strip().lower()
    return kind in {"fork", "resident"}


@dataclass
class MigrateStats:
    mode: str
    manifest_id: str
    started_at: str
    prod_root: str
    test_root: str
    copied_dirs: List[str]
    copied_files: List[str]
    debug_activation_codes_migrated: List[str]
    debug_recycle_codes_migrated: List[str]
    warnings: List[str]


def _copy_debug_dirs_and_files(dry_run: bool) -> tuple[List[str], List[str], List[str]]:
    copied_dirs: List[str] = []
    copied_files: List[str] = []
    warnings: List[str] = []

    for name in DEBUG_DIRS:
        src = PROD_SIMPLE_ROOT / name
        dst = TEST_SIMPLE_ROOT / name
        if not src.exists():
            continue
        if not src.is_dir():
            warnings.append(f"skip_non_dir:{src}")
            continue
        copied_dirs.append(name)
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dst, dirs_exist_ok=True)

    for name in DEBUG_AUDIT_FILES:
        src = PROD_SIMPLE_ROOT / name
        dst = TEST_SIMPLE_ROOT / name
        if not src.exists():
            continue
        if not src.is_file():
            warnings.append(f"skip_non_file:{src}")
            continue
        copied_files.append(name)
        if not dry_run:
            if not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            else:
                # 合并保留：直接追加源内容（审计日志允许重复，清理时再按事件去重）
                with src.open("r", encoding="utf-8") as f1, dst.open("a", encoding="utf-8") as f2:
                    f2.write(f1.read())

    return copied_dirs, copied_files, warnings


def _migrate_activation_indexes(dry_run: bool) -> tuple[List[str], List[str]]:
    prod_act_file = PROD_SIMPLE_ROOT / "activations.json"
    test_act_file = TEST_SIMPLE_ROOT / "activations.json"
    prod_rb_file = PROD_SIMPLE_ROOT / "activations_recycle_bin.json"
    test_rb_file = TEST_SIMPLE_ROOT / "activations_recycle_bin.json"

    prod_act = load_json(prod_act_file, {}) or {}
    test_act = load_json(test_act_file, {}) or {}
    prod_rb = load_json(prod_rb_file, {}) or {}
    test_rb = load_json(test_rb_file, {}) or {}

    moved_act_codes: List[str] = []
    moved_rb_codes: List[str] = []

    for code, rec in (prod_act or {}).items():
        if not isinstance(rec, dict):
            continue
        if not is_debug_activation_record(code, rec):
            continue
        c = str(code).strip().upper()
        test_act[c] = rec
        moved_act_codes.append(c)

    for code, rec in (prod_rb or {}).items():
        if not isinstance(rec, dict):
            continue
        orig = rec.get("original_record") if isinstance(rec.get("original_record"), dict) else {}
        if not is_debug_activation_record(str(code), orig):
            continue
        c = str(code).strip().upper()
        test_rb[c] = rec
        moved_rb_codes.append(c)

    if not dry_run:
        if moved_act_codes:
            save_json(test_act_file, test_act)
        if moved_rb_codes:
            save_json(test_rb_file, test_rb)

    moved_act_codes.sort()
    moved_rb_codes.sort()
    return moved_act_codes, moved_rb_codes


def run_migration(*, dry_run: bool, manifest_out: Path) -> Dict[str, Any]:
    manifest_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    copied_dirs, copied_files, warnings = _copy_debug_dirs_and_files(dry_run=dry_run)
    moved_act_codes, moved_rb_codes = _migrate_activation_indexes(dry_run=dry_run)

    stats = MigrateStats(
        mode="dry-run" if dry_run else "apply",
        manifest_id=manifest_id,
        started_at=now_iso(),
        prod_root=str(PROD_SIMPLE_ROOT),
        test_root=str(TEST_SIMPLE_ROOT),
        copied_dirs=copied_dirs,
        copied_files=copied_files,
        debug_activation_codes_migrated=moved_act_codes,
        debug_recycle_codes_migrated=moved_rb_codes,
        warnings=warnings,
    )
    payload = asdict(stats)
    payload["manifest_path"] = str(manifest_out)

    if not dry_run:
        save_json(manifest_out, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate debug simple data to data/test/simple.")
    parser.add_argument("--apply", action="store_true", help="执行迁移写入（默认 dry-run）")
    parser.add_argument(
        "--manifest-out",
        default="",
        help="manifest 输出路径（默认 data/test/simple/migration_manifests/<timestamp>.json）",
    )
    args = parser.parse_args()

    dry_run = not args.apply
    TEST_SIMPLE_ROOT.mkdir(parents=True, exist_ok=True)
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    manifest_out = (
        Path(args.manifest_out).resolve()
        if args.manifest_out
        else (MANIFEST_DIR / f"migrate-simple-debug-{ts}.json")
    )

    result = run_migration(dry_run=dry_run, manifest_out=manifest_out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if dry_run:
        print("\n[提示] 当前为 dry-run。加 --apply 才会执行写入并生成 manifest。")


if __name__ == "__main__":
    main()

