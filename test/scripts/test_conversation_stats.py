"""
离线统计脚本过滤逻辑单元测试。

覆盖：
- parse_raw_session：从 raw json 解析出 step_id / locked / user_id
- _filter_report_level：admin 排除 / 正则排除 / min-phases-locked / 无时间戳放弃
- _filter_phase_level：默认 require-locked / --include-unlocked 放开
- _compute_report_stats：时长阈值（max_minutes / min_seconds）生效
- _load_from_dir：目录扫描，含损坏 record.json 跳过 / 缺失 step 文件跳过
- _resolve_source：main 函数数据源自动判定（zip / 目录 / 默认）
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from typing import List

import pytest

# 把 scripts/ 加入 path（脚本本身不在包里）
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import conversation_stats as cs  # noqa: E402
from app.utils.report_registry import STEP_IDS  # noqa: E402


# ── 测试 fixtures ──────────────────────────────────────────────


def _make_raw_json(
    report_id: str,
    step_id: str,
    session_id: str,
    *,
    user_id: str = "user-test",
    locked: bool = True,
    is_selected: bool = True,
    messages: List[dict] = None,
) -> dict:
    """构造一份 raw json 字典（模拟 BatchExportService 导出格式）。"""
    return {
        "report_id": report_id,
        "category": f"{step_id}__{session_id}",
        "messages": messages
        or [
            {"role": "user", "content": "你好", "created_at": "2026-01-01T00:00:00Z"},
            {"role": "assistant", "content": "你好", "created_at": "2026-01-01T00:01:00Z"},
            {"role": "user", "content": "继续", "created_at": "2026-01-01T00:10:00Z"},
            {"role": "assistant", "content": "好的", "created_at": "2026-01-01T00:11:00Z"},
        ],
        "metadata": {},
        "report_user_id": user_id,
        "report_activation_code": "TESTCODE",
        "report_step_locked": locked,
        "report_step_is_selected": is_selected,
    }


def _build_zip(tmp_path: Path, raw_files: List[tuple]) -> str:
    """把 [(inner_path, dict), ...] 写成 zip，返回路径。"""
    zip_path = tmp_path / "export.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for inner_path, payload in raw_files:
            zf.writestr(inner_path, json.dumps(payload, ensure_ascii=False))
    return str(zip_path)


def _default_args(**overrides) -> argparse.Namespace:
    """构造默认 argparse Namespace（模拟命令行默认值）。"""
    ns = argparse.Namespace(
        exclude_user=[],
        exclude_user_regex=None,
        min_phases_locked=0,
        include_unlocked=False,
        max_minutes=120.0,
        min_seconds=0.0,
        show_skipped=False,
    )
    ns.__dict__.update(overrides)
    return ns


# ── parse_raw_session ─────────────────────────────────────────


def test_parse_raw_session_basic() -> None:
    """能从 category 字段解析 step_id，正确读取 locked。"""
    raw = _make_raw_json("rpt-1", "values", "sess-v", locked=True, user_id="u1")
    parsed = cs.parse_raw_session(raw, "raw/values__sess-v.json")
    assert parsed is not None
    assert parsed["step_id"] == "values"
    assert parsed["locked"] is True
    assert parsed["user_id"] == "u1"
    assert parsed["report_id"] == "rpt-1"


def test_parse_raw_session_filename_fallback() -> None:
    """category 缺失时从文件名反解 step_id。"""
    raw = _make_raw_json("rpt-1", "values", "sess-v")
    raw["category"] = ""  # 清空 category
    parsed = cs.parse_raw_session(raw, "raw/values__sess-v.json")
    assert parsed is not None
    assert parsed["step_id"] == "values"


def test_parse_raw_session_unknown_step_returns_none() -> None:
    """无法识别的 step_id 返回 None。"""
    raw = _make_raw_json("rpt-1", "values", "sess-v")
    raw["category"] = "unknown_step__xxx"
    parsed = cs.parse_raw_session(raw, "raw/unknown_step__xxx.json")
    assert parsed is None


# ── _filter_report_level ──────────────────────────────────────


def test_filter_report_no_timestamp_abandoned() -> None:
    """整份报告无任何时间戳 -> 放弃。"""
    steps = [
        {"user_id": "u1", "locked": True, "messages": [{"role": "user", "content": "x"}]},
    ]
    passed, reason = cs._filter_report_level("rpt", steps, _default_args())
    assert passed is False
    assert "无时间戳" in reason


def test_filter_report_exclude_user_exact() -> None:
    """--exclude-user 精确命中。"""
    steps = [
        {
            "user_id": "admin",
            "locked": True,
            "messages": [{"role": "user", "created_at": "2026-01-01T00:00:00Z"}],
        }
    ]
    args = _default_args(exclude_user=["admin"])
    passed, reason = cs._filter_report_level("rpt", steps, args)
    assert passed is False
    assert "admin" in reason


def test_filter_report_exclude_user_regex() -> None:
    """--exclude-user-regex 命中。"""
    steps = [
        {
            "user_id": "testuser01",
            "locked": True,
            "messages": [{"role": "user", "created_at": "2026-01-01T00:00:00Z"}],
        }
    ]
    args = _default_args(exclude_user_regex=r"^test.*")
    passed, reason = cs._filter_report_level("rpt", steps, args)
    assert passed is False
    assert "testuser01" in reason


def test_filter_report_min_phases_locked() -> None:
    """--min-phases-locked=5，但实际只有 2 个 locked -> 排除。"""
    steps = [
        {"user_id": "u1", "locked": True, "messages": [{"created_at": "2026-01-01T00:00:00Z"}]},
        {"user_id": "u1", "locked": True, "messages": [{"created_at": "2026-01-01T00:00:00Z"}]},
        {"user_id": "u1", "locked": False, "messages": []},
    ]
    args = _default_args(min_phases_locked=5)
    passed, reason = cs._filter_report_level("rpt", steps, args)
    assert passed is False
    assert "2" in reason and "5" in reason


def test_filter_report_passes_normal() -> None:
    """正常报告通过。"""
    steps = [
        {"user_id": "u1", "locked": True, "messages": [{"created_at": "2026-01-01T00:00:00Z"}]},
    ]
    passed, reason = cs._filter_report_level("rpt", steps, _default_args())
    assert passed is True


# ── _filter_phase_level ───────────────────────────────────────


def test_filter_phase_default_require_locked() -> None:
    """默认（--require-locked）：未 locked 的 phase 被过滤。"""
    step = {"locked": False}
    args = _default_args()
    passed, reason = cs._filter_phase_level(step, args)
    assert passed is False
    assert "未 locked" in reason


def test_filter_phase_include_unlocked() -> None:
    """--include-unlocked 放开未 locked phase。"""
    step = {"locked": False}
    args = _default_args(include_unlocked=True)
    passed, _ = cs._filter_phase_level(step, args)
    assert passed is True


def test_filter_phase_locked_passes() -> None:
    """locked=True 默认通过。"""
    step = {"locked": True}
    passed, _ = cs._filter_phase_level(step, _default_args())
    assert passed is True


def test_filter_phase_rumination_exempt_from_locked() -> None:
    """rumination 不要求 locked：只要有 selected session 就通过（即使 locked=False）。"""
    # rumination 有 selected，locked=False -> 通过
    step = {"step_id": "rumination", "locked": False, "is_selected": True, "session_id": "s1"}
    passed, reason = cs._filter_phase_level(step, _default_args())
    assert passed is True

    # rumination 无 selected -> 不通过
    step2 = {"step_id": "rumination", "locked": False, "is_selected": False}
    passed2, reason2 = cs._filter_phase_level(step2, _default_args())
    assert passed2 is False
    assert "rumination" in reason2


def test_filter_phase_rumination_locked_still_passes() -> None:
    """rumination locked=True 也通过（兼容）。"""
    step = {"step_id": "rumination", "locked": True, "is_selected": True}
    passed, _ = cs._filter_phase_level(step, _default_args())
    assert passed is True


# ── _compute_report_stats：时长阈值 ───────────────────────────


def test_compute_report_stats_max_minutes_filter() -> None:
    """--max-minutes=0.5（30秒）：一轮 10 分钟应被过滤。"""
    # 构造两轮 user 消息，间隔 10 分钟（600 秒）
    messages = [
        {"role": "user", "content": "q1", "created_at": "2026-01-01T00:00:00Z"},
        {"role": "assistant", "content": "a1", "created_at": "2026-01-01T00:01:00Z"},
        {"role": "user", "content": "q2", "created_at": "2026-01-01T00:10:00Z"},
        {"role": "assistant", "content": "a2", "created_at": "2026-01-01T00:11:00Z"},
    ]
    steps = [
        {
            "report_id": "rpt",
            "step_id": "values",
            "user_id": "u1",
            "locked": True,
            "messages": messages,
        }
    ]
    args = _default_args(max_minutes=0.5)  # 30 秒上限
    stats = cs._compute_report_stats("rpt", steps, args)
    # 那 10 分钟一轮应进 skipped_long_turns
    assert stats["skipped_long_turns"] >= 1
    assert stats["total_turns"] == 0


def test_compute_report_stats_min_seconds_filter() -> None:
    """--min-seconds=120：一轮 5 秒应被过滤。"""
    # 两轮 user 消息间隔 5 秒
    messages = [
        {"role": "user", "content": "q1", "created_at": "2026-01-01T00:00:00Z"},
        {"role": "assistant", "content": "a1", "created_at": "2026-01-01T00:00:03Z"},
        {"role": "user", "content": "q2", "created_at": "2026-01-01T00:00:05Z"},
        {"role": "assistant", "content": "a2", "created_at": "2026-01-01T00:00:08Z"},
    ]
    steps = [
        {
            "report_id": "rpt",
            "step_id": "values",
            "user_id": "u1",
            "locked": True,
            "messages": messages,
        }
    ]
    args = _default_args(min_seconds=120)  # 2 分钟下限
    stats = cs._compute_report_stats("rpt", steps, args)
    # 5 秒那轮应进 skipped_long_turns
    assert stats["skipped_long_turns"] >= 1


def test_compute_report_stats_normal_case() -> None:
    """正常场景：一轮 10 分钟被纳入统计。"""
    messages = [
        {"role": "user", "content": "q1", "created_at": "2026-01-01T00:00:00Z"},
        {"role": "assistant", "content": "a1", "created_at": "2026-01-01T00:01:00Z"},
        {"role": "user", "content": "q2", "created_at": "2026-01-01T00:10:00Z"},
        {"role": "assistant", "content": "a2", "created_at": "2026-01-01T00:11:00Z"},
    ]
    steps = [
        {
            "report_id": "rpt",
            "step_id": "values",
            "user_id": "u1",
            "locked": True,
            "messages": messages,
        }
    ]
    stats = cs._compute_report_stats("rpt", steps, _default_args())
    # 两条 user 消息 = 2 轮
    assert stats["total_turns"] == 2
    assert stats["skipped_long_turns"] == 0
    # 第一轮 10 分钟 = 600 秒；第二轮用 assistant 收尾约 60 秒
    assert stats["total_seconds"] >= 600.0


# ── 目录扫描：_load_from_dir ──────────────────────────────────


def _make_record_dict(
    report_id: str,
    user_id: str = "user-test",
    activation_code: str = "TESTCODE",
    steps_config: dict = None,
) -> dict:
    """
    构造一份 record 字典。

    steps_config: {step_id: {"selected": str|None, "locked": bool}}
    """
    ts = "2026-01-01T00:00:00Z"
    steps = {}
    for sid in STEP_IDS:
        cfg = (steps_config or {}).get(sid) or {}
        sess = cfg.get("selected")
        steps[sid] = {
            "step_id": sid,
            "selected_session_id": sess,
            "locked": cfg.get("locked", bool(sess)),
            "session_ids": [sess] if sess else [],
            "updated_at": ts,
        }
    return {
        "report_id": report_id,
        "activation_code": activation_code,
        "user_id": user_id,
        "created_at": ts,
        "updated_at": ts,
        "status": "in_progress",
        "final_conclusion": None,
        "steps": steps,
    }


def _write_report_to_dir(
    base: Path,
    report_id: str,
    record: dict,
    step_sessions: dict,
) -> None:
    """
    把一份 report 写到 base/{report_id}/ 下。

    step_sessions: {step_id: messages_list}，会写出 {step}__{session}.json
    """
    d = base / report_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "record.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for sid, messages in step_sessions.items():
        sess_id = record["steps"][sid]["selected_session_id"]
        payload = {
            "report_id": report_id,
            "category": f"{sid}__{sess_id}",
            "messages": messages,
            "metadata": {},
        }
        (d / f"{sid}__{sess_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def test_load_from_dir_basic(tmp_path: Path) -> None:
    """扫一个目录，含 1 份 report（2 个 phase locked），正确读出。"""
    base = tmp_path / "reports"
    base.mkdir()
    rid = "rpt-001"
    record = _make_record_dict(
        rid,
        user_id="u1",
        steps_config={
            "values": {"selected": "sess-v", "locked": True},
            "strengths": {"selected": "sess-s", "locked": True},
            "interests": {"selected": None},
        },
    )
    msgs_v = [
        {"role": "user", "content": "hi", "created_at": "2026-01-01T00:00:00Z"},
        {"role": "assistant", "content": "yo", "created_at": "2026-01-01T00:00:30Z"},
    ]
    msgs_s = [
        {"role": "user", "content": "hey", "created_at": "2026-01-01T01:00:00Z"},
        {"role": "assistant", "content": "yo", "created_at": "2026-01-01T01:00:30Z"},
    ]
    _write_report_to_dir(base, rid, record, {"values": msgs_v, "strengths": msgs_s})

    reports = cs._load_from_dir(str(base))
    assert rid in reports
    steps = reports[rid]
    # 只读 selected 的 phase -> 2 个 step（values, strengths）
    assert len(steps) == 2
    step_ids = [s["step_id"] for s in steps]
    assert "values" in step_ids
    assert "strengths" in step_ids
    # locked 状态从 record.json 正确读出
    v_step = next(s for s in steps if s["step_id"] == "values")
    assert v_step["locked"] is True
    assert v_step["user_id"] == "u1"
    # messages 内容正确
    assert len(v_step["messages"]) == 2


def test_load_from_dir_skips_corrupt_record(tmp_path: Path, capsys) -> None:
    """record.json 损坏 -> 跳过并打印警告。"""
    base = tmp_path / "reports"
    base.mkdir()
    # 写一份正常的
    rid_ok = "rpt-ok"
    record_ok = _make_record_dict(
        rid_ok,
        steps_config={"values": {"selected": "sess-v", "locked": True}},
    )
    _write_report_to_dir(
        base, rid_ok, record_ok,
        {"values": [{"role": "user", "created_at": "2026-01-01T00:00:00Z"}]},
    )
    # 写一份损坏的
    d_bad = base / "rpt-bad"
    d_bad.mkdir()
    (d_bad / "record.json").write_text("{这不是合法的json", encoding="utf-8")

    reports = cs._load_from_dir(str(base))

    # 损坏的被跳过，只留正常的
    assert "rpt-ok" in reports
    assert "rpt-bad" not in reports
    # 警告打印到 stderr
    captured = capsys.readouterr()
    assert "解析失败" in captured.err
    assert "rpt-bad" in captured.err


def test_load_from_dir_skips_missing_step_file(tmp_path: Path, capsys) -> None:
    """selected_session 文件缺失 -> 跳过该 step 并警告。"""
    base = tmp_path / "reports"
    base.mkdir()
    rid = "rpt-missing"
    record = _make_record_dict(
        rid,
        steps_config={
            "values": {"selected": "sess-v", "locked": True},
            "strengths": {"selected": "sess-s", "locked": True},
        },
    )
    # 只写 values 文件，故意不写 strengths 文件
    _write_report_to_dir(
        base, rid, record,
        {"values": [{"role": "user", "created_at": "2026-01-01T00:00:00Z"}]},
    )

    reports = cs._load_from_dir(str(base))
    assert rid in reports
    steps = reports[rid]
    # strengths 被跳过，只剩 values
    assert len(steps) == 1
    assert steps[0]["step_id"] == "values"
    captured = capsys.readouterr()
    assert "step session 文件缺失" in captured.err


def test_load_from_dir_empty(tmp_path: Path) -> None:
    """空目录 -> 返回空 dict。"""
    base = tmp_path / "empty"
    base.mkdir()
    reports = cs._load_from_dir(str(base))
    assert reports == {}


def test_load_from_dir_not_exist(tmp_path: Path) -> None:
    """目录不存在 -> 返回空 dict + 错误信息。"""
    reports = cs._load_from_dir(str(tmp_path / "nonexistent"))
    assert reports == {}


# ── main 数据源自动判定 ───────────────────────────────────────


def test_resolve_source_default(monkeypatch) -> None:
    """不传参数 -> 返回 ('dir', 默认路径)。"""
    mode, path = cs._resolve_source(None)
    assert mode == "dir"
    assert "data" in path and "reports" in path


def test_resolve_source_zip(tmp_path: Path) -> None:
    """传 zip 路径 -> 返回 ('zip', path)。"""
    zip_path = tmp_path / "test.zip"
    zip_path.write_bytes(b"")  # 创建空文件
    mode, path = cs._resolve_source(str(zip_path))
    assert mode == "zip"
    assert path == str(zip_path)


def test_resolve_source_dir(tmp_path: Path) -> None:
    """传目录 -> 返回 ('dir', path)。"""
    mode, path = cs._resolve_source(str(tmp_path))
    assert mode == "dir"
    assert path == str(tmp_path)


def test_resolve_source_invalid(tmp_path: Path) -> None:
    """传不存在的非 zip 路径 -> SystemExit。"""
    with pytest.raises(SystemExit):
        cs._resolve_source(str(tmp_path / "nonexistent-file.txt"))


# ── rumination 子 step 时长：_collect_rumination_step_durations ─


def test_collect_rumination_step_durations_basic() -> None:
    """正常快照：3 个子 step 都有 initial_at/submitted_at，正确算出时长。"""
    step_data = {
        "step_id": "rumination",
        "step_snapshots": {
            "1": {
                "initial": [{"id": "1"}],
                "submitted": [{"id": "1", "x": 1}],
                "initial_at": "2026-01-01T00:00:00Z",
                "submitted_at": "2026-01-01T00:10:00Z",  # 10 分钟
            },
            "2": {
                "initial": [],
                "submitted": [],
                "initial_at": "2026-01-01T00:10:00Z",
                "submitted_at": "2026-01-01T00:25:00Z",  # 15 分钟
            },
            "3": {
                "initial": [],
                "submitted": [],
                "initial_at": "2026-01-01T00:25:00Z",
                "submitted_at": "2026-01-01T00:40:00Z",  # 15 分钟
            },
        },
    }
    durations = cs._collect_rumination_step_durations(step_data)
    assert len(durations) == 3
    assert durations[0]["step"] == "1"
    assert abs(durations[0]["duration_seconds"] - 600) < 1  # 10 分钟
    assert durations[1]["step"] == "2"
    assert abs(durations[1]["duration_seconds"] - 900) < 1  # 15 分钟
    assert durations[2]["step"] == "3"


def test_collect_rumination_step_durations_skip_no_ts() -> None:
    """缺 submitted_at 的 step 被跳过；缺 initial_at 的 step 走兜底（用上个 submitted_at）。"""
    step_data = {
        "step_snapshots": {
            "1": {"initial": [], "submitted": [], "initial_at": "2026-01-01T00:00:00Z",
                  "submitted_at": "2026-01-01T00:10:00Z"},
            "2": {"initial": [], "submitted": [], "initial_at": None,
                  "submitted_at": "2026-01-01T00:25:00Z"},  # 缺 initial_at，兜底用 step1 的 submitted
            "3": {"initial": [], "submitted": []},  # 两个都缺，跳过
        }
    }
    durations = cs._collect_rumination_step_durations(step_data)
    # step 1 正常，step 2 走兜底（产出），step 3 完全跳过
    assert len(durations) == 2
    step_to_dur = {d["step"]: d for d in durations}
    assert step_to_dur["1"]["fallback"] is False
    assert step_to_dur["2"]["fallback"] is True
    assert step_to_dur["2"]["initial_at"] == "2026-01-01T00:10:00Z"  # 用了 step1 的 submitted


def test_collect_rumination_step_durations_skip_negative() -> None:
    """submitted_at 早于 initial_at（负时长）跳过。"""
    step_data = {
        "step_snapshots": {
            "1": {
                "initial_at": "2026-01-01T00:20:00Z",
                "submitted_at": "2026-01-01T00:10:00Z",  # 比 initial 早
            }
        }
    }
    durations = cs._collect_rumination_step_durations(step_data)
    assert durations == []


def test_collect_rumination_step_durations_fallback_prev_submitted() -> None:
    """旧数据兜底：initial_at 缺失时，用上一个 step 的 submitted_at 作为本 step 的 initial_at。"""
    step_data = {
        "step_snapshots": {
            # step 1: 两个都没有 -> 完全跳过，但 submitted_at 也没法兜底下个
            "1": {"initial": [], "submitted": []},
            # step 2: 只有 submitted_at（无 initial_at），作为第一个有 submitted 的 step，
            #         没法算时长，但 submitted_at 会作为 step 3 的兜底锚点
            "2": {"initial": [], "submitted": [], "submitted_at": "2026-01-01T00:10:00Z"},
            # step 3: 无 initial_at，用 step 2 的 submitted_at 兜底
            "3": {"initial": [], "submitted": [], "submitted_at": "2026-01-01T00:25:00Z"},  # 时长 15 分钟
            # step 4: 有完整 initial_at（新数据走正常路径）
            "4": {"initial": [], "submitted": [],
                  "initial_at": "2026-01-01T00:25:00Z",
                  "submitted_at": "2026-01-01T00:40:00Z"},  # 时长 15 分钟
        }
    }
    durations = cs._collect_rumination_step_durations(step_data)
    # step 1/2 都没产出，step 3/4 有产出
    assert len(durations) == 2
    step_to_dur = {d["step"]: d for d in durations}
    assert "3" in step_to_dur
    assert step_to_dur["3"]["fallback"] is True
    assert abs(step_to_dur["3"]["duration_seconds"] - 900) < 1  # 15 分钟
    assert "4" in step_to_dur
    assert step_to_dur["4"]["fallback"] is False  # 完整数据，不兜底
    assert abs(step_to_dur["4"]["duration_seconds"] - 900) < 1


def test_collect_rumination_step_durations_first_step_no_initial_skipped() -> None:
    """第一个 step 缺 initial_at 时无法兜底（没有上一个 submitted_at），跳过。"""
    step_data = {
        "step_snapshots": {
            "1": {"initial": [], "submitted": [],
                  "submitted_at": "2026-01-01T00:10:00Z"},  # 无 initial_at，是第一个
        }
    }
    durations = cs._collect_rumination_step_durations(step_data)
    assert durations == []


def test_collect_rumination_step_durations_empty() -> None:
    """无 step_snapshots -> 空。"""
    assert cs._collect_rumination_step_durations({}) == []
    assert cs._collect_rumination_step_durations({"step_snapshots": {}}) == []


# ── 跨 report 聚合：_aggregate_phases_across_reports ───────────


def test_aggregate_phases_basic() -> None:
    """2 份 report，values phase 都有数据，聚合出 avg/min/max。"""
    all_stats = [
        {"per_phase": [{"phase_id": "values", "turns": 10, "total_minutes": 20.0}]},
        {"per_phase": [{"phase_id": "values", "turns": 20, "total_minutes": 40.0}]},
    ]
    agg = cs._aggregate_phases_across_reports(all_stats)
    assert "values" in agg
    v = agg["values"]
    assert v["report_count"] == 2
    assert v["turns_list"] == [10, 20]
    assert v["turns_avg"] == 15.0
    assert v["turns_min"] == 10
    assert v["turns_max"] == 20
    assert v["minutes_avg"] == 30.0
    assert v["minutes_min"] == 20.0
    assert v["minutes_max"] == 40.0


def test_aggregate_phases_missing_phase() -> None:
    """某 phase 没数据 -> 不出现在聚合结果里。"""
    all_stats = [
        {"per_phase": [{"phase_id": "values", "turns": 5, "total_minutes": 10.0}]},
    ]
    agg = cs._aggregate_phases_across_reports(all_stats)
    assert "values" in agg
    assert "strengths" not in agg  # 没数据


def test_aggregate_phases_empty() -> None:
    """无数据 -> 空字典。"""
    assert cs._aggregate_phases_across_reports([]) == {}


# ── rumination step 跨 report 聚合 ────────────────────────────


def test_aggregate_rumination_steps_basic() -> None:
    """2 份 report，step 1 各有时长数据。"""
    all_stats = [
        {"rumination_step_durations": [
            {"step": "1", "duration_seconds": 600.0},
            {"step": "2", "duration_seconds": 900.0},
        ]},
        {"rumination_step_durations": [
            {"step": "1", "duration_seconds": 1200.0},
        ]},
    ]
    agg = cs._aggregate_rumination_steps_across_reports(all_stats)
    assert agg["1"] == [600.0, 1200.0]
    assert agg["2"] == [900.0]


# ── 端到端：rumination 子 step 时长从目录扫描到统计 ─────────


def test_e2e_rumination_step_durations_from_dir(tmp_path: Path) -> None:
    """
    端到端：构造 report 目录含 rumination_progress.json（带 initial_at/submitted_at），
    走 _load_from_dir -> _compute_report_stats，确认 rumination_step_durations 正确产出。
    """
    base = tmp_path / "reports"
    base.mkdir()
    rid = "rpt-rum-001"

    # record.json: rumination locked + selected
    record = _make_record_dict(
        rid,
        user_id="u-rum",
        steps_config={
            "rumination": {"selected": "sess-rum", "locked": True},
        },
    )
    # rumination session 文件
    sess_msgs = [
        {"role": "user", "content": "开始沉淀", "created_at": "2026-01-01T00:00:00Z"},
        {"role": "assistant", "content": "好的", "created_at": "2026-01-01T00:01:00Z"},
    ]
    _write_report_to_dir(base, rid, record, {"rumination": sess_msgs})

    # 额外写 rumination_progress.json（含 step 快照时间戳）
    prog = {
        "schema_version": 1,
        "filter_step": 3,
        "filter_step_snapshots": {
            "1": {
                "initial": [{"id": "1"}],
                "submitted": [{"id": "1", "x": 1}],
                "initial_at": "2026-01-01T00:00:00Z",
                "submitted_at": "2026-01-01T00:10:00Z",  # 10 分钟
            },
            "2": {
                "initial": [],
                "submitted": [],
                "initial_at": "2026-01-01T00:10:00Z",
                "submitted_at": "2026-01-01T00:30:00Z",  # 20 分钟
            },
        },
    }
    prog_path = base / rid / "rumination_progress.json"
    prog_path.write_text(json.dumps(prog, ensure_ascii=False, indent=2), encoding="utf-8")

    # 走 _load_from_dir
    reports = cs._load_from_dir(str(base))
    assert rid in reports
    rum_step = reports[rid][0]
    assert rum_step["step_id"] == "rumination"
    assert "step_snapshots" in rum_step

    # 走 _compute_report_stats
    args = _default_args()
    stats = cs._compute_report_stats(rid, reports[rid], args)
    rum_durations = stats.get("rumination_step_durations") or []
    assert len(rum_durations) == 2
    durations_by_step = {d["step"]: d["duration_seconds"] for d in rum_durations}
    assert abs(durations_by_step["1"] - 600) < 1
    assert abs(durations_by_step["2"] - 1200) < 1
