"""报告生成：JSON + Markdown"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List

from common.models import AggregateReport, TestItem, TestSuiteResult


def generate_report(
    checklist_file: str,
    items: List[TestItem],
    suite_results: List[TestSuiteResult],
    output_dir: str,
) -> AggregateReport:
    """汇总报告并写入文件。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    timestamp = datetime.now().isoformat(timespec="seconds")

    report = AggregateReport(
        timestamp=timestamp,
        checklist_file=checklist_file,
        total_items=len(items),
        items=items,
        suite_results=suite_results,
    )

    # 按测试结果映射状态
    _merge_suite_results(report, suite_results)

    # 分类统计
    for it in items:
        if it.item_type == "human_reviewed":
            if it.status == "pending":
                report.human_reviewed_pending += 1
        else:
            if it.status == "passed":
                report.automated_passed += 1
            elif it.status == "failed":
                report.automated_failed += 1
            elif it.status in ("skipped", "pending"):
                report.automated_skipped += 1

    # 写入文件
    os.makedirs(output_dir, exist_ok=True)

    json_path = os.path.join(output_dir, f"run_{ts}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(_report_to_dict(report), f, ensure_ascii=False, indent=2)

    md_path = os.path.join(output_dir, f"run_{ts}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(_render_markdown(report))

    return report


def _merge_suite_results(report: AggregateReport, suite_results: List[TestSuiteResult]):
    """将测试执行结果映射回 TestItem。"""
    # 构建 file → pass/fail 映射
    file_status: Dict[str, str] = {}
    file_fail_msgs: Dict[str, List[str]] = {}
    for sr in suite_results:
        for detail in sr.details:
            if detail.failed > 0:
                file_status[detail.file] = "failed"
                file_fail_msgs[detail.file] = detail.fail_messages
            elif detail.passed > 0 and detail.file not in file_status:
                file_status[detail.file] = "passed"

    for it in report.items:
        if it.test_file and it.item_type == "automated":
            status = file_status.get(it.test_file)
            if status:
                it.status = status
                if status == "failed":
                    msgs = file_fail_msgs.get(it.test_file, [])
                    it.evidence = "\n".join(msgs[:3]) if msgs else "详见测试输出"


def _render_markdown(report: AggregateReport) -> str:
    lines: List[str] = []
    lines.append(f"# 测试报告 — {report.checklist_file}")
    lines.append(f"> 生成时间: {report.timestamp}")
    lines.append("")

    # ── 摘要 ────────────────────────────────────────────────────────
    lines.append("## 摘要")
    lines.append("")
    lines.append(f"| 指标 | 数量 |")
    lines.append(f"|------|------|")
    lines.append(f"| 总测试项 | {report.total_items} |")
    lines.append(f"| 自动化通过 | {report.automated_passed} |")
    lines.append(f"| 自动化失败 | {report.automated_failed} |")
    lines.append(f"| 自动化跳过 | {report.automated_skipped} |")
    lines.append(f"| 人工评审待办 | {report.human_reviewed_pending} |")
    lines.append("")

    # ── 失败项 ──────────────────────────────────────────────────────
    failed = [it for it in report.items if it.status == "failed"]
    if failed:
        lines.append("## 自动化失败项")
        lines.append("")
        lines.append("| Task ID | 章节 | 描述 | 错误 |")
        lines.append("|---------|------|------|------|")
        for it in failed:
            tids = ", ".join(it.task_ids)
            lines.append(f"| {tids} | {it.section} | {it.description} | {it.evidence or '-'} |")
        lines.append("")

    # ── 按章节汇总 ──────────────────────────────────────────────────
    lines.append("## 按章节汇总")
    lines.append("")

    current_cat = ""
    for it in report.items:
        if it.category and it.category != current_cat:
            current_cat = it.category
            lines.append(f"### {current_cat}")
            lines.append("")

        if it.section:
            lines.append(f"#### {it.section}")
            lines.append("")

        status_icon = {
            "passed": "[x]",
            "failed": "[!]",
            "skipped": "[-]",
            "pending": "[ ]",
        }.get(it.status, "[?]")

        tid_str = ", ".join(it.task_ids)
        type_tag = "（人工评审）" if it.item_type == "human_reviewed" else ""
        lines.append(f"- {status_icon} {it.description} **({tid_str})** {type_tag}")
    lines.append("")

    # ── 套件详情 ────────────────────────────────────────────────────
    if report.suite_results:
        lines.append("## 测试套件详情")
        lines.append("")
        for sr in report.suite_results:
            lines.append(f"### {sr.test_type.upper()}")
            lines.append(f"- 总数: {sr.total}  通过: {sr.passed}  失败: {sr.failed}  跳过: {sr.skipped}  耗时: {sr.duration:.1f}s")
            for detail in sr.details:
                status = "PASS" if detail.failed == 0 else "FAIL"
                lines.append(f"  - [{status}] {detail.file} ({detail.passed}p/{detail.failed}f/{detail.skipped}s)")
            lines.append("")

    return "\n".join(lines)


def _report_to_dict(report: AggregateReport) -> Dict[str, Any]:
    return {
        "timestamp": report.timestamp,
        "checklist_file": report.checklist_file,
        "total_items": report.total_items,
        "automated_passed": report.automated_passed,
        "automated_failed": report.automated_failed,
        "automated_skipped": report.automated_skipped,
        "human_reviewed_pending": report.human_reviewed_pending,
        "items": [
            {
                "task_ids": it.task_ids,
                "description": it.description,
                "section": it.section,
                "category": it.category,
                "item_type": it.item_type,
                "priority": it.priority,
                "status": it.status,
                "test_file": it.test_file,
                "evidence": it.evidence,
            }
            for it in report.items
        ],
        "suite_results": [
            {
                "test_type": suite.test_type,
                "total": suite.total,
                "passed": suite.passed,
                "failed": suite.failed,
                "skipped": suite.skipped,
                "duration": suite.duration,
                "details": [
                    {
                        "file": d.file,
                        "passed": d.passed,
                        "failed": d.failed,
                        "skipped": d.skipped,
                        "fail_messages": d.fail_messages,
                    }
                    for d in suite.details
                ],
            }
            for suite in report.suite_results
        ],
    }
