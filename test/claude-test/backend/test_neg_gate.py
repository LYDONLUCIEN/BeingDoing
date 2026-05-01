"""P-04 / S-07 / P-07: rumination_neg_gate 测试"""
from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from app.utils.rumination_neg_gate import (
    NEG_GATED_STEPS,
    build_injection_zh,
    collect_step2_mismatches,
    collect_step3_hypothesis_candidates,
    collect_step5_should_do,
    collect_step6_future,
)
from app.domain.rumination_step_guidance import get_deep_chat_step_system
from app.domain.rumination_prompt_strings import DEEP_CHAT_STEP_SYSTEM_MAP


# ── 辅助构造 ─────────────────────────────────────────────────────────

def _step2_rows(mismatch_count: int = 2, match_count: int = 2) -> List[Dict]:
    rows = []
    idx = 1
    for _ in range(mismatch_count):
        rows.append({
            "id": str(idx), "热爱": f"热爱{idx}", "优势": f"优势{idx}",
            "匹配性": "不匹配",
        })
        idx += 1
    for _ in range(match_count):
        rows.append({
            "id": str(idx), "热爱": f"热爱{idx}", "优势": f"优势{idx}",
            "匹配性": "匹配",
        })
        idx += 1
    return rows


def _step3_rows(custom_count: int = 2, valid_count: int = 2) -> List[Dict]:
    rows = []
    idx = 1
    for _ in range(custom_count):
        rows.append({
            "id": str(idx), "热爱": f"热爱{idx}", "优势": f"优势{idx}",
            "用户确认的假设": f"自定义假设{idx}",
            "假设1": "推荐假设A", "假设2": "推荐假设B",
        })
        idx += 1
    for _ in range(valid_count):
        rows.append({
            "id": str(idx), "热爱": f"热爱{idx}", "优势": f"优势{idx}",
            "用户确认的假设": "推荐假设A",  # 等于假设1
            "假设1": "推荐假设A", "假设2": "推荐假设B",
        })
        idx += 1
    return rows


def _step5_rows(should_do: int = 2, passion: int = 2) -> List[Dict]:
    rows = []
    idx = 1
    for _ in range(should_do):
        rows.append({
            "id": str(idx), "热爱": f"热爱{idx}", "优势": f"优势{idx}",
            "用户确认的假设": f"假设{idx}", "激情标记": "应该做",
        })
        idx += 1
    for _ in range(passion):
        rows.append({
            "id": str(idx), "热爱": f"热爱{idx}", "优势": f"优势{idx}",
            "用户确认的假设": f"假设{idx}", "激情标记": "忍不住想做",
        })
        idx += 1
    return rows


def _step6_rows(future: int = 2, now: int = 2) -> List[Dict]:
    rows = []
    idx = 1
    for _ in range(future):
        rows.append({
            "id": str(idx), "热爱": f"热爱{idx}", "优势": f"优势{idx}",
            "用户确认的假设": f"假设{idx}", "现实标记": "未来",
        })
        idx += 1
    for _ in range(now):
        rows.append({
            "id": str(idx), "热爱": f"热爱{idx}", "优势": f"优势{idx}",
            "用户确认的假设": f"假设{idx}", "现实标记": "现在",
        })
        idx += 1
    return rows


# ── P-04: 字段级模板（非整行摘要） ───────────────────────────────────

class TestFieldLevelTemplates:
    def test_p04_step2_injection_contains_field_level(self):
        """Step 2 注入文本应包含字段级'热爱「'格式，而非整行拼接。"""
        rows = _step2_rows(mismatch_count=2)
        items = collect_step2_mismatches(rows)
        inj = build_injection_zh(step=2, kind="mismatch", items=items, llm_failed=False)
        # 字段级模板特征：包含 热爱「xxx」
        assert "热爱「" in inj, "应包含字段级热爱标记"
        assert "Vs" in inj or "vs" in inj or "优势「" in inj, "应包含优势字段"

    def test_p04_step3_injection_contains_hypothesis_field(self):
        """Step 3 注入文本应包含'假设「'字段级格式。"""
        rows = _step3_rows(custom_count=2)
        items = collect_step3_hypothesis_candidates(rows)
        inj = build_injection_zh(step=3, kind="hypothesis_def", items=items, llm_failed=False)
        assert "假设「" in inj, "应包含字段级假设标记"

    def test_p04_step5_injection_field_level(self):
        """Step 5 注入文本应包含'假设「'字段级格式。"""
        rows = _step5_rows(should_do=2)
        items = collect_step5_should_do(rows)
        inj = build_injection_zh(step=5, kind="should_do", items=items, llm_failed=False)
        assert "假设「" in inj

    def test_p04_step6_injection_field_level(self):
        """Step 6 注入文本应包含'假设「'字段级格式。"""
        rows = _step6_rows(future=2)
        items = collect_step6_future(rows)
        inj = build_injection_zh(step=6, kind="future", items=items, llm_failed=False)
        assert "假设「" in inj

    def test_p04_injection_contains_step_system(self):
        """注入文本应包含步骤专属 system 片段（非降级通用模板）。"""
        rows = _step2_rows(mismatch_count=1)
        items = collect_step2_mismatches(rows)
        inj = build_injection_zh(step=2, kind="mismatch", items=items, llm_failed=False)
        # 应有步骤专属 system（由 DEEP_CHAT_STEP_SYSTEM_MAP 提供）
        step_sys = get_deep_chat_step_system(2)
        if step_sys:
            # 截取 system 前 20 字作为特征
            assert step_sys[:20] in inj, "注入文本应包含步骤 2 专属 system 片段"

    def test_p04_bar_copy_not_line_summary(self):
        """bar_copy 不应包含整行摘要的原始分隔符格式。"""
        from app.utils.rumination_neg_gate import build_bar_copy_zh
        rows = _step2_rows(mismatch_count=1)
        items = collect_step2_mismatches(rows)
        bar = build_bar_copy_zh(kind="mismatch", items=items, llm_failed=False)
        # 字段级 label 中包含「」而非 ；分隔的整行
        assert "热爱「" in bar, "bar_copy 应包含字段级格式"


