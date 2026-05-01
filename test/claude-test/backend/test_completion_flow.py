"""S-01："完成并继续"竞态

验证：
- 点击"完成并继续"一次即可前进
- 无竞态导致的状态不一致（stepLocked / reportSelectedThreadId / session 保存时机）
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.utils.report_registry import (
    ReportRegistry,
    STEP_IDS,
    STEP_ORDER,
)


# ── helpers ──────────────────────────────────────────────────────────

def _make_registry(tmp_path) -> ReportRegistry:
    return ReportRegistry(base_dir=str(tmp_path))


def _setup_report_for_lock_test(tmp_path) -> tuple:
    """创建一个 report，为 values step 设定会话并选中，返回 (registry, report_id)。

    此后可以调用 lock_previous_step_when_entering(report_id, "strengths")
    来测试锁定逻辑。
    """
    registry = _make_registry(tmp_path)
    record = registry.ensure_report("CODE1", "u1")
    report_id = record.get("report_id")
    assert report_id

    registry.bind_session(report_id, "values", "sess-v1")
    registry.select_session(report_id, "values", "sess-v1")
    return registry, report_id


# ── S-01 tests ──────────────────────────────────────────────────────

class TestCompletionFlow:
    def test_s01_lock_and_advance_sequential(self, tmp_path):
        """顺序调用 lock + select session → 状态一致。"""
        registry, report_id = _setup_report_for_lock_test(tmp_path)

        # 锁定 values，然后为 strengths 绑定并选中
        result = registry.lock_previous_step_when_entering(report_id, "strengths")
        assert result["steps"]["values"]["locked"] is True

        registry.bind_session(report_id, "strengths", "sess-s1")
        registry.select_session(report_id, "strengths", "sess-s1")

        rec = registry.get_report_by_id(report_id)
        assert rec["steps"]["strengths"]["selected_session_id"] == "sess-s1"
        assert rec["steps"]["strengths"]["locked"] is False
        assert rec["steps"]["values"]["locked"] is True

    def test_s01_lock_step_does_not_affect_later_steps(self, tmp_path):
        """锁定 values 不影响 strengths/purpose 等后续 step。"""
        registry, report_id = _setup_report_for_lock_test(tmp_path)

        registry.lock_previous_step_when_entering(report_id, "strengths")

        rec = registry.get_report_by_id(report_id)
        assert rec["steps"]["values"]["locked"] is True
        for sid in ["strengths", "interests", "purpose", "rumination"]:
            assert rec["steps"][sid]["locked"] is False

    def test_s01_double_lock_same_step_is_idempotent(self, tmp_path):
        """对同一步骤连续 lock 两次，结果是幂等的。"""
        registry, report_id = _setup_report_for_lock_test(tmp_path)

        registry.lock_previous_step_when_entering(report_id, "strengths")
        registry.lock_previous_step_when_entering(report_id, "strengths")

        rec = registry.get_report_by_id(report_id)
        assert rec["steps"]["values"]["locked"] is True

    def test_s01_race_condition_protection(self, tmp_path):
        """并发调用 lock_previous_step_when_entering，结果应一致（不丢锁）。

        注：lock_previous_step_when_entering 内部有文件锁保护。
        此处用线程模拟并发，最终 values 应始终被锁定。
        """
        registry, report_id = _setup_report_for_lock_test(tmp_path)

        def lock_op():
            try:
                registry.lock_previous_step_when_entering(report_id, "strengths")
            except ValueError:
                pass

        # 5 个线程并发调用
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(lock_op) for _ in range(5)]
            for f in futures:
                f.result()

        rec = registry.get_report_by_id(report_id)
        assert rec["steps"]["values"]["locked"] is True
        assert rec["steps"]["strengths"]["locked"] is False
