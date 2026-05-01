"""S-05 + S-06：Journey 自动定位最新 phase + 回看（只读）vs 重填路径

S-05 验证：
- 清缓存后重新登录，Journey 自动定位到最新进度的 phase
- Journey 节点显示正确的完成/当前/锁定状态

S-06 验证：
- 回看已完成阶段：表格只读，右侧对话恢复到该阶段消息边界
- 回看后点"继续"，正确前进到当前阶段，不影响已有数据
- 重新填写：显式重置当前阶段快照，允许重新填写
"""
from __future__ import annotations

import pytest

from app.utils.report_registry import (
    ReportRegistry,
    compute_explore_resume,
    STEP_IDS,
    STEP_ORDER,
)


# ── helpers ──────────────────────────────────────────────────────────

def _make_registry(tmp_path) -> ReportRegistry:
    return ReportRegistry(base_dir=str(tmp_path))


def _make_base_record(report_id="r1", code="C1", uid="u1") -> dict:
    """创建基础的空 record dict（5 个 step 全部 unlocked）。"""
    return {
        "report_id": report_id,
        "activation_code": code,
        "user_id": uid,
        "status": "in_progress",
        "steps": {
            sid: {
                "step_id": sid,
                "selected_session_id": None,
                "locked": False,
                "session_ids": [],
            }
            for sid in STEP_IDS
        },
    }


# ── S-05: compute_explore_resume ───────────────────────────────────

class TestComputeExploreResume:
    def test_s05_resume_returns_current_step_when_no_progress(self):
        """所有 step 均未 lock → 回到第一个 step。"""
        record = _make_base_record()
        result = compute_explore_resume(record)

        assert result["resume_phase"] == "values"
        assert "values" in result["unlocked_phases"]

    def test_s05_resume_returns_first_unlocked_after_completed_steps(self):
        """values 已 lock → resume 到 strengths。"""
        record = _make_base_record()
        record["steps"]["values"]["locked"] = True
        result = compute_explore_resume(record)

        assert result["resume_phase"] == "strengths"
        assert "values" in result["unlocked_phases"]
        assert "strengths" in result["unlocked_phases"]

    def test_s05_resume_all_locked_returns_last_step(self):
        """全部 lock → resume 到最后一步 rumination。"""
        record = _make_base_record()
        for sid in STEP_IDS:
            record["steps"][sid]["locked"] = True
        result = compute_explore_resume(record)

        assert result["resume_phase"] == "rumination"
        assert len(result["unlocked_phases"]) == len(STEP_IDS)

    def test_s05_resume_empty_record_returns_values_step(self):
        """空 record（无 steps）→ 默认 values。"""
        result = compute_explore_resume({})
        assert result["resume_phase"] == "values"
        assert result["unlocked_phases"][0] == "values"

    def test_s05_resume_completed_all_phases_returns_end(self):
        """全部 step 已选定会话 → report_unlocked=True。"""
        record = _make_base_record()
        for sid in STEP_IDS:
            record["steps"][sid]["selected_session_id"] = f"sess-{sid}"
            record["steps"][sid]["locked"] = True
        result = compute_explore_resume(record)

        assert result["resume_phase"] == "rumination"
        assert result["report_unlocked"] is True

    def test_s05_resume_phase_ordering(self):
        """unlocked_phases 的顺序与 STEP_IDS 一致。"""
        record = _make_base_record()
        record["steps"]["values"]["locked"] = True
        record["steps"]["strengths"]["locked"] = True
        result = compute_explore_resume(record)

        # unlocked 应包含 values, strengths, interests
        expected_prefix = STEP_IDS[:3]
        assert result["unlocked_phases"] == list(expected_prefix)

    def test_s05_unlocked_phases_include_current_and_before(self):
        """unlocked_phases 包含 resume_phase 及之前所有 phase。"""
        record = _make_base_record()
        record["steps"]["values"]["locked"] = True
        result = compute_explore_resume(record)

        assert result["resume_phase"] == "strengths"
        assert len(result["unlocked_phases"]) == 2
        assert result["unlocked_phases"] == ["values", "strengths"]


# ── S-06: lock_previous_step_when_entering ─────────────────────────

class TestLockPreviousStep:
    def test_s06_lock_previous_step_when_entering_next(self, tmp_path):
        """进入 strengths 时，values 应被锁定。"""
        registry = _make_registry(tmp_path)
        record = registry.ensure_report("CODE1", "u1")
        report_id = record.get("report_id")
        assert report_id

        # 先为 values 选择会话
        registry.bind_session(report_id, "values", "sess-v1")
        registry.select_session(report_id, "values", "sess-v1")

        # 进入 strengths → 应锁定 values
        result = registry.lock_previous_step_when_entering(report_id, "strengths")
        assert result is not None
        assert result["steps"]["values"]["locked"] is True
        assert result["steps"]["strengths"]["locked"] is False

    def test_s06_lock_previous_step_does_not_lock_current(self, tmp_path):
        """锁定上一步，当前步骤不变。"""
        registry = _make_registry(tmp_path)
        record = registry.ensure_report("CODE1", "u1")
        report_id = record.get("report_id")

        registry.bind_session(report_id, "values", "sess-v1")
        registry.select_session(report_id, "values", "sess-v1")

        result = registry.lock_previous_step_when_entering(report_id, "strengths")
        assert result["steps"]["strengths"]["locked"] is False

    def test_s06_lock_step1_then_step2_step1_locked(self, tmp_path):
        """依次进入 step2、step3 → step1 和 step2 都被锁。"""
        registry = _make_registry(tmp_path)
        record = registry.ensure_report("CODE1", "u1")
        report_id = record.get("report_id")

        # 设定 values
        registry.bind_session(report_id, "values", "sess-v1")
        registry.select_session(report_id, "values", "sess-v1")

        # 进入 strengths → lock values
        registry.lock_previous_step_when_entering(report_id, "strengths")

        # 设定 strengths
        registry.bind_session(report_id, "strengths", "sess-s1")
        registry.select_session(report_id, "strengths", "sess-s1")

        # 进入 interests → lock strengths
        registry.lock_previous_step_when_entering(report_id, "interests")

        rec = registry.get_report_by_id(report_id)
        assert rec["steps"]["values"]["locked"] is True
        assert rec["steps"]["strengths"]["locked"] is True
        assert rec["steps"]["interests"]["locked"] is False

    def test_s06_first_step_never_locked(self, tmp_path):
        """进入第一步（values）不会锁定任何步骤。"""
        registry = _make_registry(tmp_path)
        record = registry.ensure_report("CODE1", "u1")
        report_id = record.get("report_id")

        result = registry.lock_previous_step_when_entering(report_id, "values")
        assert result is not None
        assert result["steps"]["values"]["locked"] is False

    def test_s06_reenter_same_step_not_locked(self, tmp_path):
        """重新进入同一步骤，不会锁定自己。"""
        registry = _make_registry(tmp_path)
        record = registry.ensure_report("CODE1", "u1")
        report_id = record.get("report_id")

        # 设定 values
        registry.bind_session(report_id, "values", "sess-v1")
        registry.select_session(report_id, "values", "sess-v1")

        # 再次进入 values → 不锁定（因为 idx=0，直接 return）
        result = registry.lock_previous_step_when_entering(report_id, "values")
        assert result["steps"]["values"]["locked"] is False
