"""
rumination 引导语（opening）调用链路回归测试。

覆盖目标：
1. 确认各引导语来源正确、不被混用
2. step_copy.yaml 的 rumination.intro 不会进入对话流
3. 筛选子步 opening 按 step 正确引用对应 system/user prompt
4. entry_init 首轮开场白模板独立于子步 opening
5. closing_epilogue 结束语模板独立于子步 opening

测试不依赖数据库或外部 LLM 调用，仅验证模板组装逻辑。
"""
import pytest
from app.domain.rumination_step_guidance import (
    RuminationOpeningContext,
    STEP_OPENING_MODE,
    build_opening_context,
    build_opening_llm_messages,
    build_rumination_closing_epilogue_messages,
    build_rumination_entry_init_messages,
    get_opening_mode,
    get_rumination_chat_step_addon,
    render_fixed_opening_zh,
)
from app.domain.rumination_prompt_strings import (
    DEEP_CHAT_STEP_SYSTEM_MAP,
    OPENING_USER_WITH_TABLE_ZH,
    RUMINATION_CHAT_STEP_ADDON_EN,
    RUMINATION_CHAT_STEP_ADDON_ZH,
    RUMINATION_CLOSING_EPILOGUE_SYSTEM_ZH,
    RUMINATION_CLOSING_EPILOGUE_USER_TEMPLATE_ZH,
    RUMINATION_ENTRY_INIT_SYSTEM_ZH,
    RUMINATION_ENTRY_INIT_USER_TEMPLATE_ZH,
    RUMINATION_SHORTPATH_SKIP_CLOSING_FIXED_ZH,
    STEP_1_OPENING_SYSTEM_ZH,
    STEP_2_OPENING_SYSTEM_ZH,
    STEP_3_OPENING_SYSTEM_ZH,
    STEP_4_OPENING_SYSTEM_ZH,
    STEP_4_OPENING_USER_TEMPLATE_ZH,
    STEP_5_OPENING_SYSTEM_ZH,
    STEP_6_OPENING_SYSTEM_ZH,
    STEP_7_OPENING_SYSTEM_ZH,
    STEP_OPENING_FIXED_ZH,
)
from app.domain.prompts.loader import get_step_copy


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_ctx(filter_step: int = 1, row_count: int = 5, values_list=None, values_source="survey") -> RuminationOpeningContext:
    """构造测试用 RuminationOpeningContext。"""
    progress = {
        "filter_step": filter_step,
        "filter_table": [{"id": str(i)} for i in range(row_count)],
        "filter_step_snapshots": {
            str(filter_step): {"submitted": [{"id": str(i)} for i in range(row_count)]}
        },
    }
    return build_opening_context(
        filter_step=filter_step,
        progress=progress,
        values_list=values_list or ["诚信", "成长", "自由"],
        values_source=values_source,
    )


# ===========================================================================
# 1. STEP_OPENING_MODE 覆盖：所有子步均有明确模式
# ===========================================================================

class TestStepOpeningMode:
    """验证所有子步 1-7 均在 STEP_OPENING_MODE 中有映射。"""

    @pytest.mark.parametrize("step", range(1, 8))
    def test_all_steps_have_mode(self, step: int):
        """步骤 1-7 都有明确的 opening_mode。"""
        mode = get_opening_mode(step)
        assert mode in ("fixed", "llm"), f"step {step} mode={mode!r} not in ('fixed', 'llm')"

    def test_mode_dict_keys_match_range(self):
        """STEP_OPENING_MODE 的 key 覆盖 1-7。"""
        assert set(STEP_OPENING_MODE.keys()) == set(range(1, 8))


# ===========================================================================
# 2. 固定文案模板来源隔离
# ===========================================================================

