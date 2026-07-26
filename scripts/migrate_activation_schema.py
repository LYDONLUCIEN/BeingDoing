#!/usr/bin/env python3
"""
migrate_activation_schema.py — ADR-0008 存量激活码 schema 补全迁移（一次性）

背景：
    套餐与试用体系上线后，激活码记录新增多个字段（code_type / vip_level / package_type /
    source_order_id / purchaser_user_id / report_authorized 等）。存量记录在磁盘上缺这些
    字段，运行时靠 SimpleActivationManager._load_all() 的 setdefault 懒迁移兜底（一律视
    为完整码）。本脚本把同样的默认值显式回写磁盘，让磁盘数据成为真相。

目标文件（路径写死，不接受自定义，防误操作；测试可用环境变量覆盖根目录）：
    data/simple/activations.json                      生产激活码索引
    data/simple/activations_recycle_bin.json          生产回收站（补丁打在 original_record 内）
    data/test/simple/activations.json                 沙箱激活码索引（SBX/ADM）
    data/test/simple/activations_recycle_bin.json     沙箱回收站

安全设计：
    - 无损补丁：在原始 dict 层 setdefault，不丢任何记录（含损坏条目/未知字段），不覆盖已有值
    - 时间戳备份：写入前把原文件字节级拷贝到 data/backups/activation_schema_migration_{ts}/
    - 原子写：临时文件 + os.replace，中途崩溃不留半截文件
    - 幂等：重复执行只会补仍缺的字段（第二次应输出"已补全 0"）
    - 停服保护：检测到 8000 端口在监听（后端运行中）则拒绝执行，除非 --force

用法：
    python3 scripts/migrate_activation_schema.py --dry-run   # 只读预检，不写不备份
    python3 scripts/migrate_activation_schema.py             # 实际执行（需先停服）
    python3 scripts/migrate_activation_schema.py --force     # 跳过端口检查（自担风险）

运维文档：wiki/开发文档/0726-激活码schema迁移脚本说明.md
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── 默认值清单：与 app/utils/simple_activation_manager.py 的 _load_all() setdefault
#    严格一致（权威定义）。test/backend/test_migrate_activation_schema.py 有漂移守卫测试。
SCHEMA_DEFAULTS: Dict[str, Any] = {
    "vip_level": 1,
    "is_sandbox": False,
    "sandbox_root": None,
    "fork_id": None,
    "forked_from_code": None,
    "forked_at": None,
    "forked_by_user_id": None,
    "sandbox_expires_at": None,
    "workspace_kind": None,
    "workspace_root": None,
    "report_id": None,
    "report_index_updated_at": None,
    # 套餐与试用体系：存量记录一律视为完整码（ADR-0008）
    "code_type": "full",
    "package_type": None,
    "source_order_id": None,
    "purchaser_user_id": None,
    "report_authorized": False,
}

# 测试专用：设置后以此目录替代项目根（其下应有 data/simple、data/test/simple）
ENV_ROOT_OVERRIDE = "ACTIVATION_MIGRATION_ROOT_OVERRIDE"


def _project_root() -> Path:
    override = os.environ.get(ENV_ROOT_OVERRIDE)
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parents[1]


def _targets(root: Path) -> List[Tuple[str, Path, bool]]:
    """(备份文件名, 目标路径, 是否回收站)"""
    return [
        ("simple_activations.json", root / "data" / "simple" / "activations.json", False),
        (
            "simple_activations_recycle_bin.json",
            root / "data" / "simple" / "activations_recycle_bin.json",
            True,
        ),
        ("test_activations.json", root / "data" / "test" / "simple" / "activations.json", False),
        (
            "test_activations_recycle_bin.json",
            root / "data" / "test" / "simple" / "activations_recycle_bin.json",
            True,
        ),
    ]


def _patch_record(rec: Any) -> int:
    """对单条记录 dict 做 setdefault 补丁，返回补了几个字段。非 dict 原样跳过。"""
    if not isinstance(rec, dict):
        return 0
    patched = 0
    for key, value in SCHEMA_DEFAULTS.items():
        if key not in rec:
            rec[key] = value
            patched += 1
    return patched


def _patch_file(path: Path, is_recycle_bin: bool) -> Tuple[int, int, int, Dict[str, Any]]:
    """
    加载并补丁一个 JSON 文件（内存中）。

    Returns:
        (总记录数, 被补记录数, 原本完整记录数, 补丁后的完整数据)

    Raises:
        ValueError: JSON 损坏或顶层不是 dict —— 中止，不写盘
    """
    raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    if not isinstance(raw, dict):
        raise ValueError(f"顶层结构不是 dict：{path}")
    total = len(raw)
    patched_records = 0
    for entry in raw.values():
        target = entry.get("original_record") if is_recycle_bin and isinstance(entry, dict) else entry
        if _patch_record(target) > 0:
            patched_records += 1
    return total, patched_records, total - patched_records, raw


def _atomic_write(path: Path, payload: Dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".migrate_tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ADR-0008 存量激活码 schema 补全迁移（一次性）")
    parser.add_argument("--dry-run", action="store_true", help="只读预检：统计将补的记录，不写盘不备份")
    parser.add_argument("--force", action="store_true", help="跳过后端端口检查（自担并发写风险）")
    args = parser.parse_args()

    root = _project_root()
    using_override = bool(os.environ.get(ENV_ROOT_OVERRIDE))

    # R1 防护：后端运行中拒绝执行（测试用根覆盖时跳过）
    if not args.dry_run and not args.force and not using_override and _port_in_use(8000):
        print("❌ 检测到 8000 端口在监听（后端可能运行中）。请先 ./start.sh stop 再执行；")
        print("   确需在线执行请加 --force（自担并发写丢码风险，见运维文档 R1）。")
        return 2

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = root / "data" / "backups" / f"activation_schema_migration_{timestamp}"

    print(f"数据根：{root}{'（环境变量覆盖，测试模式）' if using_override else ''}")
    print(f"模式：{'DRY-RUN（只读）' if args.dry_run else '实际执行'}")
    print("-" * 72)

    # 第一遍：加载 + 补丁（内存），任何文件损坏则整体中止，不写任何盘
    staged: List[Tuple[str, Path, Dict[str, Any], int, int, int]] = []
    for backup_name, path, is_recycle in _targets(root):
        if not path.exists():
            print(f"⏭  {path}  不存在，跳过")
            continue
        try:
            total, patched, complete, raw = _patch_file(path, is_recycle)
        except (json.JSONDecodeError, ValueError, OSError) as e:
            print(f"❌ {path}  加载失败：{e}")
            print("   已整体中止，未写任何文件。请人工检查该文件后重跑。")
            return 1
        staged.append((backup_name, path, raw, total, patched, complete))

    if not staged:
        print("没有可处理的目标文件。")
        return 0

    # 第二遍：备份 + 原子写
    if not args.dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)
        for backup_name, path, _raw, _t, _p, _c in staged:
            shutil.copyfile(path, backup_dir / backup_name)
        print(f"📦 备份完成：{backup_dir}")

    grand_total = grand_patched = 0
    for backup_name, path, raw, total, patched, complete in staged:
        grand_total += total
        grand_patched += patched
        action = "将补全" if args.dry_run else "已补全"
        print(f"{'📝' if patched else '✅'} {path}")
        print(f"   总记录 {total} | {action} {patched} | 原本完整 {complete}")
        if not args.dry_run and patched > 0:
            _atomic_write(path, raw)

    print("-" * 72)
    print(f"合计：总记录 {grand_total} | {'将补全' if args.dry_run else '已补全'} {grand_patched}")
    if args.dry_run:
        print("DRY-RUN 结束，未写任何文件。确认无误后去掉 --dry-run 实际执行。")
    else:
        print("✅ 迁移完成。如重复执行应看到「已补全 0」（幂等）。")
        print(f"   回滚方式见 wiki/开发文档/0726-激活码schema迁移脚本说明.md §四.1（备份目录见上）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
