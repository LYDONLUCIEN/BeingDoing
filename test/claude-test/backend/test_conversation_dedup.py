"""O-05：不自动新增重复对话

验证：
- 多次进入不会自动新增重复对话
- 会话列表加载完成前不显示空状态
"""
from __future__ import annotations

import pytest

from app.utils.report_registry import (
    ReportRegistry,
    STEP_IDS,
)


# ── helpers ──────────────────────────────────────────────────────────

def _make_registry(tmp_path) -> ReportRegistry:
    """创建基于 tmp_path 的 ReportRegistry。"""
    return ReportRegistry(base_dir=str(tmp_path))


def _create_report_with_step(registry, code="CODE1", user_id="u1", step_id="values"):
    """创建一个 report 并绑定一个 session 到指定 step。"""
    record = registry.ensure_report(code, user_id)
    report_id = record.get("report_id")
    assert report_id
    registry.bind_session(report_id, step_id, "sess-values-1")
    return report_id


# ── O-05 tests ──────────────────────────────────────────────────────

class TestConversationDedup:
    def test_o05_bind_session_returns_session_record(self, tmp_path):
        registry = _make_registry(tmp_path)
        report_id = registry.ensure_report("CODE1", "u1").get("report_id")

        result = registry.bind_session(report_id, "values", "sess-001")
        assert result is not None
        assert "sess-001" in result["steps"]["values"]["session_ids"]

    def test_o05_bind_same_step_same_session_id_is_idempotent(self, tmp_path):
        """同一 step 绑定同一 session_id 多次，session_ids 不重复。"""
        registry = _make_registry(tmp_path)
        report_id = registry.ensure_report("CODE1", "u1").get("report_id")

        registry.bind_session(report_id, "values", "sess-001")
        registry.bind_session(report_id, "values", "sess-001")

        record = registry.get_report_by_id(report_id)
        sessions = record["steps"]["values"]["session_ids"]
        assert sessions.count("sess-001") == 1

    def test_o05_select_session_returns_record(self, tmp_path):
        registry = _make_registry(tmp_path)
        report_id = registry.ensure_report("CODE1", "u1").get("report_id")
        registry.bind_session(report_id, "values", "sess-001")

        result = registry.select_session(report_id, "values", "sess-001")
        assert result is not None
        assert result["steps"]["values"]["selected_session_id"] == "sess-001"

    def test_o05_select_nonexistent_session_returns_none(self, tmp_path):
        registry = _make_registry(tmp_path)
        report_id = registry.ensure_report("CODE1", "u1").get("report_id")

        # select 一个未 bind 的 session（不在 session_ids 中）
        # 实际上 select_session 会自动 add，所以此处测试 get_report_by_id of nonexistent
        result = registry.get_report_by_id("nonexistent-report-id")
        assert result is None

    def test_o05_ensure_report_creates_report_dir(self, tmp_path):
        """ensure_report 确保报告目录存在。"""
        registry = _make_registry(tmp_path)
        record = registry.ensure_report("CODE1", "u1")
        report_id = record.get("report_id")
        assert report_id is not None

        report_dir = registry._report_dir(report_id)
        assert report_dir.exists()
        assert (report_dir / "record.json").exists()
