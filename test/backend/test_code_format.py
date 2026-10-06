"""
码格式工具测试（code_format，2026-10-06）

覆盖设计定稿 §3.2 归一化歧义矩阵与 §3.1 生成规则：
1. 生成：前缀/长度/分组/字符集合法（防混淆字符集剔除 0 O 1 I L）
2. 归一化：大小写/空白/全角横杠/折行换行/下划线
3. 自动补前缀：按输入上下文分流（券码框裸 8 位、激活码框裸 12 位）
4. 兼容：存量 10/12 位裸码在各自上下文原样通过（不触发补全）
5. 跨框输错：退化为「补全后查无此码」形态（可接受的输错框报错）
6. 激活码 body 未分组的重分组对齐
"""

import re

import pytest

from app.utils.code_format import (
    ACTIVATION_BODY_LENGTH,
    ACTIVATION_PREFIX,
    COUPON_BODY_LENGTH,
    COUPON_PREFIX,
    format_activation_body,
    generate_activation_code,
    generate_coupon_code,
    normalize_user_code,
)

_FORBIDDEN = set("01ILO")


class TestGenerate:
    def test_coupon_code_format(self):
        """券码：Q- + 8 位，总长 10，字符集合法"""
        for _ in range(50):
            code = generate_coupon_code()
            assert code.startswith(COUPON_PREFIX)
            body = code[len(COUPON_PREFIX):]
            assert len(body) == COUPON_BODY_LENGTH
            assert not (_FORBIDDEN & set(body))
            assert re.fullmatch(r"[A-Z0-9-]+", code)

    def test_activation_code_format(self):
        """激活码：OPENLIFE- + 12 位 body 分 3 组（4-4-4），字符集合法"""
        for _ in range(50):
            code = generate_activation_code()
            assert code.startswith(ACTIVATION_PREFIX)
            groups = code[len(ACTIVATION_PREFIX):].split("-")
            assert len(groups) == 3
            assert all(len(g) == 4 for g in groups)
            body = "".join(groups)
            assert len(body) == ACTIVATION_BODY_LENGTH
            assert not (_FORBIDDEN & set(body))

    def test_codes_unique(self):
        """批量生成无重复（secrets 随机）"""
        coupons = {generate_coupon_code() for _ in range(500)}
        activations = {generate_activation_code() for _ in range(500)}
        assert len(coupons) == 500
        assert len(activations) == 500


class TestNormalize:
    def test_empty(self):
        assert normalize_user_code("", "coupon") == ""
        assert normalize_user_code("   ", "coupon") == ""
        assert normalize_user_code(None, "coupon") == ""

    def test_case_and_trim(self):
        """小写转大写、首尾空白去除"""
        assert normalize_user_code(" q-k3m7x9a2 ", "coupon") == "Q-K3M7X9A2"
        assert normalize_user_code(
            "openlife-9f2k-8m4p-7x1d", "activation"
        ) == "OPENLIFE-9F2K-8M4P-7X1D"

    def test_fullwidth_dashes(self):
        """全角/异体横杠（富文本复制变体）→ 半角 -"""
        for dash in ("－", "—", "–", "−"):
            assert normalize_user_code(f"Q{dash}K3M7X9A2", "coupon") == "Q-K3M7X9A2"
        assert normalize_user_code("OPENLIFE－9F2K－8M4P－7X1D", "activation") == (
            "OPENLIFE-9F2K-8M4P-7X1D"
        )

    def test_line_wrap_and_whitespace(self):
        """折行/换行/中间空格全部去除（治邮件折行截断与尾随换行）"""
        wrapped = "OPENLIFE-9F2K-\n8M4P-7X1D\n"
        assert normalize_user_code(wrapped, "activation") == "OPENLIFE-9F2K-8M4P-7X1D"
        assert normalize_user_code("Q- K3M7 X9A2", "coupon") == "Q-K3M7X9A2"

    def test_underscore_as_dash(self):
        """下划线口述替代 → -"""
        assert normalize_user_code("Q_K3M7X9A2", "coupon") == "Q-K3M7X9A2"


class TestAutoPrefix:
    def test_coupon_bare_8_gets_prefix(self):
        """券码框：裸 8 位 body 自动补 Q-"""
        assert normalize_user_code("K3M7X9A2", "coupon") == "Q-K3M7X9A2"

    def test_activation_bare_12_gets_prefix_and_grouping(self):
        """激活码框：裸 12 位 body 自动补 OPENLIFE- 并 4-4-4 分组"""
        assert normalize_user_code("9F2K8M4P7X1D", "activation") == "OPENLIFE-9F2K-8M4P-7X1D"

    def test_activation_prefixed_bare_body_regrouped(self):
        """已带 OPENLIFE- 但 body 未分组的输入 → 重分组对齐查找键"""
        assert normalize_user_code("OPENLIFE-9F2K8M4P7X1D", "activation") == (
            "OPENLIFE-9F2K-8M4P-7X1D"
        )


class TestLegacyCompat:
    """存量裸码兼容（歧义矩阵，设计定稿 §3.2）"""

    def test_legacy_coupon_12_bare_untouched_in_coupon_context(self):
        """存量 12 位裸券码在券码框原样通过（不触发补全）"""
        legacy = "AB12CD34EF56"
        assert normalize_user_code(legacy, "coupon") == legacy

    def test_legacy_activation_10_bare_untouched_in_activation_context(self):
        """存量 10 位裸激活码在激活码框原样通过"""
        legacy = "AB12CD34EF"
        assert normalize_user_code(legacy, "activation") == legacy

    def test_legacy_coupon_12_in_activation_box_becomes_prefixed(self):
        """跨框：存量券码输进激活码框 → 补 OPENLIFE- 后查无此码（可接受报错）"""
        assert normalize_user_code("AB12CD34EF56", "activation") == "OPENLIFE-AB12-CD34-EF56"

    def test_activation_body_12_in_coupon_box_untouched(self):
        """跨框：新激活码裸 body 输进券码框 → 不补全，查无此券（可接受报错）"""
        assert normalize_user_code("9F2K8M4P7X1D", "coupon") == "9F2K8M4P7X1D"

    def test_format_activation_body(self):
        assert format_activation_body("9F2K8M4P7X1D") == "9F2K-8M4P-7X1D"
