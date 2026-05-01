"""
rumination_neg_gate 回归测试：步骤 2/3/5/6 深入聊天闸门的 0条/1条/多条场景。

验收标准：
- 每个步骤有独立的 system 片段（通过 DEEP_CHAT_STEP_SYSTEM_MAP）
- 深入聊天逐条处理，注入文本包含逐条约束
- 1条/多条/0条场景均有正确表现
"""
from app.utils.rumination_neg_gate import (
    NEG_GATED_STEPS,
    build_injection_zh,
    collect_step2_mismatches,
    collect_step3_hypothesis_candidates,
    collect_step5_should_do,
    collect_step6_future,
    try_build_neg_gate_response,
)
from app.domain.rumination_step_guidance import get_deep_chat_step_system
from app.domain.rumination_prompt_strings import DEEP_CHAT_STEP_SYSTEM_MAP


# ===========================================================================
# 辅助构造测试数据
# ===========================================================================

def _make_step2_rows(mismatch_count: int, match_count: int = 2) -> list:
    """构造步骤 2 表格数据：不匹配行 + 匹配行。"""
    rows = []
    idx = 1
    for _ in range(mismatch_count):
        rows.append({
            "id": str(idx),
            "热爱": f"热爱{idx}",
            "优势": f"优势{idx}",
            "匹配性": "不匹配",
            "匹配原因": "难以协同",
        })
        idx += 1
    for _ in range(match_count):
        rows.append({
            "id": str(idx),
            "热爱": f"热爱{idx}",
            "优势": f"优势{idx}",
            "匹配性": "匹配",
            "匹配原因": "结合良好",
        })
        idx += 1
    return rows


def _make_step3_rows(hypothesis_count: int, valid_count: int = 2) -> list:
    """构造步骤 3 表格数据：自定义假设行 + 标准假设行。"""
    rows = []
    idx = 1
    for _ in range(hypothesis_count):
        rows.append({
            "id": str(idx),
            "热爱": f"热爱{idx}",
            "优势": f"优势{idx}",
            "用户确认的假设": f"自定义假设{idx}",
            "假设1": "推荐假设A",
            "假设2": "推荐假设B",
        })
        idx += 1
    for _ in range(valid_count):
        rows.append({
            "id": str(idx),
            "热爱": f"热爱{idx}",
            "优势": f"优势{idx}",
            "用户确认的假设": "推荐假设A",  # 等于假设1，属于标准选项
            "假设1": "推荐假设A",
            "假设2": "推荐假设B",
        })
        idx += 1
    return rows


def _make_step5_rows(should_do_count: int, passion_count: int = 2) -> list:
    """构造步骤 5 表格数据：应该做行 + 忍不住想做行。"""
    rows = []
    idx = 1
    for _ in range(should_do_count):
        rows.append({
            "id": str(idx),
            "热爱": f"热爱{idx}",
            "优势": f"优势{idx}",
            "用户确认的假设": f"假设{idx}",
            "激情标记": "应该做",
        })
        idx += 1
    for _ in range(passion_count):
        rows.append({
            "id": str(idx),
            "热爱": f"热爱{idx}",
            "优势": f"优势{idx}",
            "用户确认的假设": f"假设{idx}",
            "激情标记": "忍不住想做",
        })
        idx += 1
    return rows


def _make_step6_rows(future_count: int, now_count: int = 2) -> list:
    """构造步骤 6 表格数据：未来行 + 现在行。"""
    rows = []
    idx = 1
    for _ in range(future_count):
        rows.append({
            "id": str(idx),
            "热爱": f"热爱{idx}",
            "优势": f"优势{idx}",
            "用户确认的假设": f"假设{idx}",
            "现实标记": "未来",
        })
        idx += 1
    for _ in range(now_count):
        rows.append({
            "id": str(idx),
            "热爱": f"热爱{idx}",
            "优势": f"优势{idx}",
            "用户确认的假设": f"假设{idx}",
            "现实标记": "现在",
        })
        idx += 1
    return rows


# ===========================================================================
# 测试：步骤 2（匹配性不匹配）
# ===========================================================================

