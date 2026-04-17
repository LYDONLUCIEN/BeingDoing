"""
Rumination 筛选流程的表格操作函数

与 rumination_prompt.md 中描述的函数对应。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.domain.conclusion_card_goals import cap_strengths_keywords_list
from app.utils.survey_storage import load_dimension_conclusions

# 与前端「假设」列「暂未选定」一致；历史数据可能仍为「待定」
RUMINATION_HYP_PENDING_MARKERS = frozenset({"待定", "暂未选定"})


def is_rumination_hypothesis_pending(val: Any) -> bool:
    t = str(val or "").strip()
    return not t or t in RUMINATION_HYP_PENDING_MARKERS


# 与 survey_storage / prior 块标题一致：【信念/禀赋/热忱/使命 阶段结果】
_RE_VALUES = re.compile(r"【信念[^】]*阶段结果】\s*\n(.*?)(?=【|$)", re.DOTALL)
_RE_STRENGTHS = re.compile(r"【禀赋[^】]*阶段结果】\s*\n(.*?)(?=【|$)", re.DOTALL)
_RE_INTERESTS = re.compile(r"【热忱[^】]*阶段结果】\s*\n(.*?)(?=【|$)", re.DOTALL)
_RE_PURPOSE = re.compile(r"【使命[^】]*阶段结果】\s*\n(.*?)(?=【|$)", re.DOTALL)


def _extract_keywords(text: str, limit: int = 10) -> List[str]:
    """从段落文本中提取可能的关键词（数字序号、顿号/逗号分隔等）"""
    if not text or not text.strip():
        return []
    found: List[str] = []
    for m in re.finditer(r"\d+[\.、]\s*([^\d\n，。、；]+)", text):
        w = m.group(1).strip()
        if w and len(w) <= 40 and w not in found:
            found.append(w)
            if len(found) >= limit:
                return found
    for part in re.split(r"[，、；;]", text):
        w = part.strip()
        if w and len(w) <= 40 and w not in found:
            found.append(w)
            if len(found) >= limit:
                return found
    return found[:limit]


def gen_table(strengths: List[str], passions: List[str]) -> List[Dict[str, Any]]:
    """
    第一步：生成热爱×优势组合表格。
    列：id, 热爱, 优势, 优势标记
    """
    if not strengths:
        strengths = ["优势1", "优势2"]
    if not passions:
        passions = ["热爱1", "热爱2"]
    rows: List[Dict[str, Any]] = []
    idx = 1
    for p in passions[:6]:
        for s in strengths[:5]:
            rows.append(
                {
                    "id": str(idx),
                    "热爱": p,
                    "优势": s,
                    "优势标记": "有充实感",
                }
            )
            idx += 1
            if idx > 12:
                return rows
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
    假设子步（第 3 步）入口：把第 2 步「匹配性」表变成可选假设的表结构。

    处理逻辑：
    1. 仅保留「匹配性 != 不匹配」的行（不匹配组合不进入假设轮）。
    2. 去掉「匹配原因」列（后续列由 table_widget 与 LLM 填充）。
    3. 为每行准备「假设1」「假设2」空槽位，由 ``fill_hypothesis_columns_for_table`` 写入两条推荐
      （个人事业向 / 公司职业向）；「假设3」固定为空，不再提供「第三条备选」文案。
    4. 保留行内已有「用户确认的假设」字符串（若历史上有值），前端仍可在该列选择：
       两条推荐之一、「其他」自填、「暂未选定」不选本条——交互与列定义不变，仅少一条备选假设文本。

    假设文案由 LLM 或占位填充，见 ``rumination_hypothesis_service``。
    """
    matched = _strip_non_matching_rows(table)
    out: List[Dict[str, Any]] = []
    for r in matched:
        row = _remove_keys(r, ("匹配原因",))
        row["假设1"] = row.get("假设1") or ""
        row["假设2"] = row.get("假设2") or ""
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
    第五轮提交后：仍空的「用户确认的假设」标为「暂未选定」（假设列可由上一轮 LLM 填充）。
    """
    out: List[Dict[str, Any]] = []
    for r in table:
        row = dict(r)
        if not (row.get("用户确认的假设") or "").strip():
            row["用户确认的假设"] = "暂未选定"
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


def extract_dimension_lists_for_rumination_table(
    reports_root: str,
    report_id: str,
    record_obj: Optional[Dict[str, Any]],
) -> Tuple[List[str], List[str], List[str], List[str]]:
    """
    为筛选表生成「热爱×优势」等行数据用的关键词列表。

    优先用 report record.json 中各维 anchor_summary.goals；其次 dimension_conclusions.json；
    再回退 prior_context_{phase}.txt 全文摘词。
    """
    v, s, i, p = extract_lists_from_report_record(record_obj)
    report_dir = Path(reports_root) / report_id
    store = load_dimension_conclusions(report_id, reports_root)

    def _read_phase_file(phase_key: str) -> str:
        path = report_dir / f"prior_context_{phase_key}.txt"
        if not path.is_file():
            return ""
        try:
            raw = path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
        return raw[:12000] if len(raw) > 12000 else raw

    if not v:
        v = _keywords_from_stored_dimension_conclusion(store.get("values"), "values", 12)
    if not v:
        v = _extract_keywords(_read_phase_file("values"), 12)
    if not s:
        s = _keywords_from_stored_dimension_conclusion(store.get("strengths"), "strengths", 12)
    if not s:
        s = cap_strengths_keywords_list(_extract_keywords(_read_phase_file("strengths"), 12))
    if not i:
        i = _keywords_from_stored_dimension_conclusion(store.get("interests"), "interests", 8)
    if not i:
        i = _extract_keywords(_read_phase_file("interests"), 8)
    purpose_out: List[str] = list(p) if p else []
    if not purpose_out:
        purpose_out = _keywords_from_stored_dimension_conclusion(store.get("purpose"), "purpose", 8)
    if not purpose_out:
        purpose_out = _extract_keywords(_read_phase_file("purpose"), 8)
    return (v, cap_strengths_keywords_list(s), i, purpose_out)


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
