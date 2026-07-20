"""
团队分析服务测试（P-E，ADR-0008/0010）

测试场景：
1. 候选报告：自己码直接可选；购买的码须授权+报告就绪；未激活赠品码不可选
2. 创建分析：数量校验（<2 拒绝）、不可选码拒绝、成功创建 generating
3. 生成：mock pdf/LLM → done 存 markdown；异常 → failed 存 error
4. 查询：本人隔离；列表不含正文、详情含正文
5. 报告授权：set_report_authorized 开关与审计
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from app.core.llmapi.base import LLMResponse
from app.models.database import Base
from app.models.user import User
from app.services import team_analysis_service as ta_mod
from app.services.team_analysis_service import AnalysisNotFoundError, TeamAnalysisService
from app.utils.simple_activation_manager import SimpleActivationManager
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
_TestSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)


class FakeRegistry:
    """内存报告注册表：code → record（均 approved）"""

    def list_reports(self):
        return [
            {"report_id": "rpt-own", "activation_code": "OWNCODE123", "user_id": "u1"},
            {"report_id": "rpt-gift", "activation_code": "GIFTCODE12", "user_id": "u2"},
        ]


class FakePdfService:
    def load_cached_markdown(self, report_id):
        return f"# 报告 {report_id} 内容"

    async def generate_markdown_only(self, report_id, vip_level=1):
        return f"# 报告 {report_id} 内容（新生成）"


class FakeProvider:
    def __init__(self, fail=False):
        self.fail = fail

    async def chat(self, messages, **kwargs):
        if self.fail:
            raise RuntimeError("LLM 不可用")
        return LLMResponse(content="# 团队匹配度分析\n\n……", model="fake")


@pytest.fixture(autouse=True)
async def _setup_db(monkeypatch, tmp_path):
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    monkeypatch.setattr(ta_mod, "AsyncSessionLocal", _TestSessionLocal)

    mgr = SimpleActivationManager(base_dir=str(tmp_path / "simple"))
    # u1 自己的码（有报告）
    own = mgr.create_activation(mode="combined", ttl_minutes=365 * 24 * 60,
                                code_type="full", package_type="annual")
    mgr.claim_owner(own.code, {"user_id": "u1", "email": "alice@test.com"})
    records = mgr._load_all()
    records[own.code].code = "OWNCODE123"
    # 直接改名：换 key
    rec = records.pop(own.code)
    rec.code = "OWNCODE123"
    records["OWNCODE123"] = rec
    mgr._save_all(records)

    # u1 购买送给 u2 的赠品码（有报告）
    gift = mgr.create_activation(mode="combined", code_type="full",
                                 package_type="annual", no_expiry=True)
    mgr.set_purchase_source(gift.code, source_order_id="order-1", purchaser_user_id="u1")
    records = mgr._load_all()
    rec = records.pop(gift.code)
    rec.code = "GIFTCODE12"
    records["GIFTCODE12"] = rec
    mgr._save_all(records)
    mgr.claim_owner("GIFTCODE12", {"user_id": "u2", "email": "bob@test.com"})

    # u1 购买的未激活赠品码（无报告）
    idle = mgr.create_activation(mode="combined", code_type="full",
                                 package_type="annual", no_expiry=True)
    mgr.set_purchase_source(idle.code, source_order_id="order-1", purchaser_user_id="u1")

    monkeypatch.setattr(ta_mod, "_activation_manager", lambda: mgr)
    monkeypatch.setattr(ta_mod, "_report_registry", lambda: FakeRegistry())
    monkeypatch.setattr(ta_mod, "_pdf_service", lambda: FakePdfService())
    monkeypatch.setattr(
        "app.utils.activation_audit.append_activation_audit", lambda *a, **k: None
    )

    now = datetime.now(timezone.utc)
    async with _TestSessionLocal() as db:
        db.add_all([
            User(id="u1", email="alice@test.com", username="alice",
                 password_hash="x", is_active=True, created_at=now),
            User(id="u2", email="bob@test.com", username="bob",
                 password_hash="x", is_active=True, created_at=now),
        ])
        await db.commit()

    yield mgr

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _patch_llm(monkeypatch, fail=False):
    monkeypatch.setattr(
        "app.services.team_analysis_service.get_llm_provider_for_vip",
        lambda vip: FakeProvider(fail=fail),
        raising=False,
    )
    # get_llm_provider_for_vip 是函数内 import，直接 patch 源头
    import app.core.llmapi.factory as factory

    monkeypatch.setattr(factory, "get_llm_provider_for_vip", lambda vip: FakeProvider(fail=fail))


# ─── 1. 候选报告 ──────────────────────────────────────────────


def test_candidates_selectability(_setup_db):
    mgr = _setup_db
    items = {c["activation_code"]: c for c in TeamAnalysisService.list_candidates("u1")}

    # 自己的码：有报告即可选
    assert items["OWNCODE123"]["role"] == "self"
    assert items["OWNCODE123"]["selectable"] is True

    # 购买的码：未授权 → 不可选
    assert items["GIFTCODE12"]["role"] == "purchased"
    assert items["GIFTCODE12"]["selectable"] is False
    assert items["GIFTCODE12"]["activated"] is True
    assert items["GIFTCODE12"]["owner_label"] == "b***@test.com"

    # 授权后 → 可选
    mgr.set_report_authorized("GIFTCODE12", True)
    items2 = {c["activation_code"]: c for c in TeamAnalysisService.list_candidates("u1")}
    assert items2["GIFTCODE12"]["selectable"] is True

    # 未激活赠品码：不可选但可见
    idle = next(c for c in items2.values() if c["role"] == "purchased" and not c.get("activated"))
    assert idle["selectable"] is False
    assert idle["has_report"] is False


# ─── 2. 创建分析 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_analysis_validation(_setup_db):
    with pytest.raises(ValueError, match="2-10"):
        await TeamAnalysisService.create_analysis("u1", ["OWNCODE123"])
    with pytest.raises(ValueError, match="不可用于团队分析"):
        await TeamAnalysisService.create_analysis("u1", ["OWNCODE123", "GIFTCODE12"])


@pytest.mark.asyncio
async def test_create_analysis_success(_setup_db):
    mgr = _setup_db
    mgr.set_report_authorized("GIFTCODE12", True)
    analysis = await TeamAnalysisService.create_analysis(
        "u1", ["OWNCODE123", "GIFTCODE12"], title="核心团队"
    )
    assert analysis.status == "generating"
    assert analysis.title == "核心团队"
    assert json.loads(analysis.code_list) == ["GIFTCODE12", "OWNCODE123"]
    assert set(json.loads(analysis.report_ids)) == {"rpt-own", "rpt-gift"}


# ─── 3. 生成 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_generation_success(_setup_db, monkeypatch):
    mgr = _setup_db
    mgr.set_report_authorized("GIFTCODE12", True)
    _patch_llm(monkeypatch)
    analysis = await TeamAnalysisService.create_analysis("u1", ["OWNCODE123", "GIFTCODE12"])

    await TeamAnalysisService.run_generation(analysis.id)

    detail = await TeamAnalysisService.get_my_analysis("u1", analysis.id)
    assert detail["status"] == "done"
    assert "团队匹配度分析" in detail["result_markdown"]


@pytest.mark.asyncio
async def test_run_generation_failure(_setup_db, monkeypatch):
    mgr = _setup_db
    mgr.set_report_authorized("GIFTCODE12", True)
    _patch_llm(monkeypatch, fail=True)
    analysis = await TeamAnalysisService.create_analysis("u1", ["OWNCODE123", "GIFTCODE12"])

    await TeamAnalysisService.run_generation(analysis.id)

    detail = await TeamAnalysisService.get_my_analysis("u1", analysis.id)
    assert detail["status"] == "failed"
    assert "LLM 不可用" in detail["error"]


# ─── 4. 查询 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_and_get_isolation(_setup_db):
    mgr = _setup_db
    mgr.set_report_authorized("GIFTCODE12", True)
    analysis = await TeamAnalysisService.create_analysis("u1", ["OWNCODE123", "GIFTCODE12"])

    items, total = await TeamAnalysisService.list_my_analyses("u1")
    assert total == 1
    assert "result_markdown" not in items[0]  # 列表不含正文

    _, total_u2 = await TeamAnalysisService.list_my_analyses("u2")
    assert total_u2 == 0

    with pytest.raises(AnalysisNotFoundError):
        await TeamAnalysisService.get_my_analysis("u2", analysis.id)


# ─── 5. 报告授权开关 ──────────────────────────────────────────


def test_set_report_authorized(_setup_db):
    mgr = _setup_db
    rec = mgr.set_report_authorized("GIFTCODE12", True, actor={"user_id": "u2"})
    assert rec.report_authorized is True
    # 持久化
    mgr2 = SimpleActivationManager(base_dir=mgr.base_dir)
    assert mgr2.get_activation("GIFTCODE12").report_authorized is True
    # 撤销
    rec2 = mgr.set_report_authorized("GIFTCODE12", False)
    assert rec2.report_authorized is False
