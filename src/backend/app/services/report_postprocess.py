"""报告后处理修正管线（ADR-0017）。

报告 markdown 一次性生成后、渲染 PDF 前的可插拔修正步骤：

确定性规则（无 LLM，先行执行）：
1. 分页标记规范化：旧式 <div STYLE="page-break-after: always;"></div> 与新标记
   <<<PAGEBREAK>>> 统一为 <div class="pb"></div>（样式在 report_pdf.css 的 .pb）。
2. 列表规范化：行首 * 统一为 -；列表块与前/后普通文本之间补空行，
   避免列表未被 markdown 解析、PDF 里出现字面 "- xxx"。
3. 标题层级归一化：提示词要求最多 #### 但 LLM 常输出 h5（与正文同字号、
   视觉上消失）。规则：h5/h6 → h4；含中文的 h4（章内小节）→ h3；
   纯英文 h4（职业角色英文名副标题）保持 h4。

LLM 修正器（针对特定章节，各自独立 prompt，可插拔扩展）：
4. 信件压缩器：「给读者的一封信」超过 ~700 字时，用专用 prompt 重写至
   550-650 字（信件区 CSS 收紧排版后，该字数 + 签名图可稳定一页内）；
   同时保证信件标题前必有分页符。校验失败 / 调用失败兜底保留原文。
"""

from __future__ import annotations

import logging
import re
from typing import Awaitable, Callable, List, Optional

logger = logging.getLogger(__name__)

# 分页标记契约：提示词要求 LLM 输出 <<<PAGEBREAK>>>，管线统一替换为该 div
PAGEBREAK_TOKEN = "<<<PAGEBREAK>>>"
PAGEBREAK_DIV = '<div class="pb"></div>'

# 信件字数控制（letter CSS 收紧排版后，~650 字 + 签名图可稳定一页内）
_LETTER_COMPRESS_THRESHOLD = 700  # 超过该字数触发压缩
_LETTER_TARGET_MIN = 550
_LETTER_TARGET_MAX = 650
# 压缩结果验收区间（过短说明压坏了，过长说明没压住，都回退原文）
_LETTER_ACCEPT_MIN = 450
_LETTER_ACCEPT_MAX = 750

_LEGACY_PB_RE = re.compile(
    r"<div[^>]*page-break-after\s*:\s*always[^>]*>\s*</div>", re.IGNORECASE
)
_LIST_ITEM_RE = re.compile(r"^(\s*)[-*]\s+")
_STAR_LIST_RE = re.compile(r"^(\s*)\*\s+")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LETTER_HEADING_RE = re.compile(r"^(#{1,6})\s*致.{0,30}一封信\s*$", re.MULTILINE)


def _count_chars(text: str) -> int:
    """计字（忽略空白与 markdown 标记符号），用于中文长文篇幅估算。"""
    return len(re.sub(r"[\s#*>\-`]", "", text))


def _normalize_pagebreaks(text: str) -> str:
    """旧式内联分页 div / <<<PAGEBREAK>>> 统一为 <div class="pb"></div>（独立成行）。"""
    text = _LEGACY_PB_RE.sub(PAGEBREAK_TOKEN, text)
    lines = text.split("\n")
    out: List[str] = []
    for line in lines:
        if PAGEBREAK_TOKEN in line:
            # 标记前后粘连文字时拆行，保证 div 独立成行（否则会被并进段落失效）
            before, _, after = line.partition(PAGEBREAK_TOKEN)
            if before.strip():
                out.append(before.rstrip())
            out.append(PAGEBREAK_DIV)
            if after.strip():
                out.append(after.lstrip())
        else:
            out.append(line)
    return "\n".join(out)


def _normalize_lists(text: str) -> str:
    """行首 * → -；列表块与相邻普通文本之间补空行（跳过代码块）。"""
    lines = text.split("\n")
    out: List[str] = []
    in_code = False
    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
            out.append(line)
            continue
        if in_code:
            out.append(line)
            continue

        normalized = _STAR_LIST_RE.sub(r"\1- ", line)
        is_item = bool(_LIST_ITEM_RE.match(normalized))
        prev = out[-1] if out else ""
        prev_is_item = bool(_LIST_ITEM_RE.match(prev)) if prev.strip() else False

        # 列表块起始：前一行是普通文本 → 补空行（否则 python-markdown 不解析为列表）
        if is_item and prev.strip() and not prev_is_item:
            out.append("")
        # 列表块结束：后接普通文本 → 补空行（否则文本被并进最后一个列表项）
        if not is_item and line.strip() and prev_is_item:
            out.append("")
        out.append(normalized)
    return "\n".join(out)


