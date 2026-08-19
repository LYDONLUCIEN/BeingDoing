"""
报告复核体系测试（2026-08-18，tasks/report-review-plan.md）

覆盖：
- 单轨锁（自 test_report_regen_limit.py 迁移）：try_acquire/release 语义、
  export 侧与 review 侧共用登记、状态接口残留 pending 兜底
- staging 影子稿：生成写 staging 不动正式缓存；发布原子替换 + .bak 备份 + 时间戳刷新
- 复核单状态机：提交（频率限制/未关闭拦截）→ regenerating → pending_confirm
  → done（发布：通知+邮件+工单关闭）/ rejected（驳回必填理由）
- API：用户提交复核（content_issue 建单 / download_issue 仅进 Feedback）；
  admin 复核端点门控（无复核单不可重新生成）
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.v1 import export as export_mod
from app.api.v1.auth import get_current_user
from app.main import app
from app.models.database import Base, get_db
from app.models.feedback import Feedback, Notification
from app.models.user import User
from app.services import report_recheck_service, report_review_service
from app.services.report_pdf_service import (
    ReportPdfService,
    is_generation_inflight,
    release_generation,
    try_acquire_generation,
)
from app.utils.report_registry import STEP_IDS, ReportRegistry


# ── 工具 ────────────────────────────────────────────────────

def _write_record(root: Path, report_id: str, payload: dict) -> None:
    d = root / "reports" / report_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "record.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _approved_record(report_id: str, with_cache: bool = False) -> dict:
    """五阶段完成 + 审核已通过的报告（复核申请的前提）。"""
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
    }
    if with_cache:
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
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(autouse=True)
def _clean_lock_and_tasks():
    yield
    export_mod._pdf_tasks.clear()
    report_recheck_service._staging_tasks.clear()
    for rid in ("rpt-a", "rpt-b", "rpt-c"):
        release_generation(rid)


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


def _override_db(factory):
    async def _get_db():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_db] = _get_db


def _patch_export_access(base: Path):
    return (
        patch("app.api.v1.export.get_activation_with_manager", return_value=(None, object())),
        patch("app.api.v1.export.get_effective_simple_root", return_value=base),
        patch("app.api.v1.export.is_super_admin_user", return_value=False),
    )


# ── 1. 单轨锁（迁移自 test_report_regen_limit.py）─────────────

def test_single_track_lock_basic() -> None:
    assert try_acquire_generation("rpt-a") is True
    assert try_acquire_generation("rpt-a") is False
    assert is_generation_inflight("rpt-a") is True
    release_generation("rpt-a")
    assert is_generation_inflight("rpt-a") is False
    release_generation("rpt-a")


def test_review_kick_shares_lock() -> None:
    """export 侧持有锁时，批复路径 kick 返回 False（不并发起第二个任务）。"""
    try_acquire_generation("rpt-b")

    async def _call():
        return report_review_service.kick_report_generation("rpt-b", "user-1", None)

    assert asyncio.run(_call()) is False
    release_generation("rpt-b")


def test_recheck_kick_shares_lock(reg: ReportRegistry) -> None:
    """正式生成路径持锁时，复核 staging 生成不并发（返回 False）。"""
    rid = "rpt-a"
    _write_record(reg.simple_base_dir, rid, _approved_record(rid))
    record = reg.get_report_by_id(rid)
    record["recheck_requests"] = [{
        "id": "rc1", "status": "pending", "description": "x",
        "feedback_id": None, "requested_by": "user-1",
        "requested_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "closed_at": None, "reject_reason": None, "regen_error": None,
    }]
    reg.save_record(record)

    try_acquire_generation(rid)

    async def _call():
        return report_recheck_service.kick_recheck_regeneration(reg, rid, "admin-1")

    assert asyncio.run(_call()) is False
    release_generation(rid)


def test_status_stale_pending_falls_back_to_cache(reg: ReportRegistry) -> None:
    """任务表残留 pending 但锁已释放（批复路径任务结束不写本表）→ 以缓存为准，不卡 generating。"""
    rid = "rpt-a"
    _write_record(reg.simple_base_dir, rid, _approved_record(rid, with_cache=True))
    (reg.simple_base_dir / "reports" / rid / "report_markdown.md").write_text("x", encoding="utf-8")
    export_mod._pdf_tasks[rid] = {"status": "pending", "error": None, "created_at": 0.0}
    _override_user("user-1")

    p1, p2, p3 = _patch_export_access(reg.simple_base_dir)
    with p1, p2, p3:
        client = TestClient(app)
        resp = client.get(
            f"/api/v1/export/report-pdf-status/{rid}", params={"activation_code": "CODE1"}
        )
        assert resp.json()["status"] == "ready"


# ── 2. staging 影子稿 ────────────────────────────────────────

def test_staging_publish_replaces_official_with_backup(reg: ReportRegistry) -> None:
    rid = "rpt-a"
    _write_record(reg.simple_base_dir, rid, _approved_record(rid, with_cache=True))
    service = ReportPdfService(base_dir=str(reg.simple_base_dir))

    official = reg.simple_base_dir / "reports" / rid / "report_markdown.md"
    official.write_text("旧版内容", encoding="utf-8")
    staging = reg.simple_base_dir / "reports" / rid / "report_markdown.staging.md"
    staging.write_text("新稿内容", encoding="utf-8")

    assert service.publish_staging(rid) is True

    assert official.read_text(encoding="utf-8") == "新稿内容"
    assert not staging.exists()
    backup = reg.simple_base_dir / "reports" / rid / "report_markdown.bak.md"
    assert backup.read_text(encoding="utf-8") == "旧版内容"
    # 缓存时间戳被刷新（_load_cached_markdown 有效性依赖）
    record = reg.get_report_by_id(rid)
    assert record["report_markdown_generated_at"] > "2026-01-01"


def test_staging_publish_without_staging_returns_false(reg: ReportRegistry) -> None:
    rid = "rpt-a"
    _write_record(reg.simple_base_dir, rid, _approved_record(rid))
    service = ReportPdfService(base_dir=str(reg.simple_base_dir))
    assert service.publish_staging(rid) is False


def test_generate_staging_does_not_touch_official(reg: ReportRegistry) -> None:
    rid = "rpt-a"
    _write_record(reg.simple_base_dir, rid, _approved_record(rid, with_cache=True))
    service = ReportPdfService(base_dir=str(reg.simple_base_dir))
    official = reg.simple_base_dir / "reports" / rid / "report_markdown.md"
    official.write_text("旧版内容", encoding="utf-8")

    with patch.object(
        ReportPdfService, "_generate_report_markdown", new=AsyncMock(return_value="新稿")
    ):
        asyncio.run(service.generate_staging_markdown(rid, user_id="user-1"))

    assert official.read_text(encoding="utf-8") == "旧版内容"  # 正式缓存不动
    assert service.load_staging_markdown(rid) == "新稿"
    service.discard_staging(rid)
    assert service.has_staging_markdown(rid) is False


# ── 3. 复核单状态机（service 层）──────────────────────────────

def test_submit_recheck_creates_entry_and_feedback(reg: ReportRegistry, db_factory) -> None:
    rid = "rpt-a"
    _write_record(reg.simple_base_dir, rid, _approved_record(rid))

    async def _run():
        async with db_factory() as db:
            report = reg.get_report_by_id(rid)
            entry = await report_recheck_service.submit_recheck(
                db, reg, report,
                user_id="user-1", user_email="user@example.com",
                description="报告内容和我的情况不符",
            )
            await db.commit()
            return entry

    entry = asyncio.run(_run())
    assert entry["status"] == "pending"
    assert entry["feedback_id"]

    record = reg.get_report_by_id(rid)
    assert report_recheck_service.get_recheck_status(record) == "pending"

    async def _check():
        async with db_factory() as db:
            fb = (
                await db.execute(select(Feedback).where(Feedback.id == entry["feedback_id"]))
            ).scalar_one()
            assert fb.type == "bug"
            assert "报告复核申请" in fb.content and rid in fb.content
            # 用户 auto_ack 通知（与「反馈 bug」同流程）
            acks = (
                await db.execute(
                    select(func.count()).select_from(Notification).where(
                        Notification.user_id == "user-1",
                        Notification.type == "feedback_auto_ack",
                    )
                )
            ).scalar_one()
            assert acks == 1

    asyncio.run(_check())


def test_submit_recheck_blocked_when_open(reg: ReportRegistry, db_factory) -> None:
    rid = "rpt-a"
    rec = _approved_record(rid)
    rec["recheck_requests"] = [{
        "id": "rc1", "status": "pending", "description": "x",
        "feedback_id": None, "requested_by": "user-1",
        "requested_at": "2020-01-01T00:00:00+00:00",
        "updated_at": "2020-01-01T00:00:00+00:00",
        "closed_at": None, "reject_reason": None, "regen_error": None,
    }]
    _write_record(reg.simple_base_dir, rid, rec)

    async def _run():
        async with db_factory() as db:
            with pytest.raises(ValueError, match="处理中"):
                await report_recheck_service.submit_recheck(
                    db, reg, reg.get_report_by_id(rid),
                    user_id="user-1", user_email="user@example.com", description="",
                )

    asyncio.run(_run())


def test_submit_recheck_daily_limit(reg: ReportRegistry, db_factory) -> None:
    """已关闭的复核单当天也算：同一报告每自然日限 1 次。"""
    from datetime import datetime, timezone

    rid = "rpt-a"
    rec = _approved_record(rid)
    rec["recheck_requests"] = [{
        "id": "rc1", "status": "done", "description": "x",
        "feedback_id": None, "requested_by": "user-1",
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "closed_at": datetime.now(timezone.utc).isoformat(),
        "reject_reason": None, "regen_error": None,
    }]
    _write_record(reg.simple_base_dir, rid, rec)

    async def _run():
        async with db_factory() as db:
            with pytest.raises(ValueError, match="每天最多"):
                await report_recheck_service.submit_recheck(
                    db, reg, reg.get_report_by_id(rid),
                    user_id="user-1", user_email="user@example.com", description="",
                )

    asyncio.run(_run())


def test_submit_recheck_blocked_when_not_approved(reg: ReportRegistry, db_factory) -> None:
    rid = "rpt-a"
    rec = _approved_record(rid)
    rec["review_status"] = "pending_review"
    _write_record(reg.simple_base_dir, rid, rec)

    async def _run():
        async with db_factory() as db:
            with pytest.raises(ValueError, match="审核通过"):
                await report_recheck_service.submit_recheck(
                    db, reg, reg.get_report_by_id(rid),
                    user_id="user-1", user_email="user@example.com", description="",
                )

    asyncio.run(_run())


def _submit_sync(reg: ReportRegistry, db_factory, rid: str) -> dict:
    async def _run():
        async with db_factory() as db:
            entry = await report_recheck_service.submit_recheck(
                db, reg, reg.get_report_by_id(rid),
                user_id="user-1", user_email="user@example.com", description="内容不准",
            )
            await db.commit()
            return entry

    return asyncio.run(_run())


def test_publish_flow(reg: ReportRegistry, db_factory) -> None:
    """完整流转：pending → regenerating → pending_confirm → done（发布+通知+工单关闭）。"""
    rid = "rpt-a"
    _write_record(reg.simple_base_dir, rid, _approved_record(rid, with_cache=True))
    (reg.simple_base_dir / "reports" / rid / "report_markdown.md").write_text("旧版", encoding="utf-8")
    entry = _submit_sync(reg, db_factory, rid)

    assert report_recheck_service.mark_regenerating(reg, rid) is not None
    assert report_recheck_service.get_recheck_status(reg.get_report_by_id(rid)) == "regenerating"
    report_recheck_service.mark_pending_confirm(reg, rid)
    assert report_recheck_service.get_recheck_status(reg.get_report_by_id(rid)) == "pending_confirm"

    # 写入 staging 新稿
    (reg.simple_base_dir / "reports" / rid / "report_markdown.staging.md").write_text(
        "新稿", encoding="utf-8"
    )

    async def _publish():
        with patch(
            "app.services.report_recheck_service.EmailService", create=True
        ), patch(
            "app.services.email_service.EmailService.send_email", new=AsyncMock()
        ) as mock_send:
            async with db_factory() as db:
                done = await report_recheck_service.publish_recheck(
                    db, reg, rid, admin_id="admin-1"
                )
                await db.commit()
            return done, mock_send

    done, mock_send = asyncio.run(_publish())
    assert done["status"] == "done"
    assert done["closed_at"]

    record = reg.get_report_by_id(rid)
    assert report_recheck_service.get_current_recheck(record) is None  # 已关闭
    assert (reg.simple_base_dir / "reports" / rid / "report_markdown.md").read_text(
        encoding="utf-8"
    ) == "新稿"

    async def _check():
        async with db_factory() as db:
            # 站内信（report_recheck_done）
            n = (
                await db.execute(
                    select(Notification).where(
                        Notification.user_id == "user-1",
                        Notification.type == "report_recheck_done",
                    )
                )
            ).scalar_one()
            assert rid in n.content
            # Feedback 工单已关闭
            fb = (
                await db.execute(select(Feedback).where(Feedback.id == entry["feedback_id"]))
            ).scalar_one()
            assert fb.status == "done"

    asyncio.run(_check())
    mock_send.assert_awaited_once()  # 邮件已发


def test_regen_failure_back_to_pending(reg: ReportRegistry, db_factory) -> None:
    rid = "rpt-a"
    _write_record(reg.simple_base_dir, rid, _approved_record(rid))
    _submit_sync(reg, db_factory, rid)

    report_recheck_service.mark_regenerating(reg, rid)
    report_recheck_service.mark_regen_failed(reg, rid, "LLM down")

    record = reg.get_report_by_id(rid)
    cur = report_recheck_service.get_current_recheck(record)
    assert cur["status"] == "pending"  # 退回 pending，可重试
    assert cur["regen_error"] == "LLM down"


def test_reject_requires_reason_and_notifies(reg: ReportRegistry, db_factory) -> None:
    rid = "rpt-a"
    _write_record(reg.simple_base_dir, rid, _approved_record(rid))
    entry = _submit_sync(reg, db_factory, rid)

    async def _reject_empty():
        async with db_factory() as db:
            with pytest.raises(ValueError, match="理由"):
                await report_recheck_service.reject_recheck(
                    db, reg, rid, admin_id="admin-1", reason="  "
                )

    asyncio.run(_reject_empty())

    async def _reject():
        async with db_factory() as db:
            done = await report_recheck_service.reject_recheck(
                db, reg, rid, admin_id="admin-1", reason="报告内容经评估无需重新生成"
            )
            await db.commit()
            return done

    done = asyncio.run(_reject())
    assert done["status"] == "rejected"
    assert report_recheck_service.get_current_recheck(reg.get_report_by_id(rid)) is None

    async def _check():
        async with db_factory() as db:
            n = (
                await db.execute(
                    select(Notification).where(
                        Notification.user_id == "user-1",
                        Notification.type == "report_recheck_rejected",
                    )
                )
            ).scalar_one()
            assert "无需重新生成" in n.content
            fb = (
                await db.execute(select(Feedback).where(Feedback.id == entry["feedback_id"]))
            ).scalar_one()
            assert fb.status == "done"

    asyncio.run(_check())


def test_publish_requires_pending_confirm(reg: ReportRegistry, db_factory) -> None:
    rid = "rpt-a"
    _write_record(reg.simple_base_dir, rid, _approved_record(rid))
    _submit_sync(reg, db_factory, rid)

    async def _run():
        async with db_factory() as db:
            with pytest.raises(ValueError, match="尚未生成完成"):
                await report_recheck_service.publish_recheck(db, reg, rid, admin_id="a")

    asyncio.run(_run())


# ── 4. API 层 ────────────────────────────────────────────────

def test_api_submit_content_issue(reg: ReportRegistry, db_factory) -> None:
    rid = "rpt-a"
    _write_record(reg.simple_base_dir, rid, _approved_record(rid, with_cache=True))
    _override_user("user-1")
    _override_db(db_factory)

    p1, p2, p3 = _patch_export_access(reg.simple_base_dir)
    with p1, p2, p3:
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/export/report-recheck/{rid}",
            params={"activation_code": "CODE1"},
            json={"category": "content_issue", "description": "内容和我情况不符"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["path"] == "recheck"
        assert body["recheck"]["status"] == "pending"

        # 重复提交 → 409
        resp2 = client.post(
            f"/api/v1/export/report-recheck/{rid}",
            params={"activation_code": "CODE1"},
            json={"category": "content_issue"},
        )
        assert resp2.status_code == 409


def test_api_submit_download_issue_goes_feedback_only(reg: ReportRegistry, db_factory) -> None:
    rid = "rpt-a"
    _write_record(reg.simple_base_dir, rid, _approved_record(rid, with_cache=True))
    _override_user("user-1")
    _override_db(db_factory)

    p1, p2, p3 = _patch_export_access(reg.simple_base_dir)
    with p1, p2, p3:
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/export/report-recheck/{rid}",
            params={"activation_code": "CODE1"},
            json={"category": "download_issue", "description": "PDF 打不开"},
        )
        assert resp.status_code == 200
        assert resp.json()["path"] == "feedback"

    # 不建复核单
    assert report_recheck_service.get_current_recheck(reg.get_report_by_id(rid)) is None

    async def _check():
        async with db_factory() as db:
            fb = (await db.execute(select(Feedback))).scalars().all()
            assert len(fb) == 1
            assert "报告下载/打开失败" in fb[0].content

    asyncio.run(_check())


def test_api_my_report_id_exposes_recheck_status(reg: ReportRegistry) -> None:
    rid = "rpt-a"
    rec = _approved_record(rid)
    rec["recheck_requests"] = [{
        "id": "rc1", "status": "regenerating", "description": "x",
        "feedback_id": None, "requested_by": "user-1",
        "requested_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "closed_at": None, "reject_reason": None, "regen_error": None,
    }]
    _write_record(reg.simple_base_dir, rid, rec)
    _override_user("user-1")

    p1, p2, p3 = _patch_export_access(reg.simple_base_dir)
    with p1, p2, p3, patch.object(export_mod, "_kick_pdf_generation"):
        client = TestClient(app)
        resp = client.get("/api/v1/export/my-report-id", params={"activation_code": "CODE1"})
        assert resp.status_code == 200
        assert resp.json()["recheck_status"] == "regenerating"


def test_admin_regenerate_requires_open_recheck(reg: ReportRegistry) -> None:
    """无复核单 → 409（admin 不能随意重新生成）。"""
    rid = "rpt-a"
    _write_record(reg.simple_base_dir, rid, _approved_record(rid))
    _override_user("admin-1")

    with (
        patch("app.api.v1.admin._is_super_admin", return_value=True),
        patch("app.api.v1.admin.ReportRegistry", lambda: reg),
    ):
        client = TestClient(app)
        resp = client.post(f"/api/v1/admin/reports/{rid}/recheck/regenerate")
        assert resp.status_code == 409
        assert "没有进行中的复核" in resp.json()["detail"]


def test_admin_recheck_lifecycle_api(reg: ReportRegistry, db_factory) -> None:
    """admin 端点全链路：提交（用户）→ 重新生成（mock LLM）→ 预览 → 发布。"""
    rid = "rpt-a"
    _write_record(reg.simple_base_dir, rid, _approved_record(rid, with_cache=True))
    (reg.simple_base_dir / "reports" / rid / "report_markdown.md").write_text("旧版", encoding="utf-8")
    _override_user("admin-1")
    _override_db(db_factory)

    # 预置复核单
    rec = reg.get_report_by_id(rid)
    rec["recheck_requests"] = [{
        "id": "rc1", "status": "pending", "description": "内容不准",
        "feedback_id": None, "requested_by": "user-1",
        "requested_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "closed_at": None, "reject_reason": None, "regen_error": None,
    }]
    reg.save_record(rec)

    admin_patches = (
        patch("app.api.v1.admin._is_super_admin", return_value=True),
        patch("app.api.v1.admin.ReportRegistry", lambda: reg),
        patch("app.api.v1.admin.AsyncSessionLocal", db_factory),
    )

    with admin_patches[0], admin_patches[1], admin_patches[2], patch.object(
        ReportPdfService, "_generate_report_markdown", new=AsyncMock(return_value="新稿")
    ), patch(
        "app.services.report_pdf_service.get_simple_base_dir",
        return_value=reg.simple_base_dir,
    ), patch(
        "app.services.email_service.EmailService.send_email", new=AsyncMock()
    ):
        client = TestClient(app)

        # 触发重新生成（TestClient 在事件循环内执行，kick 可用）
        resp = client.post(f"/api/v1/admin/reports/{rid}/recheck/regenerate")
        assert resp.status_code == 200

        # 等后台任务落地（kick 用 asyncio.create_task，TestClient 请求结束后任务仍跑；
        # 这里直接驱动一轮事件循环等待）
        import time

        for _ in range(50):
            cur = report_recheck_service.get_current_recheck(reg.get_report_by_id(rid))
            if cur and cur["status"] == "pending_confirm":
                break
            time.sleep(0.1)
        cur = report_recheck_service.get_current_recheck(reg.get_report_by_id(rid))
        assert cur["status"] == "pending_confirm"

        # 复核单详情
        resp = client.get(f"/api/v1/admin/reports/{rid}/recheck")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["has_staging"] is True
        assert data["current"]["status"] == "pending_confirm"

        # 预览 staging PDF（真实渲染链路 mock 掉 PDF 转换）
        with patch.object(
            ReportPdfService, "markdown_to_pdf_bytes", return_value=b"%PDF-fake"
        ):
            resp = client.get(f"/api/v1/admin/reports/{rid}/recheck/staging-pdf")
            assert resp.status_code == 200
            assert resp.content == b"%PDF-fake"

        # 发布前用户仍看到旧版
        assert (reg.simple_base_dir / "reports" / rid / "report_markdown.md").read_text(
            encoding="utf-8"
        ) == "旧版"

        # 确认发布
        resp = client.post(f"/api/v1/admin/reports/{rid}/recheck/publish")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "done"

        # 发布后用户看到新稿
        assert (reg.simple_base_dir / "reports" / rid / "report_markdown.md").read_text(
            encoding="utf-8"
        ) == "新稿"

        # 复核单关闭后「重新生成」入口失效
        resp = client.post(f"/api/v1/admin/reports/{rid}/recheck/regenerate")
        assert resp.status_code == 409

        # 列表透传 recheck_status（已关闭 → None）
        resp = client.get("/api/v1/admin/reports")
        item = next(i for i in resp.json()["data"]["items"] if i["report_id"] == rid)
        assert item["recheck_status"] is None
