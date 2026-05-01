#!/usr/bin/env python3
"""claude-test 统一测试入口

用法:
    python test/claude-test/run_all.py                          # 全部
    python test/claude-test/run_all.py --type backend            # 只跑后端
    python test/claude-test/run_all.py --task-ids S-02,P-06     # 指定任务
    python test/claude-test/run_all.py --human-mark U-05=pass   # 标记人工评审
    python test/claude-test/run_all.py --checklist xxx.md       # 指定清单
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from typing import List, Optional

# 确保项目根和 claude-test 都在 sys.path
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_SCRIPT_DIR, "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from common.models import TestItem, TestRunDetail, TestSuiteResult
from common.task_mapping import resolve_test_type
from common.report import generate_report
from parser.md_checklist_parser import parse_checklist


def _parse_args():
    parser = argparse.ArgumentParser(description="claude-test 统一测试入口")
    parser.add_argument(
        "--checklist",
        default=os.path.join(_PROJECT_ROOT, "4.28开发待测清单.md"),
        help="MD 清单文件路径",
    )
    parser.add_argument(
        "--type",
        choices=["backend", "frontend", "e2e", "all"],
        default="all",
        help="运行哪些测试套件（默认 all）",
    )
    parser.add_argument(
        "--task-ids",
        default="",
        help="只运行指定 Task ID（逗号分隔，如 S-02,P-06）",
    )
    parser.add_argument(
        "--human-mark",
        action="append",
        default=[],
        help="标记人工评审项（格式：TASK_ID=pass|fail）",
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(_SCRIPT_DIR, "reports"),
        help="报告输出目录",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="输出 pytest 原始日志（含每条测试 PASSED/FAILED）",
    )
    parser.add_argument(
        "--show-unmapped",
        action="store_true",
        default=True,
        help="显示未映射到测试文件的自动化项清单（默认开启，--no-show-unmapped 关闭）",
    )
    parser.add_argument(
        "--no-show-unmapped",
        dest="show_unmapped",
        action="store_false",
        help="不显示未映射项清单",
    )
    return parser.parse_args()


def _run_backend(items: List[TestItem], verbose: bool = False) -> TestSuiteResult:
    """运行后端 pytest 测试。"""
    result = TestSuiteResult(test_type="backend")
    # 收集需要跑的测试文件
    test_files = set()
    for it in items:
        if it.test_file and it.test_file.startswith("backend/"):
            full_path = os.path.join(_SCRIPT_DIR, it.test_file)
            if os.path.isfile(full_path):
                test_files.add(it.test_file)

    if not test_files:
        return result

    t0 = time.time()
    cmd = [
        sys.executable, "-m", "pytest",
        "-c", os.path.join(_SCRIPT_DIR, "pytest.ini"),
        "-v", "--tb=short", "--no-header",
        f"--rootdir={_SCRIPT_DIR}",
    ] + sorted(test_files)

    try:
        env = {**os.environ, "PYTHONPATH": os.path.join(_PROJECT_ROOT, "src", "backend")}
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=_SCRIPT_DIR,
            env=env,
        )
        raw = proc.stdout + proc.stderr
    except subprocess.TimeoutExpired:
        raw = "TIMEOUT: 测试超过 300 秒"
    except Exception as e:
        raw = f"ERROR: {e}"

    if verbose:
        print(raw)

    result.raw_output = raw
    result.duration = time.time() - t0

    # 解析 pytest 输出
    result, _ = _parse_pytest_output(raw, test_files, result)
    return result


def _parse_pytest_output(
    raw: str,
    test_files: set,
    result: TestSuiteResult,
) -> tuple[TestSuiteResult, dict]:
    """解析 pytest verbose 输出，按文件分组统计。"""
    file_details: dict[str, TestRunDetail] = {}
    for tf in test_files:
        file_details[tf] = TestRunDetail(file=tf)

    current_file = ""
    for line in raw.splitlines():
        # 匹配文件头 test_xxx.py::xxx
        m_file = re.match(r"([\w/]+\.py)", line)
        if m_file:
            # 提取相对于 claude-test 的路径
            for tf in test_files:
                if tf.endswith(m_file.group(1)):
                    current_file = tf
                    break

        # 匹配 PASS
        if " PASSED " in line or line.strip().endswith(" PASSED"):
            if current_file and current_file in file_details:
                file_details[current_file].passed += 1

        # 匹配 FAIL
        if " FAILED " in line or line.strip().endswith(" FAILED"):
            if current_file and current_file in file_details:
                file_details[current_file].failed += 1
                file_details[current_file].fail_messages.append(line.strip())

        # 匹配 ERROR
        if " ERROR " in line or line.strip().endswith(" ERROR"):
            if current_file and current_file in file_details:
                file_details[current_file].errors += 1
                file_details[current_file].fail_messages.append(line.strip())

        # 匹配 SKIPPED
        if line.strip().endswith(" SKIPPED"):
            if current_file and current_file in file_details:
                file_details[current_file].skipped += 1

    result.details = list(file_details.values())
    result.total = sum(d.passed + d.failed + d.skipped + d.errors for d in result.details)
    result.passed = sum(d.passed for d in result.details)
    result.failed = sum(d.failed for d in result.details)
    result.skipped = sum(d.skipped for d in result.details)
    result.errors = sum(d.errors for d in result.details)
    return result, file_details


def _run_frontend(_items: List[TestItem], verbose: bool = False) -> TestSuiteResult:
    """前端测试占位（vitest 未安装时跳过）。"""
    result = TestSuiteResult(test_type="frontend")
    result.raw_output = "SKIPPED: 前端测试框架（vitest）尚未安装，跳过"
    result.skipped = 1
    return result


def _run_e2e(_items: List[TestItem], verbose: bool = False) -> TestSuiteResult:
    """E2E 测试占位（playwright 未配置时跳过）。"""
    result = TestSuiteResult(test_type="e2e")
    result.raw_output = "SKIPPED: E2E 测试框架（playwright）尚未配置，跳过"
    result.skipped = 1
    return result


def _print_unmapped_summary(items: List[TestItem]):
    """打印未映射到测试文件的自动化项，帮助发现缺失。"""
    unmapped = [it for it in items if it.item_type == "automated" and not it.test_file]
    human = [it for it in items if it.item_type == "human_reviewed"]
    if unmapped:
        print(f"  未映射自动化项: {len(unmapped)} (暂无测试代码)")
        # 按 task ID 分组，只打印一个代表
        seen_ids: set = set()
        for it in unmapped:
            for tid in it.task_ids:
                if tid not in seen_ids:
                    seen_ids.add(tid)
                    print(f"    - {tid}: {it.description[:40]}")
    if human:
        print(f"  人工评审项: {len(human)} (需人工验证)")
    print()


def main():
    args = _parse_args()

    # ── 1. 解析清单 ────────────────────────────────────────────────
    checklist_path = args.checklist
    if not os.path.isfile(checklist_path):
        print(f"错误: 清单文件不存在 — {checklist_path}")
        sys.exit(1)

    title, items, priorities = parse_checklist(checklist_path)
    print(f"清单: {title}")
    print(f"测试项: {len(items)}  (自动: {sum(1 for i in items if i.item_type == 'automated')}, "
          f"人工: {sum(1 for i in items if i.item_type == 'human_reviewed')})")
    if args.show_unmapped:
        _print_unmapped_summary(items)

    # ── 2. 过滤 ────────────────────────────────────────────────────
    if args.task_ids:
        filter_ids = set(tid.strip() for tid in args.task_ids.split(","))
        items = [it for it in items if set(it.task_ids) & filter_ids]
        print(f"过滤后测试项: {len(items)}")

    # 人工标记
    for mark in args.human_mark:
        if "=" not in mark:
            continue
        tid, status = mark.split("=", 1)
        tid = tid.strip()
        status = status.strip().lower()
        for it in items:
            if tid in it.task_ids and it.item_type == "human_reviewed":
                it.status = status
                print(f"  人工标记: {tid} → {status}")

    # ── 3. 按类型分发执行 ──────────────────────────────────────────
    suite_results: List[TestSuiteResult] = []
    runners = {
        "backend": _run_backend,
        "frontend": _run_frontend,
        "e2e": _run_e2e,
    }

    types_to_run = (
        ["backend", "frontend", "e2e"]
        if args.type == "all"
        else [args.type]
    )

    for t in types_to_run:
        runner = runners[t]
        type_items = [it for it in items if resolve_test_type(it.test_file) == t]
        print(f"运行 {t} 测试 ({len(type_items)} 项)...")
        sr = runner(type_items, verbose=args.verbose)
        suite_results.append(sr)
        print(f"  结果: {sr.passed} passed, {sr.failed} failed, {sr.skipped} skipped ({sr.duration:.1f}s)")
        if sr.failed > 0:
            for d in sr.details:
                if d.fail_messages:
                    for msg in d.fail_messages[:3]:
                        print(f"    FAIL: {msg}")
        print()

    # ── 4. 汇总报告 ────────────────────────────────────────────────
    report = generate_report(
        checklist_file=os.path.basename(checklist_path),
        items=items,
        suite_results=suite_results,
        output_dir=args.output_dir,
    )

    print("=" * 60)
    print(f"报告已生成: {args.output_dir}")
    print(f"  自动化: {report.automated_passed} 通过 / {report.automated_failed} 失败 / {report.automated_skipped} 跳过")
    print(f"  人工评审待办: {report.human_reviewed_pending}")
    print("=" * 60)

    sys.exit(1 if report.automated_failed > 0 else 0)


if __name__ == "__main__":
    main()
