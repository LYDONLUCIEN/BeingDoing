"""报告后处理修正管线（ADR-0017）单元测试。"""

import asyncio
import sys
import types
from pathlib import Path

import pytest

# report_postprocess 无重依赖；但 app.services 包 __init__ 会拉 sqlalchemy 等，
# 这里按文件路径直接加载模块，保持测试轻量
import importlib.util  # noqa: E402

_MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src" / "backend" / "app" / "services" / "report_postprocess.py"
)
_spec = importlib.util.spec_from_file_location("report_postprocess", _MODULE_PATH)
_rp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_rp)

PAGEBREAK_DIV = _rp.PAGEBREAK_DIV
_count_chars = _rp._count_chars
_normalize_headings = _rp._normalize_headings
_find_letter_section = _rp._find_letter_section
_normalize_lists = _rp._normalize_lists
_normalize_pagebreaks = _rp._normalize_pagebreaks
_normalize_role_opener = _rp._normalize_role_opener
apply_report_postprocess = _rp.apply_report_postprocess


def test_pagebreak_legacy_div_normalized():
    md = "第一章内容\n\n<div STYLE=\"page-break-after: always;\"></div>\n\n第二章内容"
    out = _normalize_pagebreaks(md)
    assert PAGEBREAK_DIV in out
    assert "page-break-after" not in out
    # div 独立成行
    assert f"\n{PAGEBREAK_DIV}\n" in out


def test_pagebreak_token_normalized_and_unstuck():
    md = f"章末文字<<<PAGEBREAK>>>下一章"
    out = _normalize_pagebreaks(md)
    lines = out.split("\n")
    assert PAGEBREAK_DIV in lines
    assert "章末文字" in lines


def test_list_star_to_dash():
    md = "前文\n* 条目一\n* 条目二\n后文"
    out = _normalize_lists(md)
    assert "- 条目一" in out
    assert "* 条目一" not in out


def test_list_blank_line_inserted_around_block():
    md = "前文段落\n- 条目一\n- 条目二\n后文段落"
    out = _normalize_lists(md)
    assert "前文段落\n\n- 条目一\n- 条目二\n\n后文段落" in out


def test_list_skip_code_block():
    md = "```\n* 代码里的星号不动\n```\n* 真列表"
    out = _normalize_lists(md)
    assert "* 代码里的星号不动" in out
    assert "- 真列表" in out


def test_find_letter_section():
    md = "## 第八章 谁与你最接近\n\n内容\n\n## 致小明的一封信\n\n正文段落。\n"
    section = _find_letter_section(md)
    assert section is not None
    start, end = section
    assert md[start:end].startswith("## 致小明的一封信")
    assert "正文段落" in md[start:end]


def test_letter_pagebreak_ensured():
    md = "前一章内容\n\n## 致小明的一封信\n\n" + "短" * 100
    out = asyncio.run(apply_report_postprocess(md, llm_call=None))
    assert f"{PAGEBREAK_DIV}\n\n## 致小明的一封信" in out


def test_short_letter_not_compressed():
    called = False

    async def fake_llm(prompt: str) -> str:
        nonlocal called
        called = True
        return "x"

    md = "前文\n\n## 致小明的一封信\n\n" + "短" * 100
    out = asyncio.run(apply_report_postprocess(md, fake_llm))
    assert not called
    assert "短" * 100 in out


def test_long_letter_compressed():
    async def fake_llm(prompt: str) -> str:
        return "压缩后的信。" + "字" * 700 + "\n\n寻路·OpenLife"

    md = "前文\n\n## 致小明的一封信\n\n" + "长" * 1200
    out = asyncio.run(apply_report_postprocess(md, fake_llm))
    assert "压缩后的信。" in out
    assert "长" * 1200 not in out


def test_compress_validation_failure_keeps_original():
    async def fake_llm(prompt: str) -> str:
        return "太短"

    md = "前文\n\n## 致小明的一封信\n\n" + "长" * 1200
    out = asyncio.run(apply_report_postprocess(md, fake_llm))
    assert "长" * 1200 in out  # 验收失败回退原文


def test_compress_llm_exception_keeps_original():
    async def fake_llm(prompt: str) -> str:
        raise RuntimeError("LLM down")

    md = "前文\n\n## 致小明的一封信\n\n" + "长" * 1200
    out = asyncio.run(apply_report_postprocess(md, fake_llm))
    assert "长" * 1200 in out


