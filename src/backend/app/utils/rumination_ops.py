"""
Rumination 筛选流程的表格操作函数

与 rumination_prompt.md 中描述的函数对应。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

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
        for s in strengths[:4]:
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
    第三步入口：去掉不匹配行与匹配原因列，增加假设列与用户确认列（假设文案由 LLM 或占位填充）。
    """
    matched = _strip_non_matching_rows(table)
    out: List[Dict[str, Any]] = []
    for r in matched:
        row = _remove_keys(r, ("匹配原因",))
        row["假设1"] = row.get("假设1") or ""
        row["假设2"] = row.get("假设2") or ""
        row["假设3"] = row.get("假设3") or ""
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
    第四轮：仅对「用户确认的假设」为空的行清空并等待新假设（假设1-3 由 LLM 覆盖）。
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
    第五轮提交后：仍空的「用户确认的假设」标为「待定」（假设列可由上一轮 LLM 填充）。
    """
    out: List[Dict[str, Any]] = []
    for r in table:
        row = dict(r)
        if not (row.get("用户确认的假设") or "").strip():
            row["用户确认的假设"] = "待定"
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
        if not hyp or hyp == "待定":
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
        strengths = _extract_keywords(ms.group(1), 12)
    mi = _RE_INTERESTS.search(prior_context or "")
    if mi:
        interests = _extract_keywords(mi.group(1), 8)
    mp = _RE_PURPOSE.search(prior_context or "")
    if mp:
        purpose = _extract_keywords(mp.group(1), 8)
    return (values, strengths, interests, purpose)


def merge_row_by_id(table: List[Dict[str, Any]], row_id: str, patch: Dict[str, Any]) -> List[Dict[str, Any]]:
    """将 patch 合并到指定 id 的行，找不到则追加（不应发生）。"""
    rid = str(row_id).strip()
    found = False
    out: List[Dict[str, Any]] = []
    for r in table:
        if str(r.get("id", "")).strip() == rid:
            merged = dict(r)
            for k, v in patch.items():
                if v is not None:
                    merged[k] = v
            out.append(merged)
            found = True
        else:
            out.append(dict(r))
    if not found and patch:
        out.append({"id": rid, **patch})
    return out


def build_prior_keywords_summary(prior_context: str) -> str:
    """供 system prompt 使用的四维关键词摘要（短）。"""
    v, s, i, p = extract_from_prior_context(prior_context)
    lines = []
    if v:
        lines.append(f"- 价值观关键词：{'、'.join(v[:8])}")
    if s:
        lines.append(f"- 优势关键词：{'、'.join(s[:10])}")
    if i:
        lines.append(f"- 热爱关键词：{'、'.join(i[:6])}")
    if p:
        lines.append(f"- 工作目的/使命关键词：{'、'.join(p[:6])}")
    if not lines:
        return "（尚未从 prior 中解析到结构化关键词，请结合 prior_block 全文引导用户。）"
    return "\n".join(lines)
