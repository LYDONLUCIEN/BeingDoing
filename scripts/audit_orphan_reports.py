#!/usr/bin/env python3
"""
audit_orphan_reports.py — 孤儿 report 扫描 / 归档 / 清理工具

什么是「孤儿 report」?
  data/simple/reports/{report_id}/ 目录里存了一份 record.json,但这份 report 在业务上
  已经没有合法引用。常见来源:
    1. admin 后台历史 bug:jump_to_rumination / clone_conversation 用 admin 的 user_id
       调用 ensure_report,在真实激活码下产生归属 admin 的污染 report。
    2. 手动改 activations.json 转移激活码归属时,只改了 owner,没同步改 record.user_id,
       导致 (code, 新uid) 匹配不上旧 report,触发 ensure_report 又建一份。
    3. activation 已软删除/已不存在,但 report 目录残留。

子命令(分段式,职责分离):
    scan      只读扫描诊断,列出所有可疑 report,不动任何文件。默认命令。
    archive   把可疑 report 移动到 data/simple/reports_archive/{timestamp}/,可恢复。
    clean     永久删除可疑 report(rm -rf),需双重显式确认。

孤儿判定规则:
    activation_missing   record.activation_code 在 activations.json 中不存在
    activation_deleted   激活码存在但 status=deleted 或 deleted_at≠null
    orphan_prefix        activation_code 以 "ORPHAN__" 开头(历史迁移残留)
    cross_user           record.user_id ≠ activations[code].owner_user_id
                         (诊断用,默认 archive/clean 不纳入,需 --include-cross-user)
    duplicates           同一 (code, user_id) 在 reports/ 下有多份,保留 canonical,其余可清理

用法示例:
    # 1. 扫描当前污染状况(只读)
    python scripts/audit_orphan_reports.py scan
    python scripts/audit_orphan_reports.py scan --json

    # 2. 归档可疑 report(移到备份目录,可恢复)
    python scripts/audit_orphan_reports.py archive --dry-run
    python scripts/audit_orphan_reports.py archive --dry-run --include-orphans --include-cross-user
    python scripts/audit_orphan_reports.py archive --confirm-count 5
    python scripts/audit_orphan_reports.py archive --include-cross-user --confirm-count 2

    # 3. 永久清理(rm -rf,慎用)
    python scripts/audit_orphan_reports.py clean --confirm-count 5 --i-know-this-is-destructive

选项说明:
    --base-dir PATH       覆盖扫描的数据根目录(默认 data/simple)
    --json                scan 输出 JSON 格式(便于程序解析)
    --dry-run             archive/clean 时只打印将要执行的操作,不实际执行
                          (dry-run 时 --confirm-count 可不填)
    --confirm-count N     实际执行时必填:确认本次将处理的 report 数量(防误操作)
    --include-orphans     纳入 ORPHAN__ 前缀的 report(默认不处理)
    --include-cross-user  纳入 cross_user 类 report(默认仅诊断)
    --i-know-this-is-destructive  clean 命令必填:确认永久删除不可恢复

退出码:
    0  正常
    1  发现可疑 report(scan 模式)
    2  参数错误 / 确认失败
    3  IO 错误
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 把 src/backend 加入 path 以便 import app.utils.*
_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parent.parent / "src" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.utils.simple_activation_manager import (  # noqa: E402
    _looks_like_debug_activation_code,
    get_simple_base_dir,
)

# ──────────────────────────────────────────────────────────────────
# 数据加载
# ──────────────────────────────────────────────────────────────────


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def load_activations(base_dir: Path) -> Dict[str, Dict[str, Any]]:
    """加载 activations.json,key 为激活码(大写)。"""
    f = base_dir / "activations.json"
    raw = _load_json(f)
    return {(k or "").strip().upper(): v for k, v in raw.items()}


def iter_report_records(reports_dir: Path) -> List[Tuple[str, Dict[str, Any]]]:
    """遍历 reports/{report_id}/record.json,返回 [(report_id, record), ...]。"""
    out: List[Tuple[str, Dict[str, Any]]] = []
    if not reports_dir.is_dir():
        return out
    for sub in sorted(reports_dir.iterdir()):
        if not sub.is_dir():
            continue
        rid = sub.name
        rec_file = sub / "record.json"
        if not rec_file.is_file():
            continue
        try:
            record = json.loads(rec_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append((rid, record))
    return out


# ──────────────────────────────────────────────────────────────────
# 孤儿分类判定
# ──────────────────────────────────────────────────────────────────

CAT_ACTIVATION_MISSING = "activation_missing"
CAT_ACTIVATION_DELETED = "activation_deleted"
CAT_ORPHAN_PREFIX = "orphan_prefix"
CAT_CROSS_USER = "cross_user"
CAT_DUPLICATE = "duplicate"


def classify_reports(
    base_dir: Path,
    activations: Dict[str, Dict[str, Any]],
    reports: List[Tuple[str, Dict[str, Any]]],
) -> Dict[str, List[Dict[str, Any]]]:
    """
    对所有 report 做分类。一个 report 可能落入多个类别(按优先级取第一个作为主类别,
    但 duplicates 单独按 (code, uid) 分组返回)。

    返回 dict:
        activation_missing / activation_deleted / orphan_prefix / cross_user:
            [{report_id, activation_code, record_user_id, owner_user_id, ...}, ...]
        duplicate:
            [{key: [code, uid], canonical_report_id, extras: [{report_id,...}], ...}, ...]
    """
    by_pair: Dict[Tuple[str, str], List[str]] = defaultdict(list)
    for rid, rec in reports:
        code = (rec.get("activation_code") or "").strip().upper()
        uid = (rec.get("user_id") or "").strip()
        by_pair[(code, uid)].append(rid)

    cat: Dict[str, List[Dict[str, Any]]] = {
        CAT_ACTIVATION_MISSING: [],
        CAT_ACTIVATION_DELETED: [],
        CAT_ORPHAN_PREFIX: [],
        CAT_CROSS_USER: [],
        CAT_DUPLICATE: [],
    }

    # 先分类单个 report(优先级: missing > deleted > orphan_prefix > cross_user)
    for rid, rec in reports:
        code = (rec.get("activation_code") or "").strip().upper()
        uid = (rec.get("user_id") or "").strip()
        created = rec.get("created_at") or ""

        entry = {
            "report_id": rid,
            "activation_code": code,
            "record_user_id": uid,
            "owner_user_id": None,
            "created_at": created,
            "reason": "",
        }

        # ORPHAN__ 前缀优先于 activation_missing(历史迁移残留,语义更明确)
        if code.startswith("ORPHAN__"):
            entry["reason"] = "ORPHAN__ 前缀(历史迁移残留)"
            cat[CAT_ORPHAN_PREFIX].append(entry)
            continue

        if code not in activations:
            entry["reason"] = "activation_code 不存在于 activations.json"
            cat[CAT_ACTIVATION_MISSING].append(entry)
            continue

        act = activations[code]
        entry["owner_user_id"] = act.get("owner_user_id")

        if act.get("status") == "deleted" or act.get("deleted_at"):
            entry["reason"] = f"activation 状态={act.get('status')}, deleted_at={act.get('deleted_at')}"
            cat[CAT_ACTIVATION_DELETED].append(entry)
            continue

        owner_uid = (act.get("owner_user_id") or "").strip()
        if owner_uid and uid and owner_uid != uid:
            entry["reason"] = f"record.user_id={uid} 但 owner_user_id={owner_uid}"
            cat[CAT_CROSS_USER].append(entry)
            continue

        # 落到这里说明是「正常 report」,但它可能仍属于某个 duplicate 组(下面处理)

    # duplicates:同一 (code, uid) 多份
    for (code, uid), rids in by_pair.items():
        if len(rids) <= 1:
            continue
        # canonical 规则对齐 report_registry._sort_canonical_matches:
        # created_at 升序(最早保留),其次 session 数,其次 report_id
        rid_created: Dict[str, str] = {}
        for rid in rids:
            rec = next((r for _, r in reports if _rid_match(r, rid)), None)
            rid_created[rid] = (rec or {}).get("created_at") or "9999-12-31T23:59:59.999999Z"
        ordered = sorted(rids, key=lambda r: (rid_created[r], r))
        canonical = ordered[0]
        extras = ordered[1:]
        cat[CAT_DUPLICATE].append({
            "activation_code": code,
            "user_id": uid,
            "canonical_report_id": canonical,
            "extras": [{"report_id": r, "created_at": rid_created[r]} for r in extras],
        })

    return cat


def _rid_match(rec: Dict[str, Any], rid: str) -> bool:
    return (rec.get("report_id") or "") == rid


# ──────────────────────────────────────────────────────────────────
# 决策:哪些 report 要被 archive/clean
# ──────────────────────────────────────────────────────────────────


def collect_targets(
    cat: Dict[str, List[Dict[str, Any]]],
    *,
    include_orphans: bool,
    include_cross_user: bool,
) -> List[Dict[str, Any]]:
    """
    汇总需要处理的 report 列表。每个元素:
        {report_id, activation_code, reason, category}
    安全项:activation_missing / activation_deleted / duplicate extras
    可选项(默认排除):orphan_prefix / cross_user
    """
    targets: List[Dict[str, Any]] = []

    for e in cat.get(CAT_ACTIVATION_MISSING, []):
        targets.append({"report_id": e["report_id"], "activation_code": e["activation_code"],
                        "reason": e["reason"], "category": CAT_ACTIVATION_MISSING})
    for e in cat.get(CAT_ACTIVATION_DELETED, []):
        targets.append({"report_id": e["report_id"], "activation_code": e["activation_code"],
                        "reason": e["reason"], "category": CAT_ACTIVATION_DELETED})
    for e in cat.get(CAT_DUPLICATE, []):
        for extra in e.get("extras", []):
            targets.append({"report_id": extra["report_id"], "activation_code": e["activation_code"],
                            "reason": f"duplicate of canonical {e['canonical_report_id']}",
                            "category": CAT_DUPLICATE})

    if include_orphans:
        for e in cat.get(CAT_ORPHAN_PREFIX, []):
            targets.append({"report_id": e["report_id"], "activation_code": e["activation_code"],
                            "reason": e["reason"], "category": CAT_ORPHAN_PREFIX})
    if include_cross_user:
        for e in cat.get(CAT_CROSS_USER, []):
            targets.append({"report_id": e["report_id"], "activation_code": e["activation_code"],
                            "reason": e["reason"], "category": CAT_CROSS_USER})

    # 去重(一个 report 可能同时是 missing 和 duplicate extra)
    seen: set = set()
    unique: List[Dict[str, Any]] = []
    for t in targets:
        if t["report_id"] in seen:
            continue
        seen.add(t["report_id"])
        unique.append(t)
    return unique


# ──────────────────────────────────────────────────────────────────
# 子命令实现
# ──────────────────────────────────────────────────────────────────


def cmd_scan(args: argparse.Namespace) -> int:
    base_dir = Path(args.base_dir).resolve()
    reports_dir = base_dir / "reports"
    activations = load_activations(base_dir)
    reports = iter_report_records(reports_dir)

    cat = classify_reports(base_dir, activations, reports)
    now = datetime.now(timezone.utc).isoformat()

    if args.json:
        out = {
            "scan_time": now,
            "base_dir": str(base_dir),
            "total_reports": len(reports),
            "categories": cat,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"扫描时间: {now}")
        print(f"数据根目录: {base_dir}")
        print(f"reports/ 总 report 数: {len(reports)}")
        print()
        print("孤儿分类:")
        print(f"  activation_missing: {len(cat[CAT_ACTIVATION_MISSING])}")
        print(f"  activation_deleted: {len(cat[CAT_ACTIVATION_DELETED])}")
        print(f"  orphan_prefix:      {len(cat[CAT_ORPHAN_PREFIX])}  (默认不处理,需 --include-orphans)")
        print(f"  cross_user:         {len(cat[CAT_CROSS_USER])}  (诊断用,需 --include-cross-user)")
        print(f"  duplicates:         {len(cat[CAT_DUPLICATE])} 组")

        for name, items in [
            (CAT_CROSS_USER, cat[CAT_CROSS_USER]),
            (CAT_ACTIVATION_MISSING, cat[CAT_ACTIVATION_MISSING]),
            (CAT_ACTIVATION_DELETED, cat[CAT_ACTIVATION_DELETED]),
            (CAT_ORPHAN_PREFIX, cat[CAT_ORPHAN_PREFIX]),
        ]:
            if items:
                print(f"\n[{name}]")
                for e in items[:20]:
                    print(f"  - report_id: {e['report_id']}")
                    print(f"    code: {e['activation_code']} | record.user: {e.get('record_user_id')} | owner: {e.get('owner_user_id')}")
                    if e.get("reason"):
                        print(f"    reason: {e['reason']}")
                if len(items) > 20:
                    print(f"  ... 还有 {len(items) - 20} 条,使用 --json 查看完整列表")

        if cat[CAT_DUPLICATE]:
            print(f"\n[duplicates]")
            for d in cat[CAT_DUPLICATE]:
                print(f"  - code: {d['activation_code']} | user: {d['user_id']}")
                print(f"    canonical: {d['canonical_report_id']}")
                for extra in d["extras"]:
                    print(f"    extra:    {extra['report_id']}  (created {extra['created_at']})")

        # 计算可安全归档数
        safe = collect_targets(cat, include_orphans=False, include_cross_user=False)
        print(f"\n建议操作:")
        print(f"  可安全归档(默认): {len(safe)} 份")
        print(f"  python scripts/audit_orphan_reports.py archive --dry-run")
        print(f"  python scripts/audit_orphan_reports.py archive --confirm-count {len(safe)}")

    # 发现任何可疑就返回 1,便于 CI/脚本判断
    suspicious = (
        len(cat[CAT_ACTIVATION_MISSING])
        + len(cat[CAT_ACTIVATION_DELETED])
        + len(cat[CAT_CROSS_USER])
        + sum(len(d.get("extras", [])) for d in cat[CAT_DUPLICATE])
    )
    return 1 if suspicious > 0 else 0


def cmd_archive(args: argparse.Namespace) -> int:
    return _do_move(args, destructive=False)


def cmd_clean(args: argparse.Namespace) -> int:
    if not args.i_know_this_is_destructive:
        print("错误: clean 命令必须显式加 --i-know-this-is-destructive 确认永久删除不可恢复", file=sys.stderr)
        return 2
    return _do_move(args, destructive=True)


def _do_move(args: argparse.Namespace, *, destructive: bool) -> int:
    base_dir = Path(args.base_dir).resolve()
    reports_dir = base_dir / "reports"
    activations = load_activations(base_dir)
    reports = iter_report_records(reports_dir)
    cat = classify_reports(base_dir, activations, reports)

    targets = collect_targets(
        cat,
        include_orphans=args.include_orphans,
        include_cross_user=args.include_cross_user,
    )

    # dry-run 模式跳过 confirm-count 校验(只看数量不必先猜)
    if not args.dry_run:
        if len(targets) != args.confirm_count:
            print(
                f"错误:确认数量不匹配。实际待处理={len(targets)},参数 --confirm-count={args.confirm_count}。"
                f"请先用 scan 或 --dry-run 查看数量,再传入正确值。",
                file=sys.stderr,
            )
            return 2

    if not targets:
        print("没有需要处理的 report。")
        return 0

    action = "永久删除" if destructive else "归档"
    print(f"将{action}以下 {len(targets)} 份 report:")
    for t in targets:
        print(f"  [{t['category']}] {t['report_id']}  code={t['activation_code']}")
        print(f"    reason: {t['reason']}")

    if args.dry_run:
        print(f"\n[dry-run] 未实际{action},去掉 --dry-run 执行。")
        return 0

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if destructive:
        archive_root: Optional[Path] = None
    else:
        archive_root = base_dir / "reports_archive" / ts
        archive_root.mkdir(parents=True, exist_ok=True)
        manifest_path = archive_root / "_manifest.json"

    manifest: List[Dict[str, Any]] = []
    moved = 0
    failed = 0
    for t in targets:
        src = reports_dir / t["report_id"]
        if not src.is_dir():
            print(f"  跳过(目录不存在): {t['report_id']}", file=sys.stderr)
            failed += 1
            continue
        try:
            if destructive:
                shutil.rmtree(src)
            else:
                dst = archive_root / t["report_id"]
                shutil.move(str(src), str(dst))
                manifest.append({
                    "report_id": t["report_id"],
                    "original_path": str(src),
                    "archived_to": str(dst),
                    "category": t["category"],
                    "activation_code": t["activation_code"],
                    "reason": t["reason"],
                })
            moved += 1
        except OSError as e:
            print(f"  失败: {t['report_id']}: {e}", file=sys.stderr)
            failed += 1

    if not destructive and archive_root is not None and manifest:
        manifest_path.write_text(json.dumps({
            "archived_at": ts,
            "action": "archive",
            "count": len(manifest),
            "items": manifest,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n归档完成:{moved} 份,manifest: {manifest_path}")
        print(f"归档目录:{archive_root}")
    else:
        print(f"\n清理完成:{moved} 份,失败:{failed} 份")

    return 0 if failed == 0 else 3


# ──────────────────────────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="audit_orphan_reports.py",
        description="孤儿 report 扫描 / 归档 / 清理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--base-dir",
        default=str(get_simple_base_dir()),
        help=f"数据根目录(默认 {get_simple_base_dir()})",
    )
    sub = parser.add_subparsers(dest="cmd", required=False)

    # scan
    p_scan = sub.add_parser("scan", help="只读扫描诊断(默认)")
    p_scan.add_argument("--json", action="store_true", help="输出 JSON 格式")

    # archive
    p_arc = sub.add_parser("archive", help="归档可疑 report(可恢复)")
    p_arc.add_argument("--dry-run", action="store_true", help="只打印不执行")
    p_arc.add_argument("--confirm-count", type=int, default=0,
                       help="确认待处理数量(防误操作,dry-run 时可不填)")
    p_arc.add_argument("--include-orphans", action="store_true", help="纳入 ORPHAN__ 前缀")
    p_arc.add_argument("--include-cross-user", action="store_true",
                       help="纳入 cross_user 类(默认仅诊断)")

    # clean
    p_clean = sub.add_parser("clean", help="永久删除可疑 report(rm -rf)")
    p_clean.add_argument("--dry-run", action="store_true", help="只打印不执行")
    p_clean.add_argument("--confirm-count", type=int, default=0,
                         help="确认待处理数量(防误操作,dry-run 时可不填)")
    p_clean.add_argument("--include-orphans", action="store_true", help="纳入 ORPHAN__ 前缀")
    p_clean.add_argument("--include-cross-user", action="store_true",
                         help="纳入 cross_user 类(默认仅诊断)")
    p_clean.add_argument("--i-know-this-is-destructive", action="store_true",
                         help="必填:确认永久删除不可恢复")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cmd = args.cmd or "scan"
    if cmd == "scan":
        return cmd_scan(args)
    if cmd == "archive":
        return cmd_archive(args)
    if cmd == "clean":
        return cmd_clean(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
