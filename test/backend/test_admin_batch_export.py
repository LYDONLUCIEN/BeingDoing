"""
POST /api/v1/admin/reports/export/batch 路由测试：
- 非 super_admin -> 403
- 51 个 report -> 400
- 2 个 report（一个 5 phase、一个 3 phase）-> zip 内两个 report 子目录，md 章节正确
- 不存在的 report_id -> 跳过（_skipped.txt），其他正常
- 全部不存在 -> 404

说明（2026-10-06 重写）：早期版本 mock 了 BatchExportService 的内部结构
（export_service.collect_export_data），与现行实现早已漂移。现改为把
batch_export_service 模块内的 ReportRegistry 重定向到 tmp 目录，跑**真实**
service 的集成路径（含 raw 全量会话打包与 report_markdown.md 附带）。
"""

from __future__ import annotations

import io
import json
import zipfile
from functools import partial
from pathlib import Path
from typing import Dict
from unittest.mock import patch

import pytest
from app.api.v1.auth import get_current_user
from app.main import app
from app.utils.report_registry import STEP_IDS, ReportRegistry
from fastapi.testclient import TestClient


def _write_record(root: Path, report_id: str, payload: dict) -> None:
    d = root / "reports" / report_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "record.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _write_step_session(
    root: Path, report_id: str, step_id: str, session_id: str
) -> None:
    """写 {step}__{session}.json 会话源文件（含最小 messages 与结论）。"""
    d = root / "reports" / report_id
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session_id,
        "messages": [
            {
                "role": "user",
                "content": f"u-{session_id}",
                "created_at": "2026-01-01T00:01:00",
            },
            {
                "role": "assistant",
                "content": f"a-{session_id}",
                "created_at": "2026-01-01T00:01:05",
            },
        ],
        "metadata": {"conclusion_final": f"结论-{session_id}"},
    }
    (d / f"{step_id}__{session_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _make_record(
    report_id: str,
    activation_code: str = "TESTCODE",
    user_id: str = "user-test",
    selected_sessions: Dict[str, str] | None = None,
) -> dict:
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


def _patch_registry(base: Path):
    """把 batch_export_service 模块内实例化的 ReportRegistry 重定向到 tmp 目录。"""
    return patch(
        "app.services.batch_export_service.ReportRegistry",
        partial(ReportRegistry, base_dir=str(base)),
    )


def _override_auth(is_admin: bool):
    """覆写 get_current_user 依赖。"""
    if is_admin:

        async def _admin_user():
            return {"user_id": "admin-1", "email": "admin@example.com"}

    else:

        async def _normal_user():
            return {"user_id": "normal-1", "email": "normal@example.com"}

    app.dependency_overrides[get_current_user] = (
        _admin_user if is_admin else _normal_user
    )


@pytest.fixture(autouse=True)
def _reset_auth():
    """每个测试后清理 dependency_overrides。"""
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def admin_client():
    """super_admin TestClient。"""
    _override_auth(is_admin=True)
    with patch("app.api.v1.admin._is_super_admin", return_value=True):
        yield TestClient(app)


def test_batch_export_non_super_admin_403():
    """非 super_admin -> 403。"""
    _override_auth(is_admin=False)
    with patch("app.api.v1.admin._is_super_admin", return_value=False):
        client = TestClient(app)
        resp = client.post(
            "/api/v1/admin/reports/export/batch",
            json={"report_ids": ["r1"], "format": "md"},
        )
    assert resp.status_code == 403


def test_batch_export_over_50_returns_400(admin_client):
    """51 个 report -> 400。"""
    ids = [f"r{i}" for i in range(51)]
    resp = admin_client.post(
        "/api/v1/admin/reports/export/batch",
        json={"report_ids": ids, "format": "md"},
    )
    assert resp.status_code == 400
    assert "50" in resp.json()["detail"]


