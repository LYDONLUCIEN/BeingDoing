"""
Rumination 筛选流程的表格操作函数

与 rumination_prompt.md 中描述的函数对应。
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.domain.conclusion_card_goals import cap_strengths_keywords_list
from app.utils.survey_storage import load_dimension_conclusions

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 关键词来源标记（source tags）——用于日志与调试定位
# ---------------------------------------------------------------------------
_SOURCE_CONFIRMED = "confirmed_card"   # 已确认结论卡（dimension_conclusions.json）
_SOURCE_ANCHOR = "report_anchor"       # report record.json anchor_summary.goals
_SOURCE_TEXT = "prior_text"            # prior_context_*.txt 全文摘词（降权）
_SOURCE_NONE = "none"                  # 无任何来源

# 与前端「假设」列一致；当前文案为「无」，历史数据可能仍为「待定」「暂未选定」
RUMINATION_HYP_PENDING_MARKERS = frozenset({"待定", "暂未选定", "无"})


def is_rumination_hypothesis_pending(val: Any) -> bool:
    t = str(val or "").strip()
    return not t or t in RUMINATION_HYP_PENDING_MARKERS


def is_rumination_step3_row_hypothesis_complete(val: Any) -> bool:
    """子步 3：用户须显式选「无」或填写非空文案（不允许留空或前端内部标记）。"""
    t = str(val or "").strip()
    if not t or t.startswith("__rum_s3_"):
        return False
    return True


def is_rumination_step3_positive_hypothesis(val: Any) -> bool:
    """非「无 / 待定」类的自填假设（用于统计是否至少有一条实质方向）。"""
    t = str(val or "").strip()
    if not t:
        return False
    return t not in RUMINATION_HYP_PENDING_MARKERS


# 与 survey_storage prior 块标题一致；正则兼容新旧四维名称
_RE_VALUES = re.compile(
    r"【(?:价值观|信念)[^】]*阶段结果】\s*\n(.*?)(?=【|$)", re.DOTALL
)
_RE_STRENGTHS = re.compile(
    r"【(?:优势|禀赋)[^】]*阶段结果】\s*\n(.*?)(?=【|$)", re.DOTALL
)
_RE_INTERESTS = re.compile(
    r"【(?:热爱|热忱)[^】]*阶段结果】\s*\n(.*?)(?=【|$)", re.DOTALL
)
_RE_PURPOSE = re.compile(r"【使命[^】]*阶段结果】\s*\n(.*?)(?=【|$)", re.DOTALL)

# ---------------------------------------------------------------------------
# 句子级片段过滤器（白名单规则）
# 用于 strict 模式下过滤 prior_context 全文摘词，防止推理文本碎片被当作关键词
# ---------------------------------------------------------------------------
# 以这些词开头的片段大概率是句子而非关键词
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
# 包含这些标点的片段视为句子片段
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


def _normalize_alpha_marker(text: Any) -> str:
    """清洗文本前后的孤立括号字符。

    修复场景：
      - '(a 文案' -> '(a) 文案'（历史字母标记缺右括号）
      - ')文案' / '）文案' 等左侧孤立闭括号 -> '文案'
      - '（文案'（无配对闭括号时） -> '文案'
      - '(文案'（无配对闭括号时） -> '文案'
    """
    s = str(text or "").strip()
    if not s:
        return ""
    # 修复 '(a 文案' -> '(a) 文案'（历史字母标记缺右括号）
    s = re.sub(r"^\(([A-Za-z])\s+", r"(\1) ", s)
    # 清除左侧孤立的闭括号（半角/全角）
    s = re.sub(r"^[)）\u3011]+", "", s)
    # 左侧孤立的开括号：无配对时移除（全角）
    if s.startswith("（") and "）" not in s:
        s = s.lstrip("（")
    # 左侧孤立的开括号：无配对时移除（半角）
    if s.startswith("(") and ")" not in s:
        s = s.lstrip("(")
    return s.strip()


# a/b/c 标记 → 表格「优势标记」下拉选项文本
_MARKER_TO_LABEL: Dict[str, str] = {
    "a": "有充实感，与成功有关",
    "b": "有充实感",
    "c": "不确定",
}

# 允许的标记值
_MARKER_ALLOWED = frozenset({"a", "b", "c"})


def load_strength_markers(reports_root: str, report_id: str) -> List[str]:
    """从 dimension_conclusions.json 读取 strengths 的 strength_markers。

    Returns:
        与 strengths keywords 等长的标记列表（小写 a/b/c），
        缺失或格式异常时返回空列表。
    """
    store = load_dimension_conclusions(report_id, reports_root)
    conclusion = store.get("strengths")
    if not isinstance(conclusion, dict):
        return []
    markers = conclusion.get("strength_markers")
    if not isinstance(markers, list):
        return []
    out: List[str] = []
    for m in markers:
        v = str(m).strip().lower()
        out.append(v if v in _MARKER_ALLOWED else "")
    return out


def gen_table(
    strengths: List[str],
    passions: List[str],
    strength_markers: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    第一步：生成热爱×优势组合表格。
    列：id, 热爱, 优势, 优势标记

    strength_markers: 与 strengths 等长的标记列表（小写 a/b/c），
      来自 dimension_conclusions.json。为空或长度不匹配时默认 "有充实感"。
    """
    if not strengths:
        strengths = ["优势1", "优势2"]
    if not passions:
        passions = ["热爱1", "热爱2"]
    # 归一化标记
    markers = strength_markers if isinstance(strength_markers, list) else []
    rows: List[Dict[str, Any]] = []
    idx = 1
    for p in passions[:6]:
        p_norm = _normalize_alpha_marker(p)
        for si, s in enumerate(strengths[:5]):
            s_norm = _normalize_alpha_marker(s)
            # 标记按 strengths 索引对应（多热爱复用同一组标记）
            mk = ""
            if si < len(markers):
                mk = str(markers[si]).strip().lower()
            label = _MARKER_TO_LABEL.get(mk, "有充实感")
            rows.append(
                {
                    "id": str(idx),
                    "热爱": p_norm,
                    "优势": s_norm,
                    "优势标记": label,
                }
            )
            idx += 1
    return rows


