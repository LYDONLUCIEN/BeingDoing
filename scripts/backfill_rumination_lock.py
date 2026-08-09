#!/usr/bin/env python3
"""
backfill_rumination_lock.py — 回填 v4 终选已提交但 rumination 未锁定的报告（一次性）

背景：
    2026-08-09 发现 rumination_v4_routes.py 把已含 /reports 的 reports_root 当作
    ReportRegistry 的 base_dir 传入（__init__ 内部会再拼一层 /reports），导致
    final-selection/submit 的 lock_step 写入不存在的路径并静默失败——v4 用户终选
    提交后 record.json 的 rumination.locked 永远为 False，五阶段完成度判定不通过，
    报告页停留「尚未解锁」而非进入审核（not_started → pending_review）。

回填规则（幂等）：
    扫描每个报告目录下的 rumination_v4_progress.json，若 final_selection.submitted
    为 true，且 record.json 中 rumination 阶段 locked 为假、selected_session_id 为空，
    则置 locked=True 并刷新 updated_at。已锁定/已有 session 的一律跳过不覆盖。

顺带做 record.json 完整性扫描：列出 JSON 损坏的报告，只报告不自动修。

目标目录（路径写死，测试可用环境变量覆盖根目录）：
    data/simple/reports/        生产报告
    data/test/simple/reports/   沙箱报告（SBX/ADM）

安全设计（沿用 backfill_upgraded_from_code.py / migrate_activation_schema.py 先例）：
    - 时间戳备份：写入前把原 record.json 字节级拷贝到 data/backups/rumination_lock_backfill_{ts}/
    - 幂等：重复执行只会回填仍未锁定的报告（第二次应输出"回填 0"）
    - 原子写：临时文件 + os.replace，避免写一半损坏
    - 停服保护：检测到 8000 端口在监听（后端运行中）则拒绝执行，除非 --force

用法：
    python3 scripts/backfill_rumination_lock.py --dry-run   # 只读预演，不写不备份
    python3 scripts/backfill_rumination_lock.py             # 实际执行（需先停服）
    python3 scripts/backfill_rumination_lock.py --force     # 跳过端口检查（自担风险）
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

# 把 src/backend 加入 path 以便 import app.utils.*
_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parent.parent / "src" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.utils.simple_activation_manager import (  # noqa: E402
    get_simple_base_dir,
    get_simple_test_base_dir,
)

# 测试专用：设置后以此目录替代项目根（其下应有 data/simple、data/test/simple）
ENV_ROOT_OVERRIDE = "RUMINATION_LOCK_BACKFILL_ROOT_OVERRIDE"


def _project_root() -> Path:
    override = os.environ.get(ENV_ROOT_OVERRIDE)
    if override:
        return Path(override).resolve()
    return _THIS.parent.parent


def _targets(root: Path, using_override: bool) -> List[Tuple[str, Path]]:
    """(标签, reports 目录)"""
    if not using_override:
        return [
            ("simple", get_simple_base_dir() / "reports"),
            ("test", get_simple_test_base_dir() / "reports"),
        ]
    return [
        ("simple", root / "data" / "simple" / "reports"),
        ("test", root / "data" / "test" / "simple" / "reports"),
    ]


def _port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _v4_submitted(progress_file: Path) -> bool:
    try:
        prog = json.loads(progress_file.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"   ⚠️  进度文件损坏，跳过：{progress_file}（{e}）")
        return False
    return bool((prog.get("final_selection") or {}).get("submitted"))


def _needs_lock(record: dict) -> bool:
    rum = ((record.get("steps") or {}).get("rumination")) or {}
    if rum.get("locked"):
        return False
    if str(rum.get("selected_session_id") or "").strip():
        return False
    return True


def _atomic_write_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _scan_reports_dir(
    label: str,
    reports_dir: Path,
    backup_dir: Path,
    dry_run: bool,
    backup_state: Dict[str, bool],
) -> Dict[str, int]:
    """扫描一个 reports 目录：完整性检查 + 回填未锁定的 v4 终选报告。"""
    stats = {"scanned": 0, "corrupt": 0, "submitted": 0, "backfilled": 0, "skipped_locked": 0}
    for report_dir in sorted(p for p in reports_dir.iterdir() if p.is_dir()):
        record_file = report_dir / "record.json"
        progress_file = report_dir / "rumination_v4_progress.json"
        if not record_file.exists():
            continue
        stats["scanned"] += 1
        # 完整性扫描：只报告不自动修
        try:
            record = json.loads(record_file.read_text(encoding="utf-8"))
        except Exception as e:
            stats["corrupt"] += 1
            print(f"   🚨 record.json 损坏（仅报告不修复）：{record_file}（{e}）")
            continue
        if not progress_file.exists() or not _v4_submitted(progress_file):
            continue
        stats["submitted"] += 1
        rid = report_dir.name
        code = record.get("activation_code") or "?"
        if not _needs_lock(record):
            stats["skipped_locked"] += 1
            continue
        stats["backfilled"] += 1
        print(f"   📝 [{label}] {code} ({rid})：{'将锁定' if dry_run else '已锁定'} rumination")
        if dry_run:
            continue
        if not backup_state.get("done"):
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_state["done"] = True
        shutil.copyfile(record_file, backup_dir / f"{label}_{rid}_record.json")
        rum = (record.setdefault("steps", {})).setdefault("rumination", {"step_id": "rumination"})
        rum["locked"] = True
        rum["updated_at"] = datetime.now(timezone.utc).isoformat()
        _atomic_write_json(record_file, record)
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="回填 v4 终选已提交但 rumination 未锁定的报告（一次性）")
    parser.add_argument("--dry-run", action="store_true", help="只读预演：统计将回填的报告，不写盘不备份")
    parser.add_argument("--force", action="store_true", help="跳过后端端口检查（自担并发写风险）")
    args = parser.parse_args()

    root = _project_root()
    using_override = bool(os.environ.get(ENV_ROOT_OVERRIDE))

    # R1 防护：后端运行中拒绝执行（测试用根覆盖时跳过）
    if not args.dry_run and not args.force and not using_override and _port_in_use(8000):
        print("❌ 检测到 8000 端口在监听（后端可能运行中）。请先 ./start.sh stop 再执行；")
        print("   确需在线执行请加 --force（自担并发写风险）。")
        return 2

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = root / "data" / "backups" / f"rumination_lock_backfill_{timestamp}"

    print(f"数据根：{root}{'（环境变量覆盖，测试模式）' if using_override else ''}")
    print(f"模式：{'DRY-RUN（只读）' if args.dry_run else '实际执行'}")
    print("-" * 72)

    totals = {"scanned": 0, "corrupt": 0, "submitted": 0, "backfilled": 0, "skipped_locked": 0}
    backup_state: Dict[str, bool] = {}
    for label, reports_dir in _targets(root, using_override):
        if not reports_dir.is_dir():
            print(f"⏭  {reports_dir}  不存在，跳过")
            continue
        print(f"📂 {reports_dir}")
        stats = _scan_reports_dir(label, reports_dir, backup_dir, args.dry_run, backup_state)
        for key in totals:
            totals[key] += stats[key]
        print(
            f"   小计：扫描 {stats['scanned']} | v4 已提交 {stats['submitted']} | "
            f"{'将回填' if args.dry_run else '已回填'} {stats['backfilled']} | "
            f"已锁定跳过 {stats['skipped_locked']} | 损坏 {stats['corrupt']}"
        )

    print("-" * 72)
    if backup_state.get("done"):
        print(f"📦 备份完成：{backup_dir}")
    print(
        f"合计：扫描 {totals['scanned']} | v4 已提交 {totals['submitted']} | "
        f"{'将回填' if args.dry_run else '已回填'} {totals['backfilled']} | "
        f"已锁定跳过 {totals['skipped_locked']} | 损坏 {totals['corrupt']}（仅报告未修复）"
    )
    if args.dry_run:
        print("DRY-RUN 结束，未写任何文件。确认无误后去掉 --dry-run 实际执行。")
    else:
        print("✅ 回填完成。如重复执行应看到「已回填 0」（幂等）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