class TestStep2Mismatch:
    """步骤 2 不匹配条目采集与注入测试。"""

    def test_collect_zero_mismatches(self):
        """0 条不匹配 → collect 返回空列表。"""
        rows = _make_step2_rows(mismatch_count=0, match_count=3)
        result = collect_step2_mismatches(rows)
        assert result == []

    def test_collect_one_mismatch(self):
        """1 条不匹配 → collect 返回 1 条，含热爱和优势字段。"""
        rows = _make_step2_rows(mismatch_count=1, match_count=2)
        result = collect_step2_mismatches(rows)
        assert len(result) == 1
        assert result[0]["热爱"] == "热爱1"
        assert result[0]["优势"] == "优势1"

    def test_collect_multiple_mismatches(self):
        """多条不匹配 → collect 返回所有不匹配行。"""
        rows = _make_step2_rows(mismatch_count=4, match_count=1)
        result = collect_step2_mismatches(rows)
        assert len(result) == 4
        for i, item in enumerate(result):
            assert item["热爱"] == f"热爱{i + 1}"

    def test_injection_contains_step_system(self):
        """注入文本包含步骤 2 专属 system 片段关键词。"""
        items = [{"id": "1", "热爱": "写作", "优势": "沟通", "label": "热爱「写作」 Vs 优势「沟通」"}]
        inj = build_injection_zh(step=2, kind="mismatch", items=items, llm_failed=False)
        assert "步骤二" in inj
        assert "匹配性" in inj
        assert "逐条" in inj
        assert "热爱「写作」" in inj

    def test_injection_single_item(self):
        """1 条不匹配 → 注入文本包含该条目，且包含逐条约束。"""
        items = [{"id": "1", "热爱": "AI", "优势": "编程", "label": "热爱「AI」 Vs 优势「编程」"}]
        inj = build_injection_zh(step=2, kind="mismatch", items=items, llm_failed=False)
        assert "1." in inj
        assert "不得一次总结多条" in inj
        assert "不得跳过" in inj

    def test_injection_multiple_items(self):
        """多条不匹配 → 注入文本包含编号列表。"""
        items = [
            {"id": "1", "热爱": "A", "优势": "B", "label": "热爱「A」 Vs 优势「B」"},
            {"id": "2", "热爱": "C", "优势": "D", "label": "热爱「C」 Vs 优势「D」"},
            {"id": "3", "热爱": "E", "优势": "F", "label": "热爱「E」 Vs 优势「F」"},
        ]
        inj = build_injection_zh(step=2, kind="mismatch", items=items, llm_failed=False)
        assert "1." in inj
        assert "2." in inj
        assert "3." in inj


# ===========================================================================
# 测试：步骤 3（假设定义质检）
# ===========================================================================

class TestStep3HypothesisDef:
    """步骤 3 假设质检采集与注入测试。"""

    def test_collect_zero_candidates(self):
        """0 条候选（所有假设都是标准选项或待定）→ collect 返回空列表。"""
        rows = [
            {"id": "1", "热爱": "a", "优势": "b", "用户确认的假设": "推荐A", "假设1": "推荐A", "假设2": "推荐B"},
            {"id": "2", "热爱": "c", "优势": "d", "用户确认的假设": "暂未选定", "假设1": "x", "假设2": "y"},
            {"id": "3", "热爱": "e", "优势": "f", "用户确认的假设": "", "假设1": "x", "假设2": "y"},
        ]
        result = collect_step3_hypothesis_candidates(rows)
        assert result == []

    def test_collect_one_candidate(self):
        """1 条自定义假设 → collect 返回 1 条。"""
        rows = _make_step3_rows(hypothesis_count=1, valid_count=2)
        result = collect_step3_hypothesis_candidates(rows)
        assert len(result) == 1
        assert result[0]["假设"] == "自定义假设1"

    def test_collect_multiple_candidates(self):
        """多条自定义假设 → collect 返回所有候选。"""
        rows = _make_step3_rows(hypothesis_count=3, valid_count=1)
        result = collect_step3_hypothesis_candidates(rows)
        assert len(result) == 3

    def test_injection_contains_step_system(self):
        """注入文本包含步骤 3 专属 system 片段。"""
        items = [{"id": "1", "热爱": "AI", "优势": "编程", "假设": "做AI", "label": "假设「做AI」（热爱：AI；优势：编程）"}]
        inj = build_injection_zh(step=3, kind="hypothesis_def", items=items, llm_failed=False)
        assert "步骤三" in inj
        assert "假设定义" in inj
        assert "逐条" in inj

    def test_injection_llm_failed_uses_fallback(self):
        """LLM 质检失败 → 注入使用步骤 3 降级片段。"""
        items = [{"id": "1", "热爱": "AI", "优势": "编程", "假设": "做AI", "label": "假设「做AI」"}]
        inj = build_injection_zh(step=3, kind="hypothesis_def", items=items, llm_failed=True)
        assert "降级" in inj