def _normalize_headings(text: str) -> str:
    """标题层级归一化（跳过代码块）：h5/h6→h4；含中文的 h4→h3；纯英文 h4 保持。"""
    lines = text.split("\n")
    out: List[str] = []
    in_code = False
    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
            out.append(line)
            continue
        if in_code:
            out.append(line)
            continue
        m = _HEADING_RE.match(line)
        if not m:
            out.append(line)
            continue
        level, title = len(m.group(1)), m.group(2)
        if level >= 5:
            level = 4
        elif level == 4 and _CJK_RE.search(title):
            level = 3
        out.append("#" * level + " " + title)
    return "\n".join(out)


def _find_letter_section(text: str) -> Optional[tuple]:
    """定位「致 xxx 的一封信」章节，返回 (标题行起始, 章节结束) 字符区间；找不到返回 None。"""
    match = _LETTER_HEADING_RE.search(text)
    if not match:
        return None
    start = match.start()
    level = len(match.group(1))
    # 章节结束：下一个同级或更高级标题；找不到则到文末
    rest = text[match.end():]
    next_heading = re.search(rf"^#{{1,{level}}}\s", rest, re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(text)
    return start, end


def _ensure_letter_pagebreak(text: str, start: int) -> str:
    """信件标题前若无分页符则补一个，保证信 + 落款签名从新页开始。"""
    prefix = text[:start].rstrip()
    if prefix.endswith(PAGEBREAK_DIV):
        return text
    return prefix + "\n\n" + PAGEBREAK_DIV + "\n\n" + text[start:]


_LETTER_COMPRESS_PROMPT = """你是一位温暖而专业的中文书信编辑。下面是一份职业探索报告末尾「致用户的一封信」的正文。
请将它改写压缩到 {min_len}-{max_len} 字（中文字符计），要求：

1. 保留书信体与原有情感基调：开头感谢、2-3 段以「我看见……」为首的细节段落、结尾肯定与祝福。
2. 保留最具画面感的细节（取材自用户对话的具体小事），删掉重复抒情与空泛总结。
3. 保留结尾署名「寻路·OpenLife」。
4. 直接输出信件正文 markdown，不要输出标题，不要解释。

原信正文：
{letter}
"""


async def _compress_letter(
    text: str,
    start: int,
    end: int,
    llm_call: Callable[[str], Awaitable[str]],
) -> str:
    """信件超阈值时调用 LLM 压缩；任何失败/验收不通过都回退原文。"""
    heading_end = text.index("\n", start) + 1
    heading = text[start:heading_end]
    body = text[heading_end:end].strip()
    original_len = _count_chars(body)
    try:
        prompt = _LETTER_COMPRESS_PROMPT.format(
            min_len=_LETTER_TARGET_MIN, max_len=_LETTER_TARGET_MAX, letter=body
        )
        compressed = (await llm_call(prompt)).strip()
        # 去掉模型可能带回来的标题行
        compressed = re.sub(r"^#{1,6}\s*致.*一封信\s*\n*", "", compressed).strip()
        new_len = _count_chars(compressed)
        if not compressed or not (_LETTER_ACCEPT_MIN <= new_len <= _LETTER_ACCEPT_MAX):
            logger.warning(
                "信件压缩结果验收失败（原 %d 字 / 压缩后 %d 字），保留原文",
                original_len,
                new_len,
            )
            return text
        logger.info("信件压缩完成：%d 字 → %d 字", original_len, new_len)
        return text[:start] + heading + "\n" + compressed + "\n\n" + text[end:].lstrip("\n")
    except Exception:
        logger.exception("信件压缩 LLM 调用失败，保留原文")
        return text


async def apply_report_postprocess(
    markdown_text: str,
    llm_call: Optional[Callable[[str], Awaitable[str]]] = None,
) -> str:
    """报告后处理管线入口。

    Args:
        markdown_text: LLM 一次生成的原始报告 markdown。
        llm_call: 可选的 LLM 调用（输入 prompt 字符串，返回回复文本）；
                  为 None 时跳过所有 LLM 修正器，只跑确定性规则。
    """
    text = _normalize_pagebreaks(markdown_text)
    text = _normalize_lists(text)
    text = _normalize_headings(text)

    section = _find_letter_section(text)
    if section:
        start, end = section
        body = text[text.index("\n", start):end]
        if llm_call and _count_chars(body) > _LETTER_COMPRESS_THRESHOLD:
            text = await _compress_letter(text, start, end, llm_call)
            section = _find_letter_section(text)  # 压缩后重新定位
        if section:
            text = _ensure_letter_pagebreak(text, section[0])
    return text
