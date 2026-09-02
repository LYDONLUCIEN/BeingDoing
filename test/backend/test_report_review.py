"""
报告阻塞式审核流测试（ADR-0009 / P-C；2026-07-27 计时锚点修订）

覆盖：
- 生成钩子：ensure_report 写 review_status=not_started（不计时）
- 计时起点：v4 终选提交（final-selection/submit）即转 pending_review + 随机 3~24h deadline
  并后台预生成报告 markdown（2026-08-23 前移）；进入报告页（my-report-id）的懒触发保留兑底；
  五阶段未完成则保持 not_started 且阻塞 PDF 端点
- 存量报告（无审核字段）祖父豁免视为 approved
- 用户侧阻塞：pending → HTTP 200 返回审核中状态；approved → 放行
- admin 人工批复：manual 字段 + 站内信触发；列表审核字段与筛选
- 自动批复 job：过期 pending → approved + auto + 站内信；未过期/not_started/存量不动
- 通知幂等：重复批复/重复跑 job 不重复发站内信
- 批复后自动生成：approve_report 批复瞬间 kick 后台生成报告 markdown（五阶段未完成跳过；
  幂等批复不重复 kick）；kick 函数本身在无事件循环的同步上下文安全跳过
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.v1 import export as export_mod
from app.api.v1.auth import get_current_user
from app.main import app
from app.models.database import Base
from app.models.feedback import Notification
from app.models.user import User
from app.services import report_review_service
from app.utils.report_registry import STEP_IDS, ReportRegistry
from app.utils.report_review import (
    AUTO_APPROVE_MAX_HOURS,
    AUTO_APPROVE_MIN_HOURS,
    get_review_status,
    is_pending_review,
    start_review,
)
from sqlalchemy import select, func


# ── 工具 ────────────────────────────────────────────────────

def _write_record(root: Path, report_id: str, payload: dict) -> None:
    d = root / "reports" / report_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "record.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _base_record(report_id: str, activation_code: str = "CODE1", user_id: str = "user-1") -> dict:
    ts = "2026-01-01T00:00:00+00:00"
    return {
        "report_id": report_id,
        "activation_code": activation_code,
        "user_id": user_id,
        "created_at": ts,
        "updated_at": ts,
        "status": "in_progress",
        "final_conclusion": None,
        "steps": {},
    }


def _pending_record(report_id: str, deadline: datetime, **kw) -> dict:
    """审核中报告。审核计时起点的前提是五阶段已完成，故 steps 按完成态构造。"""
    rec = _base_record(report_id, **kw)
    ts = "2026-01-01T00:00:00+00:00"
    rec["steps"] = {
        sid: {
            "step_id": sid,
            "selected_session_id": f"sess-{sid}",
            "locked": True,
            "session_ids": [f"sess-{sid}"],
            "updated_at": ts,
        }
        for sid in STEP_IDS
    }
    rec.update(
        {
            "review_status": "pending_review",
            "review_deadline": deadline.isoformat(),
            "review_type": None,
            "reviewed_by": None,
            "reviewed_at": None,
        }
    )
    return rec


def _not_started_record(report_id: str, complete: bool = True, **kw) -> dict:
    """新建报告的审核初始态；complete=True 时五阶段均已选定会话（报告入口解锁）。"""
    rec = _base_record(report_id, **kw)
    rec.update(
        {
            "review_status": "not_started",
            "review_deadline": None,
            "review_type": None,
            "reviewed_by": None,
            "reviewed_at": None,
        }
    )
    if complete:
        ts = "2026-01-01T00:00:00+00:00"
        rec["steps"] = {
            sid: {
                "step_id": sid,
                "selected_session_id": f"sess-{sid}",
                "locked": True,
                "session_ids": [f"sess-{sid}"],
                "updated_at": ts,
            }
            for sid in STEP_IDS
        }
    return rec


@pytest.fixture
def reg(tmp_path: Path) -> ReportRegistry:
    base = tmp_path / "simple"
    base.mkdir(parents=True, exist_ok=True)
    return ReportRegistry(base_dir=str(base))


@pytest.fixture(autouse=True)
def _mock_gen_kick():
    """批复后自动生成报告的后台任务收口为 mock：避免测试触发真实 LLM 生成。"""
    real = report_review_service.kick_report_generation
    with patch.object(report_review_service, "kick_report_generation") as m:
        m._real = real  # 个别测试需调真实函数（同步上下文安全性）
        yield m


@pytest_asyncio.fixture
async def db_factory():
    """内存 SQLite（StaticPool 共享连接）的 session 工厂 + 预置用户。"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        s.add(User(
            id="user-1", email="user@example.com", username="u1",
            password_hash="x", is_active=True,
        ))
        await s.commit()
    yield factory
    await engine.dispose()


