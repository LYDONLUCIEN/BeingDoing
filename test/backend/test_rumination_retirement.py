"""退役边界：旧沉淀不能继续写入，新沉淀及历史记录彼此独立。"""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.main  # noqa: F401
from app.api.v1 import auth, simple_chat_routes
from app.services.prompt_catalog import build_prompt_catalog


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(simple_chat_routes.router, prefix="/api/v1")
    app.dependency_overrides[auth.get_current_user] = lambda: {"user_id": "member"}
    return TestClient(app)


@pytest.mark.parametrize(
    "path",
    [
        "/message",
        "/message/stream",
        "/init",
        "/thread/reopen",
        "/thread/complete",
        "/conclusion/request",
        "/thread/delete",
    ],
)
def test_old_phase_writes_stop_before_activation_or_llm_access(client, path):
    response = client.post(
        "/api/v1/simple-chat" + path,
        json={
            "activation_code": "missing",
            "phase": "rumination",
            "message": "hello",
            "thread_id": "old",
        },
    )
    assert response.status_code == 410
    assert "rumination-v4" in response.json()["detail"]


@pytest.mark.parametrize(
    "path",
    [
        "rumination-progress",
        "rumination-step-opening",
        "rumination-step-opening-stream",
        "rumination-table-submit",
        "rumination-combo-conclusion",
        "rumination-combo-guide",
        "rumination-combo-matrix-submit",
        "rumination-combo-matrix",
        "rumination-neg-resolve",
        "rumination-get-table",
    ],
)
def test_retired_routes_are_not_published(client, path):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/simple-chat/" + path not in paths
    assert "/api/v1/simple-chat/rumination-v4/create-and-start" in paths


def test_simple_chat_contract_has_no_old_matrix_fields(client):
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    fields = schemas["SimpleChatStreamRequest"]["properties"]
    assert (
        not {"combo_id", "combo_conclusion_action", "rumination_filter_step", "step3_table_action"}
        & fields.keys()
    )


def test_prompt_catalog_uses_current_v4_not_seven_step_prompts():
    catalog = build_prompt_catalog(preview_phase="rumination")
    phase = next(p for p in catalog["phases"] if p["key"] == "rumination")
    assert not phase.get("rumination_steps")
    assert any("rumination_v4_prompt.py" in s.get("source_path", "") for s in phase["sections"])
    assert all(
        item["id"] not in {"rumination_step_addon", "neg_gate_deep_chat"}
        for item in catalog["runtime_injection_catalog"]
    )


def test_version_probe_always_returns_v4_without_legacy_assignment(client, monkeypatch, tmp_path):
    from app.api.v1 import rumination_v4_routes

    monkeypatch.setattr(rumination_v4_routes, "_resolve_v4_ctx", lambda *_: (tmp_path, "report"))
    response = client.get("/api/v1/simple-chat/rumination-v4/version?activation_code=owned")
    assert response.status_code == 200
    assert response.json()["data"] == {
        "version": "v4",
        "source": "current",
        "assigned_at": None,
        "ratio_at_assignment": None,
    }


def test_v4_inputs_prefer_confirmed_cards_then_anchor_then_prior_text(tmp_path):
    from app.utils.rumination_inputs import extract_dimension_inputs

    report = tmp_path / "report"
    report.mkdir()
    (report / "dimension_conclusions.json").write_text(
        json.dumps({"values": {"keywords": ["成长"]}})
    )
    (report / "prior_context_interests.txt").write_text("写作、教育")
    record = {
        "steps": {
            "values": {"anchor_summary": {"goals": "包括稳定等，"}},
            "strengths": {"anchor_summary": {"goals": "包括沟通、分析等，"}},
        }
    }
    values, strengths, interests, purpose, sources = extract_dimension_inputs(
        str(tmp_path), "report", record
    )
    assert values == ["成长"]
    assert strengths == ["沟通", "分析"]
    assert interests == ["写作", "教育"]
    assert purpose == []
    assert sources == {
        "values": "confirmed_card",
        "strengths": "report_anchor",
        "interests": "prior_text",
        "purpose": "none",
    }


def test_legacy_export_reads_existing_data_without_creating_matrix_or_writing(tmp_path):
    from app.utils.legacy_rumination_export import load_raw_rumination_progress
    from app.utils.report_registry import ReportRegistry

    registry = ReportRegistry(base_dir=str(tmp_path))
    report = registry.reports_root / "old"
    report.mkdir(parents=True)
    path = report / "rumination_progress.json"
    original = '{"schema_version": 2, "filter_table": [{"热爱": "写作", "优势": "分析"}]}'
    path.write_text(original)
    result = load_raw_rumination_progress("old", registry)
    assert result == json.loads(original)
    assert "combo_matrix" not in result
    assert path.read_text() == original
    assert not (report / "rumination_v4_progress.json").exists()
    assert load_raw_rumination_progress("missing", registry) is None
    assert not (registry.reports_root / "missing").exists()