class TestFixedOpeningIsolation:
    """确保固定文案模板不会被其他来源的模板内容污染。"""

    def test_fixed_templates_cover_all_steps(self):
        """STEP_OPENING_FIXED_ZH 覆盖步骤 1-7。"""
        assert set(STEP_OPENING_FIXED_ZH.keys()) == set(range(1, 8))

    def test_fixed_templates_contain_row_count_placeholder(self):
        """每个固定模板都有 {row_count} 占位符，确保可格式化。"""
        for step, tmpl in STEP_OPENING_FIXED_ZH.items():
            assert "{row_count}" in tmpl, f"step {step} fixed template missing {{row_count}}"

    def test_render_fixed_opening_uses_correct_template(self):
        """render_fixed_opening_zh 使用 STEP_OPENING_FIXED_ZH 对应步骤的模板。"""
        ctx = _make_ctx(filter_step=3, row_count=8)
        text = render_fixed_opening_zh(3, ctx)
        assert "8" in text, "row_count 应被格式化到文案中"
        # 确认使用的是步骤 3 的模板（包含"假设"关键词）
        assert "假设" in text, f"step 3 fixed opening 应包含'假设'，实际: {text}"

    def test_render_fixed_step4_degradation_when_no_values(self):
        """步骤 4 无价值观关键词时追加降级提示。"""
        ctx = _make_ctx(filter_step=4, values_list=[], values_source="none")
        text = render_fixed_opening_zh(4, ctx)
        assert "手动填写" in text


# ===========================================================================
# 3. LLM 引导语：每个步骤使用正确的 system prompt
# ===========================================================================

class TestLLMOpeningSystemPromptIsolation:
    """确保每个子步的 LLM opening 引用正确的 system prompt，不会交叉。"""

    # 步骤 -> (system_prompt_var, 预期关键词)
    STEP_SYSTEM_KEYWORDS = {
        1: (STEP_1_OPENING_SYSTEM_ZH, "热爱与优势组合"),
        2: (STEP_2_OPENING_SYSTEM_ZH, "匹配性分析"),
        3: (STEP_3_OPENING_SYSTEM_ZH, "假设生成"),
        4: (STEP_4_OPENING_SYSTEM_ZH, "价值过滤"),
        5: (STEP_5_OPENING_SYSTEM_ZH, "激情过滤"),
        6: (STEP_6_OPENING_SYSTEM_ZH, "现实过滤"),
        7: (STEP_7_OPENING_SYSTEM_ZH, "最终"),
    }

    @pytest.mark.parametrize("step", range(1, 8))
    def test_step_uses_correct_system_prompt(self, step: int):
        """build_opening_llm_messages 对每个步骤返回正确的 system prompt。"""
        ctx = _make_ctx(filter_step=step)
        msgs = build_opening_llm_messages(step, ctx)
        system_contents = [m.content for m in msgs if m.role == "system"]
        assert len(system_contents) == 1, f"step {step} should have exactly 1 system message"

        expected_sys, keyword = self.STEP_SYSTEM_KEYWORDS[step]
        assert system_contents[0] == expected_sys, (
            f"step {step} system prompt 不匹配预期来源"
        )
        assert keyword in system_contents[0], (
            f"step {step} system prompt 缺少关键标识 '{keyword}'"
        )

    def test_step4_uses_special_user_template(self):
        """步骤 4 的 user prompt 使用 STEP_4_OPENING_USER_TEMPLATE_ZH（含 values_keywords）。"""
        ctx = _make_ctx(filter_step=4, values_list=["诚信", "成长"])
        msgs = build_opening_llm_messages(4, ctx)
        user_contents = [m.content for m in msgs if m.role == "user"]
        assert len(user_contents) == 1
        # 步骤 4 的 user prompt 应包含 values_keywords 字段
        assert "values_keywords" in user_contents[0].lower() or "诚信" in user_contents[0]

    @pytest.mark.parametrize("step", [1, 2, 3, 5, 6, 7])
    def test_non_step4_uses_standard_user_template(self, step: int):
        """步骤 1/2/3/5/6/7 的 user prompt 使用 OPENING_USER_WITH_TABLE_ZH。"""
        ctx = _make_ctx(filter_step=step)
        msgs = build_opening_llm_messages(step, ctx)
        user_contents = [m.content for m in msgs if m.role == "user"]
        assert len(user_contents) == 1
        # 标准模板包含"当前表格行数"和"表格数据"
        assert "当前表格行数" in user_contents[0]
        assert "表格数据" in user_contents[0]

    def test_step4_user_has_values_keywords_section(self):
        """步骤 4 user prompt 包含价值观关键词字段（step 4 专属）。"""
        ctx = _make_ctx(filter_step=4, values_list=["诚信", "成长", "自由"])
        msgs = build_opening_llm_messages(4, ctx)
        user_text = [m.content for m in msgs if m.role == "user"][0]
        # 应包含价值观关键词
        assert "诚信" in user_text or "价值观关键词" in user_text

    def test_step4_degradation_when_no_values_in_llm_mode(self):
        """步骤 4 无价值观关键词时，LLM user prompt 追加降级提示。"""
        ctx = _make_ctx(filter_step=4, values_list=[], values_source="none")
        msgs = build_opening_llm_messages(4, ctx)
        user_text = [m.content for m in msgs if m.role == "user"][0]
        assert "重要" in user_text or "未解析" in user_text, (
            "步骤 4 无价值观时应追加降级提示"
        )

    def test_out_of_range_step_clamped(self):
        """超出 1-7 范围的步骤会被 clamp 到合法范围，不会 raise。"""
        # build_opening_llm_messages 内部 clamp step 到 1-7，所以 step 8 → step 7
        ctx = _make_ctx(filter_step=8)
        msgs = build_opening_llm_messages(8, ctx)
        # step 8 被 clamp 到 7，应返回 step 7 的 system prompt
        sys_content = [m.content for m in msgs if m.role == "system"][0]
        assert sys_content == STEP_7_OPENING_SYSTEM_ZH


