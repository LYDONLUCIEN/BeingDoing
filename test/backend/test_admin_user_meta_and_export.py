"""
admin 用户类型标签 / 备注 / 按用户全量导出测试（2026-10-06）：

覆盖：
- PATCH /api/v1/admin/users/{id}/meta：改类型+备注、非法类型 400、非管理员 403
- GET /api/v1/admin/users：user_type 筛选
- POST /api/v1/admin/users/export：
  * 非管理员 403；无筛选条件 400
  * 显式 user_ids：zip 含 index.json + 每用户 profile.json（邮箱/类型/激活码）
    + 名下全部 report（md / raw / report_markdown.md）
  * 服务端 user_type 筛选模式：只导匹配用户

使用独立 in-memory SQLite + monkeypatch 各模块 AsyncSessionLocal；
ReportRegistry 与激活码管理器指向 tmp_path，不污染真实数据。
"""

from __future__ import annotations

import io
import json
import zipfile
from functools import partial
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1 import admin as admin_mod
from app.api.v1.auth import get_current_user
from app.main import app
from app.models.database import Base
from app.services import user_export_service as ues_mod
from app.utils.report_registry import ReportRegistry
from fastapi.testclient import TestClient

# ─── 测试专用引擎 + 会话工厂 ──────────────────────────────────

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
_TestSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)

USER_REAL = "user-real-1"
USER_TEST = "user-test-1"


@pytest.fixture(autouse=True)
async def _setup(monkeypatch, tmp_path):
    """每个测试前：建表 + 插两个用户 + monkeypatch DB / registry / 激活码"""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    from app.models.user import User

    async with _TestSessionLocal() as db:
        db.add_all(
            [
                User(
                    id=USER_REAL,
                    email="real@test.com",
                    username="真实用户",
                    password_hash="x",
                    user_type="real",
                ),
                User(
                    id=USER_TEST,
                    email="test@test.com",
                    username="测试账号",
                    password_hash="x",
                    user_type="test",
                ),
            ]
        )
        await db.commit()

    monkeypatch.setattr(admin_mod, "AsyncSessionLocal", _TestSessionLocal)
    monkeypatch.setattr(ues_mod, "AsyncSessionLocal", _TestSessionLocal)

    # registry 指向 tmp（user_export_service 与 batch_export_service 两处实例化）
    registry_base = tmp_path / "simple"
    registry_base.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        ues_mod, "ReportRegistry", partial(ReportRegistry, base_dir=str(registry_base))
    )
    import app.services.batch_export_service as bes_mod

    monkeypatch.setattr(
        bes_mod, "ReportRegistry", partial(ReportRegistry, base_dir=str(registry_base))
    )

    # 激活码：空映射（隔离真实 activations.json；list_activations 是同步方法）
    def _empty_list(self):  # noqa: ANN001
        return {}

    monkeypatch.setattr(
        ues_mod.SimpleActivationManager, "list_activations", _empty_list
    )

    yield

    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def admin_client():
    app.dependency_overrides[get_current_user] = _admin_override
    with patch("app.api.v1.admin._is_super_admin", return_value=True):
        yield TestClient(app)


async def _admin_override():
    return {"user_id": "admin-1", "email": "admin@example.com"}


def _write_report(base, report_id: str, user_id: str, activation_code: str) -> None:
    """在 tmp registry 下写一个最小可导出的 report（record + 一个 values 会话 + 报告 md）。"""
    d = base / "reports" / report_id
    d.mkdir(parents=True, exist_ok=True)
    record = {
        "report_id": report_id,
        "activation_code": activation_code,
        "user_id": user_id,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "status": "in_progress",
        "final_conclusion": None,
        "steps": {
            "values": {
                "step_id": "values",
                "selected_session_id": "sess-v",
                "locked": True,
                "session_ids": ["sess-v"],
            },
        },
    }
    (d / "record.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    session = {
        "session_id": "sess-v",
        "messages": [
            {"role": "user", "content": "u-1", "created_at": "2026-01-01T00:01:00"},
            {
                "role": "assistant",
                "content": "a-1",
                "created_at": "2026-01-01T00:01:05",
            },
        ],
        "metadata": {"conclusion_final": "结论"},
    }
    (d / "values__sess-v.json").write_text(
        json.dumps(session, ensure_ascii=False), encoding="utf-8"
    )
    (d / "report_markdown.md").write_text("# 报告全文（缓存）", encoding="utf-8")


# ─── PATCH /users/{id}/meta ───────────────────────────────────


