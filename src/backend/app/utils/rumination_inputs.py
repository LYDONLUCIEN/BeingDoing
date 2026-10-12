"""沉淀输入：从已确认结论、报告锚点和历史摘要解析四维关键词。"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.domain.conclusion_card_goals import cap_strengths_keywords_list
from app.utils.survey_storage import load_dimension_conclusions

logger = logging.getLogger(__name__)


_SOURCE_CONFIRMED = "confirmed_card"  # 已确认结论卡（dimension_conclusions.json）


_SOURCE_ANCHOR = "report_anchor"  # report record.json anchor_summary.goals


_SOURCE_TEXT = "prior_text"  # prior_context_*.txt 全文摘词（降权）


_SOURCE_NONE = "none"  # 无任何来源


_SENTENCE_STARTER_RE = re.compile(
    r"^(?:我(?:认为|觉得|希望|想|觉得|相信|发现)|"
    r"你(?:觉得|认为|可以|可能)|"
    r"(?:这个|那个|其实|可能|应该|可以|因为|所以|但是|而且|"
    r"或者|如果|虽然|然而|不过|同时|另外|首先|其次|"
    r"最后|总的来说|总的来说|从某种角度|对我来说|在我看来|"
    r"我们需要|一方面|另一方面|举个例子|比如说|比如说|"
    r"换句话说|也就是说|值得注意的是|除此之外|相比之下|"
    r"相比之下|更重要的是))",
)


_SENTENCE_END_RE = re.compile(r"[。！？!?\n]")


def _is_sentence_fragment(text: str) -> bool:
    """判断文本是否像句子片段而非关键词（白名单过滤器）。

    返回 True 表示应被过滤掉。
    """
    t = text.strip()
    if not t:
        return True
    # 含句末标点 → 句子
    if _SENTENCE_END_RE.search(t):
        return True
    # 以常见话语标记开头 → 句子
    if _SENTENCE_STARTER_RE.match(t):
        return True
    return False


def _extract_keywords(text: str, limit: int = 10, *, strict: bool = False) -> List[str]:
    """从段落文本中提取可能的关键词（数字序号、顿号/逗号分隔等）。

    strict=True 时启用白名单过滤，拒绝句子级片段并收紧长度上限，
    用于 prior_context 全文回退场景，降低误判权重。
    """
    if not text or not text.strip():
        return []
    max_len = 20 if strict else 40
    found: List[str] = []

    # 第一轮：数字序号列表项（如 "1. xxx"、"2、 xxx"）
    for m in re.finditer(r"\d+[\.、]\s*([^\d\n，。、；]+)", text):
        w = m.group(1).strip()
        if strict and _is_sentence_fragment(w):
            continue
        if w and len(w) <= max_len and w not in found:
            found.append(w)
            if len(found) >= limit:
                return found

    # 第二轮：按标点拆分的短片段（strict 模式下更严格）
    for part in re.split(r"[，、；;]", text):
        w = part.strip()
        if strict and _is_sentence_fragment(w):
            continue
        if w and len(w) <= max_len and w not in found:
            found.append(w)
            if len(found) >= limit:
                return found
    return found[:limit]


def extract_keywords_from_anchor_goals(goals: str, limit: int = 12) -> List[str]:
    """
    从 record.json 里 anchor_summary.goals 抽取短语（顿号/逗号/斜杠分隔）。
    优先匹配「包括…等，」式列举，否则最后一个全角冒号后的片段。
    """
    if not goals or not goals.strip():
        return []
    chunk = ""
    m_inc = re.search(r"包括(.+?)等[，,]", goals)
    if m_inc:
        chunk = m_inc.group(1).strip()
    if not chunk:
        m_inc2 = re.search(r"包括([^。]+?)(?:。|$)", goals)
        if m_inc2:
            chunk = m_inc2.group(1).strip()
    if not chunk:
        for sep in ("：", ":"):
            idx = goals.rfind(sep)
            if idx >= 0:
                tail = goals[idx + 1 :].split("。")[0].strip()
                if len(tail) >= 2:
                    chunk = tail
                    break
    if not chunk:
        q = re.search(r"「([^」]{2,120})」", goals)
        if q:
            return [q.group(1).strip()]
        return _extract_keywords(goals, limit)
    chunk = chunk.replace("/", "、")
    parts = re.split(r"[，、；;]", chunk)
    out: List[str] = []
    for p in parts:
        w = re.sub(r"^[\s\d\.、]+", "", p.strip())
        w = re.sub(r"[\s「」\"'（）\(\)]+$", "", w)
        if not w or len(w) > 50:
            continue
        if w not in out:
            out.append(w)
        if len(out) >= limit:
            break
    return out


def _keywords_from_stored_dimension_conclusion(
    conclusion: Optional[Dict[str, Any]], phase: str, limit: int
) -> List[str]:
    if not isinstance(conclusion, dict):
        return []
    k = conclusion.get("keywords") or []
    if not isinstance(k, list):
        return []
    out = [str(x).strip() for x in k if str(x).strip()]
    if phase == "strengths":
        out = cap_strengths_keywords_list(out)
    return out[:limit]


def _keywords_from_report_anchor(
    record_obj: Optional[Dict[str, Any]], phase: str, limit: int
) -> List[str]:
    """从 report record.json 的 steps.<phase>.anchor_summary.goals 提取关键词。"""
    if not record_obj or not isinstance(record_obj, dict):
        return []
    steps = record_obj.get("steps") or {}
    st = steps.get(phase)
    if not isinstance(st, dict):
        return []
    anchor = st.get("anchor_summary") or {}
    g = str(anchor.get("goals") or "")
    if not g:
        return []
    # purpose 维度特殊处理：优先提取引号内短语
    if phase == "purpose":
        q = re.search(r"[「" "]([^」" "]{2,120})[」" "]", g)
        if q:
            return [q.group(1).strip()]
    got = extract_keywords_from_anchor_goals(g, limit)
    if phase == "strengths":
        return cap_strengths_keywords_list(got)
    return got


def _read_prior_context(report_dir: Path, phase: str) -> str:
    """读取 prior_context_{phase}.txt 文件内容（截断至 12000 字符）。"""
    path = report_dir / f"prior_context_{phase}.txt"
    if not path.is_file():
        return ""
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return raw[:12000] if len(raw) > 12000 else raw


def _resolve_dimension(
    phase: str,
    store: Dict[str, Dict[str, Any]],
    record_obj: Optional[Dict[str, Any]],
    report_dir: Path,
    limit: int,
) -> Tuple[List[str], str]:
    """按优先级级联解析单个维度的关键词列表。

    优先级链路：
      1. confirmed_card — 已确认结论卡关键词（dimension_conclusions.json）
      2. report_anchor  — report record.json anchor_summary.goals
      3. prior_text     — prior_context_{phase}.txt 全文摘词（strict 模式，降权）

    返回 (keywords, source_tag)。
    """
    # ── 优先级 1：已确认结论卡（用户确认的高可信来源）──
    confirmed = _keywords_from_stored_dimension_conclusion(store.get(phase), phase, limit)
    if confirmed:
        logger.info(
            "[rumination] %s: source=%s, count=%d",
            phase,
            _SOURCE_CONFIRMED,
            len(confirmed),
        )
        return confirmed, _SOURCE_CONFIRMED

    # ── 优先级 2：report anchor（AI 中间产物的结构化目标）──
    anchor_kw = _keywords_from_report_anchor(record_obj, phase, limit)
    if anchor_kw:
        logger.info(
            "[rumination] %s: source=%s, count=%d",
            phase,
            _SOURCE_ANCHOR,
            len(anchor_kw),
        )
        return anchor_kw, _SOURCE_ANCHOR

    # ── 优先级 3：全文摘词回退（strict 模式，大幅降低权重）──
    text = _read_prior_context(report_dir, phase)
    if text:
        extracted = _extract_keywords(text, limit, strict=True)
        if extracted:
            logger.info(
                "[rumination] %s: source=%s(strict), count=%d",
                phase,
                _SOURCE_TEXT,
                len(extracted),
            )
            return extracted, _SOURCE_TEXT
        else:
            logger.warning(
                "[rumination] %s: prior_context text found but strict extraction yielded 0 keywords",
                phase,
            )

    # ── 无任何来源 ──
    logger.warning("[rumination] %s: no keywords resolved from any source", phase)
    return [], _SOURCE_NONE


def extract_dimension_inputs(
    reports_root: str,
    report_id: str,
    record_obj: Optional[Dict[str, Any]],
) -> Tuple[List[str], List[str], List[str], List[str], Dict[str, str]]:
    """
    为 v4 组合选择器和上下文提供四维关键词。

    优先级（从高到低）：
      1. 已确认结论卡关键词（dimension_conclusions.json，用户已确认）
      2. report anchor（record.json 中各维 anchor_summary.goals）
      3. prior_context 全文摘词（strict 模式，降权并过滤句子级碎片）

    每个维度仅记录来源与数量，便于定位回退链路，不记录用户关键词。

    Returns:
        (values, strengths, interests, purpose, sources)
        sources 为 {"values": source_tag, "strengths": ..., "interests": ..., "purpose": ...}
    """
    logger.info("[rumination] extract_dimension_inputs: report_id=%s START", report_id)

    store = load_dimension_conclusions(report_id, reports_root)
    report_dir = Path(reports_root) / report_id

    # 逐维度按优先级级联解析
    v, v_src = _resolve_dimension("values", store, record_obj, report_dir, 12)
    s_raw, s_src = _resolve_dimension("strengths", store, record_obj, report_dir, 12)
    s = cap_strengths_keywords_list(s_raw)
    i, i_src = _resolve_dimension("interests", store, record_obj, report_dir, 8)
    p, p_src = _resolve_dimension("purpose", store, record_obj, report_dir, 8)

    sources: Dict[str, str] = {
        "values": v_src,
        "strengths": s_src,
        "interests": i_src,
        "purpose": p_src,
    }

    logger.info(
        "[rumination] extract_dimension_inputs: report_id=%s DONE — "
        "sources: values=%s(%d), strengths=%s(%d), interests=%s(%d), purpose=%s(%d)",
        report_id,
        v_src,
        len(v),
        s_src,
        len(s),
        i_src,
        len(i),
        p_src,
        len(p),
    )
    return (v, s, i, p, sources)
