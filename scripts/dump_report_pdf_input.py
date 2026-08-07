#!/usr/bin/env python3
"""
dump_report_pdf_input.py — 报告 PDF 输入数据 dump（v4 一致性验证用）

用途（2026-08-07）：
  PDF 报告是 LLM 基于底层数据「重写」的，直接看 PDF 无法确定数据层是否正确。
  本脚本复用 ReportPdfService._collect_phase_data 的同一份数据源，把喂给 LLM 的
  原始数据确定性 dump 出来，绕开 LLM 噪音，用于验证：
    1. 底层数据是否为最新 rumination v4 结构（rumination_v4_progress.json）
    2. PDF 各阶段文本块与结论卡（conclusion_card / dimension_conclusions）是否一致

输出内容：
  - record.json 的五阶段完成状态与 report_unlocked 判定（与 admin 列表同口径）
  - dimension_conclusions.json 原始内容（4 维结论卡）
  - rumination_v4_progress.json 关键字段（final_selection / combo_sessions 结论卡）
  - _collect_phase_data 渲染出的 5 个文本块（即 LLM prompt 里实际看到的内容）

用法示例：
    # dump 指定 report（默认数据根 data/simple）
    python scripts/dump_report_pdf_input.py <report_id>

    # 指定数据根（如测试/沙箱目录）
    python scripts/dump_report_pdf_input.py <report_id> --base-dir data/simple

    # 输出 JSON（便于程序对比）
    python scripts/dump_report_pdf_input.py <report_id> --json

退出码：
    0  正常
    2  参数错误 / report 不存在
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 让脚本可直接从项目根目录运行（与 pytest.ini 的 pythonpath 口径一致）
_BACKEND = Path(__file__).resolve().parent.parent / "src" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.utils.report_registry import STEP_IDS, ReportRegistry, _report_portal_unlocked  # noqa: E402


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {"__error__": str(e)}


def collect(report_id: str, base_dir: Path) -> dict:
    reports_root = base_dir / "reports"
    report_dir = reports_root / report_id
    if not report_dir.is_dir():
        raise SystemExit(f"report 不存在: {report_dir}")

    record = _load_json(report_dir / "record.json")
    steps = record.get("steps") or {}

    # 五阶段完成状态（与 GET /admin/reports 同口径）
    step_status = {}
    for sid in STEP_IDS:
        st = steps.get(sid) or {}
        sessions = st.get("session_ids") or []
        step_status[sid] = {
            "locked": bool(st.get("locked")),
            "selected_session_id": st.get("selected_session_id"),
            "session_count": len(sessions),
            "completed": bool(sessions) or (sid == "rumination" and bool(st.get("locked"))),
        }

    # v4 状态（只保留验证相关字段，messages 全量太大）
    v4_state = _load_json(report_dir / "rumination_v4_progress.json")
    v4_summary = {
        "schema_version": v4_state.get("schema_version"),
        "final_selection": v4_state.get("final_selection"),
        "combo_sessions": [
            {
                "combo_id": c.get("combo_id"),
                "passion": c.get("passion"),
                "strengths": c.get("strengths"),
                "status": c.get("status"),
                "conclusion_card": c.get("conclusion_card"),
            }
            for c in (v4_state.get("combo_sessions") or [])
        ],
    }

    # 与 PDF 生成完全同口径的文本块（LLM 实际看到的内容）
    from app.services.report_pdf_service import ReportPdfService

    service = ReportPdfService(base_dir=str(base_dir))
    phase_blocks = service._collect_phase_data(report_id)

    return {
        "report_id": report_id,
        "base_dir": str(base_dir),
        "activation_code": record.get("activation_code"),
        "user_id": record.get("user_id"),
        "review_status": record.get("review_status"),
        "report_unlocked": _report_portal_unlocked(steps),
        "step_status": step_status,
        "dimension_conclusions": _load_json(report_dir / "dimension_conclusions.json"),
        "rumination_v4": v4_summary,
        "phase_blocks": phase_blocks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="dump 报告 PDF 的输入数据（v4 一致性验证）")
    parser.add_argument("report_id", help="报告 ID")
    parser.add_argument(
        "--base-dir",
        default="data/simple",
        help="数据根目录（默认 data/simple；测试/沙箱数据在 data/simple_test 等）",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    args = parser.parse_args()

    data = collect(args.report_id, Path(args.base_dir))

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    print(f"report_id:       {data['report_id']}")
    print(f"activation_code: {data['activation_code']}")
    print(f"user_id:         {data['user_id']}")
    print(f"review_status:   {data['review_status']}")
    print(f"report_unlocked: {data['report_unlocked']}")
    print("\n── 五阶段完成状态（admin 列表同口径）──")
    for sid, st in data["step_status"].items():
        mark = "✅" if st["completed"] else "❌"
        print(
            f"  {mark} {sid}: locked={st['locked']} "
            f"selected={st['selected_session_id']} sessions={st['session_count']}"
        )

    v4 = data["rumination_v4"]
    print("\n── rumination v4 状态 ──")
    print(f"  schema_version: {v4['schema_version']}")
    print(f"  final_selection: {json.dumps(v4['final_selection'], ensure_ascii=False)}")
    for c in v4["combo_sessions"]:
        card = c["conclusion_card"] or {}
        print(
            f"  combo {c['combo_id']} [{c['status']}]: "
            f"{c['passion']} × {c['strengths']} card_updated={card.get('updated_at')}"
        )

    print("\n── 喂给 LLM 的文本块（phase_blocks）──")
    for key, block in data["phase_blocks"].items():
        print(f"\n### {key}\n{block}")

    print("\n（完整 dimension_conclusions 原文请加 --json 查看）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