# ===========================================================================
# 测试：步骤 5（应该做）
# ===========================================================================

class TestStep5ShouldDo:
    """步骤 5 应该做条目采集与注入测试。"""

    def test_collect_zero_should_do(self):
        """0 条应该做 → collect 返回空列表。"""
        rows = _make_step5_rows(should_do_count=0, passion_count=3)
        result = collect_step5_should_do(rows)
        assert result == []

    def test_collect_one_should_do(self):
        """1 条应该做 → collect 返回 1 条。"""
        rows = _make_step5_rows(should_do_count=1, passion_count=2)
        result = collect_step5_should_do(rows)
        assert len(result) == 1
        assert result[0]["热爱"] == "热爱1"
        assert result[0]["假设"] == "假设1"

    def test_collect_multiple_should_do(self):
        """多条应该做 → collect 返回所有条目。"""
        rows = _make_step5_rows(should_do_count=3, passion_count=1)
        result = collect_step5_should_do(rows)
        assert len(result) == 3

    def test_injection_contains_step_system(self):
        """注入文本包含步骤 5 专属 system 片段。"""
        items = [{"id": "1", "热爱": "教育", "优势": "演讲", "假设": "当老师", "label": "假设「当老师」"}]
        inj = build_injection_zh(step=5, kind="should_do", items=items, llm_failed=False)
        assert "步骤五" in inj
        assert "激情过滤" in inj
        assert "应该做" in inj
        assert "逐条" in inj

    def test_injection_contains_passion_fields(self):
        """注入文本包含激情标记相关字段上下文。"""
        items = [{"id": "1", "热爱": "教育", "优势": "演讲", "假设": "当老师", "label": "假设「当老师」"}]
        inj = build_injection_zh(step=5, kind="should_do", items=items, llm_failed=False)
        assert "热爱" in inj
        assert "优势" in inj
        assert "假设" in inj


# ===========================================================================
# 测试：步骤 6（未来）
# ===========================================================================

class TestStep6Future:
    """步骤 6 未来条目采集与注入测试。"""

    def test_collect_zero_future(self):
        """0 条未来 → collect 返回空列表。"""
        rows = _make_step6_rows(future_count=0, now_count=3)
        result = collect_step6_future(rows)
        assert result == []

    def test_collect_one_future(self):
        """1 条未来 → collect 返回 1 条。"""
        rows = _make_step6_rows(future_count=1, now_count=2)
        result = collect_step6_future(rows)
        assert len(result) == 1
        assert result[0]["热爱"] == "热爱1"

    def test_collect_multiple_future(self):
        """多条未来 → collect 返回所有条目。"""
        rows = _make_step6_rows(future_count=3, now_count=1)
        result = collect_step6_future(rows)
        assert len(result) == 3

    def test_injection_contains_step_system(self):
        """注入文本包含步骤 6 专属 system 片段。"""
        items = [{"id": "1", "热爱": "太空", "优势": "物理", "假设": "上太空", "label": "假设「上太空」"}]
        inj = build_injection_zh(step=6, kind="future", items=items, llm_failed=False)
        assert "步骤六" in inj
        assert "现实过滤" in inj
        assert "未来" in inj
        assert "逐条" in inj


# ===========================================================================
# 测试：步骤差异化 system 片段独立性
# ===========================================================================

