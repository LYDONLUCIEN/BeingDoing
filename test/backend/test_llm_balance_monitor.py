"""
LLM 余额监控测试（DeepSeek 余额不足提醒）
"""
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src" / "backend"))

from app.models.database import Base
from app.models.feedback import Notification


class _ctxmgr:
    """简单的 async context manager 包装，让 fixture session 能被 service 使用"""

    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        return False


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


def _patch_db(monkeypatch, db_session):
    monkeypatch.setattr(
        "app.services.llm_balance_monitor.AsyncSessionLocal",
        lambda: _ctxmgr(db_session),
    )


def _patch_admins(monkeypatch, admin_ids=("admin-1", "admin-2")):
    async def _fake(db):
        return list(admin_ids)

    monkeypatch.setattr("app.services.llm_balance_monitor._get_super_admin_ids", _fake)


def _balance_result(total_balance, threshold=10.0, available=True):
    return {
        "available": available,
        "total_balance": total_balance,
        "currency": "CNY",
        "threshold": threshold,
        "is_low": available and total_balance is not None and total_balance < threshold,
        "checked_at": "2026-09-06T00:00:00+00:00",
        "error": None if available else "mock failure",
    }


def _patch_query(monkeypatch, result):
    async def _fake():
        return result

    monkeypatch.setattr("app.services.llm_balance_monitor.query_llm_balance", _fake)


async def _notif_count(db_session):
    q = await db_session.execute(
        select(func.count(Notification.id)).where(
            Notification.type == "llm_balance_low"
        )
    )
    return int(q.scalar_one())


@pytest.mark.asyncio
async def test_low_balance_notifies_all_super_admins(db_session, monkeypatch):
    """余额低于阈值 → 所有 super_admin 收到 llm_balance_low 站内信"""
    from app.services.llm_balance_monitor import scan_llm_balance

    _patch_db(monkeypatch, db_session)
    _patch_admins(monkeypatch, ("admin-1", "admin-2"))
    _patch_query(monkeypatch, _balance_result(5.2))

    stats = await scan_llm_balance()

    assert stats["available"] is True
    assert stats["is_low"] is True
    assert stats["notified"] == 2
    assert await _notif_count(db_session) == 2

    q = await db_session.execute(
        select(Notification).where(Notification.type == "llm_balance_low")
    )
    notif = q.scalars().first()
    assert "¥5.20" in notif.content
    assert "¥10.00" in notif.content
    assert "充值" in notif.content


@pytest.mark.asyncio
async def test_low_balance_idempotent_same_day(db_session, monkeypatch):
    """当天幂等：重复扫描不重复发"""
    from app.services.llm_balance_monitor import scan_llm_balance

    _patch_db(monkeypatch, db_session)
    _patch_admins(monkeypatch, ("admin-1",))
    _patch_query(monkeypatch, _balance_result(5.2))

    stats1 = await scan_llm_balance()
    stats2 = await scan_llm_balance()

    assert stats1["notified"] == 1
    assert stats2["notified"] == 0
    assert stats2["skipped_already_notified"] is True
    assert await _notif_count(db_session) == 1


@pytest.mark.asyncio
async def test_sufficient_balance_no_notification(db_session, monkeypatch):
    """余额充足 → 不发通知"""
    from app.services.llm_balance_monitor import scan_llm_balance

    _patch_db(monkeypatch, db_session)
    _patch_admins(monkeypatch)
    _patch_query(monkeypatch, _balance_result(88.0))

    stats = await scan_llm_balance()

    assert stats["available"] is True
    assert stats["is_low"] is False
    assert stats["notified"] == 0
    assert await _notif_count(db_session) == 0


@pytest.mark.asyncio
async def test_query_failure_no_notification(db_session, monkeypatch):
    """查询失败（网络/401）→ 不发通知"""
    from app.services.llm_balance_monitor import scan_llm_balance

    _patch_db(monkeypatch, db_session)
    _patch_admins(monkeypatch)
    _patch_query(monkeypatch, _balance_result(None, available=False))

    stats = await scan_llm_balance()

    assert stats["available"] is False
    assert stats["notified"] == 0
    assert await _notif_count(db_session) == 0


@pytest.mark.asyncio
async def test_non_deepseek_provider_skipped(monkeypatch):
    """非 deepseek provider → 余额查询直接返回不可用"""
    from app.core.llmapi.resolver import ResolvedConfig
    from app.services.llm_balance_monitor import query_llm_balance

    monkeypatch.setattr(
        "app.services.llm_balance_monitor.resolver.get_default_config",
        lambda: ResolvedConfig(
            provider="kimi", model="k1", base_url=None, api_key="sk-x",
            config_id=None, source="env",
        ),
    )

    result = await query_llm_balance()

    assert result["available"] is False
    assert "kimi" in result["error"]


@pytest.mark.asyncio
async def test_query_deepseek_balance_parsing(monkeypatch):
    """DeepSeek /user/balance 响应解析：汇总 CNY total_balance 并判定低余额"""
    from app.core.llmapi.resolver import ResolvedConfig
    from app.services.llm_balance_monitor import query_llm_balance

    monkeypatch.setattr(
        "app.services.llm_balance_monitor.resolver.get_default_config",
        lambda: ResolvedConfig(
            provider="deepseek", model="deepseek-v4-pro",
            base_url="https://api.deepseek.com", api_key="sk-x",
            config_id=None, source="env",
        ),
    )

    class _Resp:
        status_code = 200

        def json(self):
            return {
                "is_available": True,
                "balance_infos": [
                    {"currency": "CNY", "total_balance": "3.50",
                     "granted_balance": "0.00", "topped_up_balance": "3.50"},
                    {"currency": "USD", "total_balance": "99.00",
                     "granted_balance": "0.00", "topped_up_balance": "99.00"},
                ],
            }

    class _Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, headers=None):
            assert url == "https://api.deepseek.com/user/balance"
            assert headers["Authorization"] == "Bearer sk-x"
            return _Resp()

    monkeypatch.setattr(
        "app.services.llm_balance_monitor.httpx.AsyncClient", _Client
    )

    result = await query_llm_balance()

    assert result["available"] is True
    assert result["total_balance"] == 3.50  # 只汇总 CNY，忽略 USD
    assert result["is_low"] is True  # 3.50 < 默认阈值 10.0
    assert result["error"] is None
