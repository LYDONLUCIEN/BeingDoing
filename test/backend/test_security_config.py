"""生产配置及找回密码的安全边界。"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.requests import Request

from app.api.v1 import auth, simple_auth
from app.config.settings import Settings, settings
from app.main import app
from app.services import auth_service


@pytest.mark.parametrize(
    "overrides",
    [
        {"SECRET_KEY": "your-secret-key-here-change-in-production"},
        {"SECRET_KEY": "short"},
        {"REFRESH_TOKEN_SECRET_KEY": "short"},
        {"DEBUG": True},
        {"REFRESH_COOKIE_SECURE": False},
    ],
)
def test_production_rejects_insecure_configuration(overrides):
    values = {
        "APP_ENV": "production",
        "SECRET_KEY": "a" * 48,
        "DEBUG": False,
        "REFRESH_COOKIE_SECURE": True,
    }
    values.update(overrides)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_secure_production_configuration_is_accepted():
    value = Settings(
        _env_file=None,
        APP_ENV="production",
        SECRET_KEY="a" * 48,
        DEBUG=False,
        REFRESH_COOKIE_SECURE=True,
    )
    assert value.APP_ENV == "production"


@pytest.mark.parametrize("module", [auth, simple_auth])
def test_rate_limit_uses_trusted_asgi_client_not_arbitrary_forwarded_header(module):
    request = Request(
        {
            "type": "http",
            "headers": [(b"x-forwarded-for", b"attacker-chosen")],
            "client": ("203.0.113.10", 1234),
        }
    )
    assert module._client_ip(request) == "203.0.113.10"


async def test_password_reset_code_has_finite_guess_budget(monkeypatch):
    codes = {
        "member@example.com": {
            "code": "123456",
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
        }
    }
    monkeypatch.setattr(auth_service, "_password_reset_email_codes", codes)
    for _ in range(5):
        with pytest.raises(ValueError):
            await auth_service.AuthService.reset_password_with_code(
                "member@example.com", "000000", "new-password"
            )
    with pytest.raises(ValueError, match="重新获取"):
        await auth_service.AuthService.reset_password_with_code(
            "member@example.com", "123456", "new-password"
        )


@pytest.mark.parametrize(
    "path, payload",
    [
        ("code/phone", {"phone": "13800000000"}),
        (
            "confirm/phone",
            {"phone": "13800000000", "code": "123456", "new_password": "new-password"},
        ),
    ],
)
def test_mock_sms_password_reset_is_unavailable_in_production(monkeypatch, path, payload):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    response = TestClient(app).post("/api/v1/auth/password/reset/" + path, json=payload)
    assert response.status_code == 503