class TestDeepChatStepSystemIndependence:
    """验证每个步骤的 system 片段独立且差异化。"""

    def test_all_gated_steps_have_system(self):
        """步骤 2/3/5/6 均有独立的 system 片段映射。"""
        for step in NEG_GATED_STEPS:
            assert step in DEEP_CHAT_STEP_SYSTEM_MAP, f"步骤 {step} 缺少 deep chat system 映射"

    def test_step_systems_are_different(self):
        """各步骤的 system 片段内容不同（差异化）。"""
        systems = {s: DEEP_CHAT_STEP_SYSTEM_MAP[s] for s in NEG_GATED_STEPS}
        # 去重后数量不变
        unique_systems = set(systems.values())
        assert len(unique_systems) == len(systems), "步骤 system 片段存在重复内容"

    def test_step2_system_mentions_mismatch(self):
        """步骤 2 system 片段提及「不匹配」和「匹配性」。"""
        sys = DEEP_CHAT_STEP_SYSTEM_MAP[2]
        assert "不匹配" in sys
        assert "匹配性" in sys

    def test_step3_system_mentions_hypothesis_definition(self):
        """步骤 3 system 片段提及「假设」和「定义」。"""
        sys = DEEP_CHAT_STEP_SYSTEM_MAP[3]
        assert "假设" in sys
        assert "定义" in sys

    def test_step5_system_mentions_passion(self):
        """步骤 5 system 片段提及「应该做」和「忍不住想做」。"""
        sys = DEEP_CHAT_STEP_SYSTEM_MAP[5]
        assert "应该做" in sys
        assert "忍不住想做" in sys

    def test_step6_system_mentions_future(self):
        """步骤 6 system 片段提及「未来」和「现在」。"""
        sys = DEEP_CHAT_STEP_SYSTEM_MAP[6]
        assert "未来" in sys
        assert "现在" in sys

    def test_all_steps_have_anti_skip_constraint(self):
        """所有步骤 system 片段都包含逐条处理约束（防跳步）。"""
        for step in NEG_GATED_STEPS:
            sys = DEEP_CHAT_STEP_SYSTEM_MAP[step]
            assert "逐条" in sys or "一条确认后" in sys or "逐一" in sys, (
                f"步骤 {step} 缺少逐条处理约束"
            )

    def test_all_steps_have_no_skip_prohibition(self):
        """所有步骤 system 片段都包含禁止跳过的约束。"""
        for step in NEG_GATED_STEPS:
            sys = DEEP_CHAT_STEP_SYSTEM_MAP[step]
            assert "不得跳过" in sys or "禁止" in sys, (
                f"步骤 {step} 缺少禁止跳步约束"
            )

    def test_all_steps_have_field_context(self):
        """所有步骤 system 片段都包含字段上下文模板。"""
        for step in NEG_GATED_STEPS:
            sys = DEEP_CHAT_STEP_SYSTEM_MAP[step]
            assert "字段上下文" in sys, f"步骤 {step} 缺少字段上下文模板"

    def test_all_steps_have_exit_guidance(self):
        """所有步骤 system 片段都包含退出引导（结束讨论）。"""
        for step in NEG_GATED_STEPS:
            sys = DEEP_CHAT_STEP_SYSTEM_MAP[step]
            assert "结束讨论" in sys, f"步骤 {step} 缺少结束讨论引导"


# ===========================================================================
# 测试：get_deep_chat_step_system 接口
# ===========================================================================

class TestGetDeepChatStepSystem:
    """验证 get_deep_chat_step_system 接口正确性。"""

    def test_valid_steps_return_non_empty(self):
        """步骤 2/3/5/6 返回非空字符串。"""
        for step in NEG_GATED_STEPS:
            result = get_deep_chat_step_system(step)
            assert isinstance(result, str)
            assert len(result) > 100, f"步骤 {step} system 片段过短"

    def test_invalid_step_returns_empty(self):
        """非闸门步骤返回空字符串。"""
        assert get_deep_chat_step_system(1) == ""
        assert get_deep_chat_step_system(4) == ""
        assert get_deep_chat_step_system(7) == ""

    def test_step3_llm_failed_returns_fallback(self):
        """步骤 3 LLM 失败时返回降级片段。"""
        result = get_deep_chat_step_system(3, llm_failed=True)
        assert "降级" in result

    def test_step3_normal_returns_standard(self):
        """步骤 3 正常模式返回标准片段。"""
        result = get_deep_chat_step_system(3, llm_failed=False)
        assert "降级" not in result
        assert "假设定义" in result


# ===========================================================================
# 测试：注入文本逐条处理约束
# ===========================================================================

