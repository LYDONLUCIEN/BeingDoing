"""一次性修正脚本：修复被 combo_id 污染的 rumination_progress.json 行 id。

背景：1EPJC91L88 等报告在 step3b（combo matrix -> table）路径下，
后端曾把 combo_id（"pi"+"si" 双位编码，如 "20"/"23"）直接当成表行 id 写入
snapshot[3]/[4]/[5]/[7] 与 filter_table，导致行 id 与 gen_table 体系（1..15）错位。

修复策略：
  1. 以 snapshot["1"]["initial"] 为「权威映射表」——它是 gen_table 一次生成的，
     id 干净（1..N），且热爱×优势内容完整。
  2. 建立 (热爱, 优势) -> 正确 id 的映射。
  3. 遍历所有 snapshot[*] 的 initial/submitted 以及 filter_table，凡 id 不在
     权威映射的 value 集合内的行，按 (热爱, 优势) 回填正确 id。
  4. 全程先 dry-run 打印将修改的内容；--apply 才写盘；写盘前备份原文件。

用法：
  python scripts/fix_combo_id_pollution.py <report_id>            # dry-run
  python scripts/fix_combo_id_pollution.py <report_id> --apply    # 实际写盘
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REPORTS_ROOT = Path("data/simple/reports")


def build_canonical_map(snapshots: dict) -> dict | None:
    """构建回填用的双键映射。

    Returns:
        {
            "by_pair": {(热爱, 优势) -> 正确 id},   # 来自 snapshot[1].initial
            "by_hyp":  {假设文本 -> 正确 id},        # 来自 snapshot[1..5].initial/submitted
            "valid_ids": set(...),
        }
        或 None（无法建立）。
    """
    by_pair: dict[tuple[str, str], str] = {}
    by_hyp: dict[str, str] = {}

    # 主权威源：snapshot[1].initial —— gen_table 一次生成的干净表
    s1 = (snapshots.get("1") or {})
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

    # 副权威源：snapshot[3..5] —— 含热爱/优势/假设，可建立 假设文本 -> id。
    # 注意：snapshot[3..5] 自身的 id 可能已被污染，必须先按 (热爱,优势) 校正后再入 by_hyp。
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
                # 校正本行的 id：优先 (热爱,优势) 映射，否则原样
                rid = by_pair.get((p, s)) or str(r.get("id") or "").strip()
                if rid and hyp not in by_hyp:
                    by_hyp[hyp] = rid

    return {"by_pair": by_pair, "by_hyp": by_hyp, "valid_ids": set(by_pair.values())}


def fix_rows(rows: list, canonical: dict, label: str) -> tuple:
    """返回 (修改后的 rows, 改动列表)。

    判定优先级：
      1) 行同时含 热爱/优势：
           - 按 (热爱, 优势) 查 by_pair 得到 correct；若 rid != correct 则修正。
           - 即使 rid 在 valid_ids 内，只要与内容不符（如 id=10 但实际是「自我探索×审美判断」，
             应为 id=6），仍要修正。这是处理 snapshot[3..5] 污染的主力分支。
      2) 行只剩 id+假设（snapshot[6/7]/filter_table 在后续 step 中热爱/优势 被剔除）：
           - 按 假设文本 查 by_hyp 得到 correct；若 rid != correct 则修正。
           - 这同样能捕捉「id=10/13 形似合法实则内容错位」的脏数据。
    """
    if not isinstance(rows, list):
        return rows, []
    by_pair = canonical["by_pair"]
    by_hyp = canonical["by_hyp"]
    changes: list[tuple] = []
    out = []
    for r in rows:
        if not isinstance(r, dict):
            out.append(r)
            continue
        rid = str(r.get("id") or "").strip()
        p = str(r.get("热爱") or "").strip()
        s = str(r.get("优势") or "").strip()
        correct = None
        match_key = ""
        if p and s:
            correct = by_pair.get((p, s))
            match_key = f"{p} × {s}"
        if not correct:
            hyp = str(r.get("用户确认的假设") or "").strip()
            if hyp:
                correct = by_hyp.get(hyp)
                match_key = f"假设='{hyp[:24]}...'"
        if correct and correct != rid:
            new_r = dict(r)
            new_r["id"] = correct
            changes.append((label, rid, correct, match_key))
            out.append(new_r)
        else:
            out.append(r)
    return out, changes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("report_id")
    ap.add_argument("--apply", action="store_true", help="实际写盘（默认 dry-run）")
    args = ap.parse_args()

    progress_path = REPORTS_ROOT / args.report_id / "rumination_progress.json"
    if not progress_path.exists():
        print(f"[ERROR] 找不到文件: {progress_path}", file=sys.stderr)
        return 2

    data = json.loads(progress_path.read_text(encoding="utf-8"))
    snapshots = data.get("filter_step_snapshots") or {}

    canonical = build_canonical_map(snapshots)
    if not canonical:
        print(f"[ERROR] {args.report_id}: snapshot[1].initial 缺失或为空，无法建立权威 id 映射。", file=sys.stderr)
        return 3
    valid_ids = canonical["valid_ids"]
    print(f"[INFO] 权威 id 映射（共 {len(valid_ids)} 行，来自 snapshot[1].initial）:")
    for (p, s), rid in canonical["by_pair"].items():
        print(f"       id={rid}  {p} × {s}")
    print(f"[INFO] 假设文本 -> id 反查表（共 {len(canonical['by_hyp'])} 条，来自 snapshot[3..5]）")
    print()

    all_changes: list[tuple] = []

    # 1) 修 filter_table（顶层）
    ft = data.get("filter_table")
    new_ft, ch = fix_rows(ft, canonical, "filter_table")
    all_changes.extend(ch)
    if new_ft is not None:
        data["filter_table"] = new_ft

    # 2) 修每个 snapshot 的 initial / submitted
    for sk, sv in list(snapshots.items()):
        if not isinstance(sv, dict):
            continue
        for sub in ("initial", "submitted"):
            rows = sv.get(sub)
            if rows is None:
                continue
            new_rows, ch = fix_rows(rows, canonical, f"snapshot[{sk}].{sub}")
            all_changes.extend(ch)
            snapshots[sk][sub] = new_rows
    data["filter_step_snapshots"] = snapshots

    if not all_changes:
        print(f"[OK] {args.report_id}: 未发现需修正的污染 id（数据已干净）。")
        return 0

    print(f"[PLAN] 共 {len(all_changes)} 处 id 将被修正:")
    for label, old, new, match_key in all_changes:
        print(f"       {label}: id {old!r} -> {new!r}  ({match_key})")
    print()

    if not args.apply:
        print("[DRY-RUN] 未传 --apply，未写盘。")
        return 0

    backup = progress_path.with_suffix(".json.bak_combo_fix")
    shutil.copy2(progress_path, backup)
    progress_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[APPLIED] 已写盘，备份保存至: {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
