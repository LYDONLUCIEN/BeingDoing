"""子步 3 HYP_CANDIDATE 解析与 fallback 触发逻辑测试。"""

import importlib.util
from pathlib import Path

from app.utils.rumination_step3_flow import (
    STEP3_GUIDE_PHRASE,
    count_discuss_user_turns_since_last_forward,
    count_step3_confirmed_rows,
    format_step3_unlocked_rows_block,
    get_step3_row_passion_strength,
    is_strict_hyp_candidate_retry,
    parse_step3_hyp_tool_call,
    resolve_step3_explicit_row_index,
    resolve_step3_hyp_delivery,
    resolve_step3_prompt_mode,
    resolve_step3_target_row_index,
    sanitize_hyp_candidates,
    should_trigger_hyp_candidate_fallback,
    step3_unlocked_row_max_index,
    validate_step3_hyp_target_row,
    visible_reply_suggests_hyp_delivery,
)

_stream_utils_path = (
    Path(__file__).resolve().parents[2] / "src" / "backend" / "app" / "api" / "v1" / "simple_chat" / "stream_utils.py"
)
_spec = importlib.util.spec_from_file_location("_stream_utils_test", _stream_utils_path)
_stream_utils = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_stream_utils)
extract_hyp_candidates = _stream_utils.extract_hyp_candidates
extract_step3_hyp_json = _stream_utils.extract_step3_hyp_json
extract_step3_hyp_output = _stream_utils.extract_step3_hyp_output


def _rows():
    return [
        {"热爱": "教育", "优势": "沟通", "用户确认的假设": "成为教师"},
        {"热爱": "音乐", "优势": "写作", "用户确认的假设": ""},
        {"热爱": "设计", "优势": "审美", "用户确认的假设": "待定"},
    ]


class TestExtractHypCandidates:
    def test_two_blocks(self):
        raw = (
            "引导语\n"
            "[HYP_CANDIDATE]个人事业向：开设音乐写作工作坊[/HYP_CANDIDATE]\n"
            "[HYP_CANDIDATE]职业路径向：加入出版社任内容编辑[/HYP_CANDIDATE]"
        )
        visible, cands = extract_hyp_candidates(raw)
        assert len(cands) == 2
        assert "音乐写作" in cands[0]
        assert "[HYP_CANDIDATE]" not in visible

    def test_malformed_missing_end(self):
        _, cands = extract_hyp_candidates("[HYP_CANDIDATE]只有开始")
        assert cands == []


class TestExtractStep3HypJson:
    def test_json_block_with_row(self):
        raw = (
            "引导语\n"
            "[STEP3_HYP_JSON]\n"
            '{"row": 1, "candidates": ["假设A", "假设B"]}\n'
            "[/STEP3_HYP_JSON]"
        )
        visible, cands, row = extract_step3_hyp_json(raw)
        assert row == 1
        assert cands == ["假设A", "假设B"]
        assert "[STEP3_HYP_JSON]" not in visible

    def test_output_prefers_json(self):
        raw = (
            "[STEP3_HYP_JSON]\n"
            '{"row": 0, "candidates": ["J1", "J2"]}\n'
            "[/STEP3_HYP_JSON]\n"
            "[HYP_CANDIDATE]legacy[/HYP_CANDIDATE]"
        )
        visible, cands, row = extract_step3_hyp_output(raw)
        assert row == 0
        assert cands == ["J1", "J2"]


class TestHypDeliveryResolution:
    def test_explicit_row_wins(self):
        row, unresolved = resolve_step3_hyp_delivery(
            candidates=["a", "b"],
            cursor=2,
            filter_table=_rows(),
            explicit_row_index=0,
            ai_declared_row=1,
        )
        assert row == 0
        assert unresolved is False

    def test_ai_row_when_no_explicit(self):
        row, unresolved = resolve_step3_hyp_delivery(
            candidates=["a", "b"],
            cursor=2,
            filter_table=_rows(),
            explicit_row_index=None,
            ai_declared_row=1,
        )
        assert row == 1
        assert unresolved is False

    def test_unresolved_without_row(self):
        row, unresolved = resolve_step3_hyp_delivery(
            candidates=["a", "b"],
            cursor=2,
            filter_table=_rows(),
            explicit_row_index=None,
            ai_declared_row=None,
        )
        assert row is None
        assert unresolved is True

    def test_invalid_ai_row_unresolved(self):
        row, unresolved = resolve_step3_hyp_delivery(
            candidates=["a", "b"],
            cursor=1,
            filter_table=_rows(),
            explicit_row_index=None,
            ai_declared_row=5,
        )
        assert row is None
        assert unresolved is True


