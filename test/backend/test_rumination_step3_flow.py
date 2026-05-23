"""子步 3 表格触发：选「无」跳过、填假设确认提示、auto_unlock 开关。"""

from pathlib import Path

from app.domain.rumination_prompt_strings import (
    RUMINATION_CHAT_STEP_ADDON_ZH,
    STEP_3_OPENING_SYSTEM_ZH,
    STEP_OPENING_FIXED_ZH,
)
from app.utils.rumination_step3_flow import (
    apply_step3_table_trigger,
    build_step3_confirm_prompt,
    build_step3_skip_message,
)


def _sample_rows():
    return [
        {"热爱": "教育", "优势": "沟通", "用户确认的假设": ""},
        {"热爱": "教育", "优势": "写作", "用户确认的假设": ""},
    ]


class TestStep3SkipMessage:
    def test_skip_points_to_next_row(self):
        rows = _sample_rows()
        msg = build_step3_skip_message(2, rows[1])
        assert "第 2 行" in msg
        assert "教育" in msg
        assert "写作" in msg

    def test_skip_last_row_message(self):
        msg = build_step3_skip_message(None, None)
        assert "全部行已处理完毕" in msg


class TestApplyStep3TableTrigger:
    def test_none_advances_cursor(self):
        rows = _sample_rows()
        rows[0]["用户确认的假设"] = "无"
        prog = {"filter_row_cursor": 0, "filter_table": rows}
        effect, new_cursor = apply_step3_table_trigger(
            existing_prog=prog,
            merged_table=rows,
            trigger="none",
        )
        assert effect is not None
        assert effect["type"] == "skip_row"
        assert new_cursor == 1
        assert "跳过" in effect["message"]

    def test_none_does_not_skip_multiple_rows(self):
        rows = _sample_rows()
        rows[0]["用户确认的假设"] = "无"
        prog = {"filter_row_cursor": 0}
        _, new_cursor = apply_step3_table_trigger(
            existing_prog=prog,
            merged_table=rows,
            trigger="none",
        )
        assert new_cursor == 1

    def test_hypothesis_commit_does_not_advance_cursor(self):
        rows = _sample_rows()
        rows[0]["用户确认的假设"] = "成为户外故事领队"
        prog = {"filter_row_cursor": 0}
        effect, new_cursor = apply_step3_table_trigger(
            existing_prog=prog,
            merged_table=rows,
            trigger="hypothesis_commit",
        )
        assert effect is not None
        assert effect["type"] == "confirm_prompt"
        assert new_cursor is None
        assert "确认" in effect["message"]

    def test_confirm_prompt_references_row_fields(self):
        rows = _sample_rows()
        rows[0]["用户确认的假设"] = "成为户外故事领队"
        msg = build_step3_confirm_prompt(1, rows[0])
        assert "第 1 行" in msg
        assert "热爱：教育" in msg


class TestStep3PromptCopyNoLegacyUi:
    OLD_PHRASES = ["两个推荐假设", "重新生成", "🔄", "自定义二选一"]

    def test_fixed_opening_step3_no_legacy(self):
        text = STEP_OPENING_FIXED_ZH[3]
        for phrase in self.OLD_PHRASES:
            assert phrase not in text

    def test_step3_system_no_legacy(self):
        for phrase in self.OLD_PHRASES:
            assert phrase not in STEP_3_OPENING_SYSTEM_ZH

    def test_step3_addon_no_legacy(self):
        addon = RUMINATION_CHAT_STEP_ADDON_ZH[3]
        for phrase in ["两个推荐", "个人事业向 + 进入公司向", "重新生成"]:
            assert phrase not in addon
        assert "ROW_STATE" in addon
        assert "选「无」" in addon or "「无」" in addon


class TestAutoUnlockFlagDefault:
    def test_auto_unlock_disabled_by_default(self):
        content = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "backend"
            / "app"
            / "config"
            / "settings.py"
        ).read_text(encoding="utf-8")
        assert "RUMINATION_STEP3_AUTO_UNLOCK_ENABLED: bool = False" in content
