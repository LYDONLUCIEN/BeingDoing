"""全量扫描：找出所有被 combo_id 污染的 rumination_progress.json。

只读，绝不写盘。扫描 data/simple/reports/*/rumination_progress.json，
对每个 report 复用 fix 脚本的判定逻辑，统计需修正的 id 数量。

判定标准：
  - 行的 id 与 (热爱,优势) 或 假设文本 反查出的正确 id 不一致 → 受污染
  - snapshot[1].initial 缺失（无法建权威映射）→ 标记为「无法判定」，单独统计

用法：
  python scripts/scan_combo_id_pollution.py            # 扫描全部
  python scripts/scan_combo_id_pollution.py --verbose  # 详细列出每处污染
  python scripts/scan_combo_id_pollution.py --apply    # 扫描 + 自动修正所有受污染 report（带备份）
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPORTS_ROOT = Path("data/simple/reports")
REPORTS_ARCHIVE_ROOT = Path("data/simple/reports_archive")
FIX_SCRIPT = Path("scripts/fix_combo_id_pollution.py")


def build_canonical_map(snapshots: dict) -> dict | None:
    by_pair: dict[tuple[str, str], str] = {}
    by_hyp: dict[str, str] = {}
    s1 = snapshots.get("1") or {}
    for r in (s1.get("initial") or []):
        if not isinstance(r, dict):
            continue
        p = str(r.get("热爱") or "").strip()
        s = str(r.get("优势") or "").strip()
        rid = str(r.get("id") or "").strip()
        if p and s and rid:
            by_pair[(p, s)] = rid
    if not by_pair:
        return None
    for sk in ("3", "4", "5"):
        sv = snapshots.get(sk) or {}
        for sub in ("initial", "submitted"):
            for r in (sv.get(sub) or []):
                if not isinstance(r, dict):
                    continue
                p = str(r.get("热爱") or "").strip()
                s = str(r.get("优势") or "").strip()
                hyp = str(r.get("用户确认的假设") or "").strip()
                if not (p and s and hyp):
                    continue
                rid = by_pair.get((p, s)) or str(r.get("id") or "").strip()
                if rid and hyp not in by_hyp:
                    by_hyp[hyp] = rid
    return {"by_pair": by_pair, "by_hyp": by_hyp, "valid_ids": set(by_pair.values())}


def count_pollution(rows: list, canonical: dict) -> list:
    if not isinstance(rows, list):
        return []
    by_pair = canonical["by_pair"]
    by_hyp = canonical["by_hyp"]
    bad = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("id") or "").strip()
        p = str(r.get("热爱") or "").strip()
        s = str(r.get("优势") or "").strip()
        correct = by_pair.get((p, s)) if (p and s) else None
        if not correct:
            hyp = str(r.get("用户确认的假设") or "").strip()
            if hyp:
                correct = by_hyp.get(hyp)
        if correct and correct != rid:
            bad.append((rid, correct, f"{p} × {s}" if (p and s) else "hyp"))
    return bad


def scan_one(progress_path: Path, verbose: bool = False) -> tuple[str, int, list]:
    """返回 (状态, 污染数, 详情)。状态：'clean'/'polluted'/'no_map'/'no_snapshots'/'error'。"""
    try:
        data = json.loads(progress_path.read_text(encoding="utf-8"))
    except Exception as e:
        return ("error", 0, [f"读取失败: {e}"])

    snapshots = data.get("filter_step_snapshots") or {}
    canonical = build_canonical_map(snapshots)
    if not canonical:
        # snapshot[1].initial 缺失 —— 这种 report 通常还没走到 step3，本就无污染
        return ("no_map", 0, [])

    all_bad: list = []
    for r in (data.get("filter_table") or []):
        pass
    # 扫 filter_table + snapshot[3..7]
    bad_locs: list[tuple] = []

    def scan_rows(rows, label):
        if not isinstance(rows, list):
            return
        for r in rows:
            if not isinstance(r, dict):
                continue
            rid = str(r.get("id") or "").strip()
            p = str(r.get("热爱") or "").strip()
            s = str(r.get("优势") or "").strip()
            correct = canonical["by_pair"].get((p, s)) if (p and s) else None
            if not correct:
                hyp = str(r.get("用户确认的假设") or "").strip()
                if hyp:
                    correct = canonical["by_hyp"].get(hyp)
            if correct and correct != rid:
                bad_locs.append((label, rid, correct, f"{p} × {s}" if (p and s) else "hyp"))

    scan_rows(data.get("filter_table"), "filter_table")
    for sk, sv in snapshots.items():
        if not isinstance(sv, dict):
            continue
        for sub in ("initial", "submitted"):
            scan_rows(sv.get(sub), f"snapshot[{sk}].{sub}")

    if not bad_locs:
        return ("clean", 0, [])
    return ("polluted", len(bad_locs), bad_locs if verbose else [(b[0], b[1], b[2]) for b in bad_locs[:3]])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true", help="详细列出每处污染")
    ap.add_argument("--apply", action="store_true", help="扫描后对受污染 report 自动 --apply")
    args = ap.parse_args()

    if not REPORTS_ROOT.exists():
        print(f"[ERROR] reports 目录不存在: {REPORTS_ROOT}", file=sys.stderr)
        return 2

    reports = sorted(p for p in REPORTS_ROOT.glob("*/rumination_progress.json"))
    archive_reports: list[Path] = []
    if REPORTS_ARCHIVE_ROOT.exists():
        # 归档结构：reports_archive/<timestamp>/<report_id>/rumination_progress.json
        archive_reports = sorted(REPORTS_ARCHIVE_ROOT.glob("*/*/rumination_progress.json"))
    if not reports and not archive_reports:
        print(f"[INFO] 未发现任何 rumination_progress.json")
        return 0

    summary = {"clean": 0, "polluted": 0, "no_map": 0, "error": 0}
    polluted_list: list[tuple[str, int, list]] = []
    archive_polluted: list[tuple[str, int]] = []

    for p in reports:
        rid = p.parent.name
        status, n, detail = scan_one(p, args.verbose)
        summary[status] += 1
        if status == "polluted":
            polluted_list.append((rid, n, detail))

    # 归档目录只扫描统计（不再自动修，留给用户决定是否要动归档）
    for p in archive_reports:
        ts = p.parent.parent.name
        rid = p.parent.name
        label = f"{ts}/{rid}"
        status, n, _ = scan_one(p, False)
        if status == "polluted":
            archive_polluted.append((label, n))

    print("=" * 70)
    print(f"扫描完成：")
    print(f"  现役 reports/（{len(reports)} 份）")
    print(f"    ✅ 干净 (clean)            : {summary['clean']}")
    print(f"    ⚠️  受污染 (polluted)       : {summary['polluted']}")
    print(f"    ⏭  无权威映射 (no_map)     : {summary['no_map']}  (snapshot[1].initial 缺失，通常未走到 step3)")
    print(f"    ❌ 读取错误 (error)         : {summary['error']}")
    if archive_reports:
        print(f"  归档 reports_archive/（{len(archive_reports)} 份）")
        print(f"    ⚠️  受污染 (polluted)       : {len(archive_polluted)}")
    print("=" * 70)

    if not polluted_list and not archive_polluted:
        print("\n[OK] 未发现任何受污染 report（现役 + 归档均干净），无需修复。")
        return 0

    if polluted_list:
        print(f"\n现役受污染 report 清单（共 {len(polluted_list)} 个）：")
        for rid, n, detail in polluted_list:
            print(f"  {rid}   {n} 处污染")
            if args.verbose and detail:
                for d in detail[:10]:
                    print(f"     {d}")
                if len(detail) > 10:
                    print(f"     ... 共 {len(detail)} 处")

    if archive_polluted:
        print(f"\n归档受污染 report 清单（共 {len(archive_polluted)} 个，扫描脚本不会自动修）：")
        for label, n in archive_polluted:
            print(f"  {label}   {n} 处污染")

    if args.apply and polluted_list:
        print("\n[APPLY] 开始对现役受污染 report 执行修复...")
        for rid, _, _ in polluted_list:
            print(f"\n--- 修复 {rid} ---")
            r = subprocess.run(
                [sys.executable, str(FIX_SCRIPT), rid, "--apply"],
                capture_output=False,
            )
            if r.returncode != 0:
                print(f"[WARN] {rid} 修复返回码 {r.returncode}，请检查")
    elif polluted_list:
        print("\n[提示] 如需修复全部现役受污染 report，运行：")
        print(f"  python scripts/scan_combo_id_pollution.py --apply")
        print("（每个 report 会先备份再写盘，单独修可加 report_id 参数：python scripts/fix_combo_id_pollution.py <rid> --apply）")

    return 0


if __name__ == "__main__":
    sys.exit(main())
