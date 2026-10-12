"""找回/管理员重置密码后，旧刷新令牌不能继续签发登录态。"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.database import Base
from app.models.user import User
from app.services import auth_service
from app.services.auth_service import AuthService


@pytest.mark.parametrize("method", ["email", "phone", "admin"])
async def test_reset_revokes_only_the_target_users_refresh_tokens(monkeypatch, method):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(auth_service, "AsyncSessionLocal", sessions)
    monkeypatch.setattr(auth_service, "engine", engine)
    monkeypatch.setattr(auth_service, "_refresh_schema_ready", False)
    monkeypatch.setattr(auth_service, "_password_reset_email_codes", {})
    monkeypatch.setattr(auth_service, "_password_reset_phone_codes", {})
    try:
        async with sessions() as db:
            users = [
                User(
                    id=uid,
                    email=f"{uid}@example.com",
                    phone=phone,
                    password_hash=AuthService.get_password_hash("old-pass"),
                    is_active=True,
                )
                for uid, phone in [("alice", "13800000001"), ("bob", "13800000002")]
            ]
            db.add_all(users)
            await db.commit()
        alice_pair = await AuthService._issue_token_pair(users[0])
        bob_pair = await AuthService._issue_token_pair(users[1])
        record = {"code": "123456", "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5)}
        if method == "email":
            auth_service._password_reset_email_codes["alice@example.com"] = record
            await AuthService.reset_password_with_code("alice@example.com", "123456", "new-pass")
        elif method == "phone":
            auth_service._password_reset_phone_codes["13800000001"] = record
            await AuthService.reset_password_with_phone_code("13800000001", "123456", "new-pass")
        else:
            await AuthService.admin_set_password("alice", "new-pass")
        with pytest.raises(ValueError):
            await AuthService.refresh_access_token(alice_pair["refresh_token"])
        assert (await AuthService.refresh_access_token(bob_pair["refresh_token"]))["token"]
        async with sessions() as db:
            user = await db.get(User, "alice")
            assert AuthService.verify_password("new-pass", user.password_hash)
    finally:
        await engine.dispose()
