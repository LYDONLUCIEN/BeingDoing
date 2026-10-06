"""
码格式统一工具（优惠券 / 激活码，2026-10-06）

设计定稿：wiki/开发文档/10-06/优惠券多次核销与码格式区分-设计定稿.md

职责：
1. 新码生成（secrets 随机，防混淆字符集剔除 0/O/1/I/L）：
   - 优惠券：Q- + 8 位（如 Q-K3M7X9A2）
   - 激活码：OPENLIFE- + 12 位 body 分 3 组（如 OPENLIFE-9F2K-8M4P-7X1D）
2. 用户输入归一化（止血折行截断 / 富文本吞横杠 / 手输大小写）：
   trim → 全角横杠映射为 - → 去所有空白 → 转大写 → 按输入上下文自动补前缀

兼容性核心不变式：存量裸码（10 位激活码 / 12 位券码）不含连字符，
新码必含连字符 → 码空间永不相交，精确匹配即兼容。

自动补前缀按 context 分流（裸 12 位在两个输入框撞型，靠分流兜底）：
- 券码框：裸 8 位 → 补 Q-；裸 12 位 → 原样（存量券）
- 激活码框：裸 12 位 → 补 OPENLIFE-；裸 10 位 → 原样（存量激活码）
跨框输错的两种 case 均退化为清晰的「码不存在」报错，可接受（见设计文档歧义矩阵）。
"""

from __future__ import annotations

import re
import secrets
from typing import Final

# ─── 上下文（输入框语义）────────────────────────────────────

COUPON_CONTEXT: Final[str] = "coupon"
ACTIVATION_CONTEXT: Final[str] = "activation"

# ─── 防混淆字符集（剔除 0/O/1/I/L，大写）───────────────────
# 数字 8 个（2-9）+ 字母 23 个（A-Z 去 I L O）= 31 字符
CODE_ALPHABET: Final[str] = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"

# ─── 优惠券：Q- + 8 位 ──────────────────────────────────────
COUPON_PREFIX: Final[str] = "Q-"
COUPON_BODY_LENGTH: Final[int] = 8

# ─── 激活码：OPENLIFE- + 12 位 body 分 3 组（4-4-4）──────────
ACTIVATION_PREFIX: Final[str] = "OPENLIFE-"
ACTIVATION_BODY_LENGTH: Final[int] = 12
ACTIVATION_GROUP_SIZE: Final[int] = 4

# 全角/异体横杠 → 半角连字符（富文本复制常见变体）
_DASH_TRANSLATION = str.maketrans({
    "－": "-",  # 全角减号
    "—": "-",  # em dash
    "–": "-",  # en dash
    "−": "-",  # 数学减号
    "_": "-",  # 下划线（口述场景常见替代）
})
_WHITESPACE_RE = re.compile(r"\s+")


def generate_coupon_code() -> str:
    """生成新格式优惠券码：Q- + 8 位防混淆字符（如 Q-K3M7X9A2）"""
    body = "".join(secrets.choice(CODE_ALPHABET) for _ in range(COUPON_BODY_LENGTH))
    return COUPON_PREFIX + body


def generate_activation_code() -> str:
    """生成新格式激活码：OPENLIFE- + 12 位 body 分 3 组（如 OPENLIFE-9F2K-8M4P-7X1D）"""
    body = "".join(secrets.choice(CODE_ALPHABET) for _ in range(ACTIVATION_BODY_LENGTH))
    return ACTIVATION_PREFIX + format_activation_body(body)


def format_activation_body(body: str) -> str:
    """激活码 12 位裸 body → 4-4-4 分组展示（生成与归一化共用同一形态作查找键）"""
    groups = range(0, len(body), ACTIVATION_GROUP_SIZE)
    return "-".join(body[i : i + ACTIVATION_GROUP_SIZE] for i in groups)


def normalize_user_code(raw: str, context: str) -> str:
    """用户输入码归一化（validate/activate/绑定入口统一走这里）

    步骤：trim → 全角横杠映射 → 去所有空白（治折行截断/尾随换行）→ 大写
    → 无连字符且长度严格等于该上下文的 body 长度时自动补前缀。

    Args:
        raw: 用户原始输入
        context: COUPON_CONTEXT / ACTIVATION_CONTEXT（补全规则按输入框分流）

    Returns:
        归一化后的码（空输入返回 ""，由调用方报「码不能为空」）
    """
    s = (raw or "").strip().translate(_DASH_TRANSLATION)
    s = _WHITESPACE_RE.sub("", s).upper()
    if not s:
        return ""

    # 已带前缀的激活码 body 未分组（OPENLIFE-9F2K8M4P7X1D）→ 重新分组对齐查找键
    if s.startswith(ACTIVATION_PREFIX):
        rest = s[len(ACTIVATION_PREFIX):]
        if "-" not in rest and len(rest) == ACTIVATION_BODY_LENGTH:
            return ACTIVATION_PREFIX + format_activation_body(rest)
        return s

    # 裸码自动补前缀（严格长度触发；存量 10/12 位裸码不触发，原样精确匹配）
    if "-" not in s:
        if context == COUPON_CONTEXT and len(s) == COUPON_BODY_LENGTH:
            return COUPON_PREFIX + s
        if context == ACTIVATION_CONTEXT and len(s) == ACTIVATION_BODY_LENGTH:
            return ACTIVATION_PREFIX + format_activation_body(s)
    return s
