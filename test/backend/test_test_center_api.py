"""管理员测试 API 的允许/拒绝路径。"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.admin_test_center import router
from app.api.v1.auth import get_current_user
from app.config.settings import settings


@pytest.mark.parametrize(
    "environment,enabled,identity,expected",
    [
        ("development", "1", {"user_id": "operator"}, 200),
        ("development", "1", {"user_id": "other", "user_type": "admin"}, 403),
        ("production", "1", {"user_id": "operator"}, 404),
        ("development", "0", {"user_id": "operator"}, 404),
    ],
)
def test_access_boundary(tmp_path, monkeypatch, environment, enabled, identity, expected):
    monkeypatch.setattr(settings, "APP_ENV", environment)
    monkeypatch.setattr(settings, "SUPER_ADMIN_USER_IDS", "operator")
    monkeypatch.setenv("TEST_CENTER_ENABLED", enabled)
    monkeypatch.setenv("TEST_CENTER_ROOT", str(tmp_path / "control"))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: identity
    with TestClient(app) as client:
        assert client.get("/admin/test-center/catalog").status_code == expected
        if expected != 200:
            assert (
                client.post("/admin/test-center/runs", json={"case_ids": ["sample"]}).status_code
                == expected
            )
        else:
            assert (
                client.post(
                    "/admin/test-center/runs", json={"case_ids": ["../../etc/passwd"]}
                ).status_code
                == 400
            )
