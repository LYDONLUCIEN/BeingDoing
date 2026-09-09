#!/usr/bin/env python3
"""
batch_generate_reports.py — 从 admin 批量导出包批量生成 PDF 报告

用途（2026-08-07）：
  test/reports/ 这类目录里是 admin 批量导出 zip 解压后的「导出包」格式
  （summary.json / stats.json / raw/*.json / report_*.md），与 PDF 生成所需的
  注册表结构（data/simple/reports/{rid}/record.json + dimension_conclusions.json
  + {step}__{session}.json + rumination_v4_progress.json）不同。

  本脚本分两步：
    1. 暂存重建（adapter）：把导出包重建为注册表结构，写入 --staging-root：
       - record.json                 ← stats.json 元信息 + raw 文件名推导五阶段索引
       - dimension_conclusions.json  ← summary.json phases.{4维}.conclusion_final（同构直映）
       - {step}__{session}.json      ← raw/ 原样拷贝（注解键无害）
       - rumination_v4_progress.json ← v3 数据合成：raw/rumination_progress.json 的
                                       combo_matrix 提供 passion/strength 名称，
                                       summary.json 的 combo_conclusions 中
                                       state=confirmed 的 text 作为 conclusion_card.hypothesis；
                                       终选取 filter_table 的 __final 行（行号反推 combo_id，
                                       2026-09-08 修正，原误用全部 confirmed），无 __final 行时回退全部 confirmed
    2. 生成：完全复用 app.services.report_pdf_service.ReportPdfService
       （与线上 POST /export/report-pdf 同一套 LLM 提示词、同一套 PDF 渲染），
       产出 PDF + report_markdown.md 到 --output-dir。

  完整性口径（与 2026-08-07 下载门控一致）：4 维 conclusion_final 齐全
  且 rumination 至少 1 条 confirmed 结论，才生成；否则跳过（--include-incomplete 可覆盖）。

用法示例：
    # 批量生成 test/reports 下所有完整报告，PDF 输出到 test/reports_generated/
    python scripts/batch_generate_reports.py \
        --input-root test/reports --output-dir test/reports_generated

    # 只看哪些能生成、哪些跳过（不调 LLM）
    python scripts/batch_generate_reports.py \
        --input-root test/reports --output-dir test/reports_generated --dry-run

    # 指定单个 report / 覆盖跳过逻辑 / 指定 VIP 档位
    python scripts/batch_generate_reports.py --input-root test/reports \
        --output-dir out --report-id 084ce3ba-a587-4abb-8f71-ee4c3438734c
    python scripts/batch_generate_reports.py --input-root test/reports \
        --output-dir out --include-incomplete --vip-level 2

选项说明：
    --input-root PATH       导出包根目录（每个子目录名 = report_id）
    --output-dir PATH       PDF / markdown 输出目录
    --staging-root PATH     暂存注册表目录（默认 {output-dir}/_staging_simple）；
                            保留可复用 markdown 缓存，删除不影响源数据
    --report-id RID         只处理指定 report（可重复）；默认处理全部
    --include-incomplete    未完成的报告也生成（rumination 块等为占位文案）
    --vip-level N           LLM VIP 档位（默认 1，与 get_default_llm_provider 口径一致）
    --dry-run               只列出完整性判定，不生成

退出码：
    0  全部成功（或 dry-run）
    1  有报告生成失败
    2  参数错误
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path

# 让脚本可直接从项目根目录运行（与 pytest.ini 的 pythonpath 口径一致）
_BACKEND = Path(__file__).resolve().parent.parent / "src" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.rumination_v4_service import (  # noqa: E402
    default_state,
    new_combo_session,
)
from app.utils.report_registry import STEP_IDS  # noqa: E402

_DIMENSION_PHASES = ("values", "strengths", "interests", "purpose")


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return {}


# ── 第一步：导出包 → 注册表暂存 ─────────────────────────────


def stage_report(pkg_dir: Path, staging_reports: Path) -> dict:
    """把单个导出包重建为注册表结构，返回重建信息（含完整性判定）。"""
    report_id = pkg_dir.name
    stats = _load_json(pkg_dir / "stats.json")
    summary = _load_json(pkg_dir / "summary.json")
    raw_dir = pkg_dir / "raw"

    dest = staging_reports / report_id
    dest.mkdir(parents=True, exist_ok=True)

    # 1. 拷贝对话源文件 {step}__{session}.json，并推导五阶段索引
    steps: dict = {}
    for raw_file in sorted(raw_dir.glob("*__*.json")):
        step_id, session_id = raw_file.stem.split("__", 1)
        if step_id not in STEP_IDS:
            continue
        shutil.copy2(raw_file, dest / raw_file.name)
        st = steps.setdefault(
            step_id,
            {"step_id": step_id, "selected_session_id": None, "locked": True,
             "session_ids": [], "updated_at": stats.get("report_updated_at")},
        )
        st["session_ids"].append(session_id)
    for st in steps.values():
        st["selected_session_id"] = st["session_ids"][-1] if st["session_ids"] else None

    # 2. record.json（读侧 _normalize_record 会补齐其余字段）
    record = {
        "report_id": report_id,
        "activation_code": stats.get("activation_code") or "",
        "user_id": stats.get("user_id") or "",
        "created_at": stats.get("report_created_at"),
        "updated_at": stats.get("report_updated_at"),
        "status": stats.get("report_status") or "in_progress",
        "final_conclusion": stats.get("report_final_conclusion"),
        "steps": steps,
    }
    (dest / "record.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 3. dimension_conclusions.json（summary.json 的 conclusion_final 与其同构）
    phases = summary.get("phases") or {}
    dim = {}
    for phase in _DIMENSION_PHASES:
        conclusion = (phases.get(phase) or {}).get("conclusion_final")
        if conclusion:
            dim[phase] = conclusion
    (dest / "dimension_conclusions.json").write_text(
        json.dumps(dim, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 4. v3 → v4 合成 rumination_v4_progress.json
    rumi = phases.get("rumination") or {}
    combo_conclusions = rumi.get("combo_conclusions") or {}
    confirmed = {
        cid: c for cid, c in combo_conclusions.items()
        if isinstance(c, dict) and c.get("state") == "confirmed" and c.get("text")
    }
    v4_combo_count = 0
    if confirmed:
        progress = _load_json(raw_dir / "rumination_progress.json")
        matrix = {m.get("combo_id"): m for m in (progress.get("combo_matrix") or [])}
        ts = stats.get("report_updated_at")
        state = default_state()
        state["main_section"] = "end"
        for cid, cc in confirmed.items():
            m = matrix.get(cid) or {}
            passion = m.get("passion_name") or "（未知热爱）"
            strength = m.get("strength_name") or "（未知优势）"
            if not m:
                print(f"  ⚠️  combo {cid} 不在 combo_matrix 中，名称用占位", file=sys.stderr)
            sess = new_combo_session(cid, passion, [strength])
            sess["status"] = "concluded"
            sess["created_at"] = ts
            sess["updated_at"] = ts
            sess["conclusion_card"] = {
                "hypothesis": cc["text"],
                "balance_found": None,
                "balance_fail_reason": None,
                "created_at": ts,
                "updated_at": ts,
            }
            state["combo_sessions"].append(sess)

        # 终选口径（2026-09-08 修正）：v3 真正的 N选3 终选在 filter_table 的
        # __final=true 行（通常 1~3 个），行 id 是 gen_table 行号（1 + pi*5 + si），
        # 需经 combo_id_to_row_id 反推回 combo_id；此前误用全部 confirmed 组合
        # （可达 14 条，只是“聊完确认过假设”），导致报告第五章逐个剖析十几个方向。
        # 找不到有效 __final 行时回退为全部 confirmed（旧口径兼底）。
        from app.utils.rumination_combo_matrix import combo_id_to_row_id

        row_to_combo = {
            combo_id_to_row_id(m): cid for cid, m in matrix.items()
        }
        final_combo_ids = [
            row_to_combo.get(str(r.get("id")))
            for r in (progress.get("filter_table") or [])
            if r.get("__final")
        ]
        final_combo_ids = [c for c in final_combo_ids if c in confirmed]
        if not final_combo_ids:
            final_combo_ids = list(confirmed.keys())
        state["final_selection"] = {
            "selected_combo_ids": final_combo_ids,
            "submitted": True,
            "submitted_at": ts,
        }
        (dest / "rumination_v4_progress.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        v4_combo_count = len(final_combo_ids)

    dims_done = sum(1 for p in _DIMENSION_PHASES if p in dim)
    complete = dims_done == len(_DIMENSION_PHASES) and v4_combo_count > 0
    return {
        "report_id": report_id,
        "user_id": record["user_id"],
        "dims_done": dims_done,
        "confirmed_combos": v4_combo_count,
        "complete": complete,
    }


# ── 第二步：复用系统逻辑生成 PDF ────────────────────────────


async def generate_one(staging_root: Path, info: dict, output_dir: Path, vip_level: int) -> Path:
    from app.services.report_pdf_service import ReportPdfService
    from app.utils.report_registry import ReportRegistry

    report_id = info["report_id"]
    service = ReportPdfService(base_dir=str(staging_root))
    pdf_bytes = await service.generate_pdf(
        report_id, user_id=info.get("user_id") or None, force=True, vip_level=vip_level
    )

    registry = ReportRegistry(base_dir=str(staging_root))
    record = registry.get_report_by_id(report_id) or {}
    filename = service.get_report_filename(record)
    pdf_path = output_dir / filename
    pdf_path.write_bytes(pdf_bytes)

    # 同时带出 markdown 便于人工核对 LLM 产出
    md_path = staging_root / "reports" / report_id / "report_markdown.md"
    if md_path.is_file():
        shutil.copy2(md_path, output_dir / f"report_{report_id}.md")
    return pdf_path


def main() -> int:
    parser = argparse.ArgumentParser(description="从 admin 批量导出包批量生成 PDF 报告")
    parser.add_argument("--input-root", required=True, help="导出包根目录（子目录名 = report_id）")
    parser.add_argument("--output-dir", required=True, help="PDF / markdown 输出目录")
    parser.add_argument("--staging-root", default=None,
                        help="暂存注册表目录（默认 {output-dir}/_staging_simple）")
    parser.add_argument("--report-id", action="append", default=[],
                        help="只处理指定 report_id（可重复）")
    parser.add_argument("--include-incomplete", action="store_true",
                        help="未完成的报告也生成（占位文案）")
    parser.add_argument("--vip-level", type=int, default=1, help="LLM VIP 档位（默认 1）")
    parser.add_argument("--dry-run", action="store_true", help="只判定完整性，不生成")
    args = parser.parse_args()

    input_root = Path(args.input_root)
    if not input_root.is_dir():
        print(f"输入目录不存在: {input_root}", file=sys.stderr)
        return 2
    output_dir = Path(args.output_dir)
    staging_root = Path(args.staging_root) if args.staging_root else output_dir / "_staging_simple"
    staging_reports = staging_root / "reports"
    staging_reports.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    selected = set(args.report_id)
    pkg_dirs = [
        d for d in sorted(input_root.iterdir())
        if d.is_dir() and (d / "stats.json").is_file()
        and (not selected or d.name in selected)
    ]
    if not pkg_dirs:
        print("没有匹配的导出包", file=sys.stderr)
        return 2

    # 第一步：暂存重建 + 完整性判定
    print(f"暂存目录: {staging_root}")
    infos = []
    for pkg in pkg_dirs:
        info = stage_report(pkg, staging_reports)
        infos.append(info)
        mark = "✅ 完整" if info["complete"] else "⏭️  跳过（未完成）"
        print(
            f"  {info['report_id'][:8]}… 4维结论 {info['dims_done']}/4, "
            f"rumination confirmed {info['confirmed_combos']} 条 → {mark}"
        )

    todo = [i for i in infos if i["complete"] or args.include_incomplete]
    skipped = [i for i in infos if i not in todo]
    print(f"\n将生成 {len(todo)} 份，跳过 {len(skipped)} 份")
    if args.dry_run:
        return 0

    # 第二步：复用系统逻辑逐份生成
    failures = []
    for info in todo:
        rid = info["report_id"]
        print(f"\n▶ 生成 {rid} …", flush=True)
        try:
            pdf_path = asyncio.run(generate_one(staging_root, info, output_dir, args.vip_level))
            print(f"  ✅ {pdf_path.name}（{pdf_path.stat().st_size // 1024} KB）")
        except Exception as e:
            failures.append(rid)
            print(f"  ❌ 失败: {e}", file=sys.stderr)

    print(f"\n完成：成功 {len(todo) - len(failures)}，失败 {len(failures)}，跳过 {len(skipped)}")
    print(f"输出目录: {output_dir}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
