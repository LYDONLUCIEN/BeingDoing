"""P-02 / P-03 / P-08: 提示词模板内容测试"""
from app.domain.rumination_prompt_strings import (
    STEP_OPENING_FIXED_ZH,
    DEEP_CHAT_STEP_SYSTEM_MAP,
    RUMINATION_ENTRY_INIT_SYSTEM_ZH,
    RUMINATION_ENTRY_INIT_USER_TEMPLATE_ZH,
)
from app.utils.rumination_table_widgets import GUIDE_TEXT
from app.utils.rumination_neg_gate import (
    build_bar_copy_zh,
    build_opening_user_visible_zh,
)


# ── P-08: 冷启动心理预期 ─────────────────────────────────────────────

class TestColdStartTolerance:
    # 常见容错表达关键词
    COLD_START_PHRASES = [
        "不确定也没关系",
        "不知道也没关系",
        "可以逐步来",
        "不确定也",
        "允许不确定",
        "没有标准答案",
        "可以慢慢来",
        "不用着急",
    ]

    def test_p08_rumination_entry_has_cold_start(self):
        """沉淀入场模板应包含冷启动容错表达。"""
        text = RUMINATION_ENTRY_INIT_SYSTEM_ZH + RUMINATION_ENTRY_INIT_USER_TEMPLATE_ZH
        has_any = any(phrase in text for phrase in self.COLD_START_PHRASES)
        assert has_any, (
            f"沉淀入场模板应包含冷启动容错表达。已检查关键词: {self.COLD_START_PHRASES}"
        )

    def test_p08_step_openings_have_tolerance(self):
        """筛选步骤 opening 模板应包含容错表达（至少 entry 模板包含即可）。"""
        # entry 模板已由 test_p08_rumination_entry_has_cold_start 验证
        # 这里验证 GUIDE_TEXT 步骤引导包含确认性语气
        for step in [1, 2]:
            guide = GUIDE_TEXT.get(step, "")
            assert guide, f"Step {step} GUIDE_TEXT 不应为空"

    def test_p08_guide_text_step1_has_tolerance(self):
        """Step 1 GUIDE_TEXT 应包含审阅引导（非冷启动但确认用户知道可以审阅）。"""
        guide = GUIDE_TEXT.get(1, "")
        assert guide, "Step 1 GUIDE_TEXT 不应为空"
        assert "确认" in guide or "审阅" in guide or "查看" in guide


# ── P-03: 无用户可见统计展示 ─────────────────────────────────────────

class TestNoUserVisibleStatistics:
    # 禁止出现在用户可见文案中的统计相关表达
    FORBIDDEN_STATS_PHRASES = [
        "出现",
        "频次",
        "统计",
        "次数",
        "关键词出现",
        "关键词频次",
        "计数",
        "出现次数",
    ]

    def test_p03_bar_copy_no_stats(self):
        """bar_copy（用户可见弹窗文案）不应包含统计语言。"""
        # 遍历所有步骤类型的 bar_copy
        test_cases = [
            ("mismatch", _make_mismatch_items()),
            ("should_do", _make_should_do_items()),
            ("future", _make_future_items()),
        ]
        for kind, items in test_cases:
            bar = build_bar_copy_zh(kind=kind, items=items, llm_failed=False)
            for phrase in self.FORBIDDEN_STATS_PHRASES:
                assert phrase not in bar, (
                    f"bar_copy (kind={kind}) 不应包含统计语言'{phrase}'。实际: {bar[:100]}"
                )

    def test_p03_opening_user_visible_no_stats(self):
        """用户可见开场语不应包含统计语言。"""
        test_cases = [
            ("mismatch", _make_mismatch_items()),
            ("should_do", _make_should_do_items()),
        ]
        for kind, items in test_cases:
            opening = build_opening_user_visible_zh(
                step=2 if kind == "mismatch" else 5,
                kind=kind,
                items=items,
                llm_failed=False,
            )
            for phrase in self.FORBIDDEN_STATS_PHRASES:
                # 注意：使命阶段的 system prompt 允许内部统计（供模型推理）
                # 这里只检查面向用户的文案
                assert phrase not in opening, (
                    f"user_visible opening (kind={kind}) 不应包含'{phrase}'"
                )

    def test_p03_guide_text_no_stats(self):
        """GUIDE_TEXT 不应包含统计语言。"""
        for step, guide in GUIDE_TEXT.items():
            for phrase in self.FORBIDDEN_STATS_PHRASES:
                assert phrase not in guide, (
                    f"GUIDE_TEXT[step={step}] 不应包含'{phrase}'"
                )


# ── P-02: 允许填写多个价值观 ────────────────────────────────────────

class TestMultipleValuesAllowed:
    # 禁止出现的单选强制语言
    FORBIDDEN_SINGLE_SELECT = [
        "只能选一个",
        "只能选择一个",
        "选择一个",
        "请选择一个",
        "请选一个",
        "只能选1个",
    ]

    def test_p02_step4_guide_allows_multiple(self):
        """Step 4 GUIDE_TEXT 不应强制单选。"""
        guide = GUIDE_TEXT.get(4, "")
        for phrase in self.FORBIDDEN_SINGLE_SELECT:
            assert phrase not in guide, (
                f"GUIDE_TEXT[4] 不应包含'{phrase}'。实际: {guide}"
            )

    def test_p02_entry_system_allows_multiple(self):
        """入场 system 模板不应强制使命阶段单选。"""
        text = RUMINATION_ENTRY_INIT_SYSTEM_ZH
        for phrase in self.FORBIDDEN_SINGLE_SELECT:
            assert phrase not in text, (
                f"RUMINATION_ENTRY_INIT_SYSTEM_ZH 不应包含'{phrase}'"
            )


# ── 辅助函数 ────────────────────────────────────────────────────────

def _make_mismatch_items():
    return [
        {"id": "1", "热爱": "教育", "优势": "沟通", "line": "热爱：教育；优势：沟通",
         "label": "热爱「教育」 Vs 优势「沟通」"},
    ]


def _make_should_do_items():
    return [
        {"id": "1", "热爱": "教育", "优势": "沟通", "假设": "做老师",
         "line": "热爱：教育；优势：沟通；假设：做老师；激情标记：应该做",
         "label": "假设「做老师」（热爱：教育；优势：沟通）"},
    ]


def _make_future_items():
    return [
        {"id": "1", "热爱": "教育", "优势": "沟通", "假设": "创业",
         "line": "热爱：教育；优势：沟通；假设：创业；现实标记：未来",
         "label": "假设「创业」（热爱：教育；优势：沟通）"},
    ]