@pytest.mark.parametrize("content", ["[]", "null", "invalid"])
def test_legacy_export_ignores_malformed_data_without_rewriting(tmp_path, content):
    from app.utils.legacy_rumination_export import load_raw_rumination_progress
    from app.utils.report_registry import ReportRegistry

    registry = ReportRegistry(base_dir=str(tmp_path))
    report = registry.reports_root / "old"
    report.mkdir(parents=True)
    source = report / "rumination_progress.json"
    source.write_text(content)
    assert load_raw_rumination_progress("old", registry) is None
    assert source.read_text() == content


@pytest.mark.asyncio
async def test_admin_jump_uses_real_sandbox_index_and_preserves_existing_combos(
    monkeypatch, tmp_path
):
    from fastapi import HTTPException

    from app.api.v1 import admin
    from app.services.rumination_v4_service import (
        default_state,
        load_v4_state,
        new_combo_session,
        save_v4_state,
    )
    from app.utils import admin_mock, simple_activation_manager
    from app.utils.report_registry import ReportRegistry
    from app.utils.simple_activation_manager import ActivationRecord, SimpleActivationManager

    production = tmp_path / "production"
    test_root = tmp_path / "test"
    monkeypatch.setattr(simple_activation_manager, "get_simple_base_dir", lambda: production)
    monkeypatch.setattr(simple_activation_manager, "get_simple_test_base_dir", lambda: test_root)
    monkeypatch.setattr(admin_mock, "get_simple_base_dir", lambda: production)
    monkeypatch.setattr(admin, "_assert_admin_sandbox_enabled", lambda: None)
    monkeypatch.setattr(admin, "_is_super_admin", lambda user: user.get("user_id") == "admin")
    # 使用真实双根索引及解析器；只替换账户权限和受控的模拟资料来源。
    common = dict(
        session_id="sandbox-session",
        mode="combined",
        created_at="2026-01-01T00:00:00Z",
        expires_at=None,
        last_activity_at="2026-01-01T00:00:00Z",
    )
    rec = ActivationRecord(
        code="SBXTEST",
        owner_user_id="admin",
        workspace_kind="fork",
        workspace_root="sandboxes/fork1",
        **common,
    )
    SimpleActivationManager(base_dir=str(test_root)).put_activation(rec)
    prod_manager = SimpleActivationManager(base_dir=str(production))
    prod_manager.put_activation(ActivationRecord(code="REALCODE", **common))
    assert prod_manager.get_activation(rec.code) is None
    before = {
        str(p.relative_to(production)): p.read_bytes() for p in production.rglob("*") if p.is_file()
    }
    prior = tmp_path / "mock"
    prior.mkdir()
    (prior / "prior_context_values.txt").write_text("成长")
    monkeypatch.setattr(admin_mock, "_ensure_mock_structure", lambda: None)
    monkeypatch.setattr(admin_mock, "get_mock_prior_dir", lambda: prior)
    monkeypatch.setattr(admin_mock, "load_mock_record_template", lambda: {})
    request = admin.JumpToRuminationRequest(activation_code=rec.code)

    with pytest.raises(HTTPException) as denied:
        await admin.jump_to_rumination(request, {"user_id": "member"})
    assert denied.value.status_code == 403
    with pytest.raises(HTTPException) as unsafe:
        await admin.jump_to_rumination(
            admin.JumpToRuminationRequest(activation_code="REALCODE"), {"user_id": "admin"}
        )
    assert unsafe.value.status_code == 400
    sandbox = test_root / rec.workspace_root
    assert not sandbox.exists()

    registry = ReportRegistry(base_dir=str(sandbox))
    report = registry.ensure_report(
        activation_code=rec.code, user_id="admin", session_id=rec.session_id
    )
    rid = report["report_id"]
    state = default_state()
    state["combo_sessions"] = [new_combo_session("combo_1", "写作", ["分析"])]
    save_v4_state(registry.reports_root, rid, state)
    result = await admin.jump_to_rumination(request, {"user_id": "admin"})
    assert result["data"]["progress"]["combo_sessions"] == state["combo_sessions"]
    assert load_v4_state(registry.reports_root, rid)["combo_sessions"] == state["combo_sessions"]
    assert not (registry.reports_root / rid / "rumination_progress.json").exists()
    assert (sandbox / rec.session_id / "prior_context_values.txt").read_text() == "成长"
    record = registry.get_report_by_id(rid)
    assert all(
        record["steps"][phase]["locked"]
        for phase in ("values", "strengths", "interests", "purpose")
    )
    after = {
        str(p.relative_to(production)): p.read_bytes() for p in production.rglob("*") if p.is_file()
    }
    assert after == before
