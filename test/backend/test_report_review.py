"""
报告阻塞式审核流测试（ADR-0009 / P-C）

覆盖：
- 生成钩子：ensure_report 写 review_status=pending_review + 随机 3~24h deadline
- 存量报告（无审核字段）祖父豁免视为 approved
- 用户侧阻塞：pending → HTTP 200 返回审核中状态；approved → 放行
- admin 人工批复：manual 字段 + 站内信触发；列表审核字段与筛选
- 自动批复 job：过期 pending → approved + auto + 站内信；未过期/存量不动
- 通知幂等：重复批复/重复跑 job 不重复发站内信
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

from app.api.v1.auth import get_current_user
from app.main import app
from app.models.database import Base
from app.models.feedback import Notification
from app.models.user import User
from app.services import report_review_service
from app.utils.report_registry import ReportRegistry
from app.utils.report_review import (
    AUTO_APPROVE_MAX_HOURS,
    AUTO_APPROVE_MIN_HOURS,
    get_review_status,
    init_review_fields,
    is_pending_review,
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
    rec = _base_record(report_id, **kw)
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


@pytest.fixture
def reg(tmp_path: Path) -> ReportRegistry:
    base = tmp_path / "simple"
    base.mkdir(parents=True, exist_ok=True)
    return ReportRegistry(base_dir=str(base))


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


# ── 1. 生成钩子 ─────────────────────────────────────────────

def test_ensure_report_writes_review_fields(reg: ReportRegistry) -> None:
    before = datetime.now(timezone.utc)
    record = reg.ensure_report(activation_code="HOOK1", user_id="user-1")
    after = datetime.now(timezone.utc)

    assert record["review_status"] == "pending_review"
    assert record["review_type"] is None
    assert record["reviewed_by"] is None
    assert record["reviewed_at"] is None

    deadline = datetime.fromisoformat(record["review_deadline"])
    assert deadline >= before + timedelta(hours=AUTO_APPROVE_MIN_HOURS)
    assert deadline <= after + timedelta(hours=AUTO_APPROVE_MAX_HOURS)

    # 落盘一致
    on_disk = reg.get_report_by_id(record["report_id"])
    assert on_disk["review_status"] == "pending_review"
    assert on_disk["review_deadline"] == record["review_deadline"]


def test_random_deadline_within_range() -> None:
    now = datetime.now(timezone.utc)
    for _ in range(100):
        rec = init_review_fields({}, now=now)
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


# ── 4. 自动批复 job ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_auto_approve_overdue(reg: ReportRegistry, db_factory) -> None:
    now = datetime.now(timezone.utc)
    overdue = _pending_record("rpt-overdue", now - timedelta(hours=1))
    future = _pending_record("rpt-future", now + timedelta(hours=10), activation_code="A2")
    legacy = _base_record("rpt-legacy2", activation_code="A3")
    for rec in (overdue, future, legacy):
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

    # 未过期/存量不动
    assert reg.get_report_by_id("rpt-future")["review_status"] == "pending_review"
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
        assert await report_review_service.notify_report_approved(db, "user-1", "rpt-x") is True
        await db.commit()
        assert await report_review_service.notify_report_approved(db, "user-1", "rpt-x") is False
        await db.commit()
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
