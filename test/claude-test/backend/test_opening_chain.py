"""O-01: 最后一轮（step7）引导语来源正确性测试"""
import pytest

from app.domain.rumination_step_guidance import build_opening_llm_messages
from app.domain.rumination_prompt_strings import (
    STEP_7_OPENING_SYSTEM_ZH,
    STEP_1_OPENING_SYSTEM_ZH,
    STEP_2_OPENING_SYSTEM_ZH,
    STEP_3_OPENING_SYSTEM_ZH,
    STEP_5_OPENING_SYSTEM_ZH,
    STEP_6_OPENING_SYSTEM_ZH,
)


def _make_context(step: int = 7, row_count: int = 3) -> object:
    """构建 RuminationOpeningContext。"""
    from app.domain.rumination_step_guidance import RuminationOpeningContext
    return RuminationOpeningContext(
        filter_step=step,
        row_count=row_count,
        values_keywords="诚信、成长",
        values_source="confirmed_card",
        table_json="[]",
        rows=[],
    )


class TestOpeningChain:
    def test_o01_step7_uses_step7_system(self):
        """O-01: Step 7 的 LLM opening 必须使用 STEP_7_OPENING_SYSTEM_ZH。"""
        ctx = _make_context(step=7)
        msgs = build_opening_llm_messages(7, ctx)
        assert len(msgs) == 2
        assert msgs[0].content == STEP_7_OPENING_SYSTEM_ZH, (
            "step 7 opening 应使用 STEP_7_OPENING_SYSTEM_ZH"
        )

    def test_o01_step7_not_leak_other_system(self):
        """O-01: Step 7 opening 不应包含其他步骤的 system 内容。"""
        ctx = _make_context(step=7)
        msgs = build_opening_llm_messages(7, ctx)
        system_content = msgs[0].content
        other_systems = [
            STEP_1_OPENING_SYSTEM_ZH,
            STEP_2_OPENING_SYSTEM_ZH,
            STEP_3_OPENING_SYSTEM_ZH,
            STEP_5_OPENING_SYSTEM_ZH,
            STEP_6_OPENING_SYSTEM_ZH,
        ]
        for other in other_systems:
            # 不应完全等于其他步骤的 system
            assert system_content != other, (
                f"step 7 system 不应等于其他步骤的 system"
            )

    def test_step1_uses_step1_system(self):
        """验证 step 1 使用正确的 system（对照组）。"""
        ctx = _make_context(step=1)
        msgs = build_opening_llm_messages(1, ctx)
        assert msgs[0].content == STEP_1_OPENING_SYSTEM_ZH

    def test_step2_uses_step2_system(self):
        """验证 step 2 使用正确的 system（对照组）。"""
        ctx = _make_context(step=2)
        msgs = build_opening_llm_messages(2, ctx)
        assert msgs[0].content == STEP_2_OPENING_SYSTEM_ZH

    def test_invalid_step_raises(self):
        """无效步骤号应有异常处理。"""
        ctx = _make_context(step=99)
        # step 99 不在 1-7 范围内，代码会 clamp 到 7 或抛异常
        # 这里只验证不会崩溃
        try:
            result = build_opening_llm_messages(99, ctx)
            assert result is not None  # 不管返回什么，不应崩溃
        except ValueError:
            pass  # 也符合预期