class TestStrictRetryFlag:
    def test_guide_phrase_is_strict(self):
        assert is_strict_hyp_candidate_retry(f"好的，{STEP3_GUIDE_PHRASE}「假设」列") is True

    def test_guide_in_raw_even_if_stripped_from_visible(self):
        raw = f"[STEP3_HYP_JSON]\n{STEP3_GUIDE_PHRASE}\n{{bad json}}\n[/STEP3_HYP_JSON]"
        assert is_strict_hyp_candidate_retry(raw, "") is True

    def test_plain_question_not_strict(self):
        assert is_strict_hyp_candidate_retry("你怎么看？") is False


class TestSanitizeHypCandidates:
    def test_filters_guide_phrase(self):
        cands = sanitize_hyp_candidates(
            [f"{STEP3_GUIDE_PHRASE}「假设」列", "开设音乐工作坊", "加入出版社任编辑"]
        )
        assert len(cands) == 2
        assert "音乐" in cands[0]


class TestParseHypToolCall:
    def test_parses_submit_tool(self):
        tool_calls = [
            {
                "function": {
                    "name": "submit_step3_hypotheses",
                    "arguments": '{"row": 0, "candidates": ["A", "B"]}',
                }
            }
        ]
        cands, row = parse_step3_hyp_tool_call(tool_calls)
        assert row == 0
        assert cands == ["A", "B"]


class TestValidateHypRow:
    def test_unlocked_row_ok(self):
        assert validate_step3_hyp_target_row(1, 2, _rows()) == 1

    def test_locked_row_rejected(self):
        assert validate_step3_hyp_target_row(2, 1, _rows()) is None


class TestUnlockedRows:
    def test_unlocked_includes_cursor_row(self):
        rows = _rows()
        assert step3_unlocked_row_max_index(1, rows) == 1

    def test_unlocked_all_when_cursor_past_end(self):
        rows = _rows()
        assert step3_unlocked_row_max_index(5, rows) == 2

    def test_format_block_lists_indices(self):
        block = format_step3_unlocked_rows_block(_rows(), 1)
        assert "index=0" in block
        assert "index=1" in block
        assert "index=2" not in block
        assert "教育" in block


class TestExplicitRowIndex:
    def test_prefers_action_row(self):
        rows = _rows()
        idx = resolve_step3_explicit_row_index(
            filter_table=rows,
            rumination_row_index=0,
            step3_action_row=2,
        )
        assert idx == 2

    def test_rumination_row_only(self):
        rows = _rows()
        idx = resolve_step3_explicit_row_index(
            filter_table=rows,
            rumination_row_index=0,
            step3_action_row=None,
        )
        assert idx == 0

    def test_none_without_click_or_action(self):
        rows = _rows()
        assert (
            resolve_step3_explicit_row_index(
                filter_table=rows,
                rumination_row_index=None,
                step3_action_row=None,
            )
            is None
        )


class TestTargetRowIndex:
    def test_explicit_over_cursor(self):
        rows = _rows()
        idx = resolve_step3_target_row_index(
            filter_table=rows,
            cursor=2,
            rumination_row_index=0,
            step3_action_row=None,
        )
        assert idx == 0

    def test_cursor_when_no_explicit(self):
        rows = _rows()
        idx = resolve_step3_target_row_index(
            filter_table=rows,
            cursor=1,
            rumination_row_index=None,
            step3_action_row=None,
        )
        assert idx == 1


class TestPromptMode:
    def test_forward_on_table_action(self):
        assert resolve_step3_prompt_mode(step3_table_action="select_none") == "forward"
        assert resolve_step3_prompt_mode(step3_table_action="fill_hypothesis") == "forward"

    def test_discuss_default(self):
        assert resolve_step3_prompt_mode(step3_table_action=None) == "discuss"
        assert resolve_step3_prompt_mode(step3_table_action="regenerate_hyp") == "discuss"