def filter_strength(table: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """删除 优势标记 为「不确定」的行"""
    return [r for r in table if (r.get("优势标记") or "").strip() != "不确定"]


def filter_match(table: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """第二步：新增 匹配性、匹配原因 列"""
    result = []
    for r in table:
        row = dict(r)
        row.setdefault("匹配性", "匹配")
        row.setdefault("匹配原因", "结合良好")
        result.append(row)
    return result


def _strip_non_matching_rows(table: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """删除 匹配性 为「不匹配」的行（进入假设轮前）"""
    return [dict(r) for r in table if (r.get("匹配性") or "").strip() != "不匹配"]


def _remove_keys(row: Dict[str, Any], keys: Tuple[str, ...]) -> Dict[str, Any]:
    out = dict(row)
    for k in keys:
        out.pop(k, None)
    return out


def structure_hypothesis_round1_table(table: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    假设子步入口：把第 2 步「匹配性」表变成第 3 步表结构。

    处理逻辑：
    1. 仅保留「匹配性 != 不匹配」的行。
    2. 去掉「匹配原因」列。
    3. 「假设1」「假设2」「假设3」清空（假设仅在对话中探讨，不写入表的二选一推荐列）。
    4. 保留行内已有「用户确认的假设」。

    不再批量调用 LLM 预填假设列。
    """
    matched = _strip_non_matching_rows(table)
    out: List[Dict[str, Any]] = []
    for r in matched:
        row = _remove_keys(r, ("匹配原因",))
        row["假设1"] = ""
        row["假设2"] = ""
        row["假设3"] = ""
        row["用户确认的假设"] = (row.get("用户确认的假设") or "").strip()
        out.append(row)
    return out


def fallback_hypotheses(passion: str, strength: str, seed: int = 0) -> Tuple[str, str, str]:
    """LLM 不可用时的三条占位假设"""
    p, s = passion or "该领域", strength or "该优势"
    return (
        f"在「{p}」方向深耕，发挥「{s}」形成个人作品或服务",
        f"以「{s}」为杠杆，为「{p}」相关人群提供解决方案",
        f"探索「{p}」与「{s}」交叉的新型协作或内容形态",
    )


def generate_hypotheses_round2_table(table: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    第四轮：仅对「用户确认的假设」为空的行清空并等待新假设（假设1、假设2 由 LLM 覆盖；假设3 保持空）。
    """
    out: List[Dict[str, Any]] = []
    for r in table:
        row = dict(r)
        confirmed = (row.get("用户确认的假设") or "").strip()
        if not confirmed:
            row["假设1"] = ""
            row["假设2"] = ""
            row["假设3"] = ""
        out.append(row)
    return out


def generate_hypotheses_round3_finalize(table: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    第五轮提交后：仍空的「用户确认的假设」标为「无」（假设列可由上一轮 LLM 填充）。历史值「暂未选定」「待定」仍被识别为同义。
    """
    out: List[Dict[str, Any]] = []
    for r in table:
        row = dict(r)
        if not (row.get("用户确认的假设") or "").strip():
            row["用户确认的假设"] = "无"
        out.append(row)
    return out


def value_filter(table: List[Dict[str, Any]], values: List[str]) -> List[Dict[str, Any]]:
    """
    第六步入口：删除空/待定行，删除假设列，新增「工作目的」空列。
    values 仅用于下拉选项配置，不写入行内。
    """
    result: List[Dict[str, Any]] = []
    for r in table:
        hyp = (r.get("用户确认的假设") or "").strip()
        if is_rumination_hypothesis_pending(hyp):
            continue
        row = _remove_keys(r, ("假设1", "假设2", "假设3"))
        row["工作目的"] = ""
        result.append(row)
    return result


def passion_filter(table: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    第七步入口：删除「工作目的」为「都不符合」的行，新增「激情标记」列。
    """
    result: List[Dict[str, Any]] = []
    for r in table:
        if (r.get("工作目的") or "").strip() == "都不符合":
            continue
        row = dict(r)
        row.setdefault("激情标记", "")
        result.append(row)
    return result


def reality_filter(table: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    第八步入口：删除「激情标记」为「应该做」的行，新增「现实标记」列。
    """
    result: List[Dict[str, Any]] = []
    for r in table:
        if (r.get("激情标记") or "").strip() == "应该做":
            continue
        row = dict(r)
        row.setdefault("现实标记", "")
        result.append(row)
    return result


def similar_filter(table: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    第九步入口：删除「现实标记」为「未来」的行，仅保留 id 与 用户确认的假设。
    """
    result: List[Dict[str, Any]] = []
    for r in table:
        if (r.get("现实标记") or "").strip() == "未来":
            continue
        result.append(
            {
                "id": str(r.get("id", "")),
                "用户确认的假设": (r.get("用户确认的假设") or "").strip(),
            }
        )
    return result


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


def extract_lists_from_report_record(
    record: Optional[Dict[str, Any]],
) -> Tuple[List[str], List[str], List[str], List[str]]:
    """从 report 的 record.json（steps.*.anchor_summary.goals）补全四维关键词。"""
    if not record or not isinstance(record, dict):
        return [], [], [], []
    steps = record.get("steps") or {}

    def one(phase: str) -> List[str]:
        st = steps.get(phase) or {}
        if not isinstance(st, dict):
            return []
        anchor = st.get("anchor_summary") or {}
        g = str(anchor.get("goals") or "")
        if phase == "purpose":
            q = re.search(r"[「“]([^」”]{2,120})[」”]", g)
            if q:
                return [q.group(1).strip()]
        got = extract_keywords_from_anchor_goals(g, 12)
        if phase == "strengths":
            return cap_strengths_keywords_list(got)
        return got

    return (
        one("values"),
        one("strengths"),
        one("interests"),
        one("purpose"),
    )


def extract_from_prior_context(prior_context: str) -> Tuple[List[str], List[str], List[str], List[str]]:
    """
    从 prior_context 文本中提取 价值观、优势、热爱、使命 关键词列表。
    返回 (values, strengths, interests, purpose)
    """
    values: List[str] = []
    strengths: List[str] = []
    interests: List[str] = []
    purpose: List[str] = []
    mv = _RE_VALUES.search(prior_context or "")
    if mv:
        values = _extract_keywords(mv.group(1), 12)
    ms = _RE_STRENGTHS.search(prior_context or "")
    if ms:
        strengths = cap_strengths_keywords_list(_extract_keywords(ms.group(1), 12))
    mi = _RE_INTERESTS.search(prior_context or "")
    if mi:
        interests = _extract_keywords(mi.group(1), 8)
    mp = _RE_PURPOSE.search(prior_context or "")
    if mp:
        purpose = _extract_keywords(mp.group(1), 8)
    return (values, strengths, interests, purpose)


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
        q = re.search(r"[「""]([^」""]{2,120})[」""]", g)
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
            "[rumination] %s: source=%s, count=%d, sample=%s",
            phase, _SOURCE_CONFIRMED, len(confirmed), confirmed[:3],
        )
        return confirmed, _SOURCE_CONFIRMED

    # ── 优先级 2：report anchor（AI 中间产物的结构化目标）──
    anchor_kw = _keywords_from_report_anchor(record_obj, phase, limit)
    if anchor_kw:
        logger.info(
            "[rumination] %s: source=%s, count=%d, sample=%s",
            phase, _SOURCE_ANCHOR, len(anchor_kw), anchor_kw[:3],
        )
        return anchor_kw, _SOURCE_ANCHOR

    # ── 优先级 3：全文摘词回退（strict 模式，大幅降低权重）──
    text = _read_prior_context(report_dir, phase)
    if text:
        extracted = _extract_keywords(text, limit, strict=True)
        if extracted:
            logger.info(
                "[rumination] %s: source=%s(strict), count=%d, sample=%s",
                phase, _SOURCE_TEXT, len(extracted), extracted[:3],
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


def extract_dimension_lists_for_rumination_table(
    reports_root: str,
    report_id: str,
    record_obj: Optional[Dict[str, Any]],
) -> Tuple[List[str], List[str], List[str], List[str], Dict[str, str]]:
    """
    为筛选表生成「热爱×优势」等行数据用的关键词列表。

    优先级（从高到低）：
      1. 已确认结论卡关键词（dimension_conclusions.json，用户已确认）
      2. report anchor（record.json 中各维 anchor_summary.goals）
      3. prior_context 全文摘词（strict 模式，降权并过滤句子级碎片）

    每个维度的来源通过 logger 输出 source tag，便于定位回退链路。

    Returns:
        (values, strengths, interests, purpose, sources)
        sources 为 {"values": source_tag, "strengths": ..., "interests": ..., "purpose": ...}
    """
    logger.info("[rumination] extract_dimension_lists: report_id=%s START", report_id)

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
        "[rumination] extract_dimension_lists: report_id=%s DONE — "
        "sources: values=%s(%d), strengths=%s(%d), interests=%s(%d), purpose=%s(%d)",
        report_id,
        v_src, len(v), s_src, len(s), i_src, len(i), p_src, len(p),
    )
    return (v, s, i, p, sources)


# ---------------------------------------------------------------------------
# 价值观关键词快照工具（保证下拉选项与右侧对话引用同一来源）
# ---------------------------------------------------------------------------
# 快照存储键名（存在 filter_step_snapshots["4"] 内）
_VALUES_SNAPSHOT_KEY = "_values_snapshot"
_VALUES_SNAPSHOT_FIELDS = ("keywords", "source")


def build_values_snapshot(
    values_keywords: List[str], source_tag: str
) -> Dict[str, Any]:
    """构建价值观关键词快照字典，供存储到 step 4 snapshot。"""
    return {"keywords": list(values_keywords), "source": source_tag}


def load_values_snapshot_from_snapshots(
    snapshots: Dict[str, Any], step: int = 4
) -> Optional[Tuple[List[str], str]]:
    """从 filter_step_snapshots[step] 中加载价值观关键词快照。

    Returns:
        (keywords, source_tag) 或 None（快照不存在/格式不合法时）。
    """
    ent = (snapshots or {}).get(str(step))
    if not isinstance(ent, dict):
        return None
    snap = ent.get(_VALUES_SNAPSHOT_KEY)
    if not isinstance(snap, dict):
        return None
    kws = snap.get("keywords")
    src = snap.get("source", "")
    if not isinstance(kws, list):
        return None
    valid = [str(x).strip() for x in kws if str(x).strip()]
    if not valid:
        return None
    return valid, str(src)


def save_values_snapshot_to_snapshots(
    snapshots: Dict[str, Any],
    values_keywords: List[str],
    source_tag: str,
    step: int = 4,
) -> Dict[str, Any]:
    """将价值观关键词快照写入 filter_step_snapshots[step]，返回更新后的 snapshots。"""
    snapshots = dict(snapshots or {})
    sk = str(step)
    ent = dict(snapshots.get(sk) or {})
    ent[_VALUES_SNAPSHOT_KEY] = build_values_snapshot(values_keywords, source_tag)
    snapshots[sk] = ent
    return snapshots


def resolve_values_for_step4(
    reports_root: str,
    report_id: str,
    record_obj: Optional[Dict[str, Any]],
    snapshots: Dict[str, Any],
) -> Tuple[List[str], str]:
    """统一解析 step 4 使用的价值观关键词：优先使用已有快照，无快照时实时解析。

    保证下拉选项与右侧对话引用同一来源，避免关键词漂移。

    Returns:
        (values_keywords, source_tag)
    """
    # ── 优先使用已保存的快照（保证一致性）──
    cached = load_values_snapshot_from_snapshots(snapshots, step=4)
    if cached is not None:
        kws, src = cached
        logger.info(
            "[rumination] resolve_values_for_step4: using snapshot, source=%s, count=%d",
            src, len(kws),
        )
        return kws, src

    # ── 无快照时实时解析（首次进入 step 4 或快照丢失）──
    v, s, i, p, sources = extract_dimension_lists_for_rumination_table(
        reports_root, report_id, record_obj
    )
    src = sources.get("values", _SOURCE_NONE)
    logger.info(
        "[rumination] resolve_values_for_step4: live resolve, source=%s, count=%d",
        src, len(v),
    )
    return v, src


def build_prior_keywords_summary(prior_context: str) -> str:
    """供 system prompt 使用的四维关键词摘要（短）。"""
    v, s, i, p = extract_from_prior_context(prior_context)
    lines = []
    if v:
        lines.append(f"- 价值观关键词：{'、'.join(v[:8])}")
    if s:
        lines.append(f"- 优势关键词：{'、'.join(cap_strengths_keywords_list(s))}")
    if i:
        lines.append(f"- 热爱关键词：{'、'.join(i[:6])}")
    if p:
        lines.append(f"- 工作目的/使命关键词：{'、'.join(p[:6])}")
    if not lines:
        return "（尚未从 prior 中解析到结构化关键词，请结合 prior_block 全文引导用户。）"
    return "\n".join(lines)