# ===========================================================================
# 4. entry_init 首轮开场白：独立于子步 opening
# ===========================================================================

class TestEntryInitIsolation:
    """确保首轮开场白模板不会被子步 opening 引用，反之亦然。"""

    def test_entry_init_system_not_used_by_any_step_opening(self):
        """RUMINATION_ENTRY_INIT_SYSTEM_ZH 不被任何步骤的 opening 引用。"""
        for step in range(1, 8):
            ctx = _make_ctx(filter_step=step)
            msgs = build_opening_llm_messages(step, ctx)
            for m in msgs:
                if m.role == "system":
                    assert m.content != RUMINATION_ENTRY_INIT_SYSTEM_ZH, (
                        f"step {step} opening 不应使用 entry_init system prompt"
                    )

    def test_entry_init_user_template_has_basic_info(self):
        """entry_init user 模板包含 basic_info 和 prior_block 占位符。"""
        assert "{basic_info}" in RUMINATION_ENTRY_INIT_USER_TEMPLATE_ZH
        assert "{prior_block}" in RUMINATION_ENTRY_INIT_USER_TEMPLATE_ZH

    def test_entry_init_messages_structure(self):
        """build_rumination_entry_init_messages 返回 system + user 两条消息。"""
        msgs = build_rumination_entry_init_messages(basic_info="测试用户", prior_block="前序摘要")
        assert len(msgs) == 2
        assert msgs[0].role == "system"
        assert msgs[1].role == "user"
        assert "测试用户" in msgs[1].content

    def test_entry_init_system_not_in_step_opening_fixed(self):
        """STEP_OPENING_FIXED_ZH 不包含 entry_init 的任何标志性措辞。"""
        entry_keyword = "最后一轮"  # entry_init 特有
        for step, tmpl in STEP_OPENING_FIXED_ZH.items():
            assert entry_keyword not in tmpl, (
                f"step {step} fixed template 不应包含 entry_init 标志词 '{entry_keyword}'"
            )


# ===========================================================================
# 5. closing_epilogue 结束语：独立于子步 opening
# ===========================================================================

class TestClosingEpilogueIsolation:
    """确保结束语模板不会被子步 opening 引用。"""

    def test_closing_system_not_used_by_any_step_opening(self):
        """RUMINATION_CLOSING_EPILOGUE_SYSTEM_ZH 不被任何步骤的 opening 引用。"""
        for step in range(1, 8):
            ctx = _make_ctx(filter_step=step)
            msgs = build_opening_llm_messages(step, ctx)
            for m in msgs:
                if m.role == "system":
                    assert m.content != RUMINATION_CLOSING_EPILOGUE_SYSTEM_ZH

    def test_closing_epilogue_has_selected_summary(self):
        """结束语 user 模板包含 selected_summary 占位符。"""
        assert "{selected_summary}" in RUMINATION_CLOSING_EPILOGUE_USER_TEMPLATE_ZH

    def test_closing_messages_structure(self):
        """build_rumination_closing_epilogue_messages 返回 system + user。"""
        msgs = build_rumination_closing_epilogue_messages("选了方向 A")
        assert len(msgs) == 2
        assert msgs[0].role == "system"
        assert msgs[1].role == "user"
        assert "方向 A" in msgs[1].content


