#!/usr/bin/env python3
"""存量迁移：为已完成五阶段的报告补写 steps.rumination.locked = true。

背景（2026-07-30）：报告定稿后 rumination 应锁定（终选 n选3 不可再改）。
锁定机制是「进入下一阶段时锁上一阶段」，rumination 是最后一步，历史上永远
不会被锁定。新代码已在终选提交时显式锁定（V4 submit_final_selection /
V3 step7 定稿分支），本脚本负责补历史数据。

口径（满足其一即锁定）：
1. report record 的五个阶段均有 selected_session_id（_report_portal_unlocked 为 True）；
2. 同目录 rumination_v4_progress.json 的 final_selection.submitted 为 True
   （V4 已终选提交、但 record.json 的 steps 未回填的存量数据）。

用法：
    python scripts/migrate_lock_rumination.py            # dry-run，只打印
    python scripts/migrate_lock_rumination.py --apply    # 实际写入
    python scripts/migrate_lock_rumination.py --root data/simple   # 指定根目录
"""

import argparse
import json
import sys
from pathlib import Path

STEP_IDS = ("values", "strengths", "interests", "purpose", "rumination")


def portal_unlocked(steps: dict) -> bool:
    return all(bool((steps.get(s) or {}).get("selected_session_id")) for s in STEP_IDS)


def v4_final_submitted(report_dir: Path) -> bool:
    """同目录 V4 状态的 final_selection.submitted 是否为 True。"""
    v4_path = report_dir / "rumination_v4_progress.json"
    if not v4_path.is_file():
        return False
    try:
        state = json.loads(v4_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return bool((state.get("final_selection") or {}).get("submitted"))


def migrate(root: Path, apply: bool) -> None:
    reports_dir = root / "reports"
    if not reports_dir.is_dir():
        print(f"[skip] {reports_dir} 不存在")
        return
    scanned = locked = skipped = 0
    for record_path in sorted(reports_dir.glob("*/record.json")):
        scanned += 1
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[error] {record_path}: {e}")
            continue
        steps = record.get("steps") or {}
        rum = steps.get("rumination") or {}
        code = record.get("activation_code") or record_path.parent.name
        if rum.get("locked"):
            skipped += 1
            continue
        if not portal_unlocked(steps) and not v4_final_submitted(record_path.parent):
            skipped += 1
            continue
        print(f"[lock] {code} ({record_path.parent.name})")
        locked += 1
        if apply:
            rum["locked"] = True
            steps["rumination"] = rum
            record["steps"] = steps
            record_path.write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    action = "已锁定" if apply else "将锁定(dry-run)"
    print(f"\n{root}: 扫描 {scanned}，{action} {locked}，跳过 {skipped}")


def main() -> None:
    parser = argparse.ArgumentParser(description="补写 rumination.locked（报告定稿锁定）")
    parser.add_argument("--apply", action="store_true", help="实际写入（默认 dry-run）")
    parser.add_argument(
        "--root",
        action="append",
        default=None,
        help="simple 根目录（可多次指定；默认 data/simple 与 data/test/simple）",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    roots = [Path(r) for r in (args.root or [])] or [
        project_root / "data" / "simple",
        project_root / "data" / "test" / "simple",
    ]
    for root in roots:
        migrate(root, args.apply)
    if not args.apply:
        print("\n这是 dry-run。确认无误后加 --apply 实际写入。")
        sys.exit(0)


if __name__ == "__main__":
    main()
