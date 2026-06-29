"""
BatchExportService 单元测试：
- report 5 phase 全完成 / 仅 3 phase 完成 -> 章节数正确
- report 不存在 -> 返回 None（跳过）
- md / txt 两种格式
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List
from unittest.mock import AsyncMock, patch

import pytest
from app.services.batch_export_service import PHASE_LABEL_CN, BatchExportService
from app.utils.report_registry import STEP_IDS, ReportRegistry


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
    for sid in STEP_IDS:
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


def _mock_collect_export_data(user_id: str, session_id: str) -> dict:
    """模拟 ExportService.collect_export_data 的返回（不依赖 DB）。"""
    return {
        "export_time": "2026-01-01T00:00:00",
        "user": {
            "user_id": user_id,
            "email": "test@example.com",
            "username": "测试用户",
        },
        "session": {
            "session_id": session_id,
            "status": "completed",
            "created_at": "2026-01-01T00:00:00",
        },
        "conversation_history": {
            f"cat__{session_id}": [
                {
                    "role": "user",
                    "content": f"hello-{session_id}",
                    "created_at": "2026-01-01T00:01:00",
                },
                {
                    "role": "assistant",
                    "content": f"reply-{session_id}",
                    "created_at": "2026-01-01T00:01:05",
                },
            ]
        },
    }


@pytest.fixture
def batch_service(tmp_path: Path) -> BatchExportService:
    """构造一个用 tmp 目录的 BatchExportService。"""
    base = tmp_path / "simple"
    base.mkdir(parents=True, exist_ok=True)
    svc = BatchExportService()
    # 覆盖 registry 的 base_dir
    svc.registry = ReportRegistry(base_dir=str(base))
    return svc


@pytest.mark.asyncio
async def test_collect_report_export_5_phases_md(
    batch_service: BatchExportService,
) -> None:
    """5 phase 全完成 -> md 文件含 5 个章节标题。"""
    root = batch_service.registry.simple_base_dir
    rid = "rpt-full-5"
    selected = {sid: f"sess-{sid}" for sid in STEP_IDS}
    record = _make_record(rid, selected_sessions=selected)
    _write_record(root, rid, record)

    with patch.object(
        batch_service.export_service,
        "collect_export_data",
        new=AsyncMock(side_effect=_mock_collect_export_data),
    ):
        result = await batch_service.collect_report_export(rid, "md")

    assert result is not None
    filename, content = result
    assert filename == "report_rpt-full-5.md"
    # 5 个 phase 章节标题
    for i, sid in enumerate(STEP_IDS, start=1):
        label = PHASE_LABEL_CN[sid]
        assert f"## {i}. {label}（{sid}）" in content
    # 文件头
    assert "# 寻录探索报告 - rpt-full-5" in content
    assert "用户ID: user-test" in content


@pytest.mark.asyncio
async def test_collect_report_export_3_phases_txt(
    batch_service: BatchExportService,
) -> None:
    """仅 3 phase 完成（values/strengths/interests）-> txt 文件含 3 个章节，序号 1-3。"""
    root = batch_service.registry.simple_base_dir
    rid = "rpt-partial-3"
    selected = {
        "values": "sess-v",
        "strengths": "sess-s",
        "interests": "sess-i",
    }
    record = _make_record(rid, selected_sessions=selected)
    _write_record(root, rid, record)

    with patch.object(
        batch_service.export_service,
        "collect_export_data",
        new=AsyncMock(side_effect=_mock_collect_export_data),
    ):
        result = await batch_service.collect_report_export(rid, "txt")

    assert result is not None
    filename, content = result
    assert filename == "report_rpt-partial-3.txt"
    # 3 个 phase 章节标题（txt 格式无 ##）
    assert "1. 价值观（values）" in content
    assert "2. 优势（strengths）" in content
    assert "3. 热爱（interests）" in content
    # 未完成的 phase 不出现
    assert "使命（purpose）" not in content
    assert "沉淀（rumination）" not in content
    # 文件头（txt 无 # 前缀）
    assert "寻录探索报告 - rpt-partial-3" in content


@pytest.mark.asyncio
async def test_collect_report_export_not_exist(
    batch_service: BatchExportService,
) -> None:
    """report 不存在 -> 返回 None。"""
    result = await batch_service.collect_report_export("nonexistent-id", "md")
    assert result is None


@pytest.mark.asyncio
async def test_collect_report_export_zero_phases(
    batch_service: BatchExportService,
) -> None:
    """所有 phase 均未完成 -> 文件仅含头部 + 提示行。"""
    root = batch_service.registry.simple_base_dir
    rid = "rpt-empty"
    record = _make_record(rid, selected_sessions={})
    _write_record(root, rid, record)

    result = await batch_service.collect_report_export(rid, "md")
    assert result is not None
    _, content = result
    assert "（本报告暂无已完成的探索阶段）" in content
    # 无 phase 章节标题
    for sid in STEP_IDS:
        assert f"（{sid}）" not in content