# ===========================================================================
# 6. step_copy.yaml 隔离：rumination intro 不进入对话流
# ===========================================================================

class TestStepCopyIsolation:
    """确保 step_copy.yaml 的内容不会被对话流引导语复用。"""

    def test_step_copy_rumination_intro_exists(self):
        """step_copy.yaml 的 rumination.intro_zh 存在。"""
        intro = get_step_copy("rumination", "intro", "zh")
        assert intro, "rumination intro_zh 应存在"
        assert "沉淀" in intro or "选择" in intro

    def test_step_copy_rumination_intro_not_in_step_opening_fixed(self):
        """step_copy rumination intro 的内容不会出现在 STEP_OPENING_FIXED_ZH 中。"""
        step_intro = get_step_copy("rumination", "intro", "zh")
        # step_copy intro 的标志性短语不应出现在任何子步固定模板中
        for step, tmpl in STEP_OPENING_FIXED_ZH.items():
            # 取 step_copy intro 的前 20 字作为指纹，避免完全匹配（可能有共同词）
            fingerprint = step_intro[:20].replace("\n", "")
            assert fingerprint not in tmpl, (
                f"step {step} fixed template 不应包含 step_copy intro 的内容"
            )

    def test_step_copy_rumination_intro_not_in_llm_system_prompts(self):
        """step_copy rumination intro 的内容不会出现在任何 LLM opening system prompt 中。"""
        step_intro = get_step_copy("rumination", "intro", "zh")
        fingerprint = step_intro[:20].replace("\n", "")
        all_system_prompts = [
            STEP_1_OPENING_SYSTEM_ZH,
            STEP_2_OPENING_SYSTEM_ZH,
            STEP_3_OPENING_SYSTEM_ZH,
            STEP_4_OPENING_SYSTEM_ZH,
            STEP_5_OPENING_SYSTEM_ZH,
            STEP_6_OPENING_SYSTEM_ZH,
            STEP_7_OPENING_SYSTEM_ZH,
            RUMINATION_ENTRY_INIT_SYSTEM_ZH,
            RUMINATION_CLOSING_EPILOGUE_SYSTEM_ZH,
        ]
        for i, sys_prompt in enumerate(all_system_prompts, 1):
            assert fingerprint not in sys_prompt, (
                f"system prompt #{i} 不应包含 step_copy intro 内容"
            )

    def test_step_copy_outro_not_in_any_opening(self):
        """step_copy outro 不会出现在任何 opening 模板中。"""
        outro = get_step_copy("rumination", "outro", "zh")
        if not outro:
            pytest.skip("rumination outro 为空")
        fingerprint = outro[:20].replace("\n", "")
        for step, tmpl in STEP_OPENING_FIXED_ZH.items():
            assert fingerprint not in tmpl


# ===========================================================================
# 7. chat_addon 与 opening 隔离
# ===========================================================================