async def _count_notifications(factory, user_id: str = "user-1") -> int:
    async with factory() as s:
        return (
            await s.execute(
                select(func.count())
                .select_from(Notification)
                .where(Notification.user_id == user_id, Notification.type == "report_approved")
            )
        ).scalar_one()


# ── 1. 生成钩子 + 计时起点 ──────────────────────────────────

def test_ensure_report_marks_review_not_started(reg: ReportRegistry) -> None:
    """新建报告仅标记 not_started，不写 deadline（审核计时从进入报告页起算）。"""
    record = reg.ensure_report(activation_code="HOOK1", user_id="user-1")

    assert record["review_status"] == "not_started"
    assert record["review_deadline"] is None
    assert record["review_type"] is None
    assert record["reviewed_by"] is None
    assert record["reviewed_at"] is None

    # 落盘一致
    on_disk = reg.get_report_by_id(record["report_id"])
    assert on_disk["review_status"] == "not_started"
    assert on_disk["review_deadline"] is None


def test_random_deadline_within_range() -> None:
    now = datetime.now(timezone.utc)
    for _ in range(100):
        rec = start_review({}, now=now)
        deadline = datetime.fromisoformat(rec["review_deadline"])
        delta_h = (deadline - now).total_seconds() / 3600
        assert AUTO_APPROVE_MIN_HOURS <= delta_h <= AUTO_APPROVE_MAX_HOURS


def test_legacy_record_without_fields_treated_as_approved(reg: ReportRegistry, tmp_path: Path) -> None:
    """存量报告（无审核字段）祖父豁免：视为 approved，且不补写 review_status。"""
    legacy = _base_record("legacy-1")
    _write_record(reg.simple_base_dir, "legacy-1", legacy)

    loaded = reg.get_by_activation_user("CODE1", "user-1")
    assert loaded is not None
    assert "review_status" not in loaded  # normalize 不注入 review_status
    assert get_review_status(loaded) == "approved"
    assert not is_pending_review(loaded)


# ── 2. 用户侧阻塞（API） ────────────────────────────────────

def _override_user(user_id: str = "user-1"):
    async def _u():
        return {"user_id": user_id, "email": "user@example.com"}

    app.dependency_overrides[get_current_user] = _u


@pytest.fixture(autouse=True)
def _reset_overrides():
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _patch_export_access(base: Path):
    """patch export 模块的激活码解析与管理权限定，指向 tmp 注册表。"""
    return (
        patch("app.api.v1.export.get_activation_with_manager", return_value=(None, object())),
        patch("app.api.v1.export.get_effective_simple_root", return_value=base),
        patch("app.api.v1.export.is_super_admin_user", return_value=False),
    )


