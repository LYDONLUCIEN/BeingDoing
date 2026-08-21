"""xunlu 精简渲染器桥接与 RENDER_ENGINE 分流测试（ADR-0019）。"""

from pathlib import Path
from unittest.mock import patch

import pytest
from app.api.v1.auth import get_current_user
from app.main import app
from app.services import report_xunlu_renderer
from app.services.report_xunlu_renderer import (
    XunluRenderError,
    render_pdf_with_xunlu,
)
from app.services.report_pdf_service import ReportPdfService
from app.utils.report_registry import ReportRegistry
from fastapi.testclient import TestClient

SAMPLE_MD = "# 小明的寻路之旅\n\n## 阅读指南\n\n欢迎。\n\n<div class=\"pb\"></div>\n\n### 第一章 价值观分析\n\n内容。\n"


@pytest.fixture()
def report_service(tmp_path):
    """带临时 base_dir 的 ReportPdfService + 一条预置 record。"""
    registry = ReportRegistry(base_dir=str(tmp_path))
    registry.save_record(
        {
            "report_id": "rid-1",
            "report_signature": "signature_2",
            "report_markdown_generated_at": "2026-07-31T10:09:02.168467+00:00",
        }
    )
    return ReportPdfService(base_dir=str(tmp_path))


def test_render_engine_default_is_weasyprint():
    from app.config.settings import settings

    # 未设置环境变量时必须是 weasyprint（现状行为不变）
    assert settings.RENDER_ENGINE == "weasyprint"


def test_dispatch_to_xunlu_with_meta(report_service, monkeypatch):
    """运行时引擎=xunlu 时 _markdown_to_pdf 分流，且签名/日期元数据正确映射。"""
    monkeypatch.setattr(
        "app.services.report_render_config.get_render_engine", lambda: "xunlu"
    )
    captured = {}

    def fake_render(md, **kwargs):
        captured.update(kwargs)
        return b"%PDF-fake"

    monkeypatch.setattr(report_xunlu_renderer, "render_pdf_with_xunlu", fake_render)
    result = report_service._markdown_to_pdf(SAMPLE_MD, report_id="rid-1")
    assert result == b"%PDF-fake"
    # record.json 的 signature_2 → 渲染器方案 02；生成时间 → 中文日期
    assert captured["signature"] == "02"
    assert captured["date"] == "2026 年 07 月 31 日"


def test_dispatch_weasyprint_keeps_legacy(report_service, monkeypatch):
    """运行时引擎=weasyprint 时不触碰 xunlu 渲染器。"""
    monkeypatch.setattr(
        "app.services.report_render_config.get_render_engine", lambda: "weasyprint"
    )
    called = []
    monkeypatch.setattr(
        report_xunlu_renderer,
        "render_pdf_with_xunlu",
        lambda *a, **k: called.append(1) or b"",
    )
    # 不实际调 WeasyPrint（重依赖），只验证分流判断发生在 weasyprint 分支之前
    with patch.object(report_service, "_markdown_to_pdf_via_xunlu") as spy:
        try:
            report_service._markdown_to_pdf(SAMPLE_MD, report_id="rid-1")
        except Exception:
            pass  # weasyprint 渲染本身可能在测试环境失败，与本测试无关
    spy.assert_not_called()
    assert not called


def test_render_entry_missing_raises(monkeypatch, tmp_path):
    """渲染器未构建时抛出带构建提示的错误。"""
    from app.config.settings import settings

    monkeypatch.setattr(settings, "REPORT_RENDERER_DIR", str(tmp_path))
    with pytest.raises(XunluRenderError, match="npm install"):
        render_pdf_with_xunlu(SAMPLE_MD)


def _client(user_id: str) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": user_id,
        "email": f"{user_id}@example.com",
    }
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_render_from_md_non_super_admin_403():
    client = _client("user-1")
    with patch("app.api.v1.admin._is_super_admin", return_value=False):
        res = client.post("/api/v1/admin/render-pdf-from-md", json={"markdown": SAMPLE_MD})
    assert res.status_code == 403


def test_render_from_md_success():
    client = _client("admin-1")
    with patch("app.api.v1.admin._is_super_admin", return_value=True):
        with patch.object(
            report_xunlu_renderer, "render_pdf_with_xunlu", return_value=b"%PDF-fake"
        ):
            res = client.post(
                "/api/v1/admin/render-pdf-from-md",
                json={"markdown": SAMPLE_MD, "nickname": "小明", "signature": "01"},
            )
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content == b"%PDF-fake"


def test_render_from_md_empty_400():
    client = _client("admin-1")
    with patch("app.api.v1.admin._is_super_admin", return_value=True):
        res = client.post("/api/v1/admin/render-pdf-from-md", json={"markdown": "   "})
    assert res.status_code == 400