def test_batch_export_two_reports_zip(admin_client, tmp_path: Path):
    """2 个 report（5 phase / 3 phase）-> zip 内两个子目录，md 章节正确。"""
    base = tmp_path / "simple"
    base.mkdir(parents=True, exist_ok=True)

    rid_full = "rpt-full-5"
    selected_full = {
        "values": "sess-f-v",
        "strengths": "sess-f-s",
        "interests": "sess-f-i",
        "purpose": "sess-f-p",
        "rumination": "sess-f-r",
    }
    _write_record(
        base, rid_full, _make_record(rid_full, selected_sessions=selected_full)
    )
    for sid, sess in selected_full.items():
        _write_step_session(base, rid_full, sid, sess)

    rid_partial = "rpt-partial-3"
    selected_partial = {
        "values": "sess-p-v",
        "strengths": "sess-p-s",
        "interests": "sess-p-i",
    }
    _write_record(
        base, rid_partial, _make_record(rid_partial, selected_sessions=selected_partial)
    )
    for sid, sess in selected_partial.items():
        _write_step_session(base, rid_partial, sid, sess)

    with _patch_registry(base):
        resp = admin_client.post(
            "/api/v1/admin/reports/export/batch",
            json={"report_ids": [rid_full, rid_partial], "format": "md"},
        )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"

    buf = io.BytesIO(resp.content)
    with zipfile.ZipFile(buf) as zf:
        names = zf.namelist()

        # 每 report 一个子目录：md + stats + rumination_tables + summary + raw 会话
        assert f"{rid_full}/report_{rid_full}.md" in names
        assert f"{rid_partial}/report_{rid_partial}.md" in names
        assert f"{rid_full}/stats.json" in names
        assert f"{rid_full}/raw/values__sess-f-v.json" in names
        # 3 phase 报告不含 purpose/rumination 的 raw
        assert not any(n.startswith(f"{rid_partial}/raw/purpose__") for n in names)

        full_content = zf.read(f"{rid_full}/report_{rid_full}.md").decode("utf-8")
        partial_content = zf.read(f"{rid_partial}/report_{rid_partial}.md").decode(
            "utf-8"
        )

        # 5 phase 报告：5 个章节标题
        for i, sid in enumerate(STEP_IDS, start=1):
            label_cn = {
                "values": "价值观",
                "strengths": "优势",
                "interests": "热爱",
                "purpose": "使命",
                "rumination": "沉淀",
            }[sid]
            assert f"## {i}. {label_cn}（{sid}）" in full_content

        # 3 phase 报告：3 个章节标题
        assert "## 1. 价值观（values）" in partial_content
        assert "## 2. 优势（strengths）" in partial_content
        assert "## 3. 热爱（interests）" in partial_content
        assert "使命（purpose）" not in partial_content
        assert "沉淀（rumination）" not in partial_content


def test_batch_export_nonexistent_report_skipped(admin_client, tmp_path: Path):
    """不存在的 report_id 被跳过，其他正常返回。"""
    base = tmp_path / "simple"
    base.mkdir(parents=True, exist_ok=True)

    rid_valid = "rpt-valid"
    selected = {"values": "sess-v"}
    _write_record(base, rid_valid, _make_record(rid_valid, selected_sessions=selected))
    _write_step_session(base, rid_valid, "values", "sess-v")

    with _patch_registry(base):
        resp = admin_client.post(
            "/api/v1/admin/reports/export/batch",
            json={"report_ids": [rid_valid, "nonexistent-id"], "format": "md"},
        )

    assert resp.status_code == 200
    buf = io.BytesIO(resp.content)
    with zipfile.ZipFile(buf) as zf:
        names = zf.namelist()
        assert f"{rid_valid}/report_{rid_valid}.md" in names
        # 跳过清单
        assert "_skipped.txt" in names
        assert zf.read("_skipped.txt").decode("utf-8") == "nonexistent-id"
        assert not any(n.startswith("nonexistent-id/") for n in names)


def test_batch_export_all_nonexistent_returns_404(admin_client, tmp_path: Path):
    """全部 report_id 不存在 -> 404。"""
    base = tmp_path / "simple"  # 空 registry
    base.mkdir(parents=True, exist_ok=True)
    with _patch_registry(base):
        resp = admin_client.post(
            "/api/v1/admin/reports/export/batch",
            json={"report_ids": ["ghost1", "ghost2"], "format": "md"},
        )
    assert resp.status_code == 404
