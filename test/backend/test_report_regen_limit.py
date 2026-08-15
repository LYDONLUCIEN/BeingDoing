"""
报告生成单轨锁 + 用户限量重新生成测试（2026-08-15）。

覆盖：
- 单轨锁：try_acquire/release/is_generation_inflight 基本语义；
  export 侧与 review 侧共用一份登记（inflight 时批复 kick 返回 False）
- 限量重新生成：普通用户 force 每份报告限 2 次（403 拦截）、admin 不限不计数、
  生成成功才 +1（_run_pdf_generation count_regen）、失败不扣次数
- 状态接口：regen_remaining 字段（普通用户剩余次数 / admin 为 null）；
  任务表残留 pending 但锁已释放时以缓存为准（不卡 generating）
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import export as export_mod
from app.api.v1.auth import get_current_user
from app.main import app
from app.services import report_review_service
from app.services.report_pdf_service import (
    ReportPdfService,
    is_generation_inflight,
    release_generation,
    try_acquire_generation,
)
from app.utils.report_registry import STEP_IDS, ReportRegistry


# ── 工具（与 test_report_review.py 同 pattern）────────────────

def _write_record(root: Path, report_id: str, payload: dict) -> None:
    d = root / "reports" / report_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "record.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _approved_record(report_id: str, regen_count: int = 0, with_cache: bool = False) -> dict:
    """五阶段完成 + 审核已通过 + 指定已用重新生成次数的报告。"""
    ts = "2026-01-01T00:00:00+00:00"
    rec = {
        "report_id": report_id,
        "activation_code": "CODE1",
        "user_id": "user-1",
        "created_at": ts,
        "updated_at": ts,
        "status": "in_progress",
        "final_conclusion": None,
        "steps": {
            sid: {
                "step_id": sid,
                "selected_session_id": f"sess-{sid}",
                "locked": True,
                "session_ids": [f"sess-{sid}"],
                "updated_at": ts,
            }
            for sid in STEP_IDS
        },
        "review_status": "approved",
        "review_deadline": None,
        "review_type": "manual",
        "reviewed_by": "admin",
        "reviewed_at": ts,
        "report_regen_count": regen_count,
    }
    if with_cache:
        # has_cached_markdown 依赖该时间戳（无则视为无缓存）
        rec["report_markdown_generated_at"] = ts
    return rec


@pytest.fixture
def reg(tmp_path: Path) -> ReportRegistry:
    base = tmp_path / "simple"
    base.mkdir(parents=True, exist_ok=True)
    return ReportRegistry(base_dir=str(base))


def _override_user(user_id: str = "user-1"):
    async def _u():
        return {"user_id": user_id, "email": "user@example.com"}

    app.dependency_overrides[get_current_user] = _u


@pytest.fixture(autouse=True)
def _reset_overrides():
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture(autouse=True)
def _clean_lock_and_tasks():
    yield
    export_mod._pdf_tasks.clear()
    # 释放可能残留的锁
    for rid in ("rpt-a", "rpt-b", "rpt-c", "rpt-d", "rpt-e"):
        release_generation(rid)


def _patch_access(base: Path, is_admin: bool = False):
    return (
        patch("app.api.v1.export.get_activation_with_manager", return_value=(None, object())),
        patch("app.api.v1.export.get_effective_simple_root", return_value=base),
        patch("app.api.v1.export.is_super_admin_user", return_value=is_admin),
    )


# ── 1. 单轨锁 ──────────────────────────────────────────────

def test_single_track_lock_basic() -> None:
    assert try_acquire_generation("rpt-a") is True
    assert try_acquire_generation("rpt-a") is False  # 重复登记被拒
    assert is_generation_inflight("rpt-a") is True
    release_generation("rpt-a")
    assert is_generation_inflight("rpt-a") is False
    assert try_acquire_generation("rpt-a") is True
    release_generation("rpt-a")


def test_review_kick_shares_lock() -> None:
    """export 侧持有锁时，批复路径 kick 返回 False（不并发起第二个任务）。"""
    try_acquire_generation("rpt-b")

    async def _call():
        return report_review_service.kick_report_generation("rpt-b", "user-1", None)

    assert asyncio.run(_call()) is False
    release_generation("rpt-b")


def test_export_kick_marks_pending_when_inflight() -> None:
    """另一路径生成中：export kick 不重启任务，但把状态表标为 pending（供状态查询）。"""
    try_acquire_generation("rpt-c")

    async def _call():
        with patch("asyncio.create_task") as mock_create:
            export_mod._kick_pdf_generation("rpt-c", "user-1", None)
            mock_create.assert_not_called()

    asyncio.run(_call())
    assert export_mod._pdf_tasks["rpt-c"]["status"] == "pending"
    release_generation("rpt-c")


# ── 2. 限量重新生成（API）──────────────────────────────────

def test_user_force_blocked_when_exhausted(reg: ReportRegistry) -> None:
    """已用满 2 次 → 403，且不触发任何生成。"""
    rid = "rpt-a"
    _write_record(reg.simple_base_dir, rid, _approved_record(rid, regen_count=2))
    _override_user("user-1")

    p1, p2, p3 = _patch_access(reg.simple_base_dir)
    with p1, p2, p3, patch.object(export_mod, "_kick_pdf_generation") as mock_kick:
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/export/report-pdf/{rid}",
            params={"activation_code": "CODE1", "force": "true"},
        )
        assert resp.status_code == 403
        assert "重新生成次数已用完" in resp.json()["detail"]
        mock_kick.assert_not_called()


def test_user_force_allowed_with_remaining(reg: ReportRegistry) -> None:
    """已用 1 次 → 放行，kick 带 count_regen=True。"""
    rid = "rpt-a"
    _write_record(reg.simple_base_dir, rid, _approved_record(rid, regen_count=1))
    _override_user("user-1")

    p1, p2, p3 = _patch_access(reg.simple_base_dir)
    with p1, p2, p3, patch.object(export_mod, "_kick_pdf_generation") as mock_kick:
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/export/report-pdf/{rid}",
            params={"activation_code": "CODE1", "force": "true"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "generating"
        mock_kick.assert_called_once()
        assert mock_kick.call_args.kwargs.get("count_regen") is True


def test_admin_force_unlimited(reg: ReportRegistry) -> None:
    """admin force 不受次数限制且不计数（count_regen=False）。"""
    rid = "rpt-a"
    _write_record(reg.simple_base_dir, rid, _approved_record(rid, regen_count=5))
    _override_user("user-1")

    # admin 路径走 ReportRegistry() 默认目录：patch 为指向 tmp 注册表
    real_cls = ReportRegistry
    p1, p2, p3 = _patch_access(reg.simple_base_dir, is_admin=True)
    p4 = patch(
        "app.api.v1.export.ReportRegistry",
        side_effect=lambda base_dir=None: real_cls(base_dir=base_dir or str(reg.simple_base_dir)),
    )
    with p1, p2, p3, p4, patch.object(export_mod, "_kick_pdf_generation") as mock_kick:
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/export/report-pdf/{rid}",
            params={"activation_code": "CODE1", "force": "true"},
        )
        assert resp.status_code == 200
        mock_kick.assert_called_once()
        kwargs = mock_kick.call_args.kwargs
        assert kwargs.get("count_regen") is False


# ── 3. 成功才计数（_run_pdf_generation）─────────────────────

def test_regen_count_incremented_on_success(reg: ReportRegistry) -> None:
    rid = "rpt-a"
    _write_record(reg.simple_base_dir, rid, _approved_record(rid, regen_count=0))
    assert try_acquire_generation(rid)

    with patch.object(ReportPdfService, "generate_markdown_only", new=AsyncMock(return_value="md")):
        asyncio.run(export_mod._run_pdf_generation(rid, "user-1", str(reg.simple_base_dir), True, count_regen=True))

    record = reg.get_report_by_id(rid)
    assert record["report_regen_count"] == 1
    assert export_mod._pdf_tasks[rid]["status"] == "done"
    assert not is_generation_inflight(rid)  # 锁已释放


def test_regen_count_not_incremented_on_failure(reg: ReportRegistry) -> None:
    rid = "rpt-a"
    _write_record(reg.simple_base_dir, rid, _approved_record(rid, regen_count=0))
    assert try_acquire_generation(rid)

    with patch.object(ReportPdfService, "generate_markdown_only", new=AsyncMock(side_effect=RuntimeError("LLM down"))):
        asyncio.run(export_mod._run_pdf_generation(rid, "user-1", str(reg.simple_base_dir), True, count_regen=True))

    record = reg.get_report_by_id(rid)
    assert record["report_regen_count"] == 0  # 失败不扣次数
    assert export_mod._pdf_tasks[rid]["status"] == "error"
    assert not is_generation_inflight(rid)


def test_admin_run_not_counted(reg: ReportRegistry) -> None:
    rid = "rpt-a"
    _write_record(reg.simple_base_dir, rid, _approved_record(rid, regen_count=0))
    assert try_acquire_generation(rid)

    with patch.object(ReportPdfService, "generate_markdown_only", new=AsyncMock(return_value="md")):
        asyncio.run(export_mod._run_pdf_generation(rid, "user-1", str(reg.simple_base_dir), True, count_regen=False))

    assert reg.get_report_by_id(rid)["report_regen_count"] == 0


# ── 4. 状态接口 regen_remaining / 残留 pending ───────────────

def test_status_returns_regen_remaining(reg: ReportRegistry) -> None:
    rid = "rpt-a"
    _write_record(reg.simple_base_dir, rid, _approved_record(rid, regen_count=1, with_cache=True))
    # 有缓存 markdown → ready
    (reg.simple_base_dir / "reports" / rid / "report_markdown.md").write_text("x", encoding="utf-8")
    _override_user("user-1")

    p1, p2, p3 = _patch_access(reg.simple_base_dir)
    with p1, p2, p3:
        client = TestClient(app)
        resp = client.get(
            f"/api/v1/export/report-pdf-status/{rid}", params={"activation_code": "CODE1"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        assert body["regen_remaining"] == 1


def test_status_admin_regen_remaining_null(reg: ReportRegistry) -> None:
    rid = "rpt-a"
    _write_record(reg.simple_base_dir, rid, _approved_record(rid, regen_count=2, with_cache=True))
    (reg.simple_base_dir / "reports" / rid / "report_markdown.md").write_text("x", encoding="utf-8")
    _override_user("user-1")

    real_cls = ReportRegistry
    p1, p2, p3 = _patch_access(reg.simple_base_dir, is_admin=True)
    p4 = patch(
        "app.api.v1.export.ReportRegistry",
        side_effect=lambda base_dir=None: real_cls(base_dir=base_dir or str(reg.simple_base_dir)),
    )
    p5 = patch(
        "app.services.report_pdf_service.get_simple_base_dir",
        return_value=reg.simple_base_dir,
    )
    with p1, p2, p3, p4, p5:
        client = TestClient(app)
        resp = client.get(
            f"/api/v1/export/report-pdf-status/{rid}", params={"activation_code": "CODE1"}
        )
        assert resp.json()["regen_remaining"] is None


def test_status_stale_pending_falls_back_to_cache(reg: ReportRegistry) -> None:
    """任务表残留 pending 但锁已释放（批复路径任务结束不写本表）→ 以缓存为准，不卡 generating。"""
    rid = "rpt-a"
    _write_record(reg.simple_base_dir, rid, _approved_record(rid, with_cache=True))
    (reg.simple_base_dir / "reports" / rid / "report_markdown.md").write_text("x", encoding="utf-8")
    export_mod._pdf_tasks[rid] = {"status": "pending", "error": None, "created_at": 0.0}
    _override_user("user-1")

    p1, p2, p3 = _patch_access(reg.simple_base_dir)
    with p1, p2, p3:
        client = TestClient(app)
        resp = client.get(
            f"/api/v1/export/report-pdf-status/{rid}", params={"activation_code": "CODE1"}
        )
        assert resp.json()["status"] == "ready"
