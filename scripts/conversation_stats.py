#!/usr/bin/env python3
"""
离线对话每轮平均时长统计脚本（T3 离线版）。

解析 T1 BatchExportService 导出的 md/txt 文件（按冻结格式规范），
输出每个 report 的每轮平均时长统计。

用法:
    python scripts/conversation_stats.py <export_zip_or_dir>

参数:
    export_zip_or_dir: T1 导出的 zip 文件路径，或解压后的目录路径。

示例:
    python scripts/conversation_stats.py reports_batch_export_20260101_120000.zip
    python scripts/conversation_stats.py /path/to/extracted_reports/

说明:
    - 自动识别 md/txt 格式
    - 输出每个 report 的轮数 / 平均时长 / 总时长 / per_phase 明细
    - 与在线版 ConversationStatsService 的切轮逻辑保持一致
"""

from __future__ import annotations

import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 把 src/backend 加入 path 以复用 service 层的公共函数
_THIS_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _THIS_DIR.parent / "src" / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.services.conversation_stats_service import (  # noqa: E402
    PHASE_LABEL_CN,
    _aggregate_phase_stats,
    _build_reminder_text,
    compute_turn_stats_from_messages,
)
from app.utils.report_registry import STEP_IDS  # noqa: E402

# ── 正则：解析 T1 冻结格式 ─────────────────────────────────────

# 文件头标题行
_RE_TITLE_MD = re.compile(r"^# 寻录探索报告 - (.+)$")
_RE_TITLE_TXT = re.compile(r"^寻录探索报告 - (.+)$")

# 元信息行
_RE_META = re.compile(r"^([^:]+): (.*)$")

# Phase 章节标题（md: ## 1. 价值观（values） / txt: 1. 价值观（values））
_RE_PHASE_MD = re.compile(r"^## (\d+)\. (.+)（(\w+)）\s*$")
_RE_PHASE_TXT = re.compile(r"^(\d+)\. (.+)（(\w+)）\s*$")

# 消息行（md: **[角色]** 时间戳 / txt: [角色] 时间戳）
_RE_MSG_MD = re.compile(r"^\*\*\[(.+?)\]\*\*\s*(.*)$")
_RE_MSG_TXT = re.compile(r"^\[(.+?)\]\s*(.*)$")

# 角色中文 -> 英文映射（与 batch_export 反向）
_ROLE_CN_TO_EN = {
    "用户": "user",
    "助手": "assistant",
    "系统": "system",
    "工具": "tool",
}


def _detect_format(filename: str) -> str:
    """根据扩展名检测格式（md 或 txt）。"""
    if filename.endswith(".md"):
        return "md"
    return "txt"


def parse_export_file(
    content: str, filename: str
) -> Tuple[str, Dict[str, str], List[Dict]]:
    """
    解析单个 T1 导出文件，提取 report_id、元信息、phase+消息。

    Args:
        content: 文件文本内容
        filename: 文件名（用于检测格式）

    Returns:
        (report_id, meta_dict, phases)
        其中 phases = [{"phase_id": str, "phase_name": str, "messages": [...]}, ...]
    """
    fmt = _detect_format(filename)
    lines = content.split("\n")

    report_id = ""
    meta: Dict[str, str] = {}
    phases: List[Dict] = []

    i = 0
    # 1. 解析文件头标题
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        m = _RE_TITLE_MD.match(line) if fmt == "md" else _RE_TITLE_TXT.match(line)
        if m:
            report_id = m.group(1).strip()
            i += 1
            break
        # 如果不是标题行，继续扫
        i += 1

    # 2. 跳过 = 分隔线，解析元信息块
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if set(line) == {"="}:
            # = 分隔线，继续
            i += 1
            continue
        if set(line) == {"-"}:
            # - 分隔线，元信息块结束
            i += 1
            break
        m = _RE_META.match(line)
        if m:
            key = m.group(1).strip()
            val = m.group(2).strip()
            meta[key] = val
        i += 1

    # 3. 解析 phase 章节
    while i < len(lines):
        line = lines[i].strip() if i < len(lines) else ""
        if not line:
            i += 1
            continue

        # 检测 phase 标题
        phase_match = None
        if fmt == "md":
            phase_match = _RE_PHASE_MD.match(line)
        else:
            phase_match = _RE_PHASE_TXT.match(line)

        if not phase_match:
            i += 1
            continue

        # seq = phase_match.group(1)
        phase_name = phase_match.group(2)
        phase_id = phase_match.group(3)
        i += 1

        # txt 格式标题后跟 - 分隔线
        if fmt == "txt" and i < len(lines) and set(lines[i].strip()) == {"-"}:
            i += 1

        # 跳过空行 + 会话信息块（  - 字段: 值）
        while i < len(lines):
            l = lines[i]
            if l.strip().startswith("  - "):
                i += 1
                continue
            if l.strip() == "":
                i += 1
                continue
            break

        # 解析消息块
        messages: List[Dict] = []
        msg_re = _RE_MSG_MD if fmt == "md" else _RE_MSG_TXT
        while i < len(lines):
            l = lines[i]
            stripped = l.strip()
            if not stripped:
                i += 1
                continue
            # 检测是否是新的 phase 标题或文件尾
            if fmt == "md" and _RE_PHASE_MD.match(stripped):
                break
            if fmt == "txt" and _RE_PHASE_TXT.match(stripped):
                break

            m = msg_re.match(stripped)
            if m:
                role_cn = m.group(1).strip()
                timestamp = m.group(2).strip()
                role_en = _ROLE_CN_TO_EN.get(role_cn, role_cn.lower())
                # 下行是正文
                i += 1
                content_lines: List[str] = []
                while i < len(lines) and lines[i].strip():
                    # 检查是否到了下一条消息（避免吃掉下一条）
                    next_stripped = lines[i].strip()
                    if msg_re.match(next_stripped):
                        break
                    if fmt == "md" and _RE_PHASE_MD.match(next_stripped):
                        break
                    if fmt == "txt" and _RE_PHASE_TXT.match(next_stripped):
                        break
                    content_lines.append(lines[i])
                    i += 1
                messages.append(
                    {
                        "role": role_en,
                        "created_at": timestamp if timestamp else None,
                        "content": "\n".join(content_lines).strip(),
                    }
                )
            else:
                i += 1

        phases.append(
            {
                "phase_id": phase_id,
                "phase_name": phase_name,
                "messages": messages,
            }
        )

    return report_id, meta, phases


