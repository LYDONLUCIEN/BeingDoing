"""
POST /admin/users/{user_id}/reset-password 路由测试。
"""

from unittest.mock import AsyncMock, patch

import pytest
from app.api.v1.auth import get_current_user
from app.main import app
from fastapi.testclient import TestClient


def _super_admin_client() -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "admin-1",
        "email": "admin@example.com",
    }
    return TestClient(app)


def _normal_client() -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "user-1",
        "email": "user@example.com",
    }
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_admin_reset_password_non_super_admin_403():
    client = _normal_client()
    with patch("app.api.v1.admin._is_super_admin", return_value=False):
        res = client.post(
            "/api/v1/admin/users/u1/reset-password",
            json={"new_password": "NewPass123"},
        )
    assert res.status_code == 403


def test_admin_reset_password_user_not_found_404():
    client = _super_admin_client()
    with patch("app.api.v1.admin._is_super_admin", return_value=True):
        with patch(
            "app.services.auth_service.AuthService.admin_set_password",
            new_callable=AsyncMock,
            side_effect=ValueError("用户不存在"),
        ):
            res = client.post(
                "/api/v1/admin/users/nonexistent-user-id/reset-password",
                json={"new_password": "NewPass123"},
            )
    assert res.status_code == 404


def test_admin_reset_password_success():
    client = _super_admin_client()
    with patch("app.api.v1.admin._is_super_admin", return_value=True):
        with patch(
            "app.services.auth_service.AuthService.admin_set_password",
            new_callable=AsyncMock,
        ) as mock_set:
            res = client.post(
                "/api/v1/admin/users/user-abc/reset-password",
                json={"new_password": "FreshPass99"},
            )
    assert res.status_code == 200
    body = res.json()
    assert body.get("code") == 200
    assert body.get("data", {}).get("user_id") == "user-abc"
    mock_set.assert_awaited_once_with("user-abc", "FreshPass99")


def test_admin_reset_password_too_short_422():
    client = _super_admin_client()
    with patch("app.api.v1.admin._is_super_admin", return_value=True):
        res = client.post(
            "/api/v1/admin/users/u1/reset-password",
            json={"new_password": "123"},
        )
    assert res.status_code == 422
