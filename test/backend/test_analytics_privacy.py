"""点赞原文是用户私有数据；HTTP 回归覆盖匿名访问和跨用户读取、取消。"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import security
from app.api.v1 import analytics, auth
from app.models.analytics import AnalyticsLike
from app.models.database import Base
from app.services import analytics_service


@pytest.fixture
async def api(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(analytics_service, "AsyncSessionLocal", sessions)
    async with sessions() as db:
        db.add_all(
            [
                AnalyticsLike(
                    user_id="alice",
                    session_id="a",
                    message_id="only-alice",
                    content_snapshot="Alice private",
                    activation_code="CODE-A",
                ),
                AnalyticsLike(
                    user_id="bob",
                    session_id="b",
                    message_id="only-bob",
                    content_snapshot="Bob private",
                    activation_code="CODE-B",
                ),
            ]
        )
        await db.commit()
    app = FastAPI()
    app.include_router(analytics.router, prefix="/api/v1")
    yield app
    await engine.dispose()


@pytest.mark.parametrize(
    "path", ["/likes", "/likes/check?message_ids=only-alice", "/likes/message/only-alice"]
)
async def test_anonymous_cannot_read_liked_content(api, path):
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics" + path)
        assert response.status_code == 401


async def test_likes_are_scoped_to_the_authenticated_user(api):
    api.dependency_overrides[auth.get_current_user] = lambda: {"user_id": "bob"}
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/likes")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 1
        assert data["records"][0]["content_snapshot"] == "Bob private"
        response = await client.get("/api/v1/analytics/likes", params={"activation_code": "CODE-A"})
        assert response.json()["data"]["total"] == 0
        response = await client.get("/api/v1/analytics/likes/message/only-alice")
        assert response.status_code == 404
        response = await client.get(
            "/api/v1/analytics/likes/check", params={"message_ids": "only-alice,only-bob"}
        )
        assert response.json()["data"] == {"only-alice": False, "only-bob": True}
        response = await client.post("/api/v1/analytics/unlike", json={"message_id": "only-alice"})
        assert response.json()["data"]["removed"] is False
        api.dependency_overrides[auth.get_current_user] = lambda: {"user_id": "alice"}
        response = await client.get("/api/v1/analytics/likes/message/only-alice")
        assert response.json()["data"]["content"] == "Alice private"


@pytest.mark.parametrize(
    "owner, session_id, expected",
    [
        ("alice", "root-session", 200),
        ("alice", "CODE-A", 200),
        ("bob", "root-session", 403),
        (None, "root-session", 403),
        ("alice", "unrelated-session", 403),
    ],
)
async def test_like_requires_a_bound_owned_exploration(
    api, monkeypatch, owner, session_id, expected
):
    record = SimpleNamespace(
        owner_user_id=owner,
        owner_email=None,
        code="CODE-A",
        session_id="legacy-session",
        activation_session_id="root-session",
    )
    manager = SimpleNamespace(is_owner=lambda rec, user: rec.owner_user_id == user["user_id"])
    monkeypatch.setattr(security, "get_activation_with_manager", lambda code: (manager, record))
    api.dependency_overrides[auth.get_current_user] = lambda: {"user_id": "alice"}
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/analytics/like",
            json={
                "session_id": session_id,
                "activation_code": "CODE-A",
                "message_id": "new-message",
                "content_snapshot": "my content",
            },
        )
        assert response.status_code == expected
        if expected == 200:
            response = await client.get("/api/v1/analytics/likes/message/new-message")
            assert response.json()["data"]["content"] == "my content"
