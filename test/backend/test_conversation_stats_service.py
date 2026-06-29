"""
ConversationStatsService 及离线解析器单元测试（T3）。

测试要点：
1. 12 轮、总 102 分钟 -> avg 8.5 分钟
2. 缺时间戳的消息 -> 跳过该轮且 warning
3. 跨 phase 异常长时长(>2h) -> 过滤或标注
4. 离线脚本解析 T1 导出格式 -> 输出正确统计
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List
from unittest.mock import AsyncMock, patch

import pytest
from app.services.conversation_stats_service import (
    PHASE_LABEL_CN,
    ConversationStatsService,
    compute_turn_stats_from_messages,
)

# ── 辅助函数 ────────────────────────────────────────────────────


def _ts(minutes: int, base_minute: int = 0) -> str:
    """生成 ISO 时间戳（从 2026-01-01T00:00:00 起加 minutes 分钟）。"""
    base = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    dt = base + timedelta(minutes=minutes + base_minute)
    return dt.isoformat()


def _make_user_turn(
    user_ts: str,
    assistant_ts: str | None = None,
    user_idx: int = 0,
) -> List[Dict]:
    """构造一轮对话（user 消息 + 可选 assistant 消息）。"""
    msgs = [{"role": "user", "content": f"用户消息{user_idx}", "created_at": user_ts}]
    if assistant_ts:
        msgs.append(
            {
                "role": "assistant",
                "content": f"回复{user_idx}",
                "created_at": assistant_ts,
            }
        )
    return msgs


def _write_record(root: Path, report_id: str, payload: dict) -> None:
    """写一份 record.json 到指定 root/reports/{report_id}/record.json。"""
    d = root / "reports" / report_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "record.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _make_record(
    report_id: str,
    activation_code: str = "TESTCODE",
    user_id: str = "user-test",
    selected_sessions: Dict[str, str] | None = None,
) -> dict:
    """构造一份 record，selected_sessions 指定哪些 phase 选中哪个 session_id。"""
    ts = "2026-01-01T00:00:00Z"
    steps = {}
    for sid in ["values", "strengths", "interests", "purpose", "rumination"]:
        sess = (selected_sessions or {}).get(sid)
        steps[sid] = {
            "step_id": sid,
            "selected_session_id": sess,
            "locked": bool(sess),
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


# ── 公共函数测试 ────────────────────────────────────────────────


def test_12_turns_102_minutes_avg_8_5() -> None:
    """12 轮、总 102 分钟 -> avg 8.5 分钟。"""
    # 构造 12 轮 user 消息，间隔总计 102 分钟
    # 每轮间隔：8.5 分钟 = 510 秒
    # 12 轮之间有 11 个间隔 -> 11 * 8.5 = 93.5 分钟（不对）
    # 重新设计：12 轮，每轮时长（=到下一轮 user 的间隔）合计 102 分钟
    # 最后一轮用 assistant 收尾
    messages: List[Dict] = []
    # 前 11 轮：每轮时长 = 下一轮起点 - 本轮起点
    # 最后一轮：用 assistant 收尾
    # 目标：总时长 102 分钟，12 轮 -> avg = 102/12 = 8.5
    # 前 11 轮间隔 + 最后一轮 assistant 收尾 = 102 分钟
    # 简化：每轮间隔 = 8 分钟（前 11 轮），最后一轮 14 分钟（assistant 收尾）
    # 11*8 + 14 = 88 + 14 = 102 ✓
    base = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    for i in range(12):
        # user 消息
        user_min = i * 8 if i < 11 else 11 * 8  # 0, 8, 16, ..., 80, 88
        user_dt = base + timedelta(minutes=user_min)
        messages.append(
            {"role": "user", "content": f"问{i}", "created_at": user_dt.isoformat()}
        )

        if i < 11:
            # assistant 回复，在第 i+1 轮之前
            asst_dt = base + timedelta(minutes=user_min + 7)
            messages.append(
                {
                    "role": "assistant",
                    "content": f"答{i}",
                    "created_at": asst_dt.isoformat(),
                }
            )
        else:
            # 最后一轮的 assistant（收尾），14 分钟后
            asst_dt = base + timedelta(minutes=user_min + 14)
            messages.append(
                {
                    "role": "assistant",
                    "content": f"答{i}",
                    "created_at": asst_dt.isoformat(),
                }
            )

    stats = compute_turn_stats_from_messages(messages)

    assert stats["turns"] == 12
    # 前 11 轮各 8 分钟 = 88 分钟 = 5280 秒
    # 最后一轮 14 分钟 = 840 秒
    # 总计 = 6120 秒 = 102 分钟
    expected_total = 11 * 8 * 60 + 14 * 60  # 6120 秒
    assert abs(stats["total_seconds"] - expected_total) < 1.0
    avg_minutes = stats["total_seconds"] / 60.0 / stats["turns"]
    assert abs(avg_minutes - 8.5) < 0.01


def test_missing_timestamp_skipped() -> None:
    """缺时间戳的消息 -> 跳过该轮且 warning。"""
    messages = [
        {"role": "user", "content": "问0", "created_at": _ts(0)},
        {"role": "assistant", "content": "答0", "created_at": _ts(1)},
        # 第二轮 user 消息缺时间戳
        {"role": "user", "content": "问1", "created_at": None},
        {"role": "assistant", "content": "答1", "created_at": _ts(2)},
        # 第三轮正常
        {"role": "user", "content": "问2", "created_at": _ts(5)},
        {"role": "assistant", "content": "答2", "created_at": _ts(6)},
    ]
    stats = compute_turn_stats_from_messages(messages)

    # 缺时间戳的轮跳过
    assert stats["skipped_no_ts"] == 1
    # 有效轮数：第0轮(0->5分钟=300s) + 第2轮(5分钟->无下一轮,assistant收尾=1分钟=60s) = 2轮
    assert stats["turns"] == 2


def test_abnormal_long_duration_filtered() -> None:
    """跨 phase 异常长时长(>2h) -> 过滤。"""
    messages = [
        {"role": "user", "content": "问0", "created_at": _ts(0)},
        {"role": "assistant", "content": "答0", "created_at": _ts(1)},
        # 下一轮间隔 > 2 小时（7200s）
        {"role": "user", "content": "问1", "created_at": _ts(180)},  # 3 小时后
        {"role": "assistant", "content": "答1", "created_at": _ts(181)},
        # 正常的下一轮
        {"role": "user", "content": "问2", "created_at": _ts(185)},
        {"role": "assistant", "content": "答2", "created_at": _ts(186)},
    ]
    stats = compute_turn_stats_from_messages(messages)

    # 第0轮 -> 第1轮：180 分钟（异常，跳过）
    assert stats["skipped_long_turns"] >= 1
    # 第1轮 -> 第2轮：5 分钟（正常）
    assert stats["turns"] >= 1


def test_empty_messages() -> None:
    """空消息列表 -> 全零。"""
    stats = compute_turn_stats_from_messages([])
    assert stats["turns"] == 0
    assert stats["total_seconds"] == 0.0


def test_no_user_messages() -> None:
    """无 user 消息 -> 全零。"""
    messages = [
        {"role": "assistant", "content": "你好", "created_at": _ts(0)},
    ]
    stats = compute_turn_stats_from_messages(messages)
    assert stats["turns"] == 0


# ── Service 层测试（mock ExportService） ────────────────────────


@pytest.fixture
def stats_service(tmp_path: Path) -> ConversationStatsService:
    """构造一个用 tmp 目录的 ConversationStatsService。"""
    from app.utils.report_registry import ReportRegistry

    base = tmp_path / "simple"
    base.mkdir(parents=True, exist_ok=True)
    svc = ConversationStatsService()
    svc.registry = ReportRegistry(base_dir=str(base))
    return svc


def _mock_collect_export_data_12_turns(user_id: str, session_id: str) -> dict:
    """模拟 ExportService.collect_export_data 返回 12 轮对话（总 102 分钟）。"""
    messages: List[Dict] = []
    base = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    for i in range(12):
        user_min = i * 8 if i < 11 else 11 * 8
        user_dt = base + timedelta(minutes=user_min)
        messages.append(
            {"role": "user", "content": f"问{i}", "created_at": user_dt.isoformat()}
        )
        if i < 11:
            asst_dt = base + timedelta(minutes=user_min + 7)
            messages.append(
                {
                    "role": "assistant",
                    "content": f"答{i}",
                    "created_at": asst_dt.isoformat(),
                }
            )
        else:
            asst_dt = base + timedelta(minutes=user_min + 14)
            messages.append(
                {
                    "role": "assistant",
                    "content": f"答{i}",
                    "created_at": asst_dt.isoformat(),
                }
            )

    return {
        "session": {
            "session_id": session_id,
            "status": "completed",
            "created_at": "2026-01-01T00:00:00",
        },
        "conversation_history": {f"cat__{session_id}": messages},
    }


@pytest.mark.asyncio
async def test_compute_by_report_12_turns(
    stats_service: ConversationStatsService,
) -> None:
    """report 统计：12 轮、总 102 分钟 -> avg 8.5 分钟。"""
    root = stats_service.registry.simple_base_dir
    rid = "rpt-12turns"
    selected = {"values": "sess-v"}
    record = _make_record(rid, selected_sessions=selected)
    _write_record(root, rid, record)

    with patch.object(
        stats_service.export_service,
        "collect_export_data",
        new=AsyncMock(side_effect=_mock_collect_export_data_12_turns),
    ):
        result = await stats_service.compute_by_report(rid)

    assert result["per_phase"][0]["phase_id"] == "values"
    assert result["per_phase"][0]["turns"] == 12
    assert abs(result["total_minutes"] - 102.0) < 0.1
    assert abs(result["avg_minutes"] - 8.5) < 0.1
    assert "12 轮对话" in result["reminder_text"]
    assert "8.5 分钟" in result["reminder_text"]


@pytest.mark.asyncio
async def test_compute_by_report_not_exist(
    stats_service: ConversationStatsService,
) -> None:
    """report 不存在 -> 返回空统计。"""
    result = await stats_service.compute_by_report("nonexistent")
    assert result["total_turns"] == 0
    assert "不存在" in result["reminder_text"]


@pytest.mark.asyncio
async def test_compute_by_user(stats_service: ConversationStatsService) -> None:
    """user 统计：聚合该用户所有 report。"""
    root = stats_service.registry.simple_base_dir
    rid = "rpt-user1"
    record = _make_record(
        rid, user_id="user-agg", selected_sessions={"values": "sess-v"}
    )
    _write_record(root, rid, record)

    with patch.object(
        stats_service.export_service,
        "collect_export_data",
        new=AsyncMock(side_effect=_mock_collect_export_data_12_turns),
    ):
        result = await stats_service.compute_by_user("user-agg")

    assert result["total_turns"] == 12
    assert abs(result["avg_minutes"] - 8.5) < 0.1


# ── 离线脚本解析测试 ────────────────────────────────────────────


def test_parse_export_file_md_12_turns() -> None:
    """离线解析 T1 导出 md 文件 -> 12 轮、102 分钟。"""
    # 构造一个 T1 格式的 md 文件内容
    base = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    lines: List[str] = []
    lines.append("# 寻录探索报告 - rpt-offline-12")
    lines.append("=" * 30)
    lines.append("用户ID: user-offline")
    lines.append("邮箱: 未提供")
    lines.append("用户名: 未提供")
    lines.append("激活码: OFFLINE")
    lines.append("导出时间: 2026-01-01 12:00:00")
    lines.append("报告ID: rpt-offline-12")
    lines.append("")
    lines.append("-" * 20)
    lines.append("")

    # values phase
    lines.append("## 1. 价值观（values）")
    lines.append("")
    lines.append("  - 会话ID: sess-v")
    lines.append("  - 会话状态: completed")
    lines.append("  - 创建时间: 2026-01-01T00:00:00")
    lines.append("")

    for i in range(12):
        user_min = i * 8 if i < 11 else 11 * 8
        user_dt = base + timedelta(minutes=user_min)
        lines.append(f"**[用户]** {user_dt.isoformat()}")
        lines.append(f"问{i}")
        lines.append("")
        if i < 11:
            asst_dt = base + timedelta(minutes=user_min + 7)
        else:
            asst_dt = base + timedelta(minutes=user_min + 14)
        lines.append(f"**[助手]** {asst_dt.isoformat()}")
        lines.append(f"答{i}")
        lines.append("")

    content = "\n".join(lines)

    # 加入 scripts 目录到 path
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    from conversation_stats import compute_report_stats_from_parsed, parse_export_file

    report_id, meta, phases = parse_export_file(content, "report_rpt-offline-12.md")
    assert report_id == "rpt-offline-12"
    assert meta["用户ID"] == "user-offline"
    assert len(phases) == 1
    assert phases[0]["phase_id"] == "values"
    assert len(phases[0]["messages"]) == 24  # 12 user + 12 assistant

    stats = compute_report_stats_from_parsed(report_id, meta, phases)
    assert stats["per_phase"][0]["turns"] == 12
    assert abs(stats["total_minutes"] - 102.0) < 0.1
    assert abs(stats["avg_minutes"] - 8.5) < 0.1


def test_parse_export_file_txt() -> None:
    """离线解析 txt 格式。"""
    lines: List[str] = []
    lines.append("寻录探索报告 - rpt-txt")
    lines.append("=" * 30)
    lines.append("用户ID: user-txt")
    lines.append("邮箱: 未提供")
    lines.append("用户名: 未提供")
    lines.append("激活码: TXT")
    lines.append("导出时间: 2026-01-01 12:00:00")
    lines.append("报告ID: rpt-txt")
    lines.append("")
    lines.append("-" * 20)
    lines.append("")

    lines.append("1. 价值观（values）")
    lines.append("-" * 12)
    lines.append("  - 会话ID: sess-v")
    lines.append("  - 会话状态: completed")
    lines.append("  - 创建时间: 2026-01-01T00:00:00")
    lines.append("")

    base = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    # 2 轮
    lines.append(f"[用户] {base.isoformat()}")
    lines.append("问0")
    lines.append("")
    lines.append(f"[助手] {(base + timedelta(minutes=5)).isoformat()}")
    lines.append("答0")
    lines.append("")
    lines.append(f"[用户] {(base + timedelta(minutes=10)).isoformat()}")
    lines.append("问1")
    lines.append("")
    lines.append(f"[助手] {(base + timedelta(minutes=13)).isoformat()}")
    lines.append("答1")
    lines.append("")

    content = "\n".join(lines)

    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    from conversation_stats import parse_export_file

    report_id, meta, phases = parse_export_file(content, "report_rpt-txt.txt")
    assert report_id == "rpt-txt"
    assert len(phases) == 1
    assert len(phases[0]["messages"]) == 4  # 2 user + 2 assistant