# ── 渲染引擎运行时配置（ADR-0019）─────────────────────────────────


def test_render_config_set_and_get(tmp_path, monkeypatch):
    from app.services import report_render_config as cfg

    monkeypatch.setattr(cfg, "_config_path", lambda: tmp_path / "report_render_config.json")
    # 无配置文件时回退 env 默认 weasyprint
    assert cfg.get_render_engine() == "weasyprint"
    cfg.set_render_engine("xunlu")
    assert cfg.get_render_engine() == "xunlu"
    cfg.set_render_engine("weasyprint")
    assert cfg.get_render_engine() == "weasyprint"
    with pytest.raises(ValueError):
        cfg.set_render_engine("unknown")


def test_render_config_endpoints(tmp_path, monkeypatch):
    from app.services import report_render_config as cfg

    monkeypatch.setattr(cfg, "_config_path", lambda: tmp_path / "report_render_config.json")
    client = _client("admin-1")
    with patch("app.api.v1.admin._is_super_admin", return_value=True):
        res = client.get("/api/v1/admin/report-render-config")
        assert res.status_code == 200
        assert res.json()["data"]["engine"] == "weasyprint"
        res = client.post("/api/v1/admin/report-render-config", json={"engine": "xunlu"})
        assert res.status_code == 200
        assert res.json()["data"]["engine"] == "xunlu"
        res = client.post("/api/v1/admin/report-render-config", json={"engine": "bad"})
        assert res.status_code == 400


def test_render_config_non_super_admin_403():
    client = _client("user-1")
    with patch("app.api.v1.admin._is_super_admin", return_value=False):
        assert client.get("/api/v1/admin/report-render-config").status_code == 403
        assert client.post("/api/v1/admin/report-render-config", json={"engine": "xunlu"}).status_code == 403
        assert client.get("/api/v1/admin/reports/generating").status_code == 403


def test_generating_reports_endpoint():
    from app.services import report_pdf_service

    report_pdf_service.try_acquire_generation("rid-gen-1")
    try:
        client = _client("admin-1")
        with patch("app.api.v1.admin._is_super_admin", return_value=True):
            res = client.get("/api/v1/admin/reports/generating")
        assert res.status_code == 200
        assert "rid-gen-1" in res.json()["data"]["report_ids"]
    finally:
        report_pdf_service.release_generation("rid-gen-1")


def _patch_simple_base(monkeypatch, tmp_path: Path) -> Path:
    """把 ReportRegistry/ReportPdfService 的默认数据根指向临时目录。"""
    base = tmp_path / "simple"
    monkeypatch.setattr("app.utils.report_registry.get_simple_base_dir", lambda: base)
    monkeypatch.setattr("app.services.report_pdf_service.get_simple_base_dir", lambda: base)
    return base


def _make_report(base: Path, report_id: str = "rid-render") -> None:
    """造一条带 markdown 缓存的报告记录。"""
    registry = ReportRegistry(base_dir=str(base))
    registry.save_record(
        {"report_id": report_id, "report_markdown_generated_at": "2026-08-20T00:00:00+00:00"}
    )
    report_dir = base / "reports" / report_id
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "report_markdown.md").write_text(SAMPLE_MD, encoding="utf-8")


def test_admin_render_pdf_non_super_admin_403():
    client = _client("user-1")
    with patch("app.api.v1.admin._is_super_admin", return_value=False):
        res = client.get("/api/v1/admin/reports/rid-render/render-pdf")
    assert res.status_code == 403


def test_admin_render_pdf_no_markdown_409(tmp_path, monkeypatch):
    base = _patch_simple_base(monkeypatch, tmp_path)
    _make_report(base)
    # report 存在但无 markdown 缓存 → 409
    (base / "reports" / "rid-render" / "report_markdown.md").unlink()
    client = _client("admin-1")
    with patch("app.api.v1.admin._is_super_admin", return_value=True):
        res = client.get("/api/v1/admin/reports/rid-render/render-pdf")
    assert res.status_code == 409


def test_admin_render_pdf_success(tmp_path, monkeypatch):
    base = _patch_simple_base(monkeypatch, tmp_path)
    _make_report(base)
    client = _client("admin-1")
    with patch("app.api.v1.admin._is_super_admin", return_value=True):
        with patch.object(
            ReportPdfService, "_markdown_to_pdf_via_xunlu", return_value=b"%PDF-fake"
        ) as spy:
            res = client.get("/api/v1/admin/reports/rid-render/render-pdf")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content == b"%PDF-fake"
    spy.assert_called_once()
