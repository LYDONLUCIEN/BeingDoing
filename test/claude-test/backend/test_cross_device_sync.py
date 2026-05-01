"""O-06：跨设备/清缓存恢复

验证：
- 删除对话后刷新，该对话不再出现（report_registry 层面）
- 跨设备登录后 Journey 状态一致（user_id 维度数据读取）
- 清缓存后不丢失已保存数据（文件持久化验证）

策略：全部通过后端 API/工具函数直接测试，不需要前端 dev server 或 Playwright。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.utils.report_registry import ReportRegistry, STEP_IDS
from app.utils.rumination_progress import (
    load_rumination_progress,
    save_rumination_progress,
)


# ── helpers ──────────────────────────────────────────────────────────

def _make_registry(tmp_path) -> ReportRegistry:
    return ReportRegistry(base_dir=str(tmp_path))


def _make_reports_root(tmp_path: Path) -> Path:
    reports_root = tmp_path / "reports"
    reports_root.mkdir(parents=True, exist_ok=True)
    return reports_root


# ── O-06: 对话删除后不再出现 ────────────────────────────────────────

class TestSessionDeletion:
    def test_o06_remove_session_from_report(self, tmp_path):
        """从 report 中移除 session 后，该 session 不再出现。"""
        registry = _make_registry(tmp_path)
        record = registry.ensure_report("CODE1", "u1")
        report_id = record.get("report_id")

        # 绑定两个 session
        registry.bind_session(report_id, "values", "sess-001")
        registry.bind_session(report_id, "values", "sess-002")

        rec = registry.get_report_by_id(report_id)
        assert "sess-001" in rec["steps"]["values"]["session_ids"]
        assert "sess-002" in rec["steps"]["values"]["session_ids"]

        # 删除 sess-001
        registry.remove_session(report_id, "values", "sess-001")

        rec = registry.get_report_by_id(report_id)
        assert "sess-001" not in rec["steps"]["values"]["session_ids"]
        assert "sess-002" in rec["steps"]["values"]["session_ids"]

    def test_o06_remove_selected_session_clears_selection(self, tmp_path):
        """删除已选中的 session 后，selected_session_id 被清空或指向下一个。"""
        registry = _make_registry(tmp_path)
        record = registry.ensure_report("CODE1", "u1")
        report_id = record.get("report_id")

        registry.bind_session(report_id, "values", "sess-001")
        registry.bind_session(report_id, "values", "sess-002")
        registry.select_session(report_id, "values", "sess-001")

        rec = registry.get_report_by_id(report_id)
        assert rec["steps"]["values"]["selected_session_id"] == "sess-001"

        # 删除已选中的 sess-001
        registry.remove_session(report_id, "values", "sess-001")
        rec = registry.get_report_by_id(report_id)

        # selected_session_id 应被清除或指向剩余的 session
        if rec["steps"]["values"]["selected_session_id"]:
            assert rec["steps"]["values"]["selected_session_id"] == "sess-002"
        else:
            assert rec["steps"]["values"]["selected_session_id"] is None


# ── O-06: 跨设备 Journey 状态一致 ──────────────────────────────────

class TestCrossDeviceJourneyState:
    def test_o06_same_user_same_report_data(self, tmp_path):
        """同一 user_id + activation_code 得到同一份 report。"""
        registry = _make_registry(tmp_path)

        record_1 = registry.ensure_report("CODE1", "user_001")
        report_id_1 = record_1.get("report_id")

        record_2 = registry.ensure_report("CODE1", "user_001")
        report_id_2 = record_2.get("report_id")

        # 同一对 (code, user) 应返回同一 report
        assert report_id_1 == report_id_2

    def test_o06_different_users_separate_reports(self, tmp_path):
        """不同 user_id 对同一激活码有各自的 report。"""
        registry = _make_registry(tmp_path)

        record_1 = registry.ensure_report("CODE1", "user_001")
        report_id_1 = record_1.get("report_id")

        record_2 = registry.ensure_report("CODE1", "user_002")
        report_id_2 = record_2.get("report_id")

        # 不同用户有独立 report
        assert report_id_1 != report_id_2

    def test_o06_progress_persists_after_reload(self, tmp_path):
        """重新加载 rumination progress 后数据不变（模拟清缓存后恢复）。"""
        reports_root = _make_reports_root(tmp_path)
        report_id = "r1"

        # 第一次保存
        save_rumination_progress(
            reports_root, report_id,
            main_section="filter",
            filter_step=3,
        )

        # 模拟"清缓存"——重新加载
        loaded = load_rumination_progress(reports_root, report_id)
        assert loaded["main_section"] == "filter"
        assert loaded["filter_step"] == 3

        # 模拟跨设备——再次读取（数据在服务端，不在客户端缓存）
        loaded_again = load_rumination_progress(reports_root, report_id)
        assert loaded_again["main_section"] == "filter"
        assert loaded_again["filter_step"] == 3

    def test_o06_report_record_persists_across_loads(self, tmp_path):
        """report record.json 多次加载一致性。"""
        registry = _make_registry(tmp_path)
        record = registry.ensure_report("CODE1", "u1")
        report_id = record.get("report_id")

        registry.bind_session(report_id, "values", "sess-001")
        registry.select_session(report_id, "values", "sess-001")

        # 多次读取，数据一致
        rec1 = registry.get_report_by_id(report_id)
        rec2 = registry.get_report_by_id(report_id)
        assert rec1["steps"]["values"]["selected_session_id"] == \
               rec2["steps"]["values"]["selected_session_id"]
        assert rec1["report_id"] == rec2["report_id"] == report_id

    def test_o06_activation_code_lookup_returns_record(self, tmp_path):
        """通过 (activation_code, user_id) 查找 report，不受缓存影响。"""
        registry = _make_registry(tmp_path)

        # 第一次创建
        record_1 = registry.ensure_report("CODE1", "u1")
        report_id = record_1.get("report_id")
        registry.bind_session(report_id, "values", "sess-001")
        registry.select_session(report_id, "values", "sess-001")
        registry.lock_previous_step_when_entering(report_id, "strengths")

        # 后续通过 get_by_activation_user 查找
        found = registry.get_by_activation_user("CODE1", "u1")
        assert found is not None
        assert found["report_id"] == report_id
        assert found["steps"]["values"]["locked"] is True