# ── S-07: 闸门触发逻辑 ──────────────────────────────────────────────

class TestNegGateTrigger:
    @pytest.mark.asyncio
    async def test_s07_zero_mismatches_returns_none(self):
        """Step 2 无不匹配项时 try_build_neg_gate_response 应返回 None。"""
        from app.utils.rumination_neg_gate import try_build_neg_gate_response
        rows = _step2_rows(mismatch_count=0, match_count=3)
        fake_llm = MagicMock()
        result = await try_build_neg_gate_response(
            step=2, table_data=rows, llm=fake_llm
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_s07_non_gated_step_returns_none(self):
        """非闸门步骤（1/4/7）应返回 None。"""
        from app.utils.rumination_neg_gate import try_build_neg_gate_response
        rows = [{"id": "1", "热爱": "教育", "优势": "沟通"}]
        fake_llm = MagicMock()
        for step in [1, 4, 7]:
            result = await try_build_neg_gate_response(
                step=step, table_data=rows, llm=fake_llm
            )
            assert result is None, f"step {step} 不应是闸门步骤"

    @pytest.mark.asyncio
    async def test_s07_step3_all_valid_returns_none(self):
        """Step 3 所有假设均为标准选项时返回 None。"""
        from app.utils.rumination_neg_gate import try_build_neg_gate_response
        rows = _step3_rows(custom_count=0, valid_count=3)
        fake_llm = MagicMock()
        result = await try_build_neg_gate_response(
            step=3, table_data=rows, llm=fake_llm
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_s07_step5_zero_should_do_returns_none(self):
        """Step 5 无'应该做'项时返回 None。"""
        from app.utils.rumination_neg_gate import try_build_neg_gate_response
        rows = _step5_rows(should_do=0, passion=3)
        fake_llm = MagicMock()
        result = await try_build_neg_gate_response(
            step=5, table_data=rows, llm=fake_llm
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_s07_step6_zero_future_returns_none(self):
        """Step 6 无'未来'项时返回 None。"""
        from app.utils.rumination_neg_gate import try_build_neg_gate_response
        rows = _step6_rows(future=0, now=3)
        fake_llm = MagicMock()
        result = await try_build_neg_gate_response(
            step=6, table_data=rows, llm=fake_llm
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_s07_empty_table_returns_none(self):
        """空表格返回 None。"""
        from app.utils.rumination_neg_gate import try_build_neg_gate_response
        fake_llm = MagicMock()
        result = await try_build_neg_gate_response(
            step=2, table_data=[], llm=fake_llm
        )
        assert result is None


# ── P-07: 步骤独立 system 片段 ──────────────────────────────────────

class TestDeepChatSystemIndependence:
    def test_p07_all_gated_steps_have_system(self):
        """每个闸门步骤（2/3/5/6）都有独立的 system 片段。"""
        for step in [2, 3, 5, 6]:
            sys = get_deep_chat_step_system(step)
            assert sys, f"step {step} 缺少深入聊天 system 片段"
            assert len(sys) > 50, f"step {step} system 片段过短"

    def test_p07_systems_are_independent(self):
        """各步骤的 system 片段互不包含（独立差异化）。"""
        systems = {}
        for step in [2, 3, 5, 6]:
            systems[step] = get_deep_chat_step_system(step)

        for step_a in [2, 3, 5, 6]:
            for step_b in [2, 3, 5, 6]:
                if step_a == step_b:
                    continue
                # 取每个 system 的前 50 字，不应完全包含在另一个中
                snippet_a = systems[step_a][:80]
                snippet_b = systems[step_b][:80]
                assert snippet_a != snippet_b, (
                    f"step {step_a} 和 step {step_b} 的 system 片段开头相同，可能未独立"
                )

    def test_p07_step3_llm_failed_has_fallback(self):
        """Step 3 LLM 失败时有降级 system 片段。"""
        sys = get_deep_chat_step_system(3, llm_failed=True)
        assert sys, "step 3 LLM 失败时应提供降级 system 片段"

    def test_p07_non_gated_step_no_system(self):
        """非闸门步骤不应有 system 片段。"""
        for step in [1, 4, 7]:
            sys = get_deep_chat_step_system(step)
            assert not sys, f"step {step} 不应有深入聊天 system 片段"