class TestChatAddonIsolation:
    """确保 RUMINATION_CHAT_STEP_ADDON 不会出现在 opening 中。"""

    def test_addon_not_in_fixed_opening(self):
        """chat_addon 的内容不应出现在固定引导语中。"""
        for step, addon_text in RUMINATION_CHAT_STEP_ADDON_ZH.items():
            fixed = STEP_OPENING_FIXED_ZH.get(step, "")
            if addon_text and fixed:
                # 取 addon 前 15 字做指纹
                fingerprint = addon_text[:15]
                assert fingerprint not in fixed, (
                    f"step {step} chat_addon 不应出现在 fixed opening 中"
                )

    def test_addon_not_in_llm_system_opening(self):
        """chat_addon 不会被 build_opening_llm_messages 引用。"""
        all_step_systems = {
            1: STEP_1_OPENING_SYSTEM_ZH,
            2: STEP_2_OPENING_SYSTEM_ZH,
            3: STEP_3_OPENING_SYSTEM_ZH,
            4: STEP_4_OPENING_SYSTEM_ZH,
            5: STEP_5_OPENING_SYSTEM_ZH,
            6: STEP_6_OPENING_SYSTEM_ZH,
            7: STEP_7_OPENING_SYSTEM_ZH,
        }
        for step, addon in RUMINATION_CHAT_STEP_ADDON_ZH.items():
            sys_prompt = all_step_systems.get(step, "")
            if addon and sys_prompt:
                fingerprint = addon[:15]
                assert fingerprint not in sys_prompt, (
                    f"step {step} chat_addon 不应出现在 opening system prompt 中"
                )

    def test_get_chat_step_addon_coverage(self):
        """get_rumination_chat_step_addon 覆盖步骤 1-7。"""
        for step in range(1, 8):
            addon_zh = get_rumination_chat_step_addon(step, "zh")
            addon_en = get_rumination_chat_step_addon(step, "en")
            assert addon_zh, f"step {step} 缺少中文 addon"
            assert addon_en, f"step {step} 缺少英文 addon"


# ===========================================================================
# 8. deep_chat system prompt 与 opening 隔离
# ===========================================================================

class TestDeepChatIsolation:
    """确保深入聊天（neg gate）的 system 片段不会出现在 opening 中。"""

    def test_deep_chat_steps_match_expected(self):
        """DEEP_CHAT_STEP_SYSTEM_MAP 仅包含步骤 2/3/5/6。"""
        assert set(DEEP_CHAT_STEP_SYSTEM_MAP.keys()) == {2, 3, 5, 6}

    def test_deep_chat_not_in_opening_system(self):
        """深入聊天 system 片段不等于任何 opening system prompt。"""
        all_opening_systems = {
            2: STEP_2_OPENING_SYSTEM_ZH,
            3: STEP_3_OPENING_SYSTEM_ZH,
            5: STEP_5_OPENING_SYSTEM_ZH,
            6: STEP_6_OPENING_SYSTEM_ZH,
        }
        for step, deep_sys in DEEP_CHAT_STEP_SYSTEM_MAP.items():
            opening_sys = all_opening_systems.get(step)
            if opening_sys:
                assert deep_sys != opening_sys, (
                    f"step {step} deep_chat system 不应等于 opening system"
                )


# ===========================================================================
# 9. build_opening_context 边界
# ===========================================================================

class TestBuildOpeningContext:
    """验证 build_opening_context 的数据组装逻辑。"""

    def test_basic_context_fields(self):
        """基本字段正确填充。"""
        ctx = _make_ctx(filter_step=3, row_count=4, values_list=["诚信"])
        assert ctx.filter_step == 3
        assert ctx.row_count == 4
        assert "诚信" in ctx.values_keywords

    def test_empty_table_returns_zero_rows(self):
        """空表格时 row_count 为 0。"""
        progress = {"filter_step": 1, "filter_table": [], "filter_step_snapshots": {}}
        ctx = build_opening_context(filter_step=1, progress=progress, values_list=[])
        assert ctx.row_count == 0
        assert ctx.table_json == "[]"

    def test_table_json_truncation(self):
        """超长表格 JSON 被截断。"""
        from app.domain.rumination_prompt_strings import RUMINATION_OPENING_TABLE_JSON_MAX_LEN
        big_rows = [{"id": str(i), "data": "x" * 100} for i in range(200)]
        progress = {"filter_step": 1, "filter_table": big_rows, "filter_step_snapshots": {}}
        ctx = build_opening_context(filter_step=1, progress=progress, values_list=[])
        assert len(ctx.table_json) <= RUMINATION_OPENING_TABLE_JSON_MAX_LEN + 20

    def test_step_clamped_to_valid_range(self):
        """步骤号被限制在 1-7。"""
        progress = {"filter_step": 1, "filter_table": [], "filter_step_snapshots": {}}
        ctx_low = build_opening_context(filter_step=0, progress=progress, values_list=[])
        assert ctx_low.filter_step == 1
        ctx_high = build_opening_context(filter_step=99, progress=progress, values_list=[])
        assert ctx_high.filter_step == 7
