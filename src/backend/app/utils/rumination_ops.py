"""
Rumination 筛选流程的表格操作函数（占位实现）

与 rumination_prompt.md 中描述的函数对应，用于生成和过滤表格。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

# 从 prior_context 文本中简单提取关键词（启发式）
_RE_VALUES = re.compile(r"【信念[^】]*阶段结果】\s*\n(.*?)(?=【|$)", re.DOTALL)
_RE_STRENGTHS = re.compile(r"【禀赋[^】]*阶段结果】\s*\n(.*?)(?=【|$)", re.DOTALL)
_RE_INTERESTS = re.compile(r"【热忱[^】]*阶段结果】\s*\n(.*?)(?=【|$)", re.DOTALL)


def _extract_keywords(text: str, limit: int = 10) -> List[str]:
    """从段落文本中提取可能的关键词（数字序号、顿号/逗号分隔等）"""
    if not text or not text.strip():
        return []
    found: List[str] = []
    # 1. xxx 2. yyy
    for m in re.finditer(r"\d+[\.、]\s*([^\d\n，。、；]+)", text):
        w = m.group(1).strip()
        if w and len(w) <= 20 and w not in found:
            found.append(w)
            if len(found) >= limit:
                return found
    # 顿号、逗号分隔
    for part in re.split(r"[，、；;]", text):
        w = part.strip()
        if w and len(w) <= 20 and w not in found:
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
    for p in passions[:6]:  # 限制行数
        for s in strengths[:4]:
            rows.append({
                "id": str(idx),
                "热爱": p,
                "优势": s,
                "优势标记": "有充实感",
            })
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


def extract_from_prior_context(prior_context: str) -> tuple[List[str], List[str], List[str]]:
    """
    从 prior_context 文本中提取 价值观、优势、热爱 列表。
    返回 (values, strengths, interests)
    """
    values = strengths = interests = []
    if _RE_VALUES.search(prior_context):
        values = _extract_keywords(_RE_VALUES.search(prior_context).group(1), 5)
    if _RE_STRENGTHS.search(prior_context):
        strengths = _extract_keywords(_RE_STRENGTHS.search(prior_context).group(1), 10)
    if _RE_INTERESTS.search(prior_context):
        interests = _extract_keywords(_RE_INTERESTS.search(prior_context).group(1), 6)
    return (values, strengths, interests)
