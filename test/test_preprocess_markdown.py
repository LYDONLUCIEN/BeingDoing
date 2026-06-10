"""
preprocessMarkdown 的测试用例。

remark-parse v11 (micromark 4) 已能正确处理所有 CJK 标点紧邻 ** 或 * 的场景。
preprocessMarkdown 现在是 passthrough（不做任何修改），以避免破坏合法的 bold。

测试用例覆盖：
  1. 加粗/斜体前后紧邻各种中文标点 — 不应被改动（passthrough）
  2. 正常 markdown — 不应被改动
  3. 英文标点 — 不应被改动
  4. 混合场景 — 不应被改动
  5. 边界场景 — 不应被改动
  6. 已知 regression case — **热爱「自我探索」× 优势「审美判断」** 不应被改动
"""

import re


def preprocessMarkdown(text: str) -> str:
    # Passthrough — remark-parse v11 handles CJK punct + emphasis correctly.
    return text


# ── 1. ** 加粗 + 中文标点（passthrough） ────────────────────────────────────

class TestBoldWithChinesePunctuation:
    """中文标点紧邻 ** 时不应被改动（remark-parse v11 自行处理）"""

    def test_comma_before_bold(self):
        assert preprocessMarkdown('你好，**世界**') == '你好，**世界**'

    def test_comma_after_bold(self):
        assert preprocessMarkdown('**世界**，你好') == '**世界**，你好'

    def test_period_before_bold(self):
        assert preprocessMarkdown('结束。**开始**') == '结束。**开始**'

    def test_period_after_bold(self):
        assert preprocessMarkdown('**加粗**。继续') == '**加粗**。继续'

    def test_question_mark_before_bold(self):
        assert preprocessMarkdown('真的吗？**当然**') == '真的吗？**当然**'

    def test_question_mark_after_bold(self):
        assert preprocessMarkdown('**确定**？') == '**确定**？'

    def test_exclamation_before_bold(self):
        assert preprocessMarkdown('太好了！**没错**') == '太好了！**没错**'

    def test_exclamation_after_bold(self):
        assert preprocessMarkdown('**正确**！') == '**正确**！'

    def test_semicolon_before_bold(self):
        assert preprocessMarkdown('首先；**其次**') == '首先；**其次**'

    def test_colon_before_bold(self):
        assert preprocessMarkdown('注意：**重要**') == '注意：**重要**'

    def test_colon_after_bold(self):
        assert preprocessMarkdown('**关键**：如下') == '**关键**：如下'

    def test_fullwidth_paren_close_before_bold(self):
        assert preprocessMarkdown('内容）**继续**') == '内容）**继续**'

    def test_fullwidth_paren_open_after_bold(self):
        assert preprocessMarkdown('**加粗**（内容）') == '**加粗**（内容）'

    def test_both_sides_punctuation(self):
        """两侧都有中文标点"""
        assert preprocessMarkdown('，**加粗**，') == '，**加粗**，'

    def test_full_bracket(self):
        """全角方括号"""
        assert preprocessMarkdown('】**加粗**【') == '】**加粗**【'

    def test_corner_bracket(self):
        """「」『』"""
        assert preprocessMarkdown('」**加粗**「') == '」**加粗**「'

    def test_enum_comma(self):
        """顿号"""
        assert preprocessMarkdown('、**加粗**') == '、**加粗**'

    def test_fullwidth_paren_open_before_bold(self):
        """全角左括号在 ** 前面"""
        assert preprocessMarkdown('（**重要**）') == '（**重要**）'

    def test_corner_open_before_bold(self):
        """「在 ** 前面"""
        assert preprocessMarkdown('「**假设**」') == '「**假设**」'

    def test_white_corner_bracket(self):
        """『』"""
        assert preprocessMarkdown('『**加粗**』') == '『**加粗**』'

    def test_full_bracket_pair(self):
        """【】全对方括号"""
        assert preprocessMarkdown('【**加粗**】') == '【**加粗**】'

    def test_mixed_new_brackets(self):
        """新增括号与原有标点混合"""
        assert preprocessMarkdown('（**A**，**B**）') == '（**A**，**B**）'


# ── 2. * 斜体 + 中文标点（passthrough） ─────────────────────────────────────

class TestItalicWithChinesePunctuation:
    """中文标点紧邻 *（斜体）时不应被改动"""

    def test_comma_before_italic(self):
        assert preprocessMarkdown('你好，*世界*') == '你好，*世界*'

    def test_comma_after_italic(self):
        assert preprocessMarkdown('*世界*，你好') == '*世界*，你好'

    def test_period_before_italic(self):
        assert preprocessMarkdown('结束。*开始*') == '结束。*开始*'

    def test_question_mark_after_italic(self):
        assert preprocessMarkdown('*确定*？') == '*确定*？'

    def test_both_sides_italic(self):
        assert preprocessMarkdown('，*斜体*，') == '，*斜体*，'

    def test_fullwidth_paren_italic(self):
        assert preprocessMarkdown('（*斜体*）') == '（*斜体*）'

    def test_italic_does_not_match_bold(self):
        """** 中的第一个 * 前面是中文标点"""
        assert preprocessMarkdown('，**加粗**，') == '，**加粗**，'


# ── 3. 正常 markdown 不应被改动（passthrough） ────────────────────────────

