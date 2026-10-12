"""安全回归：通过 HTTP 接口验证权限边界，使用临时数据而非服务器数据。"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.main  # noqa: F401  先加载主应用，兼容现有 simple_chat 包的导入顺序
from app.api.v1 import answers, auth, chat, chat_optimized, export, simple_auth
from app.config.settings import settings
from app.services.answer_service import AnswerService
from app.services.session_service import SessionService
from app.utils.simple_activation_manager import SimpleActivationManager


@pytest.fixture
def api(monkeypatch, tmp_path):
    app = FastAPI()
    app.include_router(simple_auth.router, prefix="/api/v1")
    for module in (answers, chat, chat_optimized, export):
        app.include_router(module.router, prefix="/api/v1")
    manager = SimpleActivationManager(base_dir=str(tmp_path / "simple"))
    monkeypatch.setattr(simple_auth, "SimpleActivationManager", lambda: manager)
    monkeypatch.setattr(settings, "SUPER_ADMIN_USER_IDS", "admin")
    monkeypatch.setattr(settings, "SUPER_ADMIN_EMAILS", "")
    return app


@pytest.mark.parametrize("user_id, expected_status", [(None, 401), ("member", 403), ("admin", 200)])
def test_internal_activation_requires_super_admin(api, user_id, expected_status):
    if user_id:
        api.dependency_overrides[auth.get_current_user] = lambda: {"user_id": user_id}
    response = TestClient(api).post("/api/v1/simple-auth/activation", json={})
    assert response.status_code == expected_status
    if expected_status == 200:
        assert response.json()["data"]["activation_code"]


@pytest.mark.parametrize("method, path", [("get", "/cache/stats"), ("post", "/cache/clear")])
@pytest.mark.parametrize("user_id, expected_status", [(None, 401), ("member", 403), ("admin", 200)])
def test_cache_operations_require_super_admin(api, method, path, user_id, expected_status):
    if user_id:
        api.dependency_overrides[auth.get_current_user] = lambda: {"user_id": user_id}
    response = getattr(TestClient(api), method)("/api/v1/chat-optimized" + path)
    assert response.status_code == expected_status


@pytest.mark.parametrize(
    "method, path, payload",
    [
        ("get", "/chat/history?session_id=foreign", None),
        ("post", "/chat/messages", {"session_id": "foreign", "message": "test"}),
        ("post", "/chat/messages/stream", {"session_id": "foreign", "message": "test"}),
        ("post", "/chat/record-interrupt", {"session_id": "foreign", "partial_content": "test"}),
        ("post", "/chat/guide", {"session_id": "foreign", "current_step": "values"}),
        ("post", "/chat/guide-preference", {"session_id": "foreign", "preference": "quiet"}),
        ("post", "/chat/resummarize", {"session_id": "foreign"}),
        ("get", "/chat-optimized/notes?session_id=foreign", None),
        ("get", "/chat-optimized/answer-cards?session_id=foreign", None),
        (
            "post",
            "/chat-optimized/messages/stream",
            {"session_id": "foreign", "message": "test", "current_step": "values"},
        ),
        ("get", "/answers?session_id=foreign", None),
        ("get", "/answers/answer-1", None),
        ("patch", "/answers/answer-1", {"content": "a sufficiently long answer"}),
        (
            "post",
            "/answers",
            {
                "session_id": "foreign",
                "category": "values",
                "content": "a sufficiently long answer",
            },
        ),
        (
            "post",
            "/export/generate",
            {"user_id": "member", "session_id": "foreign", "format": "json"},
        ),
    ],
)
def test_foreign_session_is_denied_before_read_or_write(api, monkeypatch, method, path, payload):
    async def get_session(session_id):
        return {"session_id": session_id, "user_id": "another-user"}

    async def get_answer(answer_id):
        return {"id": answer_id, "session_id": "foreign"}

    monkeypatch.setattr(SessionService, "get_session", get_session)
    monkeypatch.setattr(AnswerService, "get_answer", get_answer)
    api.dependency_overrides[auth.get_current_user] = lambda: {"user_id": "member"}
    response = TestClient(api).request(method, "/api/v1" + path, json=payload)
    assert response.status_code == 403


def test_export_download_rejects_absolute_path(api, tmp_path):
    secret = tmp_path / "private.json"
    secret.write_text('{"private": true}')
    api.dependency_overrides[auth.get_current_user] = lambda: {"user_id": "member"}
    response = TestClient(api).get(
        "/api/v1/export/download", params={"export_id": str(secret.with_suffix(""))}
    )
    assert response.status_code == 400
    assert "private" not in response.text


def test_owner_can_export_and_download_but_other_users_cannot(api, monkeypatch, tmp_path):
    from app.services import export_file_store
    from app.services.export_service import ExportService

    async def get_session(session_id):
        return {"session_id": session_id, "user_id": "member"}

    async def collect_export_data(self, user_id, session_id):
        return {"user_id": user_id, "session_id": session_id, "message": "private"}

    monkeypatch.setattr(SessionService, "get_session", get_session)
    monkeypatch.setattr(ExportService, "collect_export_data", collect_export_data)
    monkeypatch.setattr(export_file_store.tempfile, "gettempdir", lambda: str(tmp_path))
    api.dependency_overrides[auth.get_current_user] = lambda: {"user_id": "member"}
    client = TestClient(api)
    response = client.post(
        "/api/v1/export/generate",
        json={
            "user_id": "member",
            "session_id": "mine",
            "format": "json",
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert "file_path" not in data
    download = client.get(data["download_url"])
    assert download.status_code == 200
    assert download.json()["message"] == "private"
    api.dependency_overrides[auth.get_current_user] = lambda: {"user_id": "other"}
    assert client.get(data["download_url"]).status_code == 404


@pytest.mark.parametrize("session_id, expected", [("../secrets", 400), ("missing", 404)])
def test_invalid_or_missing_session_is_denied(api, monkeypatch, session_id, expected):
    async def get_session(_session_id):
        return None

    monkeypatch.setattr(SessionService, "get_session", get_session)
    api.dependency_overrides[auth.get_current_user] = lambda: {"user_id": "member"}
    response = TestClient(api).get("/api/v1/chat/history", params={"session_id": session_id})
    assert response.status_code == expected


def test_report_force_regeneration_is_reserved_for_admin(api, monkeypatch):
    monkeypatch.setattr(export, "_verify_report_access", lambda *args: (None, "member"))
    api.dependency_overrides[auth.get_current_user] = lambda: {"user_id": "member"}
    response = TestClient(api).post("/api/v1/export/report-pdf/report-1?force=true")
    assert response.status_code == 403