class TestFallbackTrigger:
    def test_no_trigger_when_candidates_present(self):
        assert (
            should_trigger_hyp_candidate_fallback(
                hyp_candidates=["个人事业向：开设音乐工作坊", "职业路径向：加入出版社任编辑"],
                step3_table_action=None,
                step3_prompt_mode="discuss",
            )
            is False
        )

    def test_trigger_when_guide_phrase_misparse_as_candidate(self):
        """引导语被误包进 HYP_CANDIDATE 时仍应 retry。"""
        assert (
            should_trigger_hyp_candidate_fallback(
                hyp_candidates=[f"{STEP3_GUIDE_PHRASE}「假设」列"],
                step3_table_action=None,
                step3_prompt_mode="discuss",
            )
            is True
        )

    def test_trigger_with_guide_phrase_flag_on_raw(self):
        assert (
            should_trigger_hyp_candidate_fallback(
                hyp_candidates=[],
                step3_table_action=None,
                step3_prompt_mode="discuss",
                visible_reply="",
                guide_phrase_present=True,
            )
            is True
        )

    def test_no_trigger_on_forward(self):
        assert (
            should_trigger_hyp_candidate_fallback(
                hyp_candidates=[],
                step3_table_action="select_none",
                step3_prompt_mode="forward",
            )
            is False
        )

    def test_no_trigger_on_plain_discuss_question(self):
        assert (
            should_trigger_hyp_candidate_fallback(
                hyp_candidates=[],
                step3_table_action=None,
                step3_prompt_mode="discuss",
                visible_reply="你对这个方向怎么看？",
                discuss_user_turns_since_forward=0,
            )
            is False
        )

    def test_trigger_on_guide_phrase(self):
        assert (
            should_trigger_hyp_candidate_fallback(
                hyp_candidates=[],
                step3_table_action=None,
                step3_prompt_mode="discuss",
                visible_reply=f"好的，{STEP3_GUIDE_PHRASE}",
            )
            is True
        )

    def test_trigger_on_regenerate_action(self):
        assert (
            should_trigger_hyp_candidate_fallback(
                hyp_candidates=[],
                step3_table_action="regenerate_hyp",
                step3_prompt_mode="discuss",
            )
            is True
        )

    def test_trigger_on_explicit_row(self):
        assert (
            should_trigger_hyp_candidate_fallback(
                hyp_candidates=[],
                step3_table_action=None,
                step3_prompt_mode="discuss",
                explicit_row_index=0,
            )
            is True
        )

    def test_layer2_after_user_turn_non_question(self):
        assert (
            should_trigger_hyp_candidate_fallback(
                hyp_candidates=[],
                step3_table_action=None,
                step3_prompt_mode="discuss",
                visible_reply="根据你说的，这两个方向可能适合你。",
                discuss_user_turns_since_forward=1,
            )
            is True
        )

    def test_layer2_blocked_if_still_question(self):
        assert (
            should_trigger_hyp_candidate_fallback(
                hyp_candidates=[],
                step3_table_action=None,
                step3_prompt_mode="discuss",
                visible_reply="还想再确认一下你的偏好？",
                discuss_user_turns_since_forward=2,
            )
            is False
        )


class TestDiscussUserTurns:
    def test_counts_since_forward(self):
        msgs = [
            {"role": "user", "content": "[表格操作·选无] 用户在第 1 行选择了「无」。"},
            {"role": "assistant", "content": "我们看下一行"},
            {"role": "user", "content": "我觉得可以"},
            {"role": "assistant", "content": "还有呢？"},
        ]
        assert count_discuss_user_turns_since_last_forward(msgs) == 1

    def test_visible_reply_heuristic(self):
        assert visible_reply_suggests_hyp_delivery("这是一个总结。") is True
        assert visible_reply_suggests_hyp_delivery("你怎么看？") is False


class TestRowPassionStrength:
    def test_valid_index(self):
        p, s = get_step3_row_passion_strength(_rows(), 0)
        assert p == "教育"
        assert s == "沟通"


class TestConfirmedRowsCount:
    def test_uses_hyp_field(self):
        assert count_step3_confirmed_rows(_rows()) == 2