def test_user_side_pending_blocked(reg: ReportRegistry) -> None:
    rid = "rpt-pending"
    deadline = datetime.now(timezone.utc) + timedelta(hours=5)
    _write_record(reg.simple_base_dir, rid, _pending_record(rid, deadline))
    _override_user("user-1")

    p1, p2, p3 = _patch_export_access(reg.simple_base_dir)
    with p1, p2, p3:
        client = TestClient(app)

        # my-report-id：200 + 审核中状态
        resp = client.get("/api/v1/export/my-report-id", params={"activation_code": "CODE1"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["report_id"] == rid
        assert body["review_status"] == "pending_review"
        assert body["review_deadline"]

        # report-pdf-status：200 + pending_review，不暴露生成状态
        resp = client.get(f"/api/v1/export/report-pdf-status/{rid}", params={"activation_code": "CODE1"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "pending_review"
        assert body["review_status"] == "pending_review"
        assert body["review_deadline"]

        # report-pdf 触发：不生成，返回审核中
        resp = client.post(f"/api/v1/export/report-pdf/{rid}", params={"activation_code": "CODE1"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending_review"

        # report-pdf 下载：不返回 PDF，200 + JSON 审核中
        resp = client.get(f"/api/v1/export/report-pdf-download/{rid}", params={"activation_code": "CODE1"})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        data = resp.json()["data"]
        assert data["review_status"] == "pending_review"
        assert data["review_deadline"]


def test_user_side_approved_passes(reg: ReportRegistry) -> None:
    """approved（含存量祖父豁免）正常放行。"""
    rid = "rpt-approved"
    _write_record(reg.simple_base_dir, rid, _base_record(rid))  # 存量无字段 → approved
    _override_user("user-1")

    p1, p2, p3 = _patch_export_access(reg.simple_base_dir)
    with p1, p2, p3:
        client = TestClient(app)

        resp = client.get("/api/v1/export/my-report-id", params={"activation_code": "CODE1"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["report_id"] == rid
        assert body["review_status"] == "approved"
        assert "review_deadline" not in body

        # 无生成任务、无缓存 → status=none，但 review_status=approved 放行
        resp = client.get(f"/api/v1/export/report-pdf-status/{rid}", params={"activation_code": "CODE1"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "none"
        assert body["review_status"] == "approved"


# ── 2b. 计时起点：进入报告页才开始审核（2026-07-27 修订） ────


def test_review_starts_on_report_page_entry(reg: ReportRegistry) -> None:
    """not_started + 五阶段完成 → my-report-id 即刻转 pending + 随机 deadline，并后台预生成。"""
    rid = "rpt-start"
    _write_record(reg.simple_base_dir, rid, _not_started_record(rid, complete=True))
    _override_user("user-1")
    export_mod._pdf_tasks.pop(rid, None)

    async def _noop_generation(*args, **kwargs):
        return None

    p1, p2, p3 = _patch_export_access(reg.simple_base_dir)
    with p1, p2, p3, patch.object(export_mod, "_run_pdf_generation", _noop_generation):
        client = TestClient(app)
        before = datetime.now(timezone.utc)
        resp = client.get("/api/v1/export/my-report-id", params={"activation_code": "CODE1"})
        after = datetime.now(timezone.utc)

        assert resp.status_code == 200
        body = resp.json()
        assert body["report_id"] == rid
        assert body["review_status"] == "pending_review"
        deadline = datetime.fromisoformat(body["review_deadline"])
        assert before + timedelta(hours=AUTO_APPROVE_MIN_HOURS) <= deadline
        assert deadline <= after + timedelta(hours=AUTO_APPROVE_MAX_HOURS)

        # 审核开始即后台预生成报告 markdown（审核期间报告已在自动生成）
        assert export_mod._pdf_tasks.get(rid, {}).get("status") == "pending"

    # 落盘：pending + deadline 持久化，重复进入不重置计时
    saved = reg.get_report_by_id(rid)
    assert saved["review_status"] == "pending_review"
    assert saved["review_deadline"] == body["review_deadline"]

    with p1, p2, p3, patch.object(export_mod, "_run_pdf_generation", _noop_generation):
        client = TestClient(app)
        resp = client.get("/api/v1/export/my-report-id", params={"activation_code": "CODE1"})
        assert resp.json()["review_deadline"] == body["review_deadline"]


def test_review_not_started_when_phases_incomplete(reg: ReportRegistry) -> None:
    """五阶段未完成：保持 not_started，返回 not_started，PDF 端点同样阻塞。"""
    rid = "rpt-incomplete"
    _write_record(reg.simple_base_dir, rid, _not_started_record(rid, complete=False))
    _override_user("user-1")
    export_mod._pdf_tasks.pop(rid, None)

    p1, p2, p3 = _patch_export_access(reg.simple_base_dir)
    with p1, p2, p3:
        client = TestClient(app)

        resp = client.get("/api/v1/export/my-report-id", params={"activation_code": "CODE1"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["review_status"] == "not_started"
        assert "review_deadline" not in body

        # 直连 PDF 触发端点：五阶段未完成一律 409（2026-08-07 完成度门控，admin 也不例外）
        resp = client.post(f"/api/v1/export/report-pdf/{rid}", params={"activation_code": "CODE1"})
        assert resp.status_code == 409
        assert "尚未完成" in resp.json()["detail"]

    # 未开始审核就不应有生成任务、不落盘变更
    assert rid not in export_mod._pdf_tasks
    saved = reg.get_report_by_id(rid)
    assert saved["review_status"] == "not_started"


# ── 2c. 计时起点前移：v4 终选提交即开始审核（2026-08-23） ────


def test_review_starts_on_v4_final_submit(reg: ReportRegistry) -> None:
    """v4 终选提交成功即转 pending_review + 随机 deadline 并后台预生成（不进报告页也计时）。"""
    rid = "rpt-v4-submit"
    # 提交前的 record：前四阶段完成，rumination 未锁（submit 端点负责 lock_step）
    rec = _not_started_record(rid, complete=True)
    rec["steps"]["rumination"] = {
        "step_id": "rumination",
        "selected_session_id": None,
        "locked": False,
        "session_ids": [],
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    _write_record(reg.simple_base_dir, rid, rec)
    _override_user("user-1")
    export_mod._pdf_tasks.pop(rid, None)

    async def _noop_generation(*args, **kwargs):
        return None

    reports_root = reg.simple_base_dir / "reports"
    with (
        patch(
            "app.api.v1.rumination_v4_routes._resolve_v4_ctx_with_rec",
            return_value=(reports_root, rid, object()),
        ),
        patch("app.api.v1.rumination_v4_routes._assert_rumination_editable", return_value=None),
        patch(
            "app.api.v1.rumination_v4_routes.submit_final_selection",
            return_value={
                "final_selection": {"selected_combo_ids": ["c1"]},
                "main_section": "end",
            },
        ),
        patch("app.api.v1.rumination_v4_routes._audit_log", return_value=None),
        patch.object(export_mod, "_run_pdf_generation", _noop_generation),
    ):
        client = TestClient(app)
        before = datetime.now(timezone.utc)
        resp = client.post(
            "/api/v1/simple-chat/rumination-v4/final-selection/submit",
            json={"activation_code": "CODE1"},
        )
        after = datetime.now(timezone.utc)

    try:
        assert resp.status_code == 200
        saved = reg.get_report_by_id(rid)
        # rumination 锁定 + 审核计时开始 + 随机 deadline + 后台预生成已启动
        assert saved["steps"]["rumination"]["locked"] is True
        assert saved["review_status"] == "pending_review"
        deadline = datetime.fromisoformat(saved["review_deadline"])
        assert before + timedelta(hours=AUTO_APPROVE_MIN_HOURS) <= deadline
        assert deadline <= after + timedelta(hours=AUTO_APPROVE_MAX_HOURS)
        assert export_mod._pdf_tasks.get(rid, {}).get("status") == "pending"
    finally:
        export_mod._pdf_tasks.pop(rid, None)
        from app.services.report_pdf_service import _generation_inflight

        _generation_inflight.discard(rid)


# ── 3. admin 人工批复（API） ────────────────────────────────

def _override_admin():
    async def _a():
        return {"user_id": "admin-1", "email": "admin@example.com"}

    app.dependency_overrides[get_current_user] = _a


def test_admin_manual_approve(reg: ReportRegistry, db_factory) -> None:
    rid = "rpt-manual"
    deadline = datetime.now(timezone.utc) + timedelta(hours=5)
    _write_record(reg.simple_base_dir, rid, _pending_record(rid, deadline))
    _override_admin()

    with (
        patch("app.api.v1.admin._is_super_admin", return_value=True),
        patch("app.api.v1.admin.ReportRegistry", lambda: reg),
        patch("app.api.v1.admin.AsyncSessionLocal", db_factory),
    ):
        client = TestClient(app)
        resp = client.post(f"/api/v1/admin/reports/{rid}/approve")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["report_id"] == rid
        assert data["review_status"] == "approved"
        assert data["review_type"] == "manual"

    # record.json 落盘：manual 字段齐全
    saved = reg.get_report_by_id(rid)
    assert saved["review_status"] == "approved"
    assert saved["review_type"] == "manual"
    assert saved["reviewed_by"] == "admin-1"
    assert saved["reviewed_at"]

    # 站内信触发（同一文案「您的报告已审核通过」）
    import asyncio

    async def _check():
        async with db_factory() as s:
            rows = (
                await s.execute(
                    select(Notification).where(
                        Notification.user_id == "user-1", Notification.type == "report_approved"
                    )
                )
            ).scalars().all()
            assert len(rows) == 1
            assert "您的报告已审核通过" in rows[0].content
            assert "/explore/report/view" in rows[0].content
            assert "激活码：CODE1" in rows[0].content
            assert rid not in rows[0].content  # 内部 report_id 不透出给用户

    asyncio.run(_check())

    # 幂等：再次批复不重复通知
    with (
        patch("app.api.v1.admin._is_super_admin", return_value=True),
        patch("app.api.v1.admin.ReportRegistry", lambda: reg),
        patch("app.api.v1.admin.AsyncSessionLocal", db_factory),
    ):
        client = TestClient(app)
        resp = client.post(f"/api/v1/admin/reports/{rid}/approve")
        assert resp.status_code == 200

    async def _recheck():
        assert await _count_notifications(db_factory) == 1

    asyncio.run(_recheck())


def test_admin_approve_nonexistent_404(reg: ReportRegistry, db_factory) -> None:
    _override_admin()
    with (
        patch("app.api.v1.admin._is_super_admin", return_value=True),
        patch("app.api.v1.admin.ReportRegistry", lambda: reg),
        patch("app.api.v1.admin.AsyncSessionLocal", db_factory),
    ):
        client = TestClient(app)
        resp = client.post("/api/v1/admin/reports/no-such-id/approve")
        assert resp.status_code == 404


def test_admin_approve_forbidden_for_normal_user(reg: ReportRegistry) -> None:
    _override_user("user-1")
    client = TestClient(app)
    resp = client.post("/api/v1/admin/reports/whatever/approve")
    assert resp.status_code == 403


def test_admin_report_list_review_fields_and_filter(reg: ReportRegistry) -> None:
    now = datetime.now(timezone.utc)
    _write_record(
        reg.simple_base_dir, "rpt-p1",
        _pending_record("rpt-p1", now + timedelta(hours=3), activation_code="A1"),
    )
    _write_record(reg.simple_base_dir, "rpt-legacy", _base_record("rpt-legacy", activation_code="A2"))
    _override_admin()

    with (
        patch("app.api.v1.admin._is_super_admin", return_value=True),
        patch("app.api.v1.admin.ReportRegistry", lambda: reg),
    ):
        client = TestClient(app)

        resp = client.get("/api/v1/admin/reports")
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) == 2
        by_id = {i["report_id"]: i for i in items}
        p = by_id["rpt-p1"]
        assert p["review_status"] == "pending_review"
        assert p["review_deadline"]
        assert p["review_type"] is None
        assert p["reviewed_at"] is None
        legacy = by_id["rpt-legacy"]
        assert legacy["review_status"] == "approved"  # 祖父豁免

        # 筛选
        resp = client.get("/api/v1/admin/reports", params={"review_status": "pending_review"})
        items = resp.json()["data"]["items"]
        assert [i["report_id"] for i in items] == ["rpt-p1"]

        resp = client.get("/api/v1/admin/reports", params={"review_status": "approved"})
        items = resp.json()["data"]["items"]
        assert [i["report_id"] for i in items] == ["rpt-legacy"]


# ── 6. 完成度门控：未完成五阶段不可生成 PDF（2026-08-07） ─────


def _v4_complete_record(report_id: str, **kw) -> dict:
    """v4 口径完成态：前 4 阶段有 session，rumination 仅 locked（终选提交不写 session）。"""
    rec = _not_started_record(report_id, complete=False, **kw)
    ts = "2026-01-01T00:00:00+00:00"
    steps = {}
    for sid in STEP_IDS:
        if sid == "rumination":
            steps[sid] = {
                "step_id": sid,
                "selected_session_id": None,
                "locked": True,
                "session_ids": [],
                "updated_at": ts,
            }
        else:
            steps[sid] = {
                "step_id": sid,
                "selected_session_id": f"sess-{sid}",
                "locked": True,
                "session_ids": [f"sess-{sid}"],
                "updated_at": ts,
            }
    rec["steps"] = steps
    return rec


def _patch_admin_export(reg: ReportRegistry):
    """patch export 模块为 admin 访问 + tmp 注册表。"""
    return (
        patch("app.api.v1.export.is_super_admin_user", return_value=True),
        patch("app.api.v1.export.ReportRegistry", lambda *a, **k: reg),
    )


def test_admin_pdf_blocked_when_phases_incomplete(reg: ReportRegistry) -> None:
    """admin 不再豁免「流程未完成」：未完成的报告触发生成返回 409，不启动生成任务。"""
    rid = "rpt-admin-incomplete"
    _write_record(reg.simple_base_dir, rid, _not_started_record(rid, complete=False))
    _override_admin()
    export_mod._pdf_tasks.pop(rid, None)

    p1, p2 = _patch_admin_export(reg)
    with p1, p2:
        client = TestClient(app)
        resp = client.post(f"/api/v1/export/report-pdf/{rid}")
        assert resp.status_code == 409
        assert "尚未完成" in resp.json()["detail"]

    assert rid not in export_mod._pdf_tasks


def test_admin_pdf_allowed_when_v4_rumination_locked(reg: ReportRegistry) -> None:
    """v4 口径完成（rumination 仅 locked 无 session）→ admin 可正常触发生成。"""
    rid = "rpt-admin-v4"
    _write_record(reg.simple_base_dir, rid, _v4_complete_record(rid))
    _override_admin()
    export_mod._pdf_tasks.pop(rid, None)

    async def _noop_generation(*args, **kwargs):
        return None

    p1, p2 = _patch_admin_export(reg)
    with (
        p1,
        p2,
        patch.object(export_mod, "_run_pdf_generation", _noop_generation),
        patch(
            "app.services.report_pdf_service.ReportPdfService.has_cached_markdown",
            return_value=False,
        ),
    ):
        client = TestClient(app)
        resp = client.post(f"/api/v1/export/report-pdf/{rid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "generating"
        assert export_mod._pdf_tasks.get(rid, {}).get("status") == "pending"

    export_mod._pdf_tasks.pop(rid, None)


def test_admin_report_list_report_unlocked(reg: ReportRegistry) -> None:
    """列表返回 report_unlocked；completed_steps 把 rumination locked 计入（v4 口径）。"""
    _write_record(
        reg.simple_base_dir, "rpt-v4", _v4_complete_record("rpt-v4", activation_code="V4CODE")
    )
    _write_record(
        reg.simple_base_dir,
        "rpt-inc",
        _not_started_record("rpt-inc", complete=False, activation_code="INCCODE"),
    )
    _override_admin()

    with (
        patch("app.api.v1.admin._is_super_admin", return_value=True),
        patch("app.api.v1.admin.ReportRegistry", lambda: reg),
    ):
        client = TestClient(app)
        resp = client.get("/api/v1/admin/reports")
        assert resp.status_code == 200
        by_id = {i["report_id"]: i for i in resp.json()["data"]["items"]}

        v4 = by_id["rpt-v4"]
        assert v4["report_unlocked"] is True
        assert v4["completed_steps"] == 5  # rumination locked 计入

        inc = by_id["rpt-inc"]
        assert inc["report_unlocked"] is False
        assert inc["completed_steps"] == 0


# ── 4. 自动批复 job ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_auto_approve_overdue(reg: ReportRegistry, db_factory) -> None:
    now = datetime.now(timezone.utc)
    overdue = _pending_record("rpt-overdue", now - timedelta(hours=1))
    future = _pending_record("rpt-future", now + timedelta(hours=10), activation_code="A2")
    legacy = _base_record("rpt-legacy2", activation_code="A3")
    notstarted = _not_started_record("rpt-notstarted", complete=True, activation_code="A4")
    for rec in (overdue, future, legacy, notstarted):
        _write_record(reg.simple_base_dir, rec["report_id"], rec)

    count = await report_review_service.auto_approve_overdue(
        base_dir=str(reg.simple_base_dir), session_factory=db_factory
    )
    assert count == 1

    # 过期 → approved + auto + 站内信
    saved = reg.get_report_by_id("rpt-overdue")
    assert saved["review_status"] == "approved"
    assert saved["review_type"] == "auto"
    assert saved["reviewed_at"]
    assert saved["reviewed_by"] is None
    assert await _count_notifications(db_factory) == 1

    # 未过期/存量/not_started 不动
    assert reg.get_report_by_id("rpt-future")["review_status"] == "pending_review"
    assert reg.get_report_by_id("rpt-notstarted")["review_status"] == "not_started"
    legacy_loaded = reg.get_report_by_id("rpt-legacy2")
    assert "review_status" not in legacy_loaded
    assert get_review_status(legacy_loaded) == "approved"

    # 幂等：再次执行不重复批复、不重复通知
    count2 = await report_review_service.auto_approve_overdue(
        base_dir=str(reg.simple_base_dir), session_factory=db_factory
    )
    assert count2 == 0
    assert await _count_notifications(db_factory) == 1


# ── 5. 通知幂等（service 层） ───────────────────────────────

@pytest.mark.asyncio
async def test_notify_idempotent(db_factory) -> None:
    async with db_factory() as db:
        assert (
            await report_review_service.notify_report_approved(
                db, "user-1", "rpt-x", "CODE-X"
            )
            is True
        )
        await db.commit()
        assert (
            await report_review_service.notify_report_approved(
                db, "user-1", "rpt-x", "CODE-X"
            )
            is False
        )
        await db.commit()
        # 内容用激活码做用户可见标识，不暴露内部 report_id
        n = (
            await db.execute(
                select(Notification).where(
                    Notification.user_id == "user-1",
                    Notification.type == "report_approved",
                )
            )
        ).scalar_one()
        assert "激活码：CODE-X" in n.content
        assert "rpt-x" not in n.content
    assert await _count_notifications(db_factory) == 1


@pytest.mark.asyncio
async def test_approve_report_service_idempotent(reg: ReportRegistry, db_factory) -> None:
    rid = "rpt-svc"
    _write_record(
        reg.simple_base_dir, rid,
        _pending_record(rid, datetime.now(timezone.utc) + timedelta(hours=2)),
    )
    async with db_factory() as db:
        rec = await report_review_service.approve_report(
            reg, rid, review_type="manual", reviewed_by="admin-1", db=db
        )
        await db.commit()
        assert rec["review_type"] == "manual"
        # 重复批复：不重复通知
        rec2 = await report_review_service.approve_report(
            reg, rid, review_type="manual", reviewed_by="admin-1", db=db
        )
        await db.commit()
        assert rec2["review_status"] == "approved"
    assert await _count_notifications(db_factory) == 1


# ── 6. 批复后自动生成报告 ────────────────────────────────────

@pytest.mark.asyncio
async def test_approve_kicks_report_generation(
    reg: ReportRegistry, db_factory, _mock_gen_kick
) -> None:
    """批复通过瞬间触发后台生成；幂等重复批复不重复触发。"""
    rid = "rpt-kick"
    _write_record(
        reg.simple_base_dir, rid,
        _pending_record(rid, datetime.now(timezone.utc) + timedelta(hours=2)),
    )
    async with db_factory() as db:
        await report_review_service.approve_report(
            reg, rid, review_type="manual", reviewed_by="admin-1", db=db
        )
        await db.commit()
    assert _mock_gen_kick.call_count == 1
    args = _mock_gen_kick.call_args.args
    assert args[0] == rid
    assert args[1] == "user-1"  # record 的 user_id
    assert args[2] == str(reg.simple_base_dir)  # base_dir 来自 registry

    # 幂等：已 approved 再次批复不再 kick
    async with db_factory() as db:
        await report_review_service.approve_report(
            reg, rid, review_type="manual", reviewed_by="admin-1", db=db
        )
        await db.commit()
    assert _mock_gen_kick.call_count == 1


@pytest.mark.asyncio
async def test_approve_skips_generation_when_phases_incomplete(
    reg: ReportRegistry, db_factory, _mock_gen_kick
) -> None:
    """五阶段未完成时不触发生成（与 export 完成度门控同口径）。"""
    rid = "rpt-incomplete"
    rec = _pending_record(rid, datetime.now(timezone.utc) + timedelta(hours=2))
    rec["steps"] = {}
    _write_record(reg.simple_base_dir, rid, rec)
    async with db_factory() as db:
        await report_review_service.approve_report(
            reg, rid, review_type="manual", reviewed_by="admin-1", db=db
        )
        await db.commit()
    assert _mock_gen_kick.call_count == 0


@pytest.mark.asyncio
async def test_auto_approve_kicks_generation(
    reg: ReportRegistry, db_factory, _mock_gen_kick
) -> None:
    """超时自动批复同样触发后台生成。"""
    overdue = _pending_record(
        "rpt-kick-auto", datetime.now(timezone.utc) - timedelta(hours=1)
    )
    _write_record(reg.simple_base_dir, overdue["report_id"], overdue)
    count = await report_review_service.auto_approve_overdue(
        base_dir=str(reg.simple_base_dir), session_factory=db_factory
    )
    assert count == 1
    assert _mock_gen_kick.call_count == 1


def test_kick_generation_safe_without_running_loop(_mock_gen_kick) -> None:
    """同步上下文（无事件循环）调用 kick 安全跳过，不抛异常。"""
    assert _mock_gen_kick._real("rpt-x") is False
