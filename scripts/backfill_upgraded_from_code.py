#!/usr/bin/env python3
"""
backfill_upgraded_from_code.py — 回填试用码记录的 upgraded_from_code 溯源字段（一次性）

背景：
    消耗升级（ADR-0014）上线初期只在被消耗码上写 consumed_into，未在试用码记录上
    反写来源码。ActivationRecord 新增 upgraded_from_code 字段后（consume_for_trial_upgrade
    已实时写入），本脚本对历史存量做一次性反查回填。

回填规则（幂等）：
    对每条 status=consumed 且 consumed_into 非空的记录，找到 consumed_into 指向的
    试用码记录，若其 upgraded_from_code 为空则反写为被消耗码码值；已有值一律不覆盖
    （以首次消耗为准，打印跳过）。

目标索引（两个 SimpleActivationManager 全量记录；路径写死，测试可用环境变量覆盖根目录）：
    data/simple/activations.json        生产激活码索引
    data/test/simple/activations.json   沙箱激活码索引（SBX/ADM）

安全设计（沿用 migrate_activation_schema.py 先例）：
    - 时间戳备份：写入前把原文件字节级拷贝到 data/backups/upgraded_from_backfill_{ts}/
    - 幂等：重复执行只会回填仍为空的记录（第二次应输出"回填 0"）
    - 停服保护：检测到 8000 端口在监听（后端运行中）则拒绝执行，除非 --force

用法：
    python3 scripts/backfill_upgraded_from_code.py --dry-run   # 只读预演，不写不备份
    python3 scripts/backfill_upgraded_from_code.py             # 实际执行（需先停服）
    python3 scripts/backfill_upgraded_from_code.py --force     # 跳过端口检查（自担风险）
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

# 把 src/backend 加入 path 以便 import app.utils.*
_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parent.parent / "src" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.utils.simple_activation_manager import (  # noqa: E402
    ActivationStatus,
    SimpleActivationManager,
    get_simple_base_dir,
    get_simple_test_base_dir,
)

# 测试专用：设置后以此目录替代项目根（其下应有 data/simple、data/test/simple）
ENV_ROOT_OVERRIDE = "UPGRADED_FROM_BACKFILL_ROOT_OVERRIDE"


def _project_root() -> Path:
    override = os.environ.get(ENV_ROOT_OVERRIDE)
    if override:
        return Path(override).resolve()
    return _THIS.parent.parent


def _targets(root: Path, using_override: bool) -> List[Tuple[str, Path]]:
    """(备份文件名, 索引目录)

    默认走 get_simple_base_dir() / get_simple_test_base_dir()（生产 + 测试/沙箱两个索引）；
    测试模式（环境变量覆盖根目录）下按覆盖根拼接。
    """
    if not using_override:
        return [
            ("simple_activations.json", get_simple_base_dir()),
            ("test_activations.json", get_simple_test_base_dir()),
        ]
    return [
        ("simple_activations.json", root / "data" / "simple"),
        ("test_activations.json", root / "data" / "test" / "simple"),
    ]


def _port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _scan_manager(mgr: SimpleActivationManager, dry_run: bool) -> Dict[str, int]:
    """扫描一个索引并回填 upgraded_from_code。

    Args:
        mgr: 目标 SimpleActivationManager
        dry_run: True 时只统计不落盘

    Returns:
        统计字典：consumed（扫描到的消耗记录数）、backfilled（回填数）、
        skipped_existing（试用码已有值跳过数）、skipped_missing（试用码不存在跳过数）
    """
    stats = {"consumed": 0, "backfilled": 0, "skipped_existing": 0, "skipped_missing": 0}
    records = mgr.list_activations()
    dirty = False
    for code, rec in records.items():
        if rec.status != ActivationStatus.CONSUMED.value:
            continue
        trial_code = (getattr(rec, "consumed_into", None) or "").strip().upper()
        if not trial_code:
            continue
        stats["consumed"] += 1
        trial_rec = records.get(trial_code)
        if trial_rec is None:
            stats["skipped_missing"] += 1
            print(f"   ⏭  {code} -> {trial_code}：目标试用码不存在，跳过")
            continue
        if getattr(trial_rec, "upgraded_from_code", None):
            stats["skipped_existing"] += 1
            print(f"   ⏭  {code} -> {trial_code}：已有 upgraded_from_code，跳过（不覆盖）")
            continue
        stats["backfilled"] += 1
        print(f"   📝 {code} -> {trial_code}：{'将回填' if dry_run else '已回填'} upgraded_from_code")
        if not dry_run:
            trial_rec.upgraded_from_code = code
            records[trial_code] = trial_rec
            dirty = True
    if dirty:
        mgr._save_all(records)
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="回填试用码 upgraded_from_code 溯源字段（一次性）")
    parser.add_argument("--dry-run", action="store_true", help="只读预演：统计将回填的记录，不写盘不备份")
    parser.add_argument("--force", action="store_true", help="跳过后端端口检查（自担并发写风险）")
    args = parser.parse_args()

    root = _project_root()
    using_override = bool(os.environ.get(ENV_ROOT_OVERRIDE))

    # R1 防护：后端运行中拒绝执行（测试用根覆盖时跳过）
    if not args.dry_run and not args.force and not using_override and _port_in_use(8000):
        print("❌ 检测到 8000 端口在监听（后端可能运行中）。请先 ./start.sh stop 再执行；")
        print("   确需在线执行请加 --force（自担并发写丢码风险）。")
        return 2

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = root / "data" / "backups" / f"upgraded_from_backfill_{timestamp}"

    print(f"数据根：{root}{'（环境变量覆盖，测试模式）' if using_override else ''}")
    print(f"模式：{'DRY-RUN（只读）' if args.dry_run else '实际执行'}")
    print("-" * 72)

    totals = {"consumed": 0, "backfilled": 0, "skipped_existing": 0, "skipped_missing": 0}
    backup_done = False
    for backup_name, base_dir in _targets(root, using_override):
        activations_file = base_dir / "activations.json"
        if not activations_file.exists():
            print(f"⏭  {activations_file}  不存在，跳过")
            continue
        print(f"📂 {activations_file}")
        if not args.dry_run and not backup_done:
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_done = True
        if not args.dry_run:
            shutil.copyfile(activations_file, backup_dir / backup_name)
        mgr = SimpleActivationManager(base_dir=str(base_dir))
        stats = _scan_manager(mgr, args.dry_run)
        for key in totals:
            totals[key] += stats[key]
        print(
            f"   小计：consumed {stats['consumed']} | "
            f"{'将回填' if args.dry_run else '已回填'} {stats['backfilled']} | "
            f"跳过（已有值 {stats['skipped_existing']} / 试用码不存在 {stats['skipped_missing']}）"
        )

    print("-" * 72)
    if backup_done:
        print(f"📦 备份完成：{backup_dir}")
    print(
        f"合计：扫描 consumed {totals['consumed']} | "
        f"{'将回填' if args.dry_run else '已回填'} {totals['backfilled']} | "
        f"跳过 {totals['skipped_existing'] + totals['skipped_missing']}"
        f"（已有值 {totals['skipped_existing']} / 试用码不存在 {totals['skipped_missing']}）"
    )
    if args.dry_run:
        print("DRY-RUN 结束，未写任何文件。确认无误后去掉 --dry-run 实际执行。")
    else:
        print("✅ 回填完成。如重复执行应看到「已回填 0」（幂等）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
