"""S-08 + S-10：Rumination 回看 + "不再提醒"持久化

S-08 验证：
- 五轮结束后回看 Rumination，默认展示 step7 的只读结果表
- 无 step7 数据时，降级到最大已到达 step

S-10 验证：
- 勾选"不再提醒"后，同一激活码+phase 的已完成提醒不再弹出
- 持久化：刷新页面或重开会话后仍生效
- 重新填写（onRefill）后重置
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.utils.rumination_progress import (
    load_rumination_progress,
    save_rumination_progress,
    merge_rumination_progress_fields,
    is_neg_gate_triggered,
    mark_neg_gate_triggered,
    clear_neg_gate_triggered_step,
    max_reached_filter_step,
    DEFAULT_PROGRESS,
    MAIN_SECTIONS,
)


# ── helpers ──────────────────────────────────────────────────────────

def _make_reports_root(tmp_path: Path) -> Path:
    """创建 reports 目录结构。"""
    reports_root = tmp_path / "reports"
    reports_root.mkdir(parents=True, exist_ok=True)
    return reports_root


def _create_progress_file(reports_root: Path, report_id: str, data: dict):
    """直接写入 progress 文件。"""
    report_dir = reports_root / report_id
    report_dir.mkdir(parents=True, exist_ok=True)
    progress_file = report_dir / "rumination_progress.json"
    progress_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ── S-08: Rumination 回看 step7 降级 ──────────────────────────────

class TestRuminationRecall:
    def test_s08_step7_exists_in_snapshots_returns_step7(self, tmp_path):
        """有 step7 snapshot → max_reached 返回 7。"""
        reports_root = _make_reports_root(tmp_path)
        report_id = "r1"

        snapshots = {
            "1": {"submitted": True, "rows": [{"id": 1}]},
            "2": {"submitted": True, "rows": [{"id": 2}]},
            "7": {"submitted": True, "rows": [{"id": 7}]},
        }
        assert max_reached_filter_step(snapshots) == 7

    def test_s08_no_step7_falls_back_to_max_reached(self, tmp_path):
        """无 step7 → 降级到最大已到达 step。"""
        snapshots = {
            "1": {"submitted": True},
            "3": {"submitted": True},
            "5": {"submitted": True},
        }
        assert max_reached_filter_step(snapshots) == 5

    def test_s08_no_snapshots_returns_empty(self):
        """无 snapshot → max_reached 返回 0。"""
        assert max_reached_filter_step({}) == 0
        assert max_reached_filter_step(None) == 0

    def test_s08_progress_main_section_end_state(self, tmp_path):
        """main_section=end 时标识 rumination 阶段完成。"""
        reports_root = _make_reports_root(tmp_path)
        report_id = "r1"

        save_rumination_progress(
            reports_root, report_id,
            main_section="end",
            filter_step=7,
        )

        progress = load_rumination_progress(reports_root, report_id)
        assert progress["main_section"] == "end"
        assert progress["filter_step"] == 7

    def test_s08_progress_default_values(self, tmp_path):
        """无文件时返回默认值。"""
        reports_root = _make_reports_root(tmp_path)

        progress = load_rumination_progress(reports_root, "nonexistent")
        assert progress["main_section"] == "opening"
        assert progress["filter_step"] == 0
        assert progress["neg_gate_triggered_steps"] == []


# ── S-10: "不再提醒"持久化 ────────────────────────────────────────

class TestNegGateTriggered:
    def test_s10_not_triggered_initially(self, tmp_path):
        reports_root = _make_reports_root(tmp_path)
        report_id = "r1"

        progress = load_rumination_progress(reports_root, report_id)
        assert is_neg_gate_triggered(progress, 1) is False
        assert is_neg_gate_triggered(progress, 5) is False

    def test_s10_mark_triggered_returns_true(self, tmp_path):
        reports_root = _make_reports_root(tmp_path)
        report_id = "r1"

        progress = mark_neg_gate_triggered(reports_root, report_id, 3)
        assert is_neg_gate_triggered(progress, 3) is True

        # 持久化后重新加载也应为 True
        reloaded = load_rumination_progress(reports_root, report_id)
        assert is_neg_gate_triggered(reloaded, 3) is True

    def test_s10_clear_triggered_returns_false(self, tmp_path):
        reports_root = _make_reports_root(tmp_path)
        report_id = "r1"

        mark_neg_gate_triggered(reports_root, report_id, 3)
        progress = clear_neg_gate_triggered_step(reports_root, report_id, 3)
        assert is_neg_gate_triggered(progress, 3) is False

        # 持久化验证
        reloaded = load_rumination_progress(reports_root, report_id)
        assert is_neg_gate_triggered(reloaded, 3) is False

    def test_s10_different_steps_independent(self, tmp_path):
        """不同 step 的触发标记独立。"""
        reports_root = _make_reports_root(tmp_path)
        report_id = "r1"

        mark_neg_gate_triggered(reports_root, report_id, 2)
        mark_neg_gate_triggered(reports_root, report_id, 5)

        progress = load_rumination_progress(reports_root, report_id)
        assert is_neg_gate_triggered(progress, 2) is True
        assert is_neg_gate_triggered(progress, 5) is True
        assert is_neg_gate_triggered(progress, 3) is False

    def test_s10_mark_again_is_idempotent(self, tmp_path):
        """重复标记同一 step 不产生重复条目。"""
        reports_root = _make_reports_root(tmp_path)
        report_id = "r1"

        mark_neg_gate_triggered(reports_root, report_id, 3)
        mark_neg_gate_triggered(reports_root, report_id, 3)
        mark_neg_gate_triggered(reports_root, report_id, 3)

        progress = load_rumination_progress(reports_root, report_id)
        assert progress["neg_gate_triggered_steps"].count(3) == 1

    def test_s10_clear_nonexistent_step_no_error(self, tmp_path):
        """清除不存在的 step 标记不报错。"""
        reports_root = _make_reports_root(tmp_path)
        report_id = "r1"

        # 不标记直接清除
        progress = clear_neg_gate_triggered_step(reports_root, report_id, 99)
        assert is_neg_gate_triggered(progress, 99) is False
