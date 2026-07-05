#!/usr/bin/env python3
"""
离线对话每轮平均时长统计脚本（T3 离线版，raw JSON 数据源）。

支持两种数据源：
  1. 目录扫描（默认）：直接扫 data/simple/reports/{report_id}/ 下的
     record.json + {step}__{session}.json，locked 状态从 record.json 原生读取。
  2. zip 文件：解析 BatchExportService 导出的 zip 中的 raw/{step}__{session}.json，
     locked 状态从导出时写入的 report_step_locked 字段读取（需要新版导出）。

【为什么需要 raw JSON 而不是 md】
BatchExportService 导出的 md 是「纯净版」，故意不含时间戳（**用户**：text 格式），
无法用于时长统计。raw JSON 里的 messages[].created_at 是完整 ISO 时间戳，是唯一可用的数据源。

用法:
    # 不传参数：默认扫 data/simple/reports
    python scripts/conversation_stats.py [选项]

    # 扫指定目录
    python scripts/conversation_stats.py /path/to/reports [选项]

    # 读 zip 导出包
    python scripts/conversation_stats.py export.zip [选项]

示例:
    # 排除 admin 测试用户（可多次）
    python scripts/conversation_stats.py --exclude-user admin --exclude-user test01

    # 按正则排除用户
    python scripts/conversation_stats.py --exclude-user-regex '^(admin|test.*)'

    # 只统计 5 个 phase 全部 locked（走完全程）的报告
    python scripts/conversation_stats.py --min-phases-locked 5

    # 调整时长阈值（默认上限 120 分钟，下限 0 秒）
    python scripts/conversation_stats.py --max-minutes 30 --min-seconds 10

    # 调试：包含未 locked 的 phase + 列出被过滤的明细
    python scripts/conversation_stats.py --include-unlocked --show-skipped

过滤口径（默认）：
    - 只统计 locked=true 的 phase（用户提交确认过的）
    - 无时间戳的报告整体放弃
    - 单轮时长 > 120 分钟视为异常跳过
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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


# ── 文件名/字段解析 ──────────────────────────────────────────────

# raw 文件名格式：raw/{step_id}__{session_id}.json
_RE_RAW_NAME = re.compile(r"^raw/([^_]+(?:_[^_]+)*?)__(.+)\.json$")
# 兜底：从 category 字段反解（category = '{step_id}__{session_id}'）
_RE_CATEGORY = re.compile(r"^(.+?)__(.+)$")


def _parse_step_from_filename(filename: str) -> Optional[str]:
    """从 raw/{step}__{session}.json 路径反解 step_id。"""
    m = _RE_RAW_NAME.match(filename.replace("\\", "/"))
    if m:
        candidate = m.group(1)
        if candidate in STEP_IDS:
            return candidate
    return None


def _parse_step_from_category(category: str) -> Optional[str]:
    """从 category 字段反解 step_id。"""
    if not category:
        return None
    m = _RE_CATEGORY.match(category)
    if m:
        candidate = m.group(1)
        if candidate in STEP_IDS:
            return candidate
    # 直接匹配
    if category in STEP_IDS:
        return category
    return None


def parse_raw_session(data: Dict[str, Any], filename: str) -> Optional[Dict[str, Any]]:
    """
    解析单个 raw/{step}__{session}.json，返回结构化数据。

    Args:
        data: json.loads 后的字典
        filename: zip 内路径（用于兜底反解 step_id）

    Returns:
        结构化字典；无法识别 step_id 返回 None。
    """
    category = data.get("category") or ""
    step_id = (
        _parse_step_from_category(category)
        or _parse_step_from_filename(filename)
    )
    if step_id is None:
        return None

    report_id = data.get("report_id") or ""
    if not report_id:
        # filename 兜底：raw/{step}__{session}.json 里没 report_id 就只能跳过
        return None

    return {
        "report_id": report_id,
        "step_id": step_id,
        "session_id": data.get("session_id") or "",
        "user_id": data.get("report_user_id") or "",
        "activation_code": data.get("report_activation_code") or "",
        "locked": bool(data.get("report_step_locked")),
        "is_selected": bool(data.get("report_step_is_selected")),
        "messages": data.get("messages") or [],
    }


# ── zip 读取 + 按 report 聚合 ────────────────────────────────────


def _iter_raw_files_from_zip(zip_path: str) -> List[Tuple[str, Dict[str, Any]]]:
    """
    从 zip 中读取所有 raw/*.json 文件（排除 rumination_progress.json）。

    Args:
        zip_path: zip 文件路径

    Returns:
        [(filename, parsed_dict), ...] 列表
    """
    files: List[Tuple[str, Dict[str, Any]]] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if name.startswith("__MACOSX"):
                continue
            if not name.startswith("raw/") or not name.endswith(".json"):
                continue
            if name.endswith("rumination_progress.json"):
                continue
            try:
                content = zf.read(name).decode("utf-8")
                data = json.loads(content)
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                print(f"[警告] 解析失败 {name}: {e}", file=sys.stderr)
                continue
            if not isinstance(data, dict):
                continue
            parsed = parse_raw_session(data, name)
            if parsed is None:
                print(f"[跳过] 无法识别 step_id: {name}", file=sys.stderr)
                continue
            files.append((name, parsed))
    return files


# ── 目录扫描 ────────────────────────────────────────────────────

# 默认扫描目录（项目内 data/simple/reports）
_DEFAULT_REPORTS_DIR = _THIS_DIR.parent / "data" / "simple" / "reports"


def _load_record_safely(record_path: Path) -> Optional[dict]:
    """安全读取 record.json，损坏时返回 None 并打印警告。"""
    try:
        data = json.loads(record_path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError) as e:
        print(
            f"[警告] record.json 解析失败，跳过该 report: {record_path.parent.name}: {e}",
            file=sys.stderr,
        )
        return None
    if not isinstance(data, dict):
        return None
    return data


def _load_step_session_safely(sess_path: Path) -> Optional[dict]:
    """安全读取 {step}__{session}.json，损坏时返回 None。"""
    try:
        data = json.loads(sess_path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError) as e:
        print(
            f"[警告] step session 文件解析失败，跳过: {sess_path.name}: {e}",
            file=sys.stderr,
        )
        return None
    if not isinstance(data, dict):
        return None
    return data


def _load_from_dir(
    dir_path: str,
    *,
    _only_selected: bool = True,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    扫描 report 目录，直接读 record.json + {step}__{session}.json。

    与 _iter_raw_files_from_zip + _group_by_report 返回结构一致：
        {report_id: [step_data, ...]}

    数据来源说明（vs zip 模式）：
    - locked 状态：从 record.json 的 steps[sid].locked 原生读取（更可靠）
    - user_id / activation_code：从 record.json 原生读取
    - messages：从 {step}__{session}.json 的 messages[] 读取

    Args:
        dir_path: reports 目录路径（其下应是 {report_id}/ 子目录）
        _only_selected: 内部保留参数，当前仅支持 True（只读 selected_session_id
                       对应的文件）；False 预留给未来扩展（读所有会话）。

    Returns:
        {report_id: [step_data, ...]}
    """
    base = Path(dir_path)
    if not base.is_dir():
        print(f"错误：目录不存在: {dir_path}", file=sys.stderr)
        return {}

    reports: Dict[str, List[Dict[str, Any]]] = {}
    skipped_records = 0

    for d in sorted(base.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        record_path = d / "record.json"
        if not record_path.is_file():
            continue

        record = _load_record_safely(record_path)
        if record is None:
            skipped_records += 1
            continue

        report_id = record.get("report_id") or d.name
        user_id = record.get("user_id") or ""
        activation_code = record.get("activation_code") or ""
        steps_meta = record.get("steps") or {}

        step_list: List[Dict[str, Any]] = []
        for step_id in STEP_IDS:
            step_meta = steps_meta.get(step_id) or {}
            selected_sess = step_meta.get("selected_session_id")
            if not selected_sess:
                # 无 selected session -> 该 phase 未完成，跳过
                continue

            sess_path = d / f"{step_id}__{selected_sess}.json"
            if not sess_path.is_file():
                print(
                    f"[警告] step session 文件缺失: {sess_path.name} (report={report_id})",
                    file=sys.stderr,
                )
                continue

            sess_data = _load_step_session_safely(sess_path)
            if sess_data is None:
                continue

            step_entry: Dict[str, Any] = {
                "report_id": report_id,
                "step_id": step_id,
                "session_id": selected_sess,
                "user_id": user_id,
                "activation_code": activation_code,
                "locked": bool(step_meta.get("locked")),
                "is_selected": True,
                "messages": sess_data.get("messages") or [],
            }

            # rumination: 额外读 rumination_progress.json 的 step 快照（含时间戳）
            if step_id == "rumination":
                prog_path = d / "rumination_progress.json"
                if prog_path.is_file():
                    prog = _load_step_session_safely(prog_path)
                    if prog and isinstance(prog.get("filter_step_snapshots"), dict):
                        step_entry["step_snapshots"] = prog["filter_step_snapshots"]

            step_list.append(step_entry)

        if step_list:
            reports[report_id] = step_list

    if skipped_records > 0:
        print(
            f"[警告] 共 {skipped_records} 份 report 的 record.json 损坏，已跳过",
            file=sys.stderr,
        )

    return reports


def _group_by_report(
    raw_files: List[Tuple[str, Dict[str, Any]]],
) -> Dict[str, List[Dict[str, Any]]]:
    """按 report_id 聚合 step 文件。返回 {report_id: [step_data, ...]}。"""
    reports: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for _, parsed in raw_files:
        reports[parsed["report_id"]].append(parsed)
    return reports


# ── 过滤与统计 ───────────────────────────────────────────────────


def _report_user_id(steps: List[Dict[str, Any]]) -> str:
    """从 step 列表里取 user_id（各 step 应一致，取第一个非空）。"""
    for s in steps:
        uid = s.get("user_id") or ""
        if uid:
            return uid
    return ""


def _has_any_timestamp(steps: List[Dict[str, Any]]) -> bool:
    """检查报告是否至少有一条消息带时间戳。"""
    for s in steps:
        for m in s.get("messages") or []:
            if m.get("created_at") or m.get("timestamp"):
                return True
    return False


def _filter_report_level(
    _report_id: str,
    steps: List[Dict[str, Any]],
    args: argparse.Namespace,
) -> Tuple[bool, str]:
    """
    报告级过滤。返回 (是否通过, 被过滤原因)。

    过滤条件：
    - 无任何时间戳 → 放弃（用户要求）
    - user_id 命中 --exclude-user 或 --exclude-user-regex → 排除
    - locked phase 数 < --min-phases-locked → 排除
    """
    # 无时间戳
    if not _has_any_timestamp(steps):
        return False, "无时间戳，放弃"

    uid = _report_user_id(steps)

    # 精确排除
    if args.exclude_user and uid in args.exclude_user:
        return False, f"用户 {uid} 命中 --exclude-user"

    # 正则排除
    if args.exclude_user_regex:
        if re.search(args.exclude_user_regex, uid):
            return False, f"用户 {uid} 命中 --exclude-user-regex"

    # 最少 locked phase 数
    if args.min_phases_locked > 0:
        locked_count = sum(1 for s in steps if s.get("locked"))
        if locked_count < args.min_phases_locked:
            return False, f"locked phase 数 {locked_count} < {args.min_phases_locked}"

    return True, ""


def _compute_phase_duration(
    messages: List[Dict[str, Any]],
    *,
    gap_threshold_seconds: float = 30 * 60,
) -> Dict[str, Any]:
    """
    计算单个 phase 的「真实投入耗时」（秒）。

    口径（会话分段累加）：
        扫描消息时间戳序列，相邻两条消息间隔 > gap_threshold_seconds
        视为「用户离开」，把序列切成多个会话段。phase 耗时 = 各段
        （段首消息 → 段末消息）时长之和。这样能剔除用户跨天/跨周
        回来看页面造成的虚高耗时。

    终点选取：每段以「段末最后一条 role==assistant 的消息」为终点；
              若整段无 assistant 消息，则用段末最后一条消息。

    Args:
        messages: 该 phase 的全部消息（按时间先后）
        gap_threshold_seconds: 相邻消息间隔超过此值视为「离开」。
                              默认 30 分钟。

    Returns:
        {
            "active_seconds": float | None,   # 分段累加后的真实耗时（无有效段返回 None）
            "span_seconds": float | None,     # 首条→末条 raw 跨度（参考用）
            "segments": int,                  # 切出的会话段数
            "skipped_gap_seconds": float,     # 被视为「离开」剔除的总时长
        }
    """
    if not messages:
        return {"active_seconds": None, "span_seconds": None, "segments": 0, "skipped_gap_seconds": 0.0}

    # 抽出所有带时间戳的消息
    ts_list: List[Tuple[Any, str]] = []  # (datetime, role)
    for m in messages:
        ts = m.get("created_at") or m.get("timestamp")
        dt = _parse_iso(ts)
        if dt is None:
            continue
        ts_list.append((dt, (m.get("role") or "").strip().lower()))

    if not ts_list:
        return {"active_seconds": None, "span_seconds": None, "segments": 0, "skipped_gap_seconds": 0.0}

    # raw 跨度（参考）
    span_seconds = (ts_list[-1][0] - ts_list[0][0]).total_seconds()

    # 按间隔切分段
    segments: List[List[Tuple[Any, str]]] = [[ts_list[0]]]
    skipped_gap_seconds = 0.0
    for prev_dt, _ in ts_list[:-1]:
        pass  # 仅用于类型提示，实际循环在下
    for i in range(1, len(ts_list)):
        dt, role = ts_list[i]
        prev_dt = ts_list[i - 1][0]
        gap = (dt - prev_dt).total_seconds()
        if gap > gap_threshold_seconds:
            # 离开：结束当前段，开新段；gap 计入剔除时长
            segments.append([ts_list[i]])
            skipped_gap_seconds += gap
        else:
            segments[-1].append(ts_list[i])

    # 各段累加（段首 → 段末最后一条 assistant；无 assistant 则段末最后一条）
    active_seconds = 0.0
    for seg in segments:
        if len(seg) < 2:
            # 单条消息段：时长 0
            continue
        seg_start = seg[0][0]
        seg_end: Optional[Any] = None
        for dt, role in reversed(seg):
            if role == "assistant":
                seg_end = dt
                break
        if seg_end is None:
            seg_end = seg[-1][0]  # 段末最后一条
        dur = (seg_end - seg_start).total_seconds()
        if dur > 0:
            active_seconds += dur

    return {
        "active_seconds": active_seconds if active_seconds > 0 else None,
        "span_seconds": span_seconds,
        "segments": len(segments),
        "skipped_gap_seconds": skipped_gap_seconds,
    }


def _filter_phase_level(
    step: Dict[str, Any],
    args: argparse.Namespace,
) -> Tuple[bool, str]:
    """
    Phase 级过滤。返回 (是否通过, 被过滤原因)。

    默认（--require-locked）：只统计 locked=true 的 phase。
    --include-unlocked 时放开此限制。
    """
    if args.include_unlocked:
        return True, ""
    # rumination 是终点阶段，流程上不 lock，只要有 selected session 就统计
    if step.get("step_id") == "rumination":
        if step.get("is_selected") or step.get("session_id"):
            return True, ""
        return False, "rumination 未 selected"
    if not step.get("locked"):
        return False, "未 locked"
    return True, ""


def _compute_report_stats(
    report_id: str,
    steps: List[Dict[str, Any]],
    args: argparse.Namespace,
) -> Dict[str, Any]:
    """
    对单份 report 计算统计。返回结构：
    {
        "report_id": str,
        "user_id": str,
        "per_phase": [...],
        "phase_filtered_out": [...],  # 被过滤掉的 phase（用于 --show-skipped）
        "aggregated": {...},          # _aggregate_phase_stats 结果
        "reminder_text": str,
    }
    """
    user_id = _report_user_id(steps)
    max_seconds = args.max_minutes * 60.0
    min_seconds = float(args.min_seconds)

    per_phase: List[Dict[str, Any]] = []
    phase_filtered_out: List[Dict[str, str]] = []

    # 按 STEP_IDS 顺序排序
    steps_sorted = sorted(
        steps,
        key=lambda s: STEP_IDS.index(s["step_id"]) if s["step_id"] in STEP_IDS else 99,
    )

    for step in steps_sorted:
        phase_id = step["step_id"]
        phase_name = PHASE_LABEL_CN.get(phase_id, phase_id)

        passed, reason = _filter_phase_level(step, args)
        if not passed:
            phase_filtered_out.append(
                {"phase_id": phase_id, "phase_name": phase_name, "reason": reason}
            )
            continue

        messages = step.get("messages") or []
        stats = compute_turn_stats_from_messages(
            messages,
            max_seconds=max_seconds,
            min_seconds=min_seconds,
        )
        avg_minutes = stats["avg_seconds"] / 60.0
        total_minutes = stats["total_seconds"] / 60.0

        # phase 真实投入耗时（会话分段累加，剔除离开时段）
        gap_seconds = args.gap_threshold_minutes * 60.0
        phase_dur = _compute_phase_duration(messages, gap_threshold_seconds=gap_seconds)
        phase_duration_minutes = (
            round(phase_dur["active_seconds"] / 60.0, 1)
            if phase_dur["active_seconds"] is not None
            else None
        )
        phase_span_minutes = (
            round(phase_dur["span_seconds"] / 60.0, 1)
            if phase_dur["span_seconds"] is not None
            else None
        )

        per_phase.append(
            {
                "phase_id": phase_id,
                "phase_name": phase_name,
                "locked": step.get("locked", False),
                # 主口径：phase 真实投入耗时（分段累加）
                "phase_duration_seconds": phase_dur["active_seconds"],
                "phase_duration_minutes": phase_duration_minutes,
                "phase_segments": phase_dur["segments"],
                # 参考口径：首条→末条 raw 跨度（含离开时段）
                "phase_span_minutes": phase_span_minutes,
                # 辅助口径：对话轮次
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
    label = user_id or report_id[:8]
    aggregated["report_id"] = report_id
    aggregated["user_id"] = user_id
    aggregated["phase_filtered_out"] = phase_filtered_out
    aggregated["reminder_text"] = _build_reminder_text(
        aggregated["total_turns"],
        aggregated["avg_minutes"],
        aggregated["total_minutes"],
        label,
    )

    # rumination: 收集子 step 时长（基于 step_snapshots 的 initial_at/submitted_at）
    aggregated["rumination_step_durations"] = []
    for step in steps_sorted:
        if step["step_id"] == "rumination" and step.get("step_snapshots"):
            aggregated["rumination_step_durations"] = _collect_rumination_step_durations(step)
            break

    return aggregated


# ── 输出格式化 ───────────────────────────────────────────────────


def _print_detail_report(
    stats: Dict[str, Any],
    args: argparse.Namespace,
) -> None:
    """打印单份报告的明细（仅 --show-detail 时输出）。"""
    print(f"{'=' * 60}")
    print(f"报告: {stats['report_id']}")
    if stats.get("user_id"):
        print(f"用户ID: {stats['user_id']}")
    print(f"{'─' * 40}")
    print(f"  总轮数: {stats['total_turns']}")
    print(f"  平均每轮: {stats['avg_minutes']:.1f} 分钟")
    print(f"  总时长: {stats['total_minutes']:.0f} 分钟")
    if stats["skipped_no_ts"] > 0:
        print(f"  跳过(缺时间戳): {stats['skipped_no_ts']} 轮")
    if stats["skipped_long_turns"] > 0:
        print(
            f"  跳过(超阈值 >{args.max_minutes:.0f}分 / "
            f"<{args.min_seconds:.0f}秒): {stats['skipped_long_turns']} 轮"
        )

    if stats["per_phase"]:
        print(f"  {'─' * 36}")
        print(f"  各阶段明细（真实耗时为主，跨度作参考）:")
        for ph in stats["per_phase"]:
            lock_mark = "✓" if ph.get("locked") else " "
            dur = ph.get("phase_duration_minutes")
            span = ph.get("phase_span_minutes")
            seg = ph.get("phase_segments", 0)
            dur_str = f"{dur:.1f}分" if dur is not None else "—"
            span_str = f"{span:.1f}分" if span is not None else "—"
            seg_str = f"{seg}段" if seg > 1 else "1段"
            print(
                f"    [{lock_mark}] {ph['phase_name']}({ph['phase_id']}): "
                f"耗时{dur_str}（{seg_str}）/ 跨度{span_str} / {ph['turns']}轮"
            )

    rum_steps = stats.get("rumination_step_durations") or []
    if rum_steps:
        print(f"  {'─' * 36}")
        print(f"  rumination 子 step 时长:")
        for s in rum_steps:
            print(f"    step {s['step']}: {s['duration_minutes']:.1f} 分")

    if args.show_skipped and stats.get("phase_filtered_out"):
        print(f"  {'─' * 36}")
        print(f"  [被过滤 phase]")
        for pf in stats["phase_filtered_out"]:
            print(f"    - {pf['phase_name']}({pf['phase_id']}): {pf['reason']}")

    print()


def _parse_iso(ts: Optional[str]) -> Optional[Any]:
    """解析 ISO 时间戳为 datetime（容忍 Z 后缀）。失败返回 None。"""
    if not ts or not isinstance(ts, str):
        return None
    raw = ts.strip()
    if not raw:
        return None
    try:
        normalized = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _collect_rumination_step_durations(
    step_data: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    从 rumination step 的 step_snapshots 计算每个子 step 的时长。

    时长 = submitted_at - initial_at（首次进入 → 最后提交）。

    旧数据兜底（initial_at 缺失时）：
        用「上一个 step 的 submitted_at」作为本 step 的 initial_at。
        适用于后端补 initial_at 字段之前产生的旧 report。
        标记 fallback=True 以便区分数据来源。

    无 submitted_at 的 step：无法算时长，跳过。

    Returns:
        [{"step": "1", "duration_seconds": float, "initial_at": str,
          "submitted_at": str, "fallback": bool}, ...]
    """
    snapshots = step_data.get("step_snapshots") or {}
    # 先按 step 号排序遍历，便于「用上一个 submitted_at 兜底」
    ordered_keys = sorted(
        snapshots.keys(),
        key=lambda x: (int(x) if str(x).isdigit() else 99),
    )

    results: List[Dict[str, Any]] = []
    prev_submitted_at: Optional[str] = None  # 上一个 step 的 submitted_at，用于兜底

    for sk in ordered_keys:
        ent = snapshots[sk]
        if not isinstance(ent, dict):
            continue
        submitted_at = ent.get("submitted_at")
        if not submitted_at:
            # 没有 submitted_at 的 step 无法算时长，但它的 initial/submitted 都没，
            # 也不能用作下一个 step 的兜底锚点 -> 跳过并保持 prev 不变
            continue

        initial_at = ent.get("initial_at")
        fallback = False
        if not initial_at:
            # 兜底：用上一个 step 的 submitted_at
            if prev_submitted_at:
                initial_at = prev_submitted_at
                fallback = True
            else:
                # 第一个 step 且无 initial_at -> 无法算时长，仅记录 submitted_at
                # 供下一个 step 兜底用
                prev_submitted_at = submitted_at
                continue

        dt_ini = _parse_iso(initial_at)
        dt_sub = _parse_iso(submitted_at)
        if dt_ini is None or dt_sub is None:
            prev_submitted_at = submitted_at
            continue

        duration = (dt_sub - dt_ini).total_seconds()
        if duration >= 0:
            results.append(
                {
                    "step": str(sk),
                    "duration_seconds": duration,
                    "duration_minutes": round(duration / 60.0, 1),
                    "initial_at": initial_at,
                    "submitted_at": submitted_at,
                    "fallback": fallback,
                }
            )
        # 更新 prev_submitted_at（无论本 step 是否产出结果）
        prev_submitted_at = submitted_at

    return results


def _aggregate_phases_across_reports(
    all_stats: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """
    把多份 report 的 per_phase 跨 report 聚合，按 phase_id 分组。

    主口径：phase 整体耗时（phase_duration_minutes）。
    辅助：对话轮数（turns）一并聚合，作参考列。

    每个 phase 输出：
        {
            "phase_id": str,
            "phase_name": str,
            "report_count": int,                # 贡献了这个 phase 的 report 数
            "duration_minutes_list": [float],   # 各 report 的 phase 耗时（分钟）
            "duration_minutes_avg/min/max": float,
            "turns_list": [int],                # 各 report 的轮数（辅助）
            "turns_avg/min/max": float,
        }

    Returns:
        {phase_id: aggregated_dict}
    """
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for stat in all_stats:
        for ph in stat.get("per_phase", []):
            grouped[ph["phase_id"]].append(ph)

    aggregated: Dict[str, Dict[str, Any]] = {}
    for phase_id in STEP_IDS:
        phase_list = grouped.get(phase_id) or []
        if not phase_list:
            continue
        # 主口径：phase 耗时（None 的样本不计入耗时统计，但计入轮数）
        duration_list = [
            p["phase_duration_minutes"]
            for p in phase_list
            if p.get("phase_duration_minutes") is not None
        ]
        turns_list = [p["turns"] for p in phase_list]
        aggregated[phase_id] = {
            "phase_id": phase_id,
            "phase_name": PHASE_LABEL_CN.get(phase_id, phase_id),
            "report_count": len(phase_list),
            "duration_minutes_list": duration_list,
            "duration_minutes_avg": (
                sum(duration_list) / len(duration_list) if duration_list else 0.0
            ),
            "duration_minutes_min": (
                min(duration_list) if duration_list else 0.0
            ),
            "duration_minutes_max": (
                max(duration_list) if duration_list else 0.0
            ),
            "duration_valid_count": len(duration_list),
            # 辅助：轮数
            "turns_list": turns_list,
            "turns_avg": sum(turns_list) / len(turns_list) if turns_list else 0.0,
            "turns_min": min(turns_list) if turns_list else 0,
            "turns_max": max(turns_list) if turns_list else 0,
            # 用于算平均段数等扩展字段
            "_raw": phase_list,
        }
    return aggregated


def _aggregate_rumination_steps_across_reports(
    all_stats: List[Dict[str, Any]],
) -> Dict[str, List[float]]:
    """
    把多份 report 的 rumination 子 step 时长跨 report 聚合。

    Returns:
        {sub_step_id: [duration_seconds, ...]}
    """
    grouped: Dict[str, List[float]] = defaultdict(list)
    for stat in all_stats:
        rum_steps = stat.get("rumination_step_durations") or []
        for s in rum_steps:
            grouped[s["step"]].append(s["duration_seconds"])
    return grouped


# ── 输出：聚合报表 ──────────────────────────────────────────────


def _print_aggregate_report(
    all_stats: List[Dict[str, Any]],
    args: argparse.Namespace,
    filtered_reports: List[Tuple[str, str]],
    total_reports: int,
) -> None:
    """打印聚合报表（不输出逐 report 明细）。"""
    print(f"{'=' * 70}")
    print("对话统计聚合报表")
    print(f"{'=' * 70}")
    print(
        f"  共扫描 {total_reports} 份报告，统计 {len(all_stats)} 份"
        f"（过滤 {len(filtered_reports)} 份）"
    )
    if filtered_reports:
        reason_count: Dict[str, int] = defaultdict(int)
        for _rid, reason in filtered_reports:
            reason_count[reason] += 1
        print(f"  报告级过滤明细:")
        for reason, cnt in sorted(reason_count.items(), key=lambda x: -x[1]):
            print(f"    - {reason}: {cnt} 份")
    print()

    if not all_stats:
        print("  无可统计数据。")
        return

    # ── 各 phase 聚合表 ──────────────────────────────────────────
    phase_agg = _aggregate_phases_across_reports(all_stats)

    print(f"{'─' * 70}")
    print(
        f"【各阶段聚合】（phase 真实耗时 = 会话分段累加；离开阈值 "
        f"{args.gap_threshold_minutes:.0f} 分钟）"
    )
    print(f"{'─' * 70}")
    header = (
        f"  {'阶段':<14} "
        f"{'报告数':>6} "
        f"{'有效耗时':>8} "
        f"{'耗时分(平均)':>14} "
        f"{'耗时分(最小)':>14} "
        f"{'耗时分(最大)':>14} "
        f"{'段数(平均)':>12} "
        f"{'轮数(平均)':>12}"
    )
    print(header)
    print(f"  {'─' * 66}")
    for phase_id in STEP_IDS:
        agg = phase_agg.get(phase_id)
        if not agg:
            print(f"  {PHASE_LABEL_CN.get(phase_id, phase_id):<14} "
                  f"{'-':>6} {'-':>8} {'-':>14} {'-':>14} {'-':>14} {'-':>12} {'-':>12}")
            continue
        # 平均段数：sum(segments) / report_count
        seg_list = [p.get("phase_segments", 0) for p in agg.get("_raw", [])]
        seg_avg = (sum(seg_list) / len(seg_list)) if seg_list else 0.0
        print(
            f"  {agg['phase_name']:<14} "
            f"{agg['report_count']:>6} "
            f"{agg['duration_valid_count']:>8} "
            f"{agg['duration_minutes_avg']:>14.1f} "
            f"{agg['duration_minutes_min']:>14.1f} "
            f"{agg['duration_minutes_max']:>14.1f} "
            f"{seg_avg:>12.1f} "
            f"{agg['turns_avg']:>12.1f}"
        )
    print()

    # ── rumination 子 step 时长 ─────────────────────────────────
    rum_step_agg = _aggregate_rumination_steps_across_reports(all_stats)
    if rum_step_agg:
        print(f"{'─' * 70}")
        print("【rumination 子 step 时长】（基于 initial_at → submitted_at）")
        print(f"{'─' * 70}")
        header = (
            f"  {'子step':>6} "
            f"{'样本数':>6} "
            f"{'时长分(平均)':>14} "
            f"{'时长分(最小)':>14} "
            f"{'时长分(最大)':>14}"
        )
        print(header)
        print(f"  {'─' * 56}")
        for sk in sorted(rum_step_agg.keys(), key=lambda x: (int(x) if x.isdigit() else 99)):
            durations_min = [d / 60.0 for d in rum_step_agg[sk]]
            if not durations_min:
                continue
            print(
                f"  {sk:>6} "
                f"{len(durations_min):>6} "
                f"{sum(durations_min) / len(durations_min):>14.1f} "
                f"{min(durations_min):>14.1f} "
                f"{max(durations_min):>14.1f}"
            )
        print()

    # ── 全局总计 ────────────────────────────────────────────────
    # 主口径：所有 phase 的整体耗时之和（按 report 平均）
    all_phase_durations: List[float] = []
    for s in all_stats:
        for ph in s.get("per_phase", []):
            if ph.get("phase_duration_minutes") is not None:
                all_phase_durations.append(ph["phase_duration_minutes"])

    report_count = len(all_stats)
    sum_phase_minutes = sum(all_phase_durations)
    avg_phase_minutes = (
        sum_phase_minutes / len(all_phase_durations) if all_phase_durations else 0.0
    )
    avg_per_report_minutes = (
        sum_phase_minutes / report_count if report_count > 0 else 0.0
    )
    print(f"{'─' * 70}")
    print(
        f"【全局总计】（基于 phase 真实耗时 = 会话分段累加；离开阈值 "
        f"{args.gap_threshold_minutes:.0f} 分钟）"
    )
    print(
        f"  共 {report_count} 份 report，"
        f"有效 phase 样本 {len(all_phase_durations)} 个，"
        f"phase 平均真实耗时 {avg_phase_minutes:.1f} 分钟，"
        f"每份 report 平均 {avg_per_report_minutes:.0f} 分钟"
    )
    print()


# ── CLI ──────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="离线对话每轮平均时长统计（raw JSON 数据源）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "source",
        nargs="?",
        default=None,
        help=(
            "数据源：zip 文件路径 / report 目录路径 / 不传则默认扫 "
            f"{_DEFAULT_REPORTS_DIR.relative_to(_THIS_DIR.parent)}"
        ),
    )

    # 报告级过滤
    g_report = parser.add_argument_group("报告级过滤")
    g_report.add_argument(
        "--exclude-user",
        action="append",
        default=[],
        metavar="ID",
        help="按 user_id 精确排除（可多次）",
    )
    g_report.add_argument(
        "--exclude-user-regex",
        default=None,
        metavar="PATTERN",
        help="按正则排除 user_id",
    )
    g_report.add_argument(
        "--min-phases-locked",
        type=int,
        default=0,
        metavar="N",
        help="至少 N 个 phase locked 才统计（0=不过滤；5=只看走完全程）",
    )

    # Phase 级过滤
    g_phase = parser.add_argument_group("phase 级过滤")
    g_phase.add_argument(
        "--include-unlocked",
        action="store_true",
        help="包含未 locked 的 phase（默认只统计 locked=true 的）",
    )

    # 轮次时长过滤
    g_turn = parser.add_argument_group("轮次时长过滤")
    g_turn.add_argument(
        "--max-minutes",
        type=float,
        default=120.0,
        metavar="N",
        help="单轮时长上限（分钟），默认 120",
    )
    g_turn.add_argument(
        "--min-seconds",
        type=float,
        default=0.0,
        metavar="N",
        help="单轮时长下限（秒），默认 0 不过滤",
    )

    # phase 时长口径
    g_phase_dur = parser.add_argument_group("phase 真实耗时口径")
    g_phase_dur.add_argument(
        "--gap-threshold-minutes",
        type=float,
        default=30.0,
        metavar="N",
        help=(
            "相邻消息间隔超过此值（分钟）视为用户离开，phase 时长按会话分段累加。"
            "默认 30 分钟。设为很大的值（如 999999）等价于「首条→末条」整体跨度。"
        ),
    )

    # 输出
    g_out = parser.add_argument_group("输出")
    g_out.add_argument(
        "--show-detail",
        action="store_true",
        help="输出每份 report 的逐条明细（默认只输出聚合报表）",
    )
    g_out.add_argument(
        "--show-skipped",
        action="store_true",
        help="列出被过滤的具体 phase / 报告",
    )

    return parser


def _resolve_source(source: Optional[str]) -> Tuple[str, str]:
    """
    解析数据源。返回 (mode, path)。

    mode:
        - 'zip': 读 zip 文件
        - 'dir': 扫目录
    """
    if source is None:
        # 不传参数 -> 默认扫 data/simple/reports
        return ("dir", str(_DEFAULT_REPORTS_DIR))

    p = Path(source)
    if p.is_file() and source.endswith(".zip"):
        return ("zip", source)
    if p.is_dir():
        return ("dir", source)

    # 既不是 zip 也不是目录，报错
    raise SystemExit(
        f"错误：'{source}' 既不是 zip 文件也不是目录。\n"
        f"用法：python scripts/conversation_stats.py [zip文件 | 目录路径]\n"
        f"不传参数则默认扫 {_DEFAULT_REPORTS_DIR}"
    )


def main(argv: List[str]) -> int:
    """命令行入口。"""
    parser = _build_parser()
    args = parser.parse_args(argv[1:])

    mode, path = _resolve_source(args.source)

    if mode == "zip":
        try:
            raw_files = _iter_raw_files_from_zip(path)
        except zipfile.BadZipFile as e:
            print(f"错误：zip 文件损坏: {e}", file=sys.stderr)
            return 1

        if not raw_files:
            print(
                "错误：zip 中未找到 raw/*.json 文件。"
                "请确认这是 BatchExportService 导出的 zip，"
                "且 zip 版本包含 report_step_locked 字段（旧版本需重新导出）。",
                file=sys.stderr,
            )
            return 1

        reports = _group_by_report(raw_files)
        print(f"[zip 模式] {path}")
    else:
        reports = _load_from_dir(path)
        if not reports:
            print(
                f"错误：目录 {path} 下未找到有效的 report。",
                file=sys.stderr,
            )
            return 1
        print(f"[目录扫描] {path}")

    print(f"共发现 {len(reports)} 份报告\n")

    all_stats: List[Dict[str, Any]] = []
    filtered_reports: List[Tuple[str, str]] = []

    # 按 report_id 排序保证输出稳定
    for report_id in sorted(reports.keys()):
        steps = reports[report_id]
        passed, reason = _filter_report_level(report_id, steps, args)
        if not passed:
            filtered_reports.append((report_id, reason))
            if args.show_skipped:
                print(f"[过滤] 报告 {report_id}: {reason}")
            continue

        stats = _compute_report_stats(report_id, steps, args)
        all_stats.append(stats)
        if args.show_detail:
            _print_detail_report(stats, args)

    _print_aggregate_report(all_stats, args, filtered_reports, len(reports))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