def test_heading_h5_promoted_to_h4():
    md = "## 第一章 价值观分析\n\n##### 1. 自我实现\n\n正文"
    out = _normalize_headings(md)
    assert "#### 1. 自我实现" in out
    assert "#####" not in out


def test_heading_cjk_h4_promoted_to_h3():
    md = "#### 一、逐项价值观解析"
    assert _normalize_headings(md) == "### 一、逐项价值观解析"


def test_heading_english_h4_kept():
    md = "#### The Gentle Narrative Builder"
    assert _normalize_headings(md) == "#### The Gentle Narrative Builder"


def test_heading_chapter_h2_untouched():
    md = "## 第三章 热爱分析"
    assert _normalize_headings(md) == "## 第三章 热爱分析"


def test_heading_skip_code_block():
    md = "```\n##### 代码里的标题不动\n```"
    assert "##### 代码里的标题不动" in _normalize_headings(md)


def test_count_chars_ignores_markdown_symbols():
    assert _count_chars("# 标题\n- **加粗** 正文") == len("标题加粗正文")


# ── 职业角色开篇规范化 ─────────────────────────────────


def _role_md(opener: str = None) -> str:
    """构造当前版式报告开头：扉页 + 职业角色章 + 第一章。"""
    parts = [
        "# 小明的寻路之旅",
        "## 阅读指南",
        "指南内容。",
        PAGEBREAK_DIV,
    ]
    if opener:
        parts.append(opener)
    parts += [
        "### 寻路者",
        "#### The Pathfinder",
        "角色描述正文。",
        PAGEBREAK_DIV,
        "## 第一章 价值观分析",
        "第一章内容。",
    ]
    return "\n\n".join(parts)


def test_role_opener_inserted_when_missing():
    out = _normalize_role_opener(_role_md())
    assert "## 开篇：职业角色\n\n### 寻路者" in out


def test_role_opener_level_normalized_to_h2():
    out = _normalize_role_opener(_role_md(opener="### 开篇：职业角色"))
    assert "## 开篇：职业角色" in out
    assert "### 开篇：职业角色" not in out


def test_role_opener_legacy_format_untouched():
    # 旧版报告（无第一章）不做任何改动
    md = "# 寻路报告\n\n## 你的价值观\n\n内容"
    assert _normalize_role_opener(md) == md


def test_role_opener_applied_in_pipeline():
    out = asyncio.run(apply_report_postprocess(_role_md(), llm_call=None))
    assert "## 开篇：职业角色" in out


# ── 职业角色压缩 ─────────────────────────────────


def test_short_role_not_compressed():
    called = False

    async def fake_llm(prompt: str) -> str:
        nonlocal called
        called = True
        return "x"

    md = _role_md(opener="### 开篇：职业角色")
    out = asyncio.run(apply_report_postprocess(md, fake_llm))
    assert not called
    assert "角色描述正文。" in out


def test_long_role_compressed():
    async def fake_llm(prompt: str) -> str:
        return "压缩后的角色描述。" + "字" * 700

    md = _role_md().replace("角色描述正文。", "长" * 1200)
    out = asyncio.run(apply_report_postprocess(md, fake_llm))
    assert "压缩后的角色描述。" in out
    assert "长" * 1200 not in out
    # 标题行原样保留，章末分页符不丢
    assert "## 开篇：职业角色" in out
    assert "### 寻路者" in out
    assert "#### The Pathfinder" in out
    assert f"{PAGEBREAK_DIV}\n\n## 第一章" in out


def test_role_compress_validation_failure_keeps_original():
    async def fake_llm(prompt: str) -> str:
        return "太短"

    md = _role_md().replace("角色描述正文。", "长" * 1200)
    out = asyncio.run(apply_report_postprocess(md, fake_llm))
    assert "长" * 1200 in out  # 验收失败回退原文


def test_role_compress_llm_exception_keeps_original():
    async def fake_llm(prompt: str) -> str:
        raise RuntimeError("LLM down")

    md = _role_md().replace("角色描述正文。", "长" * 1200)
    out = asyncio.run(apply_report_postprocess(md, fake_llm))
    assert "长" * 1200 in out