def test_patch_user_meta_updates_type_and_note(admin_client):
    resp = admin_client.patch(
        f"/api/v1/admin/users/{USER_REAL}/meta",
        json={"user_type": "beta", "admin_note": "内测渠道来的"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["user_type"] == "beta"
    assert data["admin_note"] == "内测渠道来的"

    # 持久化校验：列表按 beta 筛选能查到，按 real 查不到
    r = admin_client.get("/api/v1/admin/users", params={"user_type": "beta"})
    assert r.status_code == 200
    ids = [it["user_id"] for it in r.json()["data"]["items"]]
    assert USER_REAL in ids

    r = admin_client.get("/api/v1/admin/users", params={"user_type": "real"})
    ids = [it["user_id"] for it in r.json()["data"]["items"]]
    assert USER_REAL not in ids


def test_patch_user_meta_invalid_type_400(admin_client):
    resp = admin_client.patch(
        f"/api/v1/admin/users/{USER_REAL}/meta",
        json={"user_type": "vip"},
    )
    assert resp.status_code == 400


def test_patch_user_meta_non_admin_403():
    app.dependency_overrides[get_current_user] = _admin_override
    with patch("app.api.v1.admin._is_super_admin", return_value=False):
        client = TestClient(app)
        resp = client.patch(
            f"/api/v1/admin/users/{USER_REAL}/meta",
            json={"user_type": "test"},
        )
    assert resp.status_code == 403


def test_list_users_filter_by_type(admin_client):
    r = admin_client.get("/api/v1/admin/users", params={"user_type": "test"})
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["user_id"] == USER_TEST
    assert items[0]["user_type"] == "test"
    assert "admin_note" in items[0]


# ─── POST /users/export ───────────────────────────────────────


def test_users_export_non_admin_403():
    app.dependency_overrides[get_current_user] = _admin_override
    with patch("app.api.v1.admin._is_super_admin", return_value=False):
        client = TestClient(app)
        resp = client.post("/api/v1/admin/users/export", json={"user_ids": [USER_REAL]})
    assert resp.status_code == 403


def test_users_export_requires_filter_or_ids_400(admin_client):
    resp = admin_client.post("/api/v1/admin/users/export", json={})
    assert resp.status_code == 400


def test_users_export_by_ids_zip(admin_client, tmp_path):
    base = tmp_path / "simple"
    _write_report(base, "rpt-real-1", USER_REAL, "CODEREAL1")

    resp = admin_client.post(
        "/api/v1/admin/users/export",
        json={"user_ids": [USER_REAL, USER_TEST]},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()

        # 索引
        assert "index.json" in names
        index = json.loads(zf.read("index.json"))
        assert index["user_count"] == 2
        by_id = {u["user_id"]: u for u in index["users"]}
        assert by_id[USER_REAL]["email"] == "real@test.com"
        assert by_id[USER_REAL]["report_count"] == 1
        assert by_id[USER_TEST]["report_count"] == 0

        # 有 report 的用户：profile + report 全套产物
        assert f"users/{USER_REAL}/profile.json" in names
        profile = json.loads(zf.read(f"users/{USER_REAL}/profile.json"))
        assert profile["email"] == "real@test.com"
        assert profile["user_type"] == "real"
        assert profile["reports"][0]["report_id"] == "rpt-real-1"
        assert f"users/{USER_REAL}/reports/rpt-real-1/report_rpt-real-1.md" in names
        assert f"users/{USER_REAL}/reports/rpt-real-1/raw/values__sess-v.json" in names
        # 报告全文 markdown 附带
        md = zf.read(
            f"users/{USER_REAL}/reports/rpt-real-1/report_markdown.md"
        ).decode()
        assert "报告全文（缓存）" in md

        # 无 report 的用户：仅 profile.json
        assert f"users/{USER_TEST}/profile.json" in names
        assert not any(n.startswith(f"users/{USER_TEST}/reports/") for n in names)

        # 无跳过
        assert "_skipped.txt" not in names


def test_users_export_filter_mode_only_matching_type(admin_client, tmp_path):
    base = tmp_path / "simple"
    _write_report(base, "rpt-real-1", USER_REAL, "CODEREAL1")

    resp = admin_client.post(
        "/api/v1/admin/users/export",
        json={"user_type": "test"},
    )
    assert resp.status_code == 200
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()
        assert f"users/{USER_TEST}/profile.json" in names
        assert not any(n.startswith(f"users/{USER_REAL}/") for n in names)


def test_users_export_filter_empty_result_404(admin_client):
    resp = admin_client.post(
        "/api/v1/admin/users/export",
        json={"user_type": "admin"},
    )
    assert resp.status_code == 404