class TestInjectionOneByOneConstraint:
    """验证注入文本包含显式的逐条处理流程约束。"""

    def test_step2_injection_no_batch_summary(self):
        """步骤 2 注入文本禁止一次性总结。"""
        items = [{"id": "1", "热爱": "a", "优势": "b", "label": "x"}]
        inj = build_injection_zh(step=2, kind="mismatch", items=items, llm_failed=False)
        assert "不得一次总结多条" in inj

    def test_step3_injection_no_batch_summary(self):
        """步骤 3 注入文本禁止一次性总结。"""
        items = [{"id": "1", "热爱": "a", "优势": "b", "假设": "c", "label": "x"}]
        inj = build_injection_zh(step=3, kind="hypothesis_def", items=items, llm_failed=False)
        assert "不得一次总结多条" in inj

    def test_step5_injection_no_batch_summary(self):
        """步骤 5 注入文本禁止一次性总结。"""
        items = [{"id": "1", "热爱": "a", "优势": "b", "假设": "c", "label": "x"}]
        inj = build_injection_zh(step=5, kind="should_do", items=items, llm_failed=False)
        assert "不得一次总结多条" in inj

    def test_step6_injection_no_batch_summary(self):
        """步骤 6 注入文本禁止一次性总结。"""
        items = [{"id": "1", "热爱": "a", "优势": "b", "假设": "c", "label": "x"}]
        inj = build_injection_zh(step=6, kind="future", items=items, llm_failed=False)
        assert "不得一次总结多条" in inj

    def test_step2_injection_no_skip(self):
        """步骤 2 注入文本禁止跳步。"""
        items = [{"id": "1", "热爱": "a", "优势": "b", "label": "x"}]
        inj = build_injection_zh(step=2, kind="mismatch", items=items, llm_failed=False)
        assert "不得跳过" in inj

    def test_step5_injection_no_skip(self):
        """步骤 5 注入文本禁止跳步。"""
        items = [{"id": "1", "热爱": "a", "优势": "b", "假设": "c", "label": "x"}]
        inj = build_injection_zh(step=5, kind="should_do", items=items, llm_failed=False)
        assert "不得跳过" in inj

    def test_step6_injection_no_skip(self):
        """步骤 6 注入文本禁止跳步。"""
        items = [{"id": "1", "热爱": "a", "优势": "b", "假设": "c", "label": "x"}]
        inj = build_injection_zh(step=6, kind="future", items=items, llm_failed=False)
        assert "不得跳过" in inj

    def test_injection_cannot_modify_prerequisites(self):
        """所有步骤注入文本都禁止修改前提字段。"""
        for step, kind in [(2, "mismatch"), (3, "hypothesis_def"), (5, "should_do"), (6, "future")]:
            items = [{"id": "1", "热爱": "a", "优势": "b", "假设": "c", "label": "x"}]
            inj = build_injection_zh(step=step, kind=kind, items=items, llm_failed=False)
            assert "不可修改" in inj or "不得修改" in inj, f"步骤 {step} 缺少前提字段保护"

    def test_injection_cannot_advance_to_conclusion(self):
        """所有步骤注入文本都禁止推进到结论卡。"""
        for step, kind in [(2, "mismatch"), (3, "hypothesis_def"), (5, "should_do"), (6, "future")]:
            items = [{"id": "1", "热爱": "a", "优势": "b", "假设": "c", "label": "x"}]
            inj = build_injection_zh(step=step, kind=kind, items=items, llm_failed=False)
            assert "结论卡" in inj or "最终确认" in inj, f"步骤 {step} 缺少结论卡保护"


# ===========================================================================
# 测试：字段级格式化（label）
# ===========================================================================

class TestFieldLevelFormatting:
    """验证字段级格式化正确展示关键字段。"""

    def test_step2_label_shows_passion_and_strength(self):
        """步骤 2 label 展示热爱 vs 优势。"""
        from app.utils.rumination_neg_gate import _format_mismatch_item
        label = _format_mismatch_item({"热爱": "编程", "优势": "逻辑思维"})
        assert "热爱「编程」" in label
        assert "优势「逻辑思维」" in label

    def test_step3_label_shows_hypothesis_with_context(self):
        """步骤 3 label 展示假设 + 热爱 + 优势。"""
        from app.utils.rumination_neg_gate import _format_hypothesis_item
        label = _format_hypothesis_item({"热爱": "教育", "优势": "演讲", "假设": "当老师"})
        assert "假设「当老师」" in label
        assert "热爱：教育" in label
        assert "优势：演讲" in label

    def test_step5_label_shows_hypothesis_with_context(self):
        """步骤 5 label 展示假设 + 热爱 + 优势。"""
        from app.utils.rumination_neg_gate import _format_should_do_item
        label = _format_should_do_item({"热爱": "AI", "优势": "编程", "假设": "做AI产品"})
        assert "假设「做AI产品」" in label
        assert "热爱：AI" in label

    def test_step6_label_shows_hypothesis_with_context(self):
        """步骤 6 label 展示假设 + 热爱 + 优势。"""
        from app.utils.rumination_neg_gate import _format_future_item
        label = _format_future_item({"热爱": "太空", "优势": "物理", "假设": "上太空"})
        assert "假设「上太空」" in label