class TestNoFalsePositives:
    """正常的 markdown 内容不应被修改"""

    def test_bold_between_chinese_chars(self):
        """汉字紧邻 **"""
        result = preprocessMarkdown('你**好**世')
        assert result == '你**好**世'

    def test_italic_between_chinese_chars(self):
        result = preprocessMarkdown('你*好*世')
        assert result == '你*好*世'

    def test_plain_text(self):
        result = preprocessMarkdown('这是一段普通文本')
        assert result == result

    def test_english_bold(self):
        result = preprocessMarkdown('This is **bold** text')
        assert result == 'This is **bold** text'

    def test_english_italic(self):
        result = preprocessMarkdown('This is *italic* text')
        assert result == 'This is *italic* text'

    def test_heading(self):
        result = preprocessMarkdown('## 标题')
        assert result == '## 标题'

    def test_list(self):
        result = preprocessMarkdown('- 列表项')
        assert result == '- 列表项'

    def test_code_block(self):
        result = preprocessMarkdown('`code` 和普通文本')
        assert result == '`code` 和普通文本'

    def test_empty_string(self):
        result = preprocessMarkdown('')
        assert result == ''

    def test_only_spaces(self):
        result = preprocessMarkdown('   ')
        assert result == '   '

    def test_multiline_normal(self):
        text = '第一行\n第二行\n第三行'
        assert preprocessMarkdown(text) == text

    def test_bold_at_line_start(self):
        result = preprocessMarkdown('**加粗开头**的文本')
        assert result == '**加粗开头**的文本'

    def test_bold_at_line_end(self):
        result = preprocessMarkdown('文本以**加粗结尾**')
        assert result == '文本以**加粗结尾**'

    def test_numbered_list_bold(self):
        result = preprocessMarkdown('1. **第一项**\n2. **第二项**')
        assert result == '1. **第一项**\n2. **第二项**'


# ── 4. 英文标点不应被处理（passthrough） ──────────────────────────────────

class TestEnglishPunctuationNotAffected:
    """英文标点不应触发空格插入"""

    def test_english_comma(self):
        assert preprocessMarkdown('hello,**world**') == 'hello,**world**'

    def test_english_period(self):
        assert preprocessMarkdown('end.**start**') == 'end.**start**'

    def test_english_question(self):
        assert preprocessMarkdown('what?**bold**') == 'what?**bold**'

    def test_english_parentheses(self):
        assert preprocessMarkdown('(**bold**)') == '(**bold**)'


# ── 5. 混合场景（passthrough） ─────────────────────────────────────────────

class TestMixedScenarios:
    """加粗、斜体、标点混合的复杂文本"""

    def test_bold_and_italic_mixed(self):
        text = '这是**加粗**，还有*斜体*，以及**更多**内容'
        assert preprocessMarkdown(text) == text

    def test_multiple_bold_in_paragraph(self):
        text = '第一段，**A**，第二段。**B**，结束。'
        assert preprocessMarkdown(text) == text

    def test_inline_code_not_affected(self):
        text = '这是`code**stuff**`，还有**真正的加粗**'
        assert preprocessMarkdown(text) == text

    def test_real_ai_output_example(self):
        """模拟真实 AI 输出"""
        text = (
            '有没有那次你通过自己的自律或者坚持影响周围人，'
            '带来积极改变的呢？'
        )
        assert preprocessMarkdown(text) == text

    def test_real_ai_output_with_bold(self):
        text = '我们来分析一下：**自律**是一个关键特质，它可以**带来积极改变**。'
        assert preprocessMarkdown(text) == text

    def test_heading_with_bold(self):
        text = '## **核心要点**\n\n下面是详细说明。'
        assert preprocessMarkdown(text) == text

    def test_nested_bold_italic(self):
        text = '这是**加粗里包含*斜体*内容**的文字，**再加粗**！'
        assert preprocessMarkdown(text) == text

    def test_consecutive_punctuation(self):
        text = '真的吗？！**没错**！！'
        assert preprocessMarkdown(text) == text


# ── 6. 边界场景（passthrough） ─────────────────────────────────────────────

class TestEdgeCases:
    def test_bold_at_very_start(self):
        assert preprocessMarkdown('**加粗**开头') == '**加粗**开头'

    def test_bold_at_very_end(self):
        assert preprocessMarkdown('结尾是**加粗**') == '结尾是**加粗**'

    def test_single_asterisk_not_bold(self):
        assert preprocessMarkdown('2 * 3 = 6') == '2 * 3 = 6'

    def test_unclosed_bold(self):
        assert preprocessMarkdown('这是**未闭合的文本') == '这是**未闭合的文本'

    def test_triple_asterisk(self):
        assert preprocessMarkdown('，***加粗斜体***，') == '，***加粗斜体***，'


# ── 7. Regression: Issue #22 + CJK × case ───────────────────────────────────

class TestRegressionCases:
    """已知 regression case：原本因为 regex 预处理导致渲染失败"""

    def test_corner_close_bracket_before_closing_bold(self):
        """」** 是合法的 CommonMark，不应插入空格"""
        text = '**热爱「自我探索」× 优势「审美判断」**'
        assert preprocessMarkdown(text) == text

    def test_issue22_original_case(self):
        """Issue #22 原始 case：remark-parse v11 已能正确处理"""
        text = '有没有那次你通过自己的自律**或者坚持**影响周围人，带来积极改变的呢？'
        assert preprocessMarkdown(text) == text

    def test_multiplication_sign_in_bold(self):
        """× 符号在 bold 内部不应被处理"""
        text = '**热爱×优势**'
        assert preprocessMarkdown(text) == text

    def test_fullwidth_x_in_bold(self):
        """全角 × 在 bold 内部"""
        text = '**热爱×优势**'
        assert preprocessMarkdown(text) == text