def compute_report_stats_from_parsed(
    report_id: str,
    meta: Dict[str, str],
    phases: List[Dict],
) -> Dict:
    """
    对解析后的单个 report 数据计算统计（复用 service 层公共函数）。

    Args:
        report_id: 报告 ID
        meta: 元信息字典
        phases: phase 列表

    Returns:
        统计结果字典（结构与 ConversationStatsService 一致）
    """
    per_phase: List[Dict] = []
    for phase in phases:
        phase_id = phase.get("phase_id") or ""
        phase_name = phase.get("phase_name") or PHASE_LABEL_CN.get(phase_id, phase_id)
        messages = phase.get("messages") or []
        stats = compute_turn_stats_from_messages(messages)
        avg_minutes = stats["avg_seconds"] / 60.0
        total_minutes = stats["total_seconds"] / 60.0
        per_phase.append(
            {
                "phase_id": phase_id,
                "phase_name": phase_name,
                "turns": stats["turns"],
                "avg_seconds": stats["avg_seconds"],
                "total_seconds": stats["total_seconds"],
                "avg_minutes": round(avg_minutes, 1),
                "total_minutes": round(total_minutes, 1),
                "skipped_no_ts": stats["skipped_no_ts"],
                "skipped_long_turns": stats["skipped_long_turns"],
                "total_turns_seen": stats["total_turns_seen"],
                "message_count": len(messages),
            }
        )

    aggregated = _aggregate_phase_stats(per_phase)
    aggregated["per_phase"] = per_phase
    aggregated["report_id"] = report_id
    label = meta.get("用户名") or meta.get("用户ID") or report_id[:8]
    aggregated["reminder_text"] = _build_reminder_text(
        aggregated["total_turns"],
        aggregated["avg_minutes"],
        aggregated["total_minutes"],
        label if label != "未提供" else report_id[:8],
    )
    return aggregated


def _iter_export_files(path: str) -> List[Tuple[str, str]]:
    """
    从 zip 或目录中遍历导出文件。

    Args:
        path: zip 文件或目录路径

    Returns:
        [(filename, content), ...] 列表
    """
    p = Path(path)
    files: List[Tuple[str, str]] = []

    if p.is_file() and p.suffix == ".zip":
        with zipfile.ZipFile(p, "r") as zf:
            for name in zf.namelist():
                if name.endswith((".md", ".txt")) and not name.startswith("__MACOSX"):
                    content = zf.read(name).decode("utf-8")
                    files.append((os.path.basename(name), content))
    elif p.is_dir():
        for fp in sorted(p.iterdir()):
            if fp.is_file() and fp.suffix in (".md", ".txt"):
                content = fp.read_text(encoding="utf-8")
                files.append((fp.name, content))
    else:
        print(f"错误：路径不存在或格式不支持: {path}", file=sys.stderr)
        sys.exit(1)

    return files


def main(argv: List[str]) -> int:
    """命令行入口。"""
    if len(argv) < 2:
        print(__doc__)
        return 1

    export_path = argv[1]
    files = _iter_export_files(export_path)
    if not files:
        print("未找到 .md 或 .txt 导出文件", file=sys.stderr)
        return 1

    print(f"共发现 {len(files)} 个导出文件\n")

    for filename, content in files:
        report_id, meta, phases = parse_export_file(content, filename)
        if not report_id:
            print(f"[跳过] {filename}：无法解析 report_id")
            continue

        stats = compute_report_stats_from_parsed(report_id, meta, phases)

        print(f"{'=' * 60}")
        print(f"报告: {report_id}")
        print(f"文件: {filename}")
        if meta.get("用户ID"):
            print(f"用户ID: {meta['用户ID']}")
        if meta.get("用户名") and meta["用户名"] != "未提供":
            print(f"用户名: {meta['用户名']}")
        print(f"{'─' * 40}")
        print(f"  总轮数: {stats['total_turns']}")
        print(f"  平均每轮: {stats['avg_minutes']:.1f} 分钟")
        print(f"  总时长: {stats['total_minutes']:.0f} 分钟")
        if stats["skipped_no_ts"] > 0:
            print(f"  跳过(缺时间戳): {stats['skipped_no_ts']} 轮")
        if stats["skipped_long_turns"] > 0:
            print(f"  跳过(异常>2h): {stats['skipped_long_turns']} 轮")
        print(f"  提醒: {stats['reminder_text']}")

        if stats["per_phase"]:
            print(f"  {'─' * 36}")
            print(f"  各阶段明细:")
            for ph in stats["per_phase"]:
                print(
                    f"    {ph['phase_name']}({ph['phase_id']}): "
                    f"{ph['turns']}轮 / 均{ph['avg_minutes']:.1f}分 / 总{ph['total_minutes']:.0f}分"
                )
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
