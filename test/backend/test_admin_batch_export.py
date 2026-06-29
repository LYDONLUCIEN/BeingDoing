"""
POST /admin/reports/export/batch 路由测试：
- 非 super_admin -> 403
- 51 个 report -> 400
- 2 个 report（一个 5 phase、一个 3 phase）-> zip 内 2 文件
- 不存在的 report_id -> 跳过，其他正常
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Dict
from unittest.mock import AsyncMock, patch

import pytest
from app.api.v1.auth import get_current_user
from app.main import app
from app.services.batch_export_service import BatchExportService
from app.utils.report_registry import STEP_IDS, ReportRegistry
from fastapi.testclient import TestClient


def _write_record(root: Path, report_id: str, payload: dict) -> None:
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
    return {
        "export_time": "2026-01-01T00:00:00",
        "user": {"user_id": user_id, "email": "test@example.com", "username": "测试"},
        "session": {
            "session_id": session_id,
            "status": "completed",
            "created_at": "2026-01-01T00:00:00",
        },
        "conversation_history": {
            f"cat__{session_id}": [
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
            ]
        },
    }


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
    # 确保 admin 用户在配置中
    _override_auth(is_admin=True)
    with patch("app.api.v1.admin._is_super_admin", return_value=True):
        yield TestClient(app)


def test_batch_export_non_super_admin_403():
    """非 super_admin -> 403。"""
    _override_auth(is_admin=False)
    with patch("app.api.v1.admin._is_super_admin", return_value=False):
        client = TestClient(app)
        resp = client.post(
            "/admin/reports/export/batch",
            json={"report_ids": ["r1"], "format": "md"},
        )
    assert resp.status_code == 403


def test_batch_export_over_50_returns_400(admin_client):
    """51 个 report -> 400。"""
    ids = [f"r{i}" for i in range(51)]
    resp = admin_client.post(
        "/admin/reports/export/batch",
        json={"report_ids": ids, "format": "md"},
    )
    assert resp.status_code == 400
    assert "单次最多导出 50 个" in resp.json()["detail"]


def test_batch_export_empty_ids_returns_400(admin_client):
    """空 report_ids -> 400。"""
    resp = admin_client.post(
        "/admin/reports/export/batch",
        json={"report_ids": [], "format": "md"},
    )
    assert resp.status_code == 400


def test_batch_export_invalid_format_returns_400(admin_client):
    """非法 format -> 400。"""
    resp = admin_client.post(
        "/admin/reports/export/batch",
        json={"report_ids": ["r1"], "format": "pdf"},
    )
    assert resp.status_code == 400


def test_batch_export_two_reports_zip(admin_client, tmp_path: Path):
    """2 个 report（5 phase + 3 phase）-> zip 内 2 文件，章节数正确。"""
    # 准备 ReportRegistry 数据
    base = tmp_path / "simple"
    base.mkdir(parents=True, exist_ok=True)
    registry = ReportRegistry(base_dir=str(base))

    rid_full = "rpt-full-5"
    selected_full = {sid: f"sess-full-{sid}" for sid in STEP_IDS}
    _write_record(
        base, rid_full, _make_record(rid_full, selected_sessions=selected_full)
    )

    rid_partial = "rpt-partial-3"
    selected_partial = {
        "values": "sess-p-v",
        "strengths": "sess-p-s",
        "interests": "sess-p-i",
    }
    _write_record(
        base, rid_partial, _make_record(rid_partial, selected_sessions=selected_partial)
    )

    # Mock BatchExportService 的 registry 指向 tmp_path，collect_export_data 走 mock
    def _patch_service():
        svc = BatchExportService()
        svc.registry = ReportRegistry(base_dir=str(base))
        svc.export_service.collect_export_data = AsyncMock(
            side_effect=_mock_collect_export_data
        )
        return svc

    with patch("app.api.v1.admin.BatchExportService", side_effect=_patch_service):
        resp = admin_client.post(
            "/admin/reports/export/batch",
            json={"report_ids": [rid_full, rid_partial], "format": "md"},
        )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"

    # 解压 zip 验证
    buf = io.BytesIO(resp.content)
    with zipfile.ZipFile(buf) as zf:
        names = zf.namelist()
        assert len(names) == 2
        assert "report_rpt-full-5.md" in names
        assert "report_rpt-partial-3.md" in names

        full_content = zf.read("report_rpt-full-5.md").decode("utf-8")
        partial_content = zf.read("report_rpt-partial-3.md").decode("utf-8")

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
    _write_record(
        base,
        rid_valid,
        _make_record(rid_valid, selected_sessions={"values": "sess-v"}),
    )

    def _patch_service():
        svc = BatchExportService()
        svc.registry = ReportRegistry(base_dir=str(base))
        svc.export_service.collect_export_data = AsyncMock(
            side_effect=_mock_collect_export_data
        )
        return svc

    with patch("app.api.v1.admin.BatchExportService", side_effect=_patch_service):
        resp = admin_client.post(
            "/admin/reports/export/batch",
            json={"report_ids": [rid_valid, "nonexistent-id"], "format": "md"},
        )

    assert resp.status_code == 200
    buf = io.BytesIO(resp.content)
    with zipfile.ZipFile(buf) as zf:
        names = zf.namelist()
        # 仅有效 report 一个文件
        assert len(names) == 1
        assert "report_rpt-valid.md" in names


def test_batch_export_all_nonexistent_returns_404(admin_client):
    """全部 report_id 不存在 -> 404。"""
    with patch("app.api.v1.admin.BatchExportService") as MockSvc:
        svc = MockSvc.return_value
        svc.collect_report_export = AsyncMock(return_value=None)
        resp = admin_client.post(
            "/admin/reports/export/batch",
            json={"report_ids": ["ghost1", "ghost2"], "format": "md"},
        )
    assert resp.status_code == 404
