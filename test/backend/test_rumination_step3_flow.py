"""子步 3 表格操作辅助函数测试。"""

from pathlib import Path

from app.domain.rumination_prompt_strings import (
    RUMINATION_CHAT_STEP_ADDON_ZH,
    STEP_3_OPENING_SYSTEM_ZH,
    STEP_OPENING_FIXED_ZH,
)
from app.utils.rumination_step3_flow import row_hyp, row_fields_line


def _sample_rows():
    return [
        {"热爱": "教育", "优势": "沟通", "用户确认的假设": ""},
        {"热爱": "教育", "优势": "写作", "用户确认的假设": ""},
    ]


class TestRowHelpers:
    def test_row_hyp_empty(self):
        assert row_hyp({"用户确认的假设": ""}) == ""
        assert row_hyp({}) == ""

    def test_row_hyp_with_value(self):
        assert row_hyp({"用户确认的假设": "成为教师"}) == "成为教师"

    def test_row_fields_line(self):
        row = {"热爱": "音乐", "优势": "编程"}
        result = row_fields_line(row)
        assert "热爱：音乐" in result
        assert "优势：编程" in result

    def test_row_fields_line_missing(self):
        row = {}
        result = row_fields_line(row)
        assert "（未填）" in result


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
